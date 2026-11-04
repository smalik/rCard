-- Plytos M0 foundations: people, per-person keys, cards, card lines, card
-- versions, targets and the event log.
--
-- Rules this schema enforces (see docs/data-model.md):
--   * Every row belongs to one person, and row-level security limits the app
--     role to the signed-in person's rows.
--   * Card versions are append-only for the app role. Only the account
--     deletion function can remove them, and only redaction can blank one.
--   * A card has exactly one main line (facts) and at most one variant line
--     per target (framing only).
--   * Each version's number follows its parent on the same line, so history
--     reads v1, v2, v3 without gaps.
--   * Card content is stored encrypted with the owner's own data key.

create schema if not exists plytos;
-- Wrapped data keys live apart from the data they unlock. Not named "vault":
-- Supabase projects already have a schema by that name.
create schema if not exists plytos_vault;

-- Group roles. Login roles (Cloud SQL IAM users, test users) are granted
-- membership by the migration runner, never here.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'plytos_app') then
    create role plytos_app nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'plytos_shredder') then
    create role plytos_shredder nologin;
  end if;
end
$$;

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- Time-ordered UUID (RFC 9562 version 7), so IDs sort by creation time and
-- are never sequential or guessable.
create or replace function plytos.uuid_v7() returns uuid
language plpgsql volatile
as $$
declare
  ts_ms bigint := floor(extract(epoch from clock_timestamp()) * 1000);
  b bytea := uuid_send(gen_random_uuid());
begin
  b := overlay(b placing substring(int8send(ts_ms) from 3) from 1 for 6);
  b := set_byte(b, 6, (get_byte(b, 6) & 15) | 112);
  return encode(b, 'hex')::uuid;
end
$$;

-- The person the current transaction acts for. The API sets it with
-- set_config('plytos.user_id', ..., true) at the start of every transaction.
-- Unset means no rows are visible.
create or replace function plytos.current_user_id() returns uuid
language sql stable
as $$
  select nullif(current_setting('plytos.user_id', true), '')::uuid
$$;

-- ---------------------------------------------------------------------------
-- People and keys
-- ---------------------------------------------------------------------------

create table plytos.app_user (
  id uuid primary key default plytos.uuid_v7(),
  auth_subject text not null unique,
  status text not null default 'active'
    check (status in ('active', 'dormant')),
  created_at timestamptz not null default now()
);

