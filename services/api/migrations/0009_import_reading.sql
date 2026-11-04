-- Reading a resume in the background.
--
-- An upload is kept at once and read afterwards by the worker, so the person
-- doesn't wait on the request and can leave and come back. While it's read,
-- the import says which stage it's at; the stage names are fixed words, never
-- content. What was read is written once, when the reading finishes, and
-- never changes after that.
--
-- The worker claims due reads across people (claim_resume_imports returns
-- only IDs), then reads each one as its owner, so row-level security holds.
-- A read whose lease runs out is claimed again, up to three tries. One that
-- runs out on its last try is given up on and returned with gave_up set, so
-- the worker can tell the person.

alter table plytos.resume_import
  add column state text not null default 'read'
    check (state in ('reading', 'read', 'failed')),
  add column stage text check (stage in ('file', 'pictures', 'structure', 'checks')),
  add column attempts smallint not null default 0 check (attempts >= 0),
  add column run_after timestamptz not null default now(),
  add column locked_until timestamptz,
  -- A short code such as 'unreadable'. Never content.
  add column error_code text check (error_code ~ '^[a-z][a-z_]{0,63}$'),
  alter column result_ciphertext drop not null,
  add constraint resume_import_read_has_result
    check ((state = 'read') = (result_ciphertext is not null));

create index resume_import_due on plytos.resume_import (run_after) where state = 'reading';

-- What was read is written once, and a read import stays read.
create or replace function plytos.resume_import_read_once() returns trigger
language plpgsql
set search_path = pg_catalog, plytos
as $$
begin
  if old.result_ciphertext is not null
     and new.result_ciphertext is distinct from old.result_ciphertext then
    raise exception 'what was read from a resume never changes'
      using errcode = 'check_violation';
  end if;
  if old.state = 'read' and new.state <> 'read' then
    raise exception 'a read import stays read' using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger resume_import_read_once
  before update on plytos.resume_import
  for each row execute function plytos.resume_import_read_once();

grant update (result_ciphertext, state, stage, attempts, run_after, locked_until, error_code)
  on plytos.resume_import to plytos_app;

create or replace function plytos.claim_resume_imports(max_reads integer, lease_seconds integer)
returns table (id uuid, owner_id uuid, gave_up boolean)
language plpgsql security definer
set search_path = pg_catalog, plytos
as $$
begin
  -- A read that ran out of time on its last try stops here.
  return query
  update plytos.resume_import i
     set state = 'failed', stage = null, locked_until = null, error_code = 'gave_up',
         updated_at = now()
   where i.state = 'reading' and i.attempts >= 3 and i.locked_until < now()
  returning i.id, i.owner_id, true;

  return query
  update plytos.resume_import i
     set attempts = i.attempts + 1,
         locked_until = now() + make_interval(secs => lease_seconds)
   where i.id in (
     select q.id from plytos.resume_import q
      where q.state = 'reading' and q.run_after <= now() and q.attempts < 3
        and (q.locked_until is null or q.locked_until < now())
      order by q.run_after
      limit greatest(max_reads, 0)
      for update skip locked)
  returning i.id, i.owner_id, false;
end
$$;

revoke all on function plytos.claim_resume_imports(integer, integer) from public;
grant execute on function plytos.claim_resume_imports(integer, integer) to plytos_app;
