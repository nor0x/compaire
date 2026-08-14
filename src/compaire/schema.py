"""The on-disk experiment format.

This module is the single source of truth for the contract between the CLI and
the website. The JSON Schema and the TypeScript types the site compiles against
are both generated from here (see ``compaire.export``), so a field added below
reaches the frontend by running ``compaire schema --export``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

#: Text outputs smaller than this are inlined in experiment.json instead of
#: being written to their own asset file.
INLINE_TEXT_LIMIT = 4096

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

ViewKind = Literal["gallery", "slider", "table", "html", "svg", "text"]
Modality = Literal["text", "image"]
RunStatus = Literal["ok", "error"]


def _check_id(value: str) -> str:
    if not ID_PATTERN.match(value):
        raise ValueError(
            f"{value!r} is not a valid id: use lowercase letters, digits and single hyphens"
        )
    return value


def _check_relpath(value: str) -> str:
    """Asset paths must stay inside the experiment directory.

    Contributed experiments arrive by pull request, so a path is untrusted input
    until proven otherwise: no absolute paths, no drive letters, no traversal.
    """
    if not value:
        raise ValueError("path must not be empty")
    if "\\" in value:
        raise ValueError(f"{value!r} must use forward slashes")
    if value.startswith("/") or re.match(r"^[a-zA-Z]:", value):
        raise ValueError(f"{value!r} must be relative to the experiment directory")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"{value!r} must not contain '.', '..' or empty segments")
    return value


ExperimentId = Annotated[str, AfterValidator(_check_id)]
RelPath = Annotated[str, AfterValidator(_check_relpath)]


class Author(BaseModel):
    """Who contributed the experiment."""

    model_config = ConfigDict(extra="forbid")

    name: str
    github: str | None = None
    url: str | None = None


class PromptParams(BaseModel):
    """Sampling parameters, applied identically to every model in the run."""

    model_config = ConfigDict(extra="allow")

    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    seed: int | None = None


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    system: str | None = None
    #: Set when the prompt came from a file; the file is committed alongside
    #: the experiment so the run stays reproducible.
    file: RelPath | None = None
    params: PromptParams = Field(default_factory=PromptParams)


class Usage(BaseModel):
    """Token and cost accounting, as reported by OpenRouter.

    Extra keys are kept, so the provider's own nested breakdowns
    (``completion_tokens_details`` and friends) survive in the committed file
    even though only the fields below are named here.
    """

    model_config = ConfigDict(extra="allow")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    #: Tokens the model spent thinking before answering, lifted out of
    #: ``completion_tokens_details``. ``None`` when the provider said nothing.
    #:
    #: Do not assume a relationship to ``completion_tokens``: across real
    #: OpenRouter responses some providers count reasoning inside the completion
    #: total and others report more reasoning than completion tokens. It is the
    #: provider's own number, reported as-is.
    reasoning_tokens: int | None = None
    #: Total charged, in USD. ``None`` when the provider did not report it.
    cost: float | None = None

    @property
    def reasoned(self) -> bool:
        return bool(self.reasoning_tokens)


class TextOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"] = "text"
    #: Inlined when the output is small, otherwise ``path`` points at the file.
    text: str | None = None
    path: RelPath | None = None
    bytes: int | None = None
    format: Literal["plain", "markdown"] = "markdown"

    def model_post_init(self, _context: object) -> None:
        if (self.text is None) == (self.path is None):
            raise ValueError("text output needs exactly one of 'text' or 'path'")


class ImageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["image"] = "image"
    path: RelPath
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    alt: str | None = None


class HtmlOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["html"] = "html"
    path: RelPath
    bytes: int | None = None


class SvgOutput(BaseModel):
    """A vector drawing: an image the site can render and source it can show.

    Kept separate from :class:`ImageOutput` because SVG is text, cannot go
    through Pillow, and — unlike every other asset — is a live document when
    opened directly.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["svg"] = "svg"
    path: RelPath
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    alt: str | None = None
    #: True when the writer had to remove something before committing the file.
    #: The site says so, because the stored artifact is then not byte-for-byte
    #: what the model returned.
    sanitized: bool = False
    #: What was removed, e.g. ``["<script>", "onclick", "href to https://…"]``.
    removed: list[str] = Field(default_factory=list)


Output = Annotated[
    TextOutput | ImageOutput | HtmlOutput | SvgOutput,
    Field(discriminator="kind"),
]


class Run(BaseModel):
    """One model's answer to the prompt.

    Failures are recorded rather than dropped — a model that refuses or times
    out is part of the comparison.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    id: str
    model: str
    model_name: str | None = None
    sample_index: int = 0
    status: RunStatus = "ok"
    error: str | None = None
    latency_ms: int | None = None
    usage: Usage | None = None
    outputs: list[Output] = Field(default_factory=list)
    generation_id: str | None = None
    #: Who contributed this particular result. A comparison grows by pull
    #: request, so the model that arrived a month later has its own author and
    #: date rather than inheriting the experiment's.
    author: Author | None = None
    created_at: datetime | None = None

    def model_post_init(self, _context: object) -> None:
        if self.status == "error" and not self.error:
            raise ValueError(f"run {self.id!r} failed but carries no error message")


class Experiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    id: ExperimentId
    title: str
    description: str | None = None
    #: Who started the comparison. Individual results carry their own author.
    author: Author | None = None
    created_at: datetime
    #: Set when `compaire extend` appends results.
    updated_at: datetime | None = None
    view: ViewKind = "table"
    modality: Modality = "text"
    tags: list[str] = Field(default_factory=list)
    prompt: PromptSpec
    runs: list[Run] = Field(default_factory=list)
    #: Version of the CLI that produced the directory.
    tool_version: str | None = None

    @property
    def total_cost(self) -> float:
        return sum(run.usage.cost or 0.0 for run in self.runs if run.usage)

    @property
    def models(self) -> list[str]:
        """Every model in the comparison, in the order it was added."""
        return list(dict.fromkeys(run.model for run in self.runs))

    @property
    def contributors(self) -> list[Author]:
        """Distinct authors, the experiment's own first."""
        seen: dict[str, Author] = {}
        for author in (self.author, *(run.author for run in self.runs)):
            if author is not None:
                seen.setdefault(author.name, author)
        return list(seen.values())

    @property
    def samples_per_model(self) -> int | None:
        """Samples each model contributed, or ``None`` when it varies."""
        counts = {
            model: sum(1 for run in self.runs if run.model == model) for model in self.models
        }
        distinct = set(counts.values())
        return distinct.pop() if len(distinct) == 1 else None


class IndexEntry(BaseModel):
    """The card shown on the site's landing page.

    Deliberately small: the list page loads only this, never the full runs.
    """

    model_config = ConfigDict(extra="forbid")

    id: ExperimentId
    title: str
    description: str | None = None
    author: Author | None = None
    created_at: datetime
    updated_at: datetime | None = None
    view: ViewKind
    modality: Modality
    tags: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    run_count: int = 0
    #: How many people have contributed results, so a card can show it growing.
    contributors: int = 1
    #: Relative path (within the experiment directory) of a representative image.
    thumb: RelPath | None = None
    total_cost: float | None = None


class Index(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    generated_at: datetime
    experiments: list[IndexEntry] = Field(default_factory=list)
