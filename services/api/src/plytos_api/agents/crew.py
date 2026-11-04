"""The agents that run, built from the settings."""

from __future__ import annotations

from plytos_api.agents.listener import Listener
from plytos_api.agents.runtime import Agent
from plytos_api.agents.stitcher import Stitcher
from plytos_api.agents.thinking import thinker_for
from plytos_api.config import Settings


def crew(settings: Settings) -> dict[str, Agent]:
    thinker = thinker_for(
        settings.ai_provider,
        settings.ai_model,
        settings.ai_effort,
        settings.ai_vertex_project,
        settings.ai_vertex_region,
    )
    agents: list[Agent] = [
        Listener(thinker, settings.stitch_delay_seconds),
        Stitcher(thinker),
    ]
    return {a.name: a for a in agents}
