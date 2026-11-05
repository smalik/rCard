-- The Summarizer: an agent that sums up a job's accomplishments as the
-- employment's headline and each title's story (docs/agents.md). It runs from
-- the same queue as the other agents, so the queue learns its name. It makes
-- no proposals: what it writes is saved as Plytos's own words, marked as such
-- inside the encrypted card content, and the person's words are left alone.
alter table plytos.agent_run drop constraint agent_run_agent_check;
alter table plytos.agent_run add constraint agent_run_agent_check
  check (agent in ('check_in', 'listener', 'stitcher', 'fact_checker', 'connector',
                   'strategist', 'scout', 'assembler', 'critic', 'summarizer'));
