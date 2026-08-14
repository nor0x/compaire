"""Fan a single prompt out across models.

One slow or failing model must not take the comparison down with it, so every
call is isolated: failures become ``status="error"`` runs that the site renders
alongside the successes.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .openrouter import ModelInfo, ModelResult, OpenRouterError, Provider
from .schema import Modality, PromptParams, Usage

ProgressCallback = Callable[["RunOutcome"], None]


@dataclass(slots=True)
class RunOutcome:
    """A finished call, successful or not, before it is written to disk."""

    id: str
    model: str
    sample_index: int
    status: str = "ok"
    error: str | None = None
    latency_ms: int = 0
    usage: Usage | None = None
    result: ModelResult | None = None
    model_name: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass(slots=True)
class RunPlan:
    prompt: str
    models: Sequence[str]
    system: str | None = None
    params: PromptParams = field(default_factory=PromptParams)
    modality: Modality = "text"
    samples: int = 1
    concurrency: int = 4

    def calls(self) -> list[tuple[str, int]]:
        return [(model, i) for model in self.models for i in range(self.samples)]


def run_id(model: str, sample_index: int) -> str:
    slug = model.replace("/", "-").replace(":", "-").replace(".", "-").lower()
    return f"{slug}__{sample_index}"


async def execute(
    provider: Provider,
    plan: RunPlan,
    *,
    model_names: dict[str, str] | None = None,
    on_done: ProgressCallback | None = None,
) -> list[RunOutcome]:
    """Run every (model, sample) pair, bounded by ``plan.concurrency``.

    Results come back in plan order regardless of completion order, so the
    written experiment is stable across runs.
    """
    semaphore = asyncio.Semaphore(max(1, plan.concurrency))
    names = model_names or {}

    async def one(model: str, sample_index: int) -> RunOutcome:
        outcome = RunOutcome(
            id=run_id(model, sample_index),
            model=model,
            sample_index=sample_index,
            model_name=names.get(model),
        )
        async with semaphore:
            started = time.perf_counter()
            try:
                if plan.modality == "image":
                    result = await provider.image(
                        model, plan.prompt, plan.params, sample_index
                    )
                else:
                    result = await provider.chat(
                        model, plan.prompt, plan.system, plan.params, sample_index
                    )
            except OpenRouterError as exc:
                outcome.status = "error"
                outcome.error = str(exc)
            except Exception as exc:  # noqa: BLE001 — one model must not sink the run
                outcome.status = "error"
                outcome.error = f"{type(exc).__name__}: {exc}"
            else:
                outcome.result = result
                outcome.usage = result.usage
            outcome.latency_ms = int((time.perf_counter() - started) * 1000)
        if on_done:
            on_done(outcome)
        return outcome

    return list(await asyncio.gather(*(one(m, i) for m, i in plan.calls())))


def estimate_cost(
    plan: RunPlan, catalog: dict[str, ModelInfo]
) -> list[tuple[str, float | None]]:
    """Best-effort price per model for ``--dry-run``.

    ``None`` means the model is not in the catalog and cannot be priced, which
    is worth showing rather than silently reporting as free.
    """
    prompt_tokens = max(1, len(plan.prompt) // 4)
    max_tokens = plan.params.max_tokens or 1024
    estimates: list[tuple[str, float | None]] = []
    for model in plan.models:
        info = catalog.get(model)
        if info is None:
            estimates.append((model, None))
            continue
        if plan.modality == "image" or (info.generates_images and info.image_price):
            per_call = info.image_price or 0.0
        else:
            per_call = prompt_tokens * info.prompt_price + max_tokens * info.completion_price
        estimates.append((model, per_call * plan.samples))
    return estimates


def total_estimate(estimates: Sequence[tuple[str, float | None]]) -> float:
    return sum(value for _, value in estimates if value is not None)
