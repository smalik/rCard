-- Agents: the small crew that works over a person's account.
--
-- Plytos is one conversation. The person talks in fragments (tidbits), and
-- small agents file them, join them into accomplishments, check the facts and
-- assemble resumes. Agents never decide. Everything they make is a proposal
-- until the person keeps it, and only then does it become a card version,
-- recorded with author_kind = 'ai' (docs/agents.md).
--
-- Content is encrypted with the person's own key: messages, tidbits, what an
-- agent read from them, and proposals. Only IDs, kinds, states, counts and
-- times are clear (docs/data-model.md).

-- ---------------------------------------------------------------------------
-- Agent runs: the work queue and the record of what ran
-- ---------------------------------------------------------------------------

-- One run of one agent for one person: why it ran, its state while queued or
-- running, and what it cost once done. Never content.
create table plytos.agent_run (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  agent text not null
    check (agent in ('check_in', 'listener', 'stitcher', 'fact_checker', 'connector',
                     'strategist', 'scout', 'assembler', 'critic')),
  -- What started it: a message, a tidbit, a card change, or the schedule.
  trigger_kind text not null check (trigger_kind in ('message', 'tidbit', 'card', 'schedule')),
  trigger_id uuid,
  -- Runs that should happen once however often they're asked for (the
  -- Stitcher after a burst of notes) share a key while queued.
  dedupe_key text,
  state text not null default 'queued'
    check (state in ('queued', 'running', 'done', 'failed')),
  attempts smallint not null default 0 check (attempts >= 0),
  run_after timestamptz not null default now(),
  locked_until timestamptz,
  model text,
  input_tokens integer check (input_tokens >= 0),
  output_tokens integer check (output_tokens >= 0),
  -- A short code such as 'model_unavailable'. Never content or model output.
  error_code text check (error_code ~ '^[a-z][a-z_]{0,63}$'),
  created_at timestamptz not null default now(),
  finished_at timestamptz,
  unique (id, owner_id),
  constraint agent_run_finish_is_consistent
    check ((state in ('done', 'failed')) = (finished_at is not null))
);

create index agent_run_due on plytos.agent_run (run_after) where state in ('queued', 'running');
create index agent_run_by_owner on plytos.agent_run (owner_id, created_at);
create unique index agent_run_one_queued
  on plytos.agent_run (owner_id, dedupe_key)
  where state = 'queued' and dedupe_key is not null;

-- The worker claims due runs across people, then works on each one inside
-- that person's own transaction (Database.as_user), so row-level security
-- still holds for everything it reads and writes. This function returns only
-- IDs and agent names. A run whose lease ran out is claimed again.
create or replace function plytos.claim_agent_runs(max_runs integer, lease_seconds integer)
returns table (id uuid, owner_id uuid, agent text)
language plpgsql security definer
set search_path = pg_catalog, plytos
as $$
begin
  return query
  update plytos.agent_run r
     set state = 'running',
         attempts = r.attempts + 1,
         locked_until = now() + make_interval(secs => lease_seconds)
   where r.id in (
     select q.id from plytos.agent_run q
      where (q.state = 'queued' and q.run_after <= now())
         or (q.state = 'running' and q.locked_until < now())
      order by q.run_after
      limit greatest(max_runs, 0)
      for update skip locked)
  returning r.id, r.owner_id, r.agent;
end
$$;

-- ---------------------------------------------------------------------------
-- Proposals: everything an agent suggests
-- ---------------------------------------------------------------------------

-- What an agent proposes and why, encrypted. What it draws on is a list of
-- IDs (tidbits and cards). Nothing changes until the person keeps it.
create table plytos.proposal (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  agent text not null
    check (agent in ('check_in', 'listener', 'stitcher', 'fact_checker', 'connector',
                     'strategist', 'scout', 'assembler', 'critic')),
  kind text not null
    check (kind in ('new_card', 'card_version', 'variant', 'resume', 'question', 'insight')),
  -- The existing card it changes, when it changes one.
  card_id uuid,
  payload_ciphertext bytea not null,
  cites uuid[] not null default '{}',
  run_id uuid,
  state text not null default 'open'
    check (state in ('open', 'kept', 'edited', 'dismissed', 'superseded')),
  decided_at timestamptz,
  -- The card version made when the person kept it.
  result_version_id uuid references plytos.card_version (id),
  created_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (card_id, owner_id) references plytos.card (id, owner_id),
  foreign key (run_id, owner_id) references plytos.agent_run (id, owner_id),
  constraint proposal_decision_is_consistent
    check ((state = 'open') = (decided_at is null)),
  constraint proposal_result_only_when_kept
    check (result_version_id is null or state in ('kept', 'edited'))
);

create index proposal_open on plytos.proposal (owner_id, created_at) where state = 'open';

