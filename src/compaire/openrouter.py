"""Async OpenRouter client.

Covers the three endpoints the tool needs: chat completions, image generation
and the model catalog. Everything else in the package talks to models through
the :class:`Provider` protocol, which is what lets ``--provider mock`` stand in
without a network or an API key.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

from .config import (
    API_BASE,
    APP_TITLE,
    APP_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_S,
    cache_dir,
)
from .schema import PromptParams, Usage

MODELS_CACHE_TTL_S = 24 * 60 * 60
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}

DATA_URL_RE = re.compile(r"^data:(?P<media>[\w.+-]+/[\w.+-]+);base64,(?P<payload>.+)$", re.DOTALL)
_NUMERIC_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")


class OpenRouterError(RuntimeError):
    """A request failed in a way the run should record rather than crash on."""

    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass(slots=True)
class ImageBlob:
    data: bytes
    media_type: str = "image/png"


@dataclass(slots=True)
class ModelResult:
    """One model's reply, normalized across the chat and image endpoints."""

    text: str | None = None
    images: list[ImageBlob] = field(default_factory=list)
    usage: Usage | None = None
    generation_id: str | None = None
    finish_reason: str | None = None


@dataclass(slots=True)
class ModelInfo:
    id: str
    name: str
    context_length: int | None = None
    #: USD per token, as advertised by the catalog.
    prompt_price: float = 0.0
    completion_price: float = 0.0
    #: USD per generated image, for models priced per image rather than per token.
    image_price: float = 0.0
    input_modalities: list[str] = field(default_factory=list)
    output_modalities: list[str] = field(default_factory=list)
    description: str = ""
    #: True when *every* advertised price is zero. Checking the whole pricing
    #: block rather than just tokens keeps this honest if a model ever becomes
    #: free per token but charges per request or per image.
    free: bool = False

    @property
    def generates_images(self) -> bool:
        return "image" in self.output_modalities

    @property
    def storable(self) -> bool:
        """Whether the experiment format can keep everything this model emits.

        Audio and video have no output kind, so a model that produces them
        would have part of its answer silently dropped — which is worse than
        leaving it out of a comparison.
        """
        return set(self.output_modalities or ["text"]) <= {"text", "image"}

    @property
    def unstorable_modalities(self) -> list[str]:
        return sorted(set(self.output_modalities or ["text"]) - {"text", "image"})


class Provider(Protocol):
    """What the runner needs from a backend.

    ``sample_index`` distinguishes repeated calls with identical inputs. A real
    API varies on its own, so the client ignores it; the mock provider needs it
    to make sample 2 differ from sample 1.
    """

    async def chat(
        self,
        model: str,
        prompt: str,
        system: str | None,
        params: PromptParams,
        sample_index: int,
    ) -> ModelResult: ...

    async def image(
        self, model: str, prompt: str, params: PromptParams, sample_index: int
    ) -> ModelResult: ...

    async def models(self) -> list[ModelInfo]: ...


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_model_info(raw: dict[str, Any]) -> ModelInfo:
    pricing = raw.get("pricing") or {}
    architecture = raw.get("architecture") or {}
    return ModelInfo(
        id=raw.get("id", ""),
        name=raw.get("name") or raw.get("id", ""),
        context_length=raw.get("context_length"),
        prompt_price=_float(pricing.get("prompt")),
        completion_price=_float(pricing.get("completion")),
        image_price=_float(pricing.get("image")),
        input_modalities=list(architecture.get("input_modalities") or []),
        output_modalities=list(architecture.get("output_modalities") or ["text"]),
        description=raw.get("description") or "",
        free=_is_free(pricing),
    )


def _is_free(pricing: dict[str, Any]) -> bool:
    """Every numeric price is zero. A catalog entry with no prices is not free."""
    values = []
    for value in pricing.values():
        if isinstance(value, (int, float)) or (
            isinstance(value, str) and _NUMERIC_RE.match(value.strip())
        ):
            values.append(float(value))
    return bool(values) and all(value == 0 for value in values)


def decode_data_url(url: str) -> ImageBlob | None:
    match = DATA_URL_RE.match(url.strip())
    if not match:
        return None
    try:
        payload = base64.b64decode(match.group("payload"), validate=False)
    except (ValueError, TypeError):
        return None
    return ImageBlob(data=payload, media_type=match.group("media"))


def _extract_inline_images(message: dict[str, Any]) -> list[ImageBlob]:
    """Pull images out of a chat message.

    Chat models that emit images are less consistently documented than the
    dedicated images endpoint, so accept the shapes seen in the wild: a bare
    data URL string, ``{"image_url": {"url": ...}}``, or ``{"b64_json": ...}``.
    """
    blobs: list[ImageBlob] = []
    for item in message.get("images") or []:
        if isinstance(item, str):
            blob = decode_data_url(item)
        elif isinstance(item, dict):
            url = (item.get("image_url") or {}).get("url") if "image_url" in item else None
            if url:
                blob = decode_data_url(url)
            elif item.get("b64_json"):
                blob = ImageBlob(
                    data=base64.b64decode(item["b64_json"]),
                    media_type=item.get("media_type") or "image/png",
                )
            else:
                blob = None
        else:
            blob = None
        if blob:
            blobs.append(blob)
    return blobs


