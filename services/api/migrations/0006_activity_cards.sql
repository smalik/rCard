-- Activities: talks, conferences, publications, boards, memberships,
-- volunteering and interests. They're context cards, like education, and
-- take no parent. Resume imports propose them for sections that hold these.
alter table plytos.card drop constraint card_kind_check;
alter table plytos.card add constraint card_kind_check
  check (kind in ('employment', 'position', 'engagement', 'project',
                  'accomplishment', 'story', 'skill', 'education', 'credential',
                  'activity', 'role'));
