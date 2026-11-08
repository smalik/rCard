"""Copies one person from one Plytos database to another.

Made for moving off the Supabase preview onto Cloud SQL. Run it from a
machine that can reach both databases, after the target's migrations have
run, connecting to each as the owner of its tables:

    PLYTOS_TRANSFER_SOURCE_URL   the source database
    PLYTOS_TRANSFER_SOURCE_KEK   the key that wrapped the source's data keys
    PLYTOS_TRANSFER_TARGET_URL   the target database
    PLYTOS_TRANSFER_TARGET_KEK   the key that wraps the target's data keys

    python -m plytos_api.transfer --from-subject dev:sam \\
        --to-subject iap:accounts.google.com:1234 [--replace] [--commit]

Content moves exactly as stored, still encrypted with the person's data key.
Only the data key itself is unsealed with the source's key and sealed again
with the target's, and the person signs in under the new subject. Without
--commit everything runs, including the resealing, in a transaction that is
then rolled back. Only table names and row counts are printed.

If someone already signs in to the target under the new subject, an empty
account (one made by signing in first) gives way. One with anything in it
stops the copy, unless --replace says to erase it, in the same transaction.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql

from plytos_api.keys import KeyEncryptionKey, kek_from_setting

SCHEMAS = ["plytos", "plytos_vault"]
USERS = "plytos.app_user"
KEYS = "plytos_vault.user_key"
# The column that names the person a row belongs to.
_OWNER_COLUMN = {USERS: "id", KEYS: "user_id"}

Row = tuple[Any, ...]


class TransferError(Exception):
    """The copy can't go ahead; nothing was written."""


@dataclass(frozen=True)
class ForeignKey:
    table: str
    columns: tuple[str, ...]
    parent: str
    parent_columns: tuple[str, ...]


@dataclass
class Table:
    name: str
    columns: list[str]
    nullable: set[str]
    primary_key: tuple[str, ...]
    owner_column: str
    foreign_keys: list[ForeignKey] = field(default_factory=list)


@dataclass
class Plan:
    """Tables in an order that satisfies every reference, plus the
    references filled in afterwards because two tables point at each other."""

    order: list[Table]
    deferred: list[ForeignKey]


@dataclass(frozen=True)
class Report:
    user_id: UUID
    counts: dict[str, int]
    # What the account already under the new subject held before it was
    # erased, by table; None when there was no such account.
    replaced: dict[str, int] | None
    committed: bool


def _quoted(name: str) -> sql.Composable:
    schema, table = name.split(".")
    return sql.Identifier(schema, table)


def _columns(names: Sequence[str]) -> sql.Composable:
    return sql.SQL(", ").join(sql.Identifier(c) for c in names)


def read_tables(conn: psycopg.Connection) -> dict[str, Table]:
    tables: dict[str, Table] = {}
    rows = conn.execute(
        "select c.oid, n.nspname || '.' || c.relname"
        "  from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where c.relkind in ('r', 'p') and n.nspname = any(%s)"
        " order by 2",
        (SCHEMAS,),
    ).fetchall()
    by_oid: dict[int, str] = {}
    for oid, name in rows:
        attrs = conn.execute(
            "select attname, not attnotnull, attgenerated <> ''"
            "  from pg_attribute where attrelid = %s and attnum > 0 and not attisdropped"
            " order by attnum",
            (oid,),
        ).fetchall()
        columns = [a for a, _, generated in attrs if not generated]
        primary_key = tuple(
            r[0]
            for r in conn.execute(
                "select a.attname from pg_index i"
                "  join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)"
                " where i.indrelid = %s and i.indisprimary"
                " order by array_position(i.indkey::int2[], a.attnum)",
                (oid,),
            ).fetchall()
        )
        owner = _OWNER_COLUMN.get(name, "owner_id")
        if owner not in columns:
            # Every person's row must say whose it is; a table that doesn't
            # can't be copied one person at a time.
            raise TransferError(f"{name} has no {owner} column, so it can't be copied per person")
        tables[name] = Table(
            name=name,
            columns=columns,
            nullable={a for a, nullable, _ in attrs if nullable},
            primary_key=primary_key,
            owner_column=owner,
        )
        by_oid[oid] = name
    for child, parent, columns, parent_columns in conn.execute(
        "select conrelid, confrelid,"
        "  array(select a.attname from unnest(conkey) with ordinality k(n, i)"
        "        join pg_attribute a on a.attrelid = conrelid and a.attnum = k.n order by k.i),"
        "  array(select a.attname from unnest(confkey) with ordinality k(n, i)"
        "        join pg_attribute a on a.attrelid = confrelid and a.attnum = k.n order by k.i)"
        "  from pg_constraint where contype = 'f' and conrelid = any(%s)",
        (list(by_oid),),
    ).fetchall():
        if parent not in by_oid:
            raise TransferError(f"{by_oid[child]} refers to a table outside {', '.join(SCHEMAS)}")
        tables[by_oid[child]].foreign_keys.append(
            ForeignKey(by_oid[child], tuple(columns), by_oid[parent], tuple(parent_columns))
        )
    return tables


