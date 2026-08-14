from __future__ import annotations

import asyncio

from compaire.mock import MockProvider
from compaire.openrouter import ModelInfo, ModelResult, OpenRouterError
from compaire.runner import RunPlan, estimate_cost, execute, run_id, total_estimate
from compaire.schema import PromptParams


class TrackingProvider:
    """Records overlap so the concurrency limit can be asserted."""

    def __init__(self, fail: set[str] | None = None, delay: float = 0.01):
        self.fail = fail or set()
        self.delay = delay
        self.active = 0
        self.peak = 0
        self.seen: list[tuple[str, int]] = []

    async def chat(self, model, prompt, system=None, params=None, sample_index=0) -> ModelResult:
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.seen.append((model, sample_index))
        try:
            await asyncio.sleep(self.delay)
            if model in self.fail:
                raise OpenRouterError(f"{model} exploded")
            return ModelResult(text=f"{model} says hi #{sample_index}")
        finally:
            self.active -= 1

    async def image(self, model, prompt, params=None, sample_index=0) -> ModelResult:
        return await self.chat(model, prompt, sample_index=sample_index)

    async def models(self):
        return []


async def test_results_keep_plan_order_regardless_of_timing() -> None:
    plan = RunPlan(prompt="p", models=["a/1", "b/2", "c/3"], concurrency=3)
    outcomes = await execute(TrackingProvider(), plan)
    assert [o.model for o in outcomes] == ["a/1", "b/2", "c/3"]


async def test_one_failure_does_not_sink_the_run() -> None:
    plan = RunPlan(prompt="p", models=["a/1", "bad/2", "c/3"])
    outcomes = await execute(TrackingProvider(fail={"bad/2"}), plan)
    assert [o.status for o in outcomes] == ["ok", "error", "ok"]
    assert "exploded" in outcomes[1].error
    assert outcomes[1].result is None


async def test_unexpected_exceptions_are_captured_too() -> None:
    class Broken:
        async def chat(self, model, prompt, system=None, params=None, sample_index=0):
            raise RuntimeError("kaboom")

        async def image(self, model, prompt, params=None, sample_index=0):
            raise RuntimeError("kaboom")

        async def models(self):
            return []

    outcomes = await execute(Broken(), RunPlan(prompt="p", models=["a/1"]))
    assert outcomes[0].status == "error"
    assert outcomes[0].error == "RuntimeError: kaboom"


async def test_concurrency_is_bounded() -> None:
    provider = TrackingProvider(delay=0.02)
    plan = RunPlan(prompt="p", models=[f"m/{i}" for i in range(8)], concurrency=2)
    await execute(provider, plan)
    assert provider.peak <= 2


async def test_samples_multiply_the_calls() -> None:
    provider = TrackingProvider(delay=0)
    plan = RunPlan(prompt="p", models=["a/1", "b/2"], samples=3)
    outcomes = await execute(provider, plan)
    assert len(outcomes) == 6
    assert {o.id for o in outcomes} == {f"{run_id(m, i)}" for m in ("a/1", "b/2") for i in range(3)}


async def test_each_sample_is_told_which_one_it_is() -> None:
    """Providers that cannot vary on their own need the index to differ."""
    provider = TrackingProvider(delay=0)
    await execute(provider, RunPlan(prompt="p", models=["a/1"], samples=3))
    assert sorted(provider.seen) == [("a/1", 0), ("a/1", 1), ("a/1", 2)]


async def test_mock_samples_differ_from_each_other() -> None:
    provider = MockProvider(view="gallery")
    first = await provider.image("mock/painter", "same prompt", None, 0)
    second = await provider.image("mock/painter", "same prompt", None, 1)
    assert first.images[0].data != second.images[0].data


async def test_latency_is_recorded_for_failures_as_well() -> None:
    outcomes = await execute(
        TrackingProvider(fail={"a/1"}, delay=0.01), RunPlan(prompt="p", models=["a/1"])
    )
    assert outcomes[0].latency_ms >= 0


async def test_mock_provider_is_deterministic() -> None:
    provider = MockProvider(view="table")
    first = await provider.chat("mock/writer", "same prompt")
    second = await provider.chat("mock/writer", "same prompt")
    assert first.text == second.text


def test_estimate_cost_prices_tokens() -> None:
    catalog = {"a/1": ModelInfo(id="a/1", name="A", prompt_price=1e-6, completion_price=2e-6)}
    plan = RunPlan(prompt="x" * 400, models=["a/1"], params=PromptParams(max_tokens=1000))
    ((model, value),) = estimate_cost(plan, catalog)
    assert model == "a/1"
    assert value == 100 * 1e-6 + 1000 * 2e-6


def test_estimate_cost_flags_unknown_models() -> None:
    estimates = estimate_cost(RunPlan(prompt="x", models=["ghost/1"]), {})
    assert estimates == [("ghost/1", None)]
    assert total_estimate(estimates) == 0.0


def test_estimate_cost_uses_per_image_price() -> None:
    catalog = {"p/1": ModelInfo(id="p/1", name="P", image_price=0.04, output_modalities=["image"])}
    plan = RunPlan(prompt="draw", models=["p/1"], modality="image", samples=3)
    assert estimate_cost(plan, catalog) == [("p/1", 0.12)]
