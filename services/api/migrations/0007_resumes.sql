-- Resumes: the documents a person builds from their cards.
--
-- A resume is a selection, not a copy. It names which employments appear,
-- which of their accomplishments are switched on and in what order, which
-- wording each one uses, and which context cards (education, credentials,
-- skills, activities) come along. Words and facts stay on the cards, so a
-- fact corrected on a card shows at once in every resume that uses it.
--
-- Depth: every save is a new numbered version, append-only and hash-chained
-- like card versions. The person names the versions that matter; a name is
-- a separate insert-only row, newest first, so naming never edits a version.
--
-- Breadth: a resume can be made from another, its parent. Each version
-- records which of the parent's versions it has caught up with, so the app
-- can show what changed in the parent since and let the person take only
-- what they want.
--
-- Names, labels and the selection are encrypted with the person's key. Only
-- IDs, numbers, hashes and times are clear (docs/data-model.md).

create table plytos.resume (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  name_ciphertext bytea not null,
  -- The audience it's made for. Its variants are the default wording.
  target_id uuid,
  -- The resume it was made from. Set once, at creation.
  parent_id uuid,
  head_version_id uuid,
  created_at timestamptz not null default clock_timestamp(),
  archived_at timestamptz,
  unique (id, owner_id),
  foreign key (target_id, owner_id) references plytos.target (id, owner_id),
  foreign key (parent_id, owner_id) references plytos.resume (id, owner_id)
);

create index resume_by_owner on plytos.resume (owner_id, created_at);

create table plytos.resume_version (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null,
  resume_id uuid not null,
  number integer not null check (number >= 1),
  parent_id uuid references plytos.resume_version (id),
  -- The parent resume's version this one has caught up with.
  synced_parent_version_id uuid references plytos.resume_version (id),
  schema_version smallint not null check (schema_version >= 1),
  author_kind text not null check (author_kind in ('person', 'ai', 'reviewer')),
  author_ref text,
  content_ciphertext bytea,
  content_hash bytea not null check (length(content_hash) = 32),
  chain_hash bytea not null check (length(chain_hash) = 32),
  created_at timestamptz not null default clock_timestamp(),
  redacted_at timestamptz,
  unique (resume_id, number),
  unique (id, owner_id),
  foreign key (resume_id, owner_id) references plytos.resume (id, owner_id),
  constraint first_resume_version_has_no_parent
    check ((number = 1) = (parent_id is null)),
  constraint resume_redaction_is_consistent
    check ((content_ciphertext is null) = (redacted_at is not null))
);

alter table plytos.resume
  add constraint resume_head_fk
  foreign key (head_version_id) references plytos.resume_version (id);

create table plytos.resume_version_name (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null,
  version_id uuid not null,
  name_ciphertext bytea not null,
  created_at timestamptz not null default clock_timestamp(),
  foreign key (version_id, owner_id) references plytos.resume_version (id, owner_id)
);

create index resume_version_name_by_version on plytos.resume_version_name (version_id, created_at);

-- Version numbers follow their parent on the same resume, and a resume only
-- catches up with versions of its own parent resume.
create or replace function plytos.resume_version_guard() returns trigger
language plpgsql
as $$
declare
  parent_resume uuid;
  parent_number integer;
  made_from uuid;
  synced_resume uuid;
begin
  if new.parent_id is not null then
    select resume_id, number into parent_resume, parent_number
      from plytos.resume_version where id = new.parent_id;
    if parent_resume is distinct from new.resume_id then
      raise exception 'parent version % belongs to another resume', new.parent_id
        using errcode = 'check_violation';
    end if;
    if new.number <> parent_number + 1 then
      raise exception 'version number % does not follow parent number %',
        new.number, parent_number using errcode = 'check_violation';
    end if;
  end if;

  if new.synced_parent_version_id is not null then
    select parent_id into made_from from plytos.resume where id = new.resume_id;
    select resume_id into synced_resume
      from plytos.resume_version where id = new.synced_parent_version_id;
    if made_from is null or synced_resume is distinct from made_from then
      raise exception 'a resume can only catch up with its own parent resume'
        using errcode = 'check_violation';
    end if;
  end if;

  return new;
end
$$;

create trigger resume_version_guard
  before insert on plytos.resume_version
  for each row execute function plytos.resume_version_guard();

-- Versions never change, except redaction: erasing the content while the
-- number, date and hashes stay so the history still verifies.
create or replace function plytos.resume_version_immutable() returns trigger
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
  raise exception 'resume versions are append-only; only redaction may change one'
    using errcode = 'insufficient_privilege';
end
$$;

create trigger resume_version_immutable
  before update on plytos.resume_version
  for each row execute function plytos.resume_version_immutable();

alter table plytos.resume enable row level security;
create policy resume_owner on plytos.resume
  using (owner_id = plytos.current_user_id())
  with check (owner_id = plytos.current_user_id());

alter table plytos.resume_version enable row level security;
create policy resume_version_owner on plytos.resume_version
  using (owner_id = plytos.current_user_id())
  with check (owner_id = plytos.current_user_id());

alter table plytos.resume_version_name enable row level security;
create policy resume_version_name_owner on plytos.resume_version_name
  using (owner_id = plytos.current_user_id())
  with check (owner_id = plytos.current_user_id());

grant select, insert on plytos.resume to plytos_app;
grant update (name_ciphertext, target_id, head_version_id, archived_at) on plytos.resume to plytos_app;
-- Append-only: no update or delete for the app.
grant select, insert on plytos.resume_version to plytos_app;
grant select, insert on plytos.resume_version_name to plytos_app;

-- Account deletion also removes resumes.
create or replace function plytos.purge_user(target_user uuid) returns void
language plpgsql security definer
set search_path = pg_catalog, plytos, plytos_vault
as $$
begin
  delete from plytos_vault.user_key where user_id = target_user;
  delete from plytos.event where owner_id = target_user;
  delete from plytos.resume_import where owner_id = target_user;
  delete from plytos.check_in_plan where owner_id = target_user;
  delete from plytos.tidbit where owner_id = target_user;
  delete from plytos.message where owner_id = target_user;
  delete from plytos.proposal where owner_id = target_user;
  delete from plytos.agent_run where owner_id = target_user;
  update plytos.resume set head_version_id = null where owner_id = target_user;
  delete from plytos.resume_version_name where owner_id = target_user;
  delete from plytos.resume_version where owner_id = target_user;
  delete from plytos.resume where owner_id = target_user;
  update plytos.card_line set head_version_id = null where owner_id = target_user;
  delete from plytos.card_version where owner_id = target_user;
  delete from plytos.card_line where owner_id = target_user;
  delete from plytos.target where owner_id = target_user;
  delete from plytos.card where owner_id = target_user;
  delete from plytos.app_user where id = target_user;
end
$$;