def _parse_usage(raw: dict[str, Any] | None) -> Usage | None:
    """Normalize the usage block, promoting reasoning tokens to the top level.

    OpenRouter reports them at ``completion_tokens_details.reasoning_tokens``.
    Lifting the value out means the site can show it without knowing the
    provider's nesting, while the original block is still preserved by the
    model's ``extra="allow"``.
    """
    if not raw:
        return None
    usage = dict(raw)
    if "reasoning_tokens" not in usage:
        details = usage.get("completion_tokens_details")
        if isinstance(details, dict) and details.get("reasoning_tokens") is not None:
            usage["reasoning_tokens"] = details["reasoning_tokens"]
    return Usage.model_validate(usage)


class OpenRouterClient:
    """Thin async wrapper. One instance is shared by every run in a batch."""

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = API_BASE,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        client: httpx.AsyncClient | None = None,
        cache_path: Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._cache_path = cache_path if cache_path is not None else cache_dir() / "models.json"
        self._owns_client = client is None
        headers = {
            "Content-Type": "application/json",
            # Attribution headers; optional, but they make runs traceable on the
            # OpenRouter dashboard.
            "HTTP-Referer": APP_URL,
            "X-OpenRouter-Title": APP_TITLE,
        }
        # The catalog is public, so browsing models works with no key at all.
        # Anything that actually costs money still needs one, and the API says
        # so itself.
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.AsyncClient(timeout=timeout, headers=headers)

    async def __aenter__(self) -> OpenRouterClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(f"{self.base_url}{path}", json=payload)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last = OpenRouterError(f"request failed: {exc}")
            else:
                if response.status_code < 400:
                    return response.json()
                body = response.text[:2000]
                last = OpenRouterError(
                    f"HTTP {response.status_code}: {_error_message(body)}",
                    status=response.status_code,
                    body=body,
                )
                if response.status_code not in RETRY_STATUS:
                    raise last
                retry_after = _retry_after_seconds(response)
                if attempt < self.max_retries:
                    await asyncio.sleep(retry_after or _backoff(attempt))
                    continue
            if attempt < self.max_retries:
                await asyncio.sleep(_backoff(attempt))
        raise last or OpenRouterError("request failed")

    async def chat(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        params: PromptParams | None = None,
        sample_index: int = 0,  # noqa: ARG002 — the API varies between calls on its own
    ) -> ModelResult:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {"model": model, "messages": messages}
        payload.update(_param_payload(params))
        data = await self._post("/chat/completions", payload)

        choices = data.get("choices") or []
        if not choices:
            raise OpenRouterError(f"{model} returned no choices", body=json.dumps(data)[:2000])
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):  # some providers return content parts
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        return ModelResult(
            text=content or None,
            images=_extract_inline_images(message),
            usage=_parse_usage(data.get("usage")),
            generation_id=data.get("id"),
            finish_reason=choices[0].get("finish_reason"),
        )

    async def image(
        self,
        model: str,
        prompt: str,
        params: PromptParams | None = None,
        sample_index: int = 0,  # noqa: ARG002 — see chat()
    ) -> ModelResult:
        payload: dict[str, Any] = {"model": model, "prompt": prompt}
        extra = params.model_dump(exclude_none=True) if params else {}
        for key in ("n", "aspect_ratio", "resolution", "quality", "output_format"):
            if key in extra:
                payload[key] = extra[key]
        data = await self._post("/images", payload)

        images: list[ImageBlob] = []
        for item in data.get("data") or []:
            if item.get("b64_json"):
                images.append(
                    ImageBlob(
                        data=base64.b64decode(item["b64_json"]),
                        media_type=item.get("media_type") or "image/png",
                    )
                )
            elif item.get("url"):
                blob = decode_data_url(item["url"])
                if blob:
                    images.append(blob)
        if not images:
            raise OpenRouterError(f"{model} returned no images", body=json.dumps(data)[:2000])
        return ModelResult(
            images=images,
            usage=_parse_usage(data.get("usage")),
            generation_id=data.get("id"),
        )

    async def models(self, *, refresh: bool = False) -> list[ModelInfo]:
        cached = None if refresh else self._read_cache()
        if cached is None:
            response = await self._client.get(f"{self.base_url}/models")
            response.raise_for_status()
            cached = response.json().get("data") or []
            self._write_cache(cached)
        return [parse_model_info(raw) for raw in cached]

    def _read_cache(self) -> list[dict[str, Any]] | None:
        try:
            blob = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if time.time() - blob.get("fetched_at", 0) > MODELS_CACHE_TTL_S:
            return None
        return blob.get("data")

    def _write_cache(self, data: list[dict[str, Any]]) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps({"fetched_at": time.time(), "data": data}), encoding="utf-8"
            )
        except OSError:
            pass  # a cold cache is a slow run, not a failed one


def _param_payload(params: PromptParams | None) -> dict[str, Any]:
    if params is None:
        return {}
    payload = params.model_dump(exclude_none=True)
    # Image-only knobs would be rejected by the chat endpoint.
    for key in ("aspect_ratio", "resolution", "quality", "output_format", "n"):
        payload.pop(key, None)
    return payload


def _backoff(attempt: int) -> float:
    return min(2.0**attempt, 30.0) + random.uniform(0, 0.5)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return min(float(raw), 60.0)
    except ValueError:
        return None


def _error_message(body: str) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return body.strip() or "no response body"
    error = parsed.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error or parsed)
