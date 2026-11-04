-- Check-ins: when Plytos asks the person what moved at work.
--
-- Once a month, at a time the person picked: a week of the month, a weekday
-- and a local time ("the last Friday at 4 PM"), in their time zone. The
-- Check-in agent runs from the queue (plytos.agent_run, queued under the
-- dedupe key 'check_in' for the next time due), asks one short question, and
-- queues itself for the month after. The plan holds no content, only when to
-- ask (docs/agents.md).

create table plytos.check_in_plan (
  owner_id uuid primary key references plytos.app_user (id),
  -- 'off' keeps the day and time for when they're turned back on.
  state text not null check (state in ('on', 'off')),
  -- Which week of the month: the first to the fourth, or -1 for the last.
  week smallint not null check (week in (1, 2, 3, 4, -1)),
  -- ISO weekday: 1 is Monday, 7 is Sunday.
  weekday smallint not null check (weekday between 1 and 7),
  local_time time not null,
  -- An IANA name such as 'America/Chicago', checked by the app against
  -- pg_timezone_names.
  time_zone text not null check (length(time_zone) between 1 and 64),
  -- In the app for now; text messages after carrier registration.
  channel text not null default 'app' check (channel in ('app')),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp()
);

alter table plytos.check_in_plan enable row level security;
create policy check_in_plan_owner on plytos.check_in_plan
  using (owner_id = plytos.current_user_id())
  with check (owner_id = plytos.current_user_id());

grant select, insert on plytos.check_in_plan to plytos_app;
grant update (state, week, weekday, local_time, time_zone, channel, updated_at)
  on plytos.check_in_plan to plytos_app;

-- Account deletion also removes the check-in plan.
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
  update plytos.card_line set head_version_id = null where owner_id = target_user;
  delete from plytos.card_version where owner_id = target_user;
  delete from plytos.card_line where owner_id = target_user;
  delete from plytos.target where owner_id = target_user;
  delete from plytos.card where owner_id = target_user;
  delete from plytos.app_user where id = target_user;
end
$$;