def plan(tables: dict[str, Table]) -> Plan:
    """Orders tables so each row's references already exist when it's
    written. Where two tables refer to each other, one optional reference is
    left empty at first and filled in once both sides exist."""
    waiting = {
        name: {fk for fk in t.foreign_keys if fk.parent != name} for name, t in tables.items()
    }
    order: list[Table] = []
    deferred: list[ForeignKey] = []
    while waiting:
        ready = sorted(
            n for n, fks in waiting.items() if all(fk.parent not in waiting for fk in fks)
        )
        if not ready:
            # Two or more tables refer to each other: let go of an optional
            # reference in the loop, and fill it in once both sides exist.
            optional = [
                fk
                for fk in _a_loop(waiting)
                if all(c in tables[fk.table].nullable for c in fk.columns)
                and tables[fk.table].primary_key
            ]
            if not optional:
                raise TransferError("tables refer to each other with no optional reference")
            fk = optional[0]
            waiting[fk.table].discard(fk)
            deferred.append(fk)
            continue
        for name in ready:
            order.append(tables[name])
            del waiting[name]
    return Plan(order, deferred)


def _a_loop(waiting: dict[str, set[ForeignKey]]) -> list[ForeignKey]:
    """A loop of references among tables that are all still waiting. Every
    one of them waits on another, so following references must come back
    round."""
    node = min(waiting)
    path: list[ForeignKey] = []
    seen = {node: 0}
    while True:
        fk = min(
            (fk for fk in waiting[node] if fk.parent in waiting),
            key=lambda fk: (fk.parent, fk.columns),
        )
        path.append(fk)
        node = fk.parent
        if node in seen:
            return path[seen[node] :]
        seen[node] = len(path)


def _parents_first(table: Table, rows: list[Row]) -> list[Row]:
    """Orders rows that refer to rows of their own table after those rows."""
    own = [fk for fk in table.foreign_keys if fk.parent == table.name]
    if not own:
        return rows
    at = {c: i for i, c in enumerate(table.columns)}
    keys: dict[tuple[str, ...], dict[Row, int]] = {}
    for fk in own:
        keys[fk.parent_columns] = {
            tuple(row[at[c]] for c in fk.parent_columns): i for i, row in enumerate(rows)
        }
    needs: dict[int, set[int]] = defaultdict(set)
    for i, row in enumerate(rows):
        for fk in own:
            value = tuple(row[at[c]] for c in fk.columns)
            if any(v is None for v in value):
                continue
            parent = keys[fk.parent_columns].get(value)
            if parent is None:
                raise TransferError(f"a row of {table.name} refers to a row that isn't theirs")
            if parent != i:
                needs[i].add(parent)
    ordered: list[Row] = []
    placed: set[int] = set()
    pending = list(range(len(rows)))
    while pending:
        progressed = [i for i in pending if needs[i] <= placed]
        if not progressed:
            raise TransferError(f"rows of {table.name} refer to each other in a loop")
        for i in progressed:
            ordered.append(rows[i])
            placed.add(i)
        pending = [i for i in pending if i not in placed]
    return ordered


def _key_aad(user_id: UUID) -> bytes:
    # Matches keys._key_aad: the person's id binds their wrapped key to them.
    return b"plytos.user_key:" + user_id.bytes


def _migrations(conn: psycopg.Connection) -> list[tuple[str, str]]:
    return [
        (v, c)
        for v, c in conn.execute(
            "select version, checksum from plytos_meta.schema_migration order by version"
        ).fetchall()
    ]