-- A proposal is decided once. After that it stays as it was decided.
create or replace function plytos.proposal_decided_once() returns trigger
language plpgsql
as $$
begin
  if old.state <> 'open' then
    raise exception 'proposal % was already decided', old.id
      using errcode = 'check_violation';
  end if;
  if (to_jsonb(new) - 'state' - 'decided_at' - 'result_version_id')
     <> (to_jsonb(old) - 'state' - 'decided_at' - 'result_version_id') then
    raise exception 'only the decision on a proposal can change'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end
$$;

create trigger proposal_decided_once
  before update on plytos.proposal
  for each row execute function plytos.proposal_decided_once();

-- ---------------------------------------------------------------------------
-- The conversation
-- ---------------------------------------------------------------------------

-- The person's messages and Plytos's replies, in order. A reply that offers
-- something to keep points at its proposal. Messages never change.
create table plytos.message (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  author text not null check (author in ('person', 'plytos')),
  channel text not null default 'app' check (channel in ('app', 'text_message', 'email')),
  body_ciphertext bytea not null,
  proposal_id uuid,
  created_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (proposal_id, owner_id) references plytos.proposal (id, owner_id),
  constraint only_plytos_offers_proposals
    check (proposal_id is null or author = 'plytos')
);

create index message_by_owner on plytos.message (owner_id, created_at);

-- ---------------------------------------------------------------------------
-- Tidbits
-- ---------------------------------------------------------------------------

-- A quick note, voice memo or photo about work, kept for the life of the
-- account. The original never changes. The Listener reads it once: it files
-- it under the job it belongs to and records what it found (projects,
-- numbers, people) beside the original.
create table plytos.tidbit (
  id uuid primary key default plytos.uuid_v7(),
  owner_id uuid not null references plytos.app_user (id),
  kind text not null check (kind in ('text', 'voice', 'photo')),
  -- The message it arrived in, when it came through the conversation.
  message_id uuid,
  -- When it happened, as far as the person said; arrival time otherwise.
  said_at timestamptz not null default now(),
  body_ciphertext bytea not null,
  -- The Listener's reading, set once.
  card_id uuid,
  reading_ciphertext bytea,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  unique (id, owner_id),
  foreign key (message_id, owner_id) references plytos.message (id, owner_id),
  foreign key (card_id, owner_id) references plytos.card (id, owner_id),
  constraint tidbit_reading_is_whole
    check ((reading_ciphertext is null) = (read_at is null))
);

create index tidbit_by_owner on plytos.tidbit (owner_id, said_at);
create index tidbit_unread on plytos.tidbit (owner_id) where read_at is null;
create index tidbit_by_card on plytos.tidbit (card_id) where card_id is not null;

-- The original stays as it was. Only an unread tidbit can take a reading.
create or replace function plytos.tidbit_read_once() returns trigger
language plpgsql
as $$
begin
  if old.read_at is not null then
    raise exception 'tidbit % was already read', old.id
      using errcode = 'check_violation';
  end if;
  if (to_jsonb(new) - 'card_id' - 'reading_ciphertext' - 'read_at')
     <> (to_jsonb(old) - 'card_id' - 'reading_ciphertext' - 'read_at') then
    raise exception 'a tidbit''s original never changes'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end
$$;

create trigger tidbit_read_once
  before update on plytos.tidbit
  for each row execute function plytos.tidbit_read_once();

-- ---------------------------------------------------------------------------
-- Row-level security and privileges
-- ---------------------------------------------------------------------------

do $$
declare
  t text;
begin
  foreach t in array array['agent_run', 'proposal', 'message', 'tidbit']
  loop
    execute format('alter table plytos.%I enable row level security', t);
    execute format(
      'create policy %I on plytos.%I using (owner_id = plytos.current_user_id())'
      ' with check (owner_id = plytos.current_user_id())',
      t || '_owner', t);
  end loop;
end
$$;

grant select, insert on plytos.agent_run to plytos_app;
grant update (state, run_after, locked_until, model, input_tokens, output_tokens,
              error_code, finished_at) on plytos.agent_run to plytos_app;
grant select, insert on plytos.proposal to plytos_app;
grant update (state, decided_at, result_version_id) on plytos.proposal to plytos_app;
-- Append-only: no update or delete for the app.
grant select, insert on plytos.message to plytos_app;
grant select, insert on plytos.tidbit to plytos_app;
grant update (card_id, reading_ciphertext, read_at) on plytos.tidbit to plytos_app;

revoke all on function plytos.claim_agent_runs(integer, integer) from public;
grant execute on function plytos.claim_agent_runs(integer, integer) to plytos_app;

-- Account deletion also removes the conversation, tidbits, proposals and runs.
create or replace function plytos.purge_user(target_user uuid) returns void
language plpgsql security definer
set search_path = pg_catalog, plytos, plytos_vault
as $$
begin
  delete from plytos_vault.user_key where user_id = target_user;
  delete from plytos.event where owner_id = target_user;
  delete from plytos.resume_import where owner_id = target_user;
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
