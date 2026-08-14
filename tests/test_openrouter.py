from __future__ import annotations

import base64
import io
import json

import httpx
import pytest
from PIL import Image

from compaire.openrouter import (
    OpenRouterClient,
    OpenRouterError,
    decode_data_url,
    parse_model_info,
)
from compaire.schema import PromptParams


def data_url() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (1, 2, 3)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def client(handler, **kwargs) -> OpenRouterClient:
    transport = httpx.MockTransport(handler)
    return OpenRouterClient(
        "test-key", client=httpx.AsyncClient(transport=transport), **kwargs
    )


@pytest.fixture(autouse=True)
def no_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry backoff must not slow the suite down."""

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("compaire.openrouter.asyncio.sleep", instant)


def chat_response(content: str = "hello", **extra) -> dict:
    return {
        "id": "gen-1",
        "choices": [{"message": {"content": content, **extra}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12, "cost": 0.002},
    }


async def test_chat_parses_text_usage_and_id() -> None:
    async with client(lambda request: httpx.Response(200, json=chat_response())) as api:
        result = await api.chat("a/b", "hi")
    assert result.text == "hello"
    assert result.generation_id == "gen-1"
    assert result.usage.total_tokens == 12
    assert result.usage.cost == 0.002


async def test_chat_sends_system_prompt_and_params() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        captured["headers"] = request.headers
        return httpx.Response(200, json=chat_response())

    async with client(handler) as api:
        await api.chat("a/b", "hi", "be terse", PromptParams(temperature=0.5, max_tokens=10))

    payload = captured["payload"]
    assert payload["messages"][0] == {"role": "system", "content": "be terse"}
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 10


async def test_chat_joins_content_parts() -> None:
    response = chat_response()
    response["choices"][0]["message"]["content"] = [
        {"type": "text", "text": "part one "},
        {"type": "text", "text": "part two"},
    ]
    async with client(lambda request: httpx.Response(200, json=response)) as api:
        result = await api.chat("a/b", "hi")
    assert result.text == "part one part two"


@pytest.mark.parametrize(
    "images",
    [
        [data_url()],
        [{"image_url": {"url": data_url()}}],
        [{"b64_json": data_url().split(",", 1)[1], "media_type": "image/png"}],
    ],
)
async def test_chat_understands_the_inline_image_shapes(images: list) -> None:
    response = chat_response(images=images)
    async with client(lambda request: httpx.Response(200, json=response)) as api:
        result = await api.chat("a/b", "draw")
    assert len(result.images) == 1
    assert result.images[0].data[:4] == b"\x89PNG"


async def test_images_endpoint_decodes_base64() -> None:
    payload = {
        "data": [{"b64_json": base64.b64encode(b"raw-bytes").decode(), "media_type": "image/webp"}],
        "usage": {"prompt_tokens": 1, "cost": 0.04},
    }
    async with client(lambda request: httpx.Response(200, json=payload)) as api:
        result = await api.image("p/1", "a cat")
    assert result.images[0].data == b"raw-bytes"
    assert result.images[0].media_type == "image/webp"
    assert result.usage.cost == 0.04


async def test_empty_image_response_is_an_error() -> None:
    async with client(lambda request: httpx.Response(200, json={"data": []})) as api:
        with pytest.raises(OpenRouterError, match="no images"):
            await api.image("p/1", "a cat")


async def test_rate_limits_are_retried_then_succeed() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=chat_response())

    async with client(handler, max_retries=3) as api:
        result = await api.chat("a/b", "hi")
    assert calls["n"] == 3
    assert result.text == "hello"


async def test_retries_give_up_and_report_the_last_error() -> None:
    async with client(
        lambda request: httpx.Response(503, json={"error": {"message": "upstream down"}}),
        max_retries=2,
    ) as api:
        with pytest.raises(OpenRouterError, match="upstream down") as excinfo:
            await api.chat("a/b", "hi")
    assert excinfo.value.status == 503


async def test_client_errors_are_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    async with client(handler, max_retries=3) as api:
        with pytest.raises(OpenRouterError, match="bad key"):
            await api.chat("a/b", "hi")
    assert calls["n"] == 1


async def test_transport_errors_are_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("no route to host")
        return httpx.Response(200, json=chat_response())

    async with client(handler, max_retries=2) as api:
        assert (await api.chat("a/b", "hi")).text == "hello"
    assert calls["n"] == 2


async def test_models_are_cached(tmp_path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": [{"id": "a/b", "name": "A B"}]})

    api = client(handler, cache_path=tmp_path / "models.json")
    async with api:
        first = await api.models()
        second = await api.models()
    assert calls["n"] == 1
    assert [m.id for m in first] == [m.id for m in second] == ["a/b"]


def test_parse_model_info_reads_pricing_strings() -> None:
    info = parse_model_info(
        {
            "id": "x/y",
            "name": "X Y",
            "context_length": 8000,
            "pricing": {"prompt": "0.000002", "completion": "0.000008", "image": "0.04"},
            "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]},
        }
    )
    assert (info.prompt_price, info.completion_price, info.image_price) == (2e-6, 8e-6, 0.04)
    assert info.generates_images


async def test_reasoning_tokens_are_lifted_out_of_the_nested_details() -> None:
    """The site should not need to know the provider's nesting."""
    response = chat_response()
    response["usage"] = {
        "prompt_tokens": 194,
        "completion_tokens": 2000,
        "completion_tokens_details": {"reasoning_tokens": 1500},
        "prompt_tokens_details": {"cached_tokens": 0},
        "total_tokens": 2194,
        "cost": 0.95,
    }
    async with client(lambda request: httpx.Response(200, json=response)) as api:
        usage = (await api.chat("a/b", "hi")).usage

    assert usage.reasoning_tokens == 1500
    assert usage.reasoned is True
    assert usage.completion_tokens == 2000
    # The provider's own block is preserved rather than flattened away.
    assert usage.model_dump()["completion_tokens_details"] == {"reasoning_tokens": 1500}


