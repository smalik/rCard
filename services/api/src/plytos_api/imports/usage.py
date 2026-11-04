"""What each Claude call in an import cost: tokens, seconds and dollars.

Every request the import makes is recorded as an ``AiCall`` with the step it
served (reading pictures, reading the structure, checking placements, pulling
facts, proofreading), the tokens the API reported, how long it took and what
it cost at list price. The import keeps its calls with the rest of its result,
and each is logged as one line of numbers, never the resume's text.

Prices are list prices in US dollars per million tokens. A model missing here
gets no cost, only its tokens.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


class Price(BaseModel):
    input: float
    output: float
    # Prompts longer than this are billed at the long rates, for the whole request.
    long_above: int | None = None
    long_input: float | None = None
    long_output: float | None = None


PRICES: dict[str, Price] = {
    "claude-haiku-5-5": Price(
        input=0.10, output=0.50, long_above=100_000, long_input=0.50, long_output=2.50
    ),
}
# Cache reads and writes, as multiples of the input price.
CACHE_READ = 0.1
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.0


class AiCall(BaseModel):
    """One request to Claude, in numbers only."""

    step: str
    model: str
    effort: str
    ok: bool
    stop_reason: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    # Part of output_tokens, when the API reports it.
    thinking_tokens: int | None = None
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    images: int = 0
    seconds: float = 0.0
    cost_usd: float | None = None


class AiUsage(BaseModel):
    """Every Claude call one import made, and their totals."""

    calls: list[AiCall] = Field(default_factory=list)

    @property
    def input_tokens(self) -> int:
        return sum(c.input_tokens + c.cache_write_tokens + c.cache_read_tokens for c in self.calls)

    @property
    def output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def seconds(self) -> float:
        return sum(c.seconds for c in self.calls)

    @property
    def cost_usd(self) -> float | None:
        costs = [c.cost_usd for c in self.calls]
        return None if any(c is None for c in costs) else sum(c or 0.0 for c in costs)


def record(
    step: str,
    model: str,
    effort: str,
    usage: Any,
    *,
    seconds: float,
    stop_reason: str | None,
    images: int = 0,
) -> AiCall:
    """The call, from the ``usage`` block the API returned, logged as numbers only."""
    write_1h = 0
    details = getattr(usage, "cache_creation", None)
    if details is not None:
        write_1h = getattr(details, "ephemeral_1h_input_tokens", 0) or 0
    thinking = getattr(getattr(usage, "output_tokens_details", None), "thinking_tokens", None)
    call = AiCall(
        step=step,
        model=model,
        effort=effort,
        ok=stop_reason == "end_turn",
        stop_reason=stop_reason,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        thinking_tokens=thinking,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        images=images,
        seconds=round(seconds, 3),
    )
    call.cost_usd = cost(call, write_1h=write_1h)
    log.info(
        "Claude call: step=%s model=%s effort=%s stop=%s in=%d out=%d thinking=%s "
        "cache_write=%d cache_read=%d images=%d seconds=%.2f cost_usd=%s",
        call.step,
        call.model,
        call.effort,
        call.stop_reason,
        call.input_tokens,
        call.output_tokens,
        call.thinking_tokens,
        call.cache_write_tokens,
        call.cache_read_tokens,
        call.images,
        call.seconds,
        f"{call.cost_usd:.6f}" if call.cost_usd is not None else "unknown",
    )
    return call


def failed(step: str, model: str, effort: str, error: str, *, seconds: float) -> AiCall:
    """A call that got no answer. Requests the API refuses aren't billed."""
    log.info("Claude call: step=%s model=%s failed=%s seconds=%.2f", step, model, error, seconds)
    return AiCall(
        step=step,
        model=model,
        effort=effort,
        ok=False,
        error=error,
        seconds=round(seconds, 3),
        cost_usd=0.0,
    )


def cost(call: AiCall, *, write_1h: int = 0) -> float | None:
    """The call's list price in dollars, or None when the model's price isn't known."""
    price = PRICES.get(call.model)
    if price is None:
        return None
    prompt = call.input_tokens + call.cache_write_tokens + call.cache_read_tokens
    long = price.long_above is not None and prompt > price.long_above
    per_in = (price.long_input if long else None) or price.input
    per_out = (price.long_output if long else None) or price.output
    write_5m = max(0, call.cache_write_tokens - write_1h)
    dollars = (
        call.input_tokens * per_in
        + write_5m * per_in * CACHE_WRITE_5M
        + write_1h * per_in * CACHE_WRITE_1H
        + call.cache_read_tokens * per_in * CACHE_READ
        + call.output_tokens * per_out
    ) / 1_000_000
    return round(dollars, 8)
