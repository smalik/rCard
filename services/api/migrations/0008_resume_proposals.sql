-- Resumes in use: made from an import, and offered by the Assembler.
--
-- A resume made "as written" from an import remembers which import, so the
-- app doesn't offer to make it twice. Deleting the import keeps the resume
-- and drops the link, like a message that shared it.
--
-- The Assembler offers a version of a resume made for a target. Keeping it
-- makes a new resume, and the proposal points at the resume version it made,
-- the way a kept card proposal points at its card version.

alter table plytos.resume
  add column import_id uuid,
  add constraint resume_import_link
    foreign key (import_id, owner_id) references plytos.resume_import (id, owner_id)
    on delete set null (import_id);

create unique index resume_one_per_import on plytos.resume (owner_id, import_id)
  where import_id is not null and archived_at is null;

-- A message can point at the resume it's about, such as asking for a version
-- of that resume. Resumes are archived, never deleted, so the link stays.
alter table plytos.message
  add column resume_id uuid,
  add constraint message_resume_link
    foreign key (resume_id, owner_id) references plytos.resume (id, owner_id);

alter table plytos.proposal
  add column result_resume_version_id uuid,
  add constraint proposal_resume_result_owner
    foreign key (result_resume_version_id, owner_id)
    references plytos.resume_version (id, owner_id),
  add constraint proposal_resume_result_only_when_kept
    check (result_resume_version_id is null or state in ('kept', 'edited')),
  add constraint proposal_has_one_result
    check (result_version_id is null or result_resume_version_id is null);

-- A proposal is decided once, and only its decision columns change.
create or replace function plytos.proposal_decided_once() returns trigger
language plpgsql
as $$
begin
  if old.state <> 'open' then
    raise exception 'proposal % was already decided', old.id
      using errcode = 'check_violation';
  end if;
  if (to_jsonb(new) - 'state' - 'decided_at' - 'result_version_id' - 'result_resume_version_id')
     <> (to_jsonb(old) - 'state' - 'decided_at' - 'result_version_id'
         - 'result_resume_version_id') then
    raise exception 'only the decision on a proposal can change'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end
$$;

grant update (result_resume_version_id) on plytos.proposal to plytos_app;
