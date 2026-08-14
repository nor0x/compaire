"""Turn run outcomes into a committable experiment directory.

Layout produced::

    experiments/<id>/
      experiment.json   # the contract the website reads
      spec.toml         # inputs, so anyone can reproduce the run
      prompt.txt        # the prompt verbatim
      assets/<sha8>.*   # content-addressed outputs

Assets are named by content hash, so two models returning byte-identical
output share one file instead of bloating the pull request.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from . import __version__, svg
from .config import ASSETS_DIRNAME, EXPERIMENT_FILENAME, SPEC_FILENAME
from .runner import RunOutcome, RunPlan
from .schema import (
    INLINE_TEXT_LIMIT,
    Author,
    Experiment,
    HtmlOutput,
    ImageOutput,
    Output,
    PromptSpec,
    Run,
    SvgOutput,
    TextOutput,
    ViewKind,
)

PROMPT_FILENAME = "prompt.txt"
HTML_FENCE_RE = re.compile(r"```(?:html)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
HTML_START_RE = re.compile(r"\s*(?:<!doctype html|<html[\s>])", re.IGNORECASE)
DOCTYPE_RE = re.compile(r"<!doctype html", re.IGNORECASE)
SVG_FENCE_RE = re.compile(r"```(?:svg|xml)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
SVG_OPEN_RE = re.compile(r"<svg[\s>]", re.IGNORECASE)
SVG_CLOSE = "</svg>"


def slugify(value: str, *, fallback: str = "experiment") -> str:
    """Title -> directory name. Must satisfy ``schema.ID_PATTERN``."""
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or fallback


def unique_dir(parent: Path, slug: str) -> tuple[Path, str]:
    """Pick a free directory name, suffixing ``-2``, ``-3``… on collision."""
    candidate, index = slug, 1
    while (parent / candidate).exists():
        index += 1
        candidate = f"{slug}-{index}"
    return parent / candidate, candidate


def extract_html(text: str) -> str | None:
    """Pull a page out of a model's answer.

    Models asked for a web page answer in one of three ways: a fenced ``html``
    block, the bare document, or a sentence of preamble followed by a doctype.
    Prose that merely mentions ``<html>`` is not a page and stays a text output.
    """
    fence = HTML_FENCE_RE.search(text)
    if fence:
        return fence.group(1).strip()
    if HTML_START_RE.match(text):
        return text.strip()
    doctype = DOCTYPE_RE.search(text[:2000])
    if doctype:
        return text[doctype.start() :].strip()
    return None


def extract_svg(text: str) -> str | None:
    """Pull a drawing out of a model's answer.

    Unlike HTML, SVG has an unambiguous end tag, so the document can be sliced
    out of whatever the model wrapped it in — a fenced block, a sentence of
    preamble, or a trailing "let me know what you think". Prose that merely
    mentions ``<svg>`` has no closing tag and stays a text output.
    """
    fence = SVG_FENCE_RE.search(text)
    candidate = fence.group(1) if fence else text

    start = SVG_OPEN_RE.search(candidate)
    end = candidate.lower().rfind(SVG_CLOSE)
    if not start or end < start.start():
        return None
    return candidate[start.start() : end + len(SVG_CLOSE)].strip()


@dataclass(slots=True)
class AssetStore:
    """Writes content-addressed files under ``<experiment>/assets``."""

    directory: Path

    def put(self, data: bytes, suffix: str) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()[:8]
        name = f"{digest}{suffix}"
        path = self.directory / name
        if not path.exists():
            path.write_bytes(data)
        return f"{ASSETS_DIRNAME}/{name}"


def encode_webp(data: bytes, *, quality: int = 88) -> tuple[bytes, int, int, bool]:
    """Re-encode to WebP, which is what keeps gallery experiments inside budget.

    Returns ``(data, width, height, converted)``. Falls back to the original
    bytes if Pillow cannot read them, so an exotic format is preserved rather
    than lost.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="WEBP", quality=quality, method=4)
    except Exception:  # noqa: BLE001 — unreadable image, keep what the model sent
        return data, 0, 0, False
    return buffer.getvalue(), width, height, True


def build_outputs(outcome: RunOutcome, view: ViewKind, store: AssetStore) -> list[Output]:
    outputs: list[Output] = []
    result = outcome.result
    if result is None:
        return outputs

    for blob in result.images:
        # SVG is vector text: Pillow cannot read it, and re-encoding it to WebP
        # would throw away the source the code view needs.
        if blob.media_type.lower() == "image/svg+xml":
            svg_output = _build_svg(blob.data, outcome, store)
            if svg_output:
                outputs.append(svg_output)
                continue

        data, width, height, converted = encode_webp(blob.data)
        suffix = ".webp" if converted else _suffix_for(blob.media_type)
        path = store.put(data, suffix)
        outputs.append(
            ImageOutput(
                path=path,
                width=width or None,
                height=height or None,
                bytes=len(data),
                alt=f"{outcome.model_name or outcome.model} output",
            )
        )

    text = (result.text or "").strip()
    if not text:
        return outputs

    if view == "html":
        html = extract_html(text)
        if html:
            data = html.encode("utf-8")
            outputs.append(HtmlOutput(path=store.put(data, ".html"), bytes=len(data)))
            return outputs

    if view == "svg":
        drawing = extract_svg(text)
        svg_output = _build_svg(drawing.encode("utf-8"), outcome, store) if drawing else None
        if svg_output:
            outputs.append(svg_output)
            return outputs

    encoded = text.encode("utf-8")
    if len(encoded) > INLINE_TEXT_LIMIT:
        outputs.append(
            TextOutput(path=store.put(encoded, ".md"), bytes=len(encoded), format="markdown")
        )
    else:
        outputs.append(TextOutput(text=text, bytes=len(encoded), format="markdown"))
    return outputs