def _owned_counts(conn: psycopg.Connection, tables: list[Table], user_id: UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        row = conn.execute(
            sql.SQL("select count(*) from {} where {} = %s").format(
                _quoted(table.name), sql.Identifier(table.owner_column)
            ),
            (user_id,),
        ).fetchone()
        counts[table.name] = int(row[0]) if row else 0
    return counts


def transfer(
    source_url: str,
    source_kek: KeyEncryptionKey,
    target_url: str,
    target_kek: KeyEncryptionKey,
    from_subject: str,
    to_subject: str,
    *,
    commit: bool,
    replace: bool = False,
) -> Report:
    if not from_subject or not to_subject:
        raise TransferError("name the subject to copy from and the one to copy to")
    with (
        psycopg.connect(source_url) as source,
        psycopg.connect(target_url) as target,
    ):
        # One consistent picture of the source, read without writing.
        source.execute("set transaction isolation level repeatable read, read only")
        # Refuse to run at all if row security would hide rows, rather than
        # quietly copying part of someone.
        for conn in (source, target):
            conn.execute("set local row_security = off")

        if _migrations(source) != _migrations(target):
            raise TransferError(
                "the two databases are at different migrations; migrate the target first"
            )
        tables = read_tables(source)
        if read_tables(target).keys() != tables.keys():
            raise TransferError("the two databases have different tables")
        steps = plan(tables)

        found = source.execute(
            "select id from plytos.app_user where auth_subject = %s", (from_subject,)
        ).fetchone()
        if found is None:
            raise TransferError(f"nobody signs in as {from_subject} in the source")
        user_id: UUID = found[0]

        if target.execute("select 1 from plytos.app_user where id = %s", (user_id,)).fetchone():
            raise TransferError("this person is already in the target")
        replaced: dict[str, int] | None = None
        existing = target.execute(
            "select id from plytos.app_user where auth_subject = %s", (to_subject,)
        ).fetchone()
        if existing is not None:
            # Signing in before the copy makes an empty account; it can go.
            # One with anything in it stays, and the copy stops, unless the
            # person asked for it to be replaced.
            counts = _owned_counts(target, steps.order, existing[0])
            used = any(n for name, n in counts.items() if name not in (USERS, KEYS))
            if used and not replace:
                raise TransferError(
                    f"{to_subject} already has things in the target;"
                    " --replace erases them before copying"
                )
            _erase(target, steps, existing[0])
            replaced = {name: n for name, n in counts.items() if n}

        held_back: dict[str, set[str]] = defaultdict(set)
        for fk in steps.deferred:
            held_back[fk.table].update(fk.columns)
        fill_in: list[tuple[Table, list[Row]]] = []

        for table in steps.order:
            rows = source.execute(
                sql.SQL("select {} from {} where {} = %s").format(
                    _columns(table.columns), _quoted(table.name), sql.Identifier(table.owner_column)
                ),
                (user_id,),
            ).fetchall()
            rows = [_reseal(table, row, source_kek, target_kek, to_subject) for row in rows]
            rows = _parents_first(table, rows)
            later = held_back[table.name]
            if later:
                fill_in.append((table, rows))
                at = {c: i for i, c in enumerate(table.columns)}
                rows = [
                    tuple(None if c in later else row[at[c]] for c in table.columns) for row in rows
                ]
            if rows:
                with target.cursor() as cur:
                    cur.executemany(
                        sql.SQL("insert into {} ({}) values ({})").format(
                            _quoted(table.name),
                            _columns(table.columns),
                            sql.SQL(", ").join(sql.Placeholder() * len(table.columns)),
                        ),
                        rows,
                    )

        for table, rows in fill_in:
            filled = sorted(held_back[table.name])
            at = {c: i for i, c in enumerate(table.columns)}
            updates = [
                tuple(row[at[c]] for c in filled) + tuple(row[at[c]] for c in table.primary_key)
                for row in rows
                if any(row[at[c]] is not None for c in filled)
            ]
            if updates:
                with target.cursor() as cur:
                    cur.executemany(
                        sql.SQL("update {} set {} where {}").format(
                            _quoted(table.name),
                            sql.SQL(", ").join(
                                sql.SQL("{} = %s").format(sql.Identifier(c)) for c in filled
                            ),
                            sql.SQL(" and ").join(
                                sql.SQL("{} = %s").format(sql.Identifier(c))
                                for c in table.primary_key
                            ),
                        ),
                        updates,
                    )

        copied = _owned_counts(source, steps.order, user_id)
        if _owned_counts(target, steps.order, user_id) != copied:
            raise TransferError("the target doesn't hold the same rows after copying")
        if copied.get(KEYS) != 1:
            raise TransferError("this person has no data key to bring across")
        source.rollback()
        if commit:
            target.commit()
        else:
            target.rollback()
    return Report(user_id, copied, replaced, commit)


def _erase(conn: psycopg.Connection, steps: Plan, user_id: UUID) -> None:
    """Deletes everything one person has, the rows that point at others
    first. References between tables that point at each other are cleared
    beforehand, as the copy fills them in afterwards."""
    by_name = {table.name: table for table in steps.order}
    held_back: dict[str, set[str]] = defaultdict(set)
    for fk in steps.deferred:
        held_back[fk.table].update(fk.columns)
    for name, columns in held_back.items():
        table = by_name[name]
        conn.execute(
            sql.SQL("update {} set {} where {} = %s").format(
                _quoted(name),
                sql.SQL(", ").join(
                    sql.SQL("{} = null").format(sql.Identifier(c)) for c in sorted(columns)
                ),
                sql.Identifier(table.owner_column),
            ),
            (user_id,),
        )
    for table in reversed(steps.order):
        conn.execute(
            sql.SQL("delete from {} where {} = %s").format(
                _quoted(table.name), sql.Identifier(table.owner_column)
            ),
            (user_id,),
        )
    if any(_owned_counts(conn, steps.order, user_id).values()):
        raise TransferError("the account being replaced didn't erase cleanly")


def _reseal(
    table: Table,
    row: Row,
    source_kek: KeyEncryptionKey,
    target_kek: KeyEncryptionKey,
    to_subject: str,
) -> Row:
    at = {c: i for i, c in enumerate(table.columns)}
    values = list(row)
    if table.name == USERS:
        values[at["auth_subject"]] = to_subject
    elif table.name == KEYS:
        if values[at["kek_name"]] != source_kek.name:
            raise TransferError("the source data key was sealed with a different key")
        user_id: UUID = values[at["user_id"]]
        aad = _key_aad(user_id)
        dek = source_kek.unwrap(bytes(values[at["wrapped_dek"]]), aad)
        wrapped = target_kek.wrap(dek, aad)
        if target_kek.unwrap(wrapped, aad) != dek:
            raise TransferError("the resealed data key doesn't open again")
        values[at["kek_name"]] = target_kek.name
        values[at["wrapped_dek"]] = wrapped
    return tuple(values)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from-subject", required=True, help="how the person signs in now")
    parser.add_argument("--to-subject", required=True, help="how they'll sign in after the copy")
    parser.add_argument("--commit", action="store_true", help="keep the copy (default: rehearse)")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="erase whatever the target already holds under --to-subject first",
    )
    args = parser.parse_args(argv)
    try:
        settings = {
            name: os.environ[name]
            for name in (
                "PLYTOS_TRANSFER_SOURCE_URL",
                "PLYTOS_TRANSFER_SOURCE_KEK",
                "PLYTOS_TRANSFER_TARGET_URL",
                "PLYTOS_TRANSFER_TARGET_KEK",
            )
        }
    except KeyError as missing:
        print(f"set {missing.args[0]}", file=sys.stderr)
        return 2
    try:
        report = transfer(
            settings["PLYTOS_TRANSFER_SOURCE_URL"],
            kek_from_setting(settings["PLYTOS_TRANSFER_SOURCE_KEK"], allow_local=True),
            settings["PLYTOS_TRANSFER_TARGET_URL"],
            kek_from_setting(settings["PLYTOS_TRANSFER_TARGET_KEK"], allow_local=True),
            args.from_subject,
            args.to_subject,
            commit=args.commit,
            replace=args.replace,
        )
    except TransferError as refused:
        print(f"Nothing copied: {refused}", file=sys.stderr)
        return 1
    for name, count in report.counts.items():
        print(f"{name:32} {count:6}")
    if report.replaced is not None:
        if set(report.replaced) <= {USERS, KEYS}:
            print(f"Removed the empty account {args.to_subject} made before the copy.")
        else:
            print(f"Erased what {args.to_subject} held before the copy:")
            for name, count in report.replaced.items():
                print(f"  {name:30} {count:6}")
    print("Copied." if report.committed else "Rehearsal only: nothing kept. Add --commit to copy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
