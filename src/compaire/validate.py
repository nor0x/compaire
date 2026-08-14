"""The pull-request gate.

Contributed experiments are untrusted input: the JSON may be hand-edited, the
assets may be huge, and a path may try to point outside its directory. Every
check here runs in CI, and anything reported at ``error`` level fails the build.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from . import svg
from .config import ASSETS_DIRNAME, EXPERIMENT_FILENAME, Limits
from .indexer import iter_experiment_dirs
from .schema import SCHEMA_VERSION, Experiment

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"


@dataclass(slots=True)
class Issue:
    level: str
    where: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.level == LEVEL_ERROR

    def __str__(self) -> str:
        return f"[{self.level}] {self.where}: {self.message}"


def validate_tree(root: Path, *, limits: Limits | None = None, strict: bool = False) -> list[Issue]:
    """Validate every experiment under ``root``, plus cross-experiment rules."""
    limits = limits or Limits()
    issues: list[Issue] = []
    directories = iter_experiment_dirs(root)

    if not directories and root.exists():
        issues.append(Issue(LEVEL_WARNING, str(root), "no experiments found"))

    seen: dict[str, Path] = {}
    for directory in directories:
        experiment, dir_issues = validate_experiment(directory, limits=limits, strict=strict)
        issues.extend(dir_issues)
        if experiment is None:
            continue
        if experiment.id in seen:
            issues.append(
                Issue(
                    LEVEL_ERROR,
                    directory.name,
                    f"duplicate experiment id {experiment.id!r}, already used by "
                    f"{seen[experiment.id].name}",
                )
            )
        seen[experiment.id] = directory

    if strict:
        issues = [Issue(LEVEL_ERROR, i.where, i.message) if not i.is_error else i for i in issues]
    return issues


def validate_experiment(
    directory: Path, *, limits: Limits | None = None, strict: bool = False
) -> tuple[Experiment | None, list[Issue]]:
    limits = limits or Limits()
    where = directory.name
    issues: list[Issue] = []
    manifest = directory / EXPERIMENT_FILENAME

    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, [Issue(LEVEL_ERROR, where, f"cannot read {EXPERIMENT_FILENAME}: {exc}")]
    except json.JSONDecodeError as exc:
        return None, [Issue(LEVEL_ERROR, where, f"{EXPERIMENT_FILENAME} is not valid JSON: {exc}")]

    try:
        experiment = Experiment.model_validate(raw)
    except ValidationError as exc:
        return None, [
            Issue(LEVEL_ERROR, where, f"{_loc(error)}: {error['msg']}") for error in exc.errors()
        ]

    if experiment.id != directory.name:
        issues.append(
            Issue(LEVEL_ERROR, where, f"id {experiment.id!r} does not match its directory name")
        )
    if experiment.schema_version != SCHEMA_VERSION:
        issues.append(
            Issue(
                LEVEL_ERROR,
                where,
                f"schema_version {experiment.schema_version} is not supported "
                f"(this tool writes version {SCHEMA_VERSION})",
            )
        )
    if not experiment.runs:
        issues.append(Issue(LEVEL_ERROR, where, "experiment has no runs"))

    issues.extend(_check_assets(directory, experiment, limits, strict))
    issues.extend(_check_view(directory.name, experiment))
    return experiment, issues


def _check_assets(
    directory: Path, experiment: Experiment, limits: Limits, strict: bool
) -> list[Issue]:
    issues: list[Issue] = []
    referenced: set[Path] = set()

    paths = [("prompt.file", experiment.prompt.file)] if experiment.prompt.file else []
    for run in experiment.runs:
        for output in run.outputs:
            path = getattr(output, "path", None)
            if path:
                paths.append((f"run {run.id}", path))

    for where_detail, relative in paths:
        target = (directory / relative).resolve()
        try:
            target.relative_to(directory.resolve())
        except ValueError:
            issues.append(
                Issue(
                    LEVEL_ERROR,
                    directory.name,
                    f"{where_detail} references {relative!r} outside the experiment directory",
                )
            )
            continue
        if not target.is_file():
            issues.append(
                Issue(
                    LEVEL_ERROR,
                    directory.name,
                    f"{where_detail} references missing {relative!r}",
                )
            )
            continue
        referenced.add(target)
        size = target.stat().st_size
        if size > limits.max_asset_bytes:
            issues.append(
                Issue(
                    LEVEL_ERROR,
                    directory.name,
                    f"{relative} is {_size(size)}, over the "
                    f"{_size(limits.max_asset_bytes)} per-asset limit",
                )
            )

    for run in experiment.runs:
        for output in run.outputs:
            if output.kind == "image":
                issues.extend(_check_image(directory, output.path))
            elif output.kind == "svg":
                issues.extend(_check_svg(directory, output.path))

    assets_dir = directory / ASSETS_DIRNAME
    if assets_dir.is_dir():
        for asset in sorted(assets_dir.rglob("*")):
            if asset.is_file() and asset.resolve() not in referenced:
                issues.append(
                    Issue(
                        LEVEL_WARNING,
                        directory.name,
                        f"{ASSETS_DIRNAME}/{asset.name} is not referenced by any run",
                    )
                )

    total = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
    if total > limits.max_experiment_bytes:
        issues.append(
            Issue(
                LEVEL_ERROR,
                directory.name,
                f"experiment is {_size(total)}, over the "
                f"{_size(limits.max_experiment_bytes)} budget — drop a few samples "
                "or shrink the images",
            )
        )
    return issues


def _check_image(directory: Path, relative: str) -> list[Issue]:
    target = directory / relative
    if not target.is_file():
        return []
    try:
        with Image.open(io.BytesIO(target.read_bytes())) as image:
            image.verify()
    except Exception as exc:  # noqa: BLE001 — any failure means it will not render
        return [Issue(LEVEL_ERROR, directory.name, f"{relative} is not a readable image: {exc}")]
    return []


def _check_svg(directory: Path, relative: str) -> list[Issue]:
    """Re-run the write-time rules, so a hand-edited asset fails review.

    An `.svg` in the repository is a live same-origin document when opened
    directly, which makes this the one asset check that is about safety rather
    than about rendering.
    """
    target = directory / relative
    if not target.is_file():
        return []
    data = target.read_bytes()
    try:
        found = svg.findings(data)
    except svg.SvgError as exc:
        return [Issue(LEVEL_ERROR, directory.name, f"{relative} is not a usable SVG: {exc}")]
    if found:
        return [
            Issue(
                LEVEL_ERROR,
                directory.name,
                f"{relative} contains {', '.join(found)} — re-run `compaire run` "
                "instead of editing the asset by hand",
            )
        ]
    return []


def _check_view(where: str, experiment: Experiment) -> list[Issue]:
    """Catch experiments whose chosen view has nothing to show."""
    kinds = {output.kind for run in experiment.runs for output in run.outputs}
    successful = [run for run in experiment.runs if run.status == "ok"]

    # Both views render through an <img>, which is as happy with a drawing as
    # with a photo.
    if experiment.view in ("gallery", "slider") and not kinds & {"image", "svg"}:
        return [
            Issue(
                LEVEL_ERROR,
                where,
                f"view {experiment.view!r} needs image or svg outputs but the "
                "experiment has none",
            )
        ]
    if experiment.view == "html" and "html" not in kinds:
        return [
            Issue(LEVEL_ERROR, where, "view 'html' needs html outputs but the experiment has none")
        ]
    if experiment.view == "svg" and "svg" not in kinds:
        return [
            Issue(LEVEL_ERROR, where, "view 'svg' needs svg outputs but the experiment has none")
        ]
    if experiment.view == "slider" and len(successful) < 2:
        return [
            Issue(LEVEL_WARNING, where, "view 'slider' compares two results but only one succeeded")
        ]
    if not successful:
        return [Issue(LEVEL_WARNING, where, "every run failed")]
    return []


def _loc(error: dict) -> str:
    return ".".join(str(part) for part in error.get("loc", ())) or "experiment"


def _size(value: float) -> str:
    """Human-readable bytes. A budget message that reads '0.0 MB over 0.0 MB'
    tells the contributor nothing, so scale the unit to the number."""
    if value < 1024:
        return f"{value:.0f} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value / (1024 * 1024):.1f} MB"
