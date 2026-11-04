-- Career tree: cards nest.
--
-- An employment (the employer and the tenure) holds its positions, and a
-- position holds its accomplishments. Agency, consulting and freelance work
-- adds an engagement per client in between. Each level is its own card with
-- its own versions, so a fact lives at one level and the levels below show
-- it without copying it (docs/data-model.md).
--
-- Where a card sits is a fact on its main line: content.parent, encrypted
-- with the rest of the version. card.parent_id mirrors the current main
-- version's parent in clear so the tree can be read without decrypting. It
-- holds only IDs, never names.

alter table plytos.card drop constraint card_kind_check;
alter table plytos.card add constraint card_kind_check
  check (kind in ('employment', 'position', 'engagement', 'project',
                  'accomplishment', 'story', 'skill', 'education', 'credential',
                  -- The flat kind from before the tree. Old cards keep it;
                  -- new cards never use it.
                  'role'));

alter table plytos.card add column parent_id uuid;
alter table plytos.card add constraint card_parent_same_owner
  foreign key (parent_id, owner_id) references plytos.card (id, owner_id);
create index card_by_parent on plytos.card (parent_id) where parent_id is not null;

-- Which kind may sit under which. Every allowed parent ranks above its child
-- (employment, position, engagement, project, accomplishment, story) and a
-- card's kind never changes, so the tree can't loop.
create or replace function plytos.card_parent_guard() returns trigger
language plpgsql
as $$
declare
  parent_kind text;
begin
  if new.parent_id is null then
    return new;
  end if;
  select kind into parent_kind from plytos.card where id = new.parent_id;
  if not (
    (new.kind = 'position' and parent_kind = 'employment')
    or (new.kind = 'engagement' and parent_kind in ('employment', 'position'))
    or (new.kind = 'project' and parent_kind in ('employment', 'position', 'engagement'))
    or (new.kind = 'accomplishment'
        and parent_kind in ('employment', 'position', 'engagement', 'project'))
    or (new.kind = 'story' and parent_kind = 'accomplishment')
  ) then
    raise exception 'a % card can''t sit under a % card', new.kind, coalesce(parent_kind, 'missing')
      using errcode = 'check_violation';
  end if;
  return new;
end
$$;

create trigger card_parent_guard
  before insert or update of parent_id on plytos.card
  for each row execute function plytos.card_parent_guard();

-- The app moves a card by saving a main version with a new parent, then
-- updating this mirror in the same transaction.
grant update (parent_id) on plytos.card to plytos_app;