def _build_svg(data: bytes, outcome: RunOutcome, store: AssetStore) -> SvgOutput | None:
    """Clean the drawing, store it, and record anything that had to go.

    Returns ``None`` when the bytes are not a usable SVG, so the caller can fall
    back to keeping the model's answer as text rather than losing it.
    """
    try:
        cleaned, removed = svg.sanitize(data)
    except svg.SvgError:
        return None

    width, height = svg.intrinsic_size(cleaned)
    return SvgOutput(
        path=store.put(cleaned, ".svg"),
        width=width,
        height=height,
        bytes=len(cleaned),
        alt=f"{outcome.model_name or outcome.model} drawing",
        sanitized=bool(removed),
        removed=removed,
    )


def _suffix_for(media_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }.get(media_type.lower(), ".bin")


def build_run(
    outcome: RunOutcome,
    view: ViewKind,
    store: AssetStore,
    *,
    author: Author | None = None,
    created_at: datetime | None = None,
) -> Run:
    """One finished call as a manifest entry, assets written along the way.

    Shared by ``compaire run`` and ``compaire extend`` so a result appended
    months later is indistinguishable in shape from the originals.
    """
    return Run(
        id=outcome.id,
        model=outcome.model,
        model_name=outcome.model_name,
        sample_index=outcome.sample_index,
        status="ok" if outcome.ok else "error",
        error=outcome.error,
        latency_ms=outcome.latency_ms,
        usage=outcome.usage,
        outputs=build_outputs(outcome, view, store),
        generation_id=outcome.result.generation_id if outcome.result else None,
        author=author,
        created_at=created_at,
    )


def build_experiment(
    *,
    experiment_id: str,
    title: str,
    plan: RunPlan,
    outcomes: list[RunOutcome],
    directory: Path,
    view: ViewKind = "table",
    description: str | None = None,
    author: Author | None = None,
    tags: list[str] | None = None,
    created_at: datetime | None = None,
) -> Experiment:
    """Write every asset, then assemble the manifest that references them."""
    store = AssetStore(directory / ASSETS_DIRNAME)
    stamp = created_at or datetime.now(UTC)
    runs = [
        build_run(outcome, view, store, author=author, created_at=stamp)
        for outcome in outcomes
    ]
    return Experiment(
        id=experiment_id,
        title=title,
        description=description,
        author=author,
        created_at=created_at or datetime.now(UTC),
        view=view,
        modality=plan.modality,
        tags=tags or [],
        prompt=PromptSpec(
            text=plan.prompt,
            system=plan.system,
            file=PROMPT_FILENAME,
            params=plan.params,
        ),
        runs=runs,
        tool_version=__version__,
    )


def write_experiment(experiment: Experiment, directory: Path) -> Path:
    """Persist the manifest, the prompt and the reproducible spec."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = experiment.model_dump(mode="json", exclude_none=False)
    (directory / EXPERIMENT_FILENAME).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _write(directory / PROMPT_FILENAME, experiment.prompt.text)
    _write(directory / SPEC_FILENAME, render_spec(experiment))
    return directory / EXPERIMENT_FILENAME


def prune_unreferenced(directory: Path, experiment: Experiment) -> list[Path]:
    """Delete assets no run points at any more.

    ``compaire extend --replace`` orphans the old model's files, and validate
    turns an unreferenced asset into an error under ``--strict``, so the command
    has to clean up after itself.
    """
    referenced = {
        (directory / path).resolve()
        for run in experiment.runs
        for output in run.outputs
        if (path := getattr(output, "path", None))
    }
    assets = directory / ASSETS_DIRNAME
    if not assets.is_dir():
        return []

    removed = []
    for asset in sorted(assets.iterdir()):
        if asset.is_file() and asset.resolve() not in referenced:
            asset.unlink()
            removed.append(asset)
    return removed


def _write(path: Path, content: str) -> None:
    """Always LF, so the same run produces the same bytes on every platform."""
    path.write_text(content, encoding="utf-8", newline="\n")


def render_spec(experiment: Experiment) -> str:
    """A TOML file that reproduces this experiment via ``compaire run --spec``.

    Derived from the manifest rather than from the invocation that produced it,
    so a comparison that a second contributor extended still has a spec that
    describes all of it.
    """
    lines = [
        "# Reproduce this experiment with:",
        "#   compaire run --spec spec.toml",
        "",
        f"title = {_toml(experiment.title)}",
        f"id = {_toml(experiment.id)}",
    ]
    if experiment.description:
        lines.append(f"description = {_toml(experiment.description)}")
    lines += [
        f"view = {_toml(experiment.view)}",
        f"modality = {_toml(experiment.modality)}",
        f"tags = {_toml(experiment.tags)}",
        f"prompt_file = {_toml(PROMPT_FILENAME)}",
    ]
    if experiment.prompt.system:
        lines.append(f"system = {_toml(experiment.prompt.system)}")
    lines += [
        f"samples = {experiment.samples_per_model or 1}",
        f"models = {_toml(experiment.models)}",
    ]
    params = experiment.prompt.params.model_dump(exclude_none=True)
    if params:
        lines += ["", "[params]"]
        lines += [f"{key} = {_toml(value)}" for key, value in sorted(params.items())]
    return "\n".join(lines) + "\n"


def _toml(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    return json.dumps(str(value))  # JSON string escaping is valid TOML basic-string escaping