async def test_reasoning_may_exceed_the_completion_count() -> None:
    """Seen in real responses: several providers cap `completion_tokens` at
    max_tokens while reporting reasoning separately, so nothing may treat this
    as a subset."""
    response = chat_response()
    response["usage"] = {
        "completion_tokens": 500,
        "completion_tokens_details": {"reasoning_tokens": 551},
        "total_tokens": 600,
    }
    async with client(lambda request: httpx.Response(200, json=response)) as api:
        usage = (await api.chat("a/b", "hi")).usage
    assert (usage.completion_tokens, usage.reasoning_tokens) == (500, 551)


async def test_a_model_that_does_not_reason_reports_nothing() -> None:
    async with client(lambda request: httpx.Response(200, json=chat_response())) as api:
        usage = (await api.chat("a/b", "hi")).usage
    assert usage.reasoning_tokens is None
    assert usage.reasoned is False


async def test_an_explicit_zero_is_kept_as_zero() -> None:
    """`0` means "asked and told none", which differs from never reported."""
    response = chat_response()
    response["usage"] = {"completion_tokens_details": {"reasoning_tokens": 0}}
    async with client(lambda request: httpx.Response(200, json=response)) as api:
        usage = (await api.chat("a/b", "hi")).usage
    assert usage.reasoning_tokens == 0
    assert usage.reasoned is False


async def test_a_top_level_reasoning_count_is_left_alone() -> None:
    response = chat_response()
    response["usage"] = {
        "reasoning_tokens": 7,
        "completion_tokens_details": {"reasoning_tokens": 999},
    }
    async with client(lambda request: httpx.Response(200, json=response)) as api:
        assert (await api.chat("a/b", "hi")).usage.reasoning_tokens == 7


@pytest.mark.parametrize(
    ("pricing", "expected"),
    [
        ({"prompt": "0", "completion": "0"}, True),
        ({"prompt": "0", "completion": "0", "image": "0", "request": "0"}, True),
        ({"prompt": "0", "completion": "0.000008"}, False),
        # Free per token but charging per request is not free.
        ({"prompt": "0", "completion": "0", "request": "0.01"}, False),
        ({}, False),  # a catalog entry with no prices tells us nothing
        ({"prompt": "0", "overrides": {"some": "object"}}, True),
    ],
)
def test_free_checks_every_price(pricing: dict, expected: bool) -> None:
    assert parse_model_info({"id": "a/b", "pricing": pricing}).free is expected


@pytest.mark.parametrize(
    ("outputs", "storable"),
    [
        (["text"], True),
        (["text", "image"], True),
        (["image"], True),
        (["text", "audio"], False),  # half the answer would be dropped
        (["audio"], False),
        (["text", "video"], False),
    ],
)
def test_storable_requires_every_output_to_fit(outputs: list[str], storable: bool) -> None:
    info = parse_model_info({"id": "a/b", "architecture": {"output_modalities": outputs}})
    assert info.storable is storable


def test_unstorable_modalities_are_named() -> None:
    info = parse_model_info(
        {"id": "a/b", "architecture": {"output_modalities": ["text", "audio", "video"]}}
    )
    assert info.unstorable_modalities == ["audio", "video"]


async def test_the_catalog_works_without_a_key() -> None:
    """`/models` is public, so browsing must not demand credentials."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": [{"id": "a/b", "name": "A B"}]})

    api = OpenRouterClient(
        None, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    async with api:
        assert [info.id for info in await api.models()] == ["a/b"]
    assert seen["auth"] is None


def test_decode_data_url_rejects_garbage() -> None:
    assert decode_data_url("https://example.com/a.png") is None