-- Each person's data encryption key, wrapped by a key-encryption key held in
-- Cloud KMS. Deleting this row makes every copy of the person's content
-- unreadable (crypto-shredding).
create table plytos_vault.user_key (
  user_id uuid primary key references plytos.app_user (id),
  kek_name text not null,
  wrapped_dek bytea not null,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Cards
-- ---------------------------------------------------------------------------

create table plytos.card (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  kind text not null
    check (kind in ('role', 'accomplishment', 'skill', 'project',
                    'education', 'credential', 'story')),
  status text not null default 'draft'
    check (status in ('draft', 'approved', 'archived')),
  -- Trust ladder: 0 self-stated, 1 evidence attached, 2 reviewer confirmed,
  -- 3 attested, 4 issued credential.
  trust_level smallint not null default 0 check (trust_level between 0 and 4),
  created_at timestamptz not null default now(),
  unique (id, owner_id)
);

-- A named audience that spans cards: an industry, a company, a role, one
-- application, or anything the person names. Names are encrypted.
create table plytos.target (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  kind text not null
    check (kind in ('industry', 'company', 'role', 'application', 'custom')),
  parent_id uuid,
  name_ciphertext bytea not null,
  created_at timestamptz not null default now(),
  archived_at timestamptz,
  unique (id, owner_id),
  foreign key (parent_id, owner_id) references plytos.target (id, owner_id)
);

-- A card's line of versions. target_id null is the main line, which holds
-- the facts. Any other line is a variant for one target and changes framing
-- only.
create table plytos.card_line (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null,
  card_id uuid not null,
  target_id uuid,
  head_version_id uuid,
  state text not null default 'current'
    check (state in ('current', 'behind', 'archived')),
  created_at timestamptz not null default now(),
  unique (id, card_id, owner_id),
  foreign key (card_id, owner_id) references plytos.card (id, owner_id),
  foreign key (target_id, owner_id) references plytos.target (id, owner_id),
  constraint main_line_is_never_behind
    check (target_id is not null or state <> 'behind')
);

create unique index card_line_one_main
  on plytos.card_line (card_id) where target_id is null;
create unique index card_line_one_per_target
  on plytos.card_line (card_id, target_id) where target_id is not null;

-- One permanent snapshot of a card. Content is the encrypted canonical JSON
-- of the card at that version; hashes are of the plaintext, so history can be
-- verified without decrypting and still checks out after redaction.
create table plytos.card_version (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null,
  card_id uuid not null,
  line_id uuid not null,
  number integer not null check (number >= 1),
  parent_id uuid references plytos.card_version (id),
  based_on_main_version_id uuid references plytos.card_version (id),
  schema_version smallint not null check (schema_version >= 1),
  author_kind text not null check (author_kind in ('person', 'ai', 'reviewer')),
  author_ref text,
  content_ciphertext bytea,
  content_hash bytea not null check (length(content_hash) = 32),
  chain_hash bytea not null check (length(chain_hash) = 32),
  created_at timestamptz not null default now(),
  redacted_at timestamptz,
  unique (line_id, number),
  foreign key (line_id, card_id, owner_id)
    references plytos.card_line (id, card_id, owner_id),
  constraint first_version_has_no_parent
    check ((number = 1) = (parent_id is null)),
  constraint redaction_is_consistent
    check ((content_ciphertext is null) = (redacted_at is not null))
);

create index card_version_by_card on plytos.card_version (card_id, created_at);

alter table plytos.card_line
  add constraint card_line_head_fk
  foreign key (head_version_id) references plytos.card_version (id);

-- Structural rules no CHECK constraint can express across rows.
create or replace function plytos.card_version_guard() returns trigger
language plpgsql
as $$
declare
  line_target uuid;
  parent_line uuid;
  parent_number integer;
  base_line_target uuid;
  base_card uuid;
begin
  select target_id into line_target from plytos.card_line where id = new.line_id;

  if new.parent_id is not null then
    select line_id, number into parent_line, parent_number
      from plytos.card_version where id = new.parent_id;
    if parent_line is distinct from new.line_id then
      raise exception 'parent version % is on a different line', new.parent_id
        using errcode = 'check_violation';
    end if;
    if new.number <> parent_number + 1 then
      raise exception 'version number % does not follow parent number %',
        new.number, parent_number using errcode = 'check_violation';
    end if;
  end if;

  if line_target is null then
    if new.based_on_main_version_id is not null then
      raise exception 'main line versions are not based on another version'
        using errcode = 'check_violation';
    end if;
  else
    if new.based_on_main_version_id is null then
      raise exception 'variant versions must name the main version they are based on'
        using errcode = 'check_violation';
    end if;
    select l.target_id, v.card_id into base_line_target, base_card
      from plytos.card_version v
      join plytos.card_line l on l.id = v.line_id
     where v.id = new.based_on_main_version_id;
    if base_card is distinct from new.card_id or base_line_target is not null then
      raise exception 'variant must be based on a main line version of the same card'
        using errcode = 'check_violation';
    end if;
  end if;

  return new;
end
$$;

create trigger card_version_guard
  before insert on plytos.card_version
  for each row execute function plytos.card_version_guard();

-- Versions never change, except redaction: erasing the content while the
-- number, date and hashes stay so the history still verifies.
create or replace function plytos.card_version_immutable() returns trigger
language plpgsql
as $$
begin
  if new.content_ciphertext is null
     and new.redacted_at is not null
     and old.redacted_at is null
     and (to_jsonb(new) - 'content_ciphertext' - 'redacted_at')
         = (to_jsonb(old) - 'content_ciphertext' - 'redacted_at') then
    return new;
  end if;
  raise exception 'card versions are append-only; only redaction may change one'
    using errcode = 'insufficient_privilege';
end
$$;

create trigger card_version_immutable
  before update on plytos.card_version
  for each row execute function plytos.card_version_immutable();

-- ---------------------------------------------------------------------------
-- Event log (append-only; never holds card content)
-- ---------------------------------------------------------------------------

create table plytos.event (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  actor_kind text not null
    check (actor_kind in ('person', 'ai', 'reviewer', 'system')),
  actor_ref text,
  action text not null,
  record_type text not null,
  record_id uuid not null,
  occurred_at timestamptz not null default now()
);

create index event_by_record on plytos.event (owner_id, record_type, record_id);

-- ---------------------------------------------------------------------------
-- Sign-in lookup and account deletion
-- ---------------------------------------------------------------------------

-- Finds the person for a verified sign-in subject. Runs with the owner's
-- rights because the caller does not know the person's ID yet.
create or replace function plytos.user_id_for_subject(subject text) returns uuid
language sql stable security definer
set search_path = pg_catalog, plytos
as $$
  select id from plytos.app_user where auth_subject = subject
$$;

-- Erases a person: destroys their data key first (so any surviving copy,
-- including backups, is unreadable), then deletes every row they own.
create or replace function plytos.purge_user(target_user uuid) returns void
language plpgsql security definer
set search_path = pg_catalog, plytos, plytos_vault
as $$
begin
  delete from plytos_vault.user_key where user_id = target_user;
  delete from plytos.event where owner_id = target_user;
  update plytos.card_line set head_version_id = null where owner_id = target_user;
  delete from plytos.card_version where owner_id = target_user;
  delete from plytos.card_line where owner_id = target_user;
  delete from plytos.target where owner_id = target_user;
  delete from plytos.card where owner_id = target_user;
  delete from plytos.app_user where id = target_user;
end
$$;

-- ---------------------------------------------------------------------------
-- Row-level security
--
-- The app role never owns these tables, so the policies always apply to it.
-- RLS is not forced on the owner, which lets the two security-definer
-- functions above act across rows.
-- ---------------------------------------------------------------------------

alter table plytos.app_user enable row level security;
create policy app_user_self on plytos.app_user
  using (id = plytos.current_user_id())
  with check (id = plytos.current_user_id());

alter table plytos_vault.user_key enable row level security;
create policy user_key_self on plytos_vault.user_key
  using (user_id = plytos.current_user_id())
  with check (user_id = plytos.current_user_id());

do $$
declare
  t text;
begin
  foreach t in array array['card', 'target', 'card_line', 'card_version', 'event']
  loop
    execute format('alter table plytos.%I enable row level security', t);
    execute format(
      'create policy %I on plytos.%I using (owner_id = plytos.current_user_id())'
      ' with check (owner_id = plytos.current_user_id())',
      t || '_owner', t);
  end loop;
end
$$;

-- ---------------------------------------------------------------------------
-- Privileges
-- ---------------------------------------------------------------------------

revoke all on schema plytos, plytos_vault from public;
revoke all on all functions in schema plytos from public;

grant usage on schema plytos, plytos_vault to plytos_app;
grant execute on function plytos.uuid_v7(), plytos.current_user_id(),
  plytos.user_id_for_subject(text) to plytos_app;

grant select, insert on plytos.app_user to plytos_app;
grant update (status) on plytos.app_user to plytos_app;
grant select, insert on plytos_vault.user_key to plytos_app;
grant select, insert on plytos.card to plytos_app;
grant update (status, trust_level) on plytos.card to plytos_app;
grant select, insert on plytos.target to plytos_app;
grant update (archived_at) on plytos.target to plytos_app;
grant select, insert on plytos.card_line to plytos_app;
grant update (head_version_id, state) on plytos.card_line to plytos_app;
-- Append-only: no update or delete for the app.
grant select, insert on plytos.card_version to plytos_app;
grant select, insert on plytos.event to plytos_app;

grant usage on schema plytos to plytos_shredder;
grant execute on function plytos.purge_user(uuid) to plytos_shredder;
