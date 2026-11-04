-- Resume imports.
--
-- An import keeps the person's original file, untouched, beside what Plytos
-- read from it and the person's progress checking it. Everything in a row
-- is encrypted with the person's own data key, so deleting their key makes
-- it unreadable like the rest of their content.
--
-- A proposed card inside an import is not a card. It becomes one only when
-- the person approves it, through the normal card tables.

create table plytos.resume_import (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  file_format text not null check (file_format in ('docx', 'pdf', 'text')),
  file_size integer not null check (file_size > 0),
  -- The original file and its name (file names carry the person's name).
  file_ciphertext bytea not null,
  name_ciphertext bytea not null,
  -- What the import read: proposed cards, the audit, and the text they quote.
  result_ciphertext bytea not null,
  -- Which questions the person settled and what they decided on each card.
  progress_ciphertext bytea not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index resume_import_by_owner on plytos.resume_import (owner_id, created_at);

alter table plytos.resume_import enable row level security;
create policy resume_import_owner on plytos.resume_import
  using (owner_id = plytos.current_user_id())
  with check (owner_id = plytos.current_user_id());

-- The person can delete an import, original file and all, at any time.
-- The file and what was read from it never change; only progress does.
grant select, insert, delete on plytos.resume_import to plytos_app;
grant update (progress_ciphertext, updated_at) on plytos.resume_import to plytos_app;

-- Account deletion also removes imports.
create or replace function plytos.purge_user(target_user uuid) returns void
language plpgsql security definer
set search_path = pg_catalog, plytos, vault
as $$
begin
  delete from vault.user_key where user_id = target_user;
  delete from plytos.event where owner_id = target_user;
  delete from plytos.resume_import where owner_id = target_user;
  update plytos.card_line set head_version_id = null where owner_id = target_user;
  delete from plytos.card_version where owner_id = target_user;
  delete from plytos.card_line where owner_id = target_user;
  delete from plytos.target where owner_id = target_user;
  delete from plytos.card where owner_id = target_user;
  delete from plytos.app_user where id = target_user;
end
$$;
