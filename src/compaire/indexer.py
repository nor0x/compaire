"""Build ``experiments/index.json``.

The site's landing page loads this one file instead of every experiment, so it
stays deliberately small: enough to render a card and filter on it, nothing
more.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .config import EXPERIMENT_FILENAME, INDEX_FILENAME
from .schema import Experiment, Index, IndexEntry


def load_experiment(directory: Path) -> Experiment:
    raw = json.loads((directory / EXPERIMENT_FILENAME).read_text(encoding="utf-8"))
    return Experiment.model_validate(raw)


def iter_experiment_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        path for path in root.iterdir() if path.is_dir() and (path / EXPERIMENT_FILENAME).is_file()
    )


def to_entry(experiment: Experiment) -> IndexEntry:
    thumb = next(
        (
            output.path
            for run in experiment.runs
            for output in run.outputs
            if output.kind in ("image", "svg")
        ),
        None,
    )
    cost = experiment.total_cost
    return IndexEntry(
        id=experiment.id,
        title=experiment.title,
        description=experiment.description,
        author=experiment.author,
        created_at=experiment.created_at,
        updated_at=experiment.updated_at,
        view=experiment.view,
        modality=experiment.modality,
        tags=experiment.tags,
        models=experiment.models,
        run_count=len(experiment.runs),
        contributors=len(experiment.contributors) or 1,
        thumb=thumb,
        total_cost=round(cost, 6) if cost else None,
    )


def build(root: Path, *, generated_at: datetime | None = None) -> Index:
    """Newest activity first — a comparison someone just extended is news too."""
    entries = [to_entry(load_experiment(d)) for d in iter_experiment_dirs(root)]
    entries.sort(key=lambda entry: (entry.updated_at or entry.created_at, entry.id), reverse=True)
    return Index(generated_at=generated_at or datetime.now(UTC), experiments=entries)


def render(index: Index) -> str:
    return json.dumps(index.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def write(root: Path, *, generated_at: datetime | None = None) -> Path:
    path = root / INDEX_FILENAME
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(render(build(root, generated_at=generated_at)), encoding="utf-8", newline="\n")
    return path


def is_stale(root: Path) -> bool:
    """Whether the checked-in index still matches the experiments on disk.

    ``generated_at`` is ignored — a timestamp that moves on every CI run would
    make the check useless.
    """
    path = root / INDEX_FILENAME
    if not path.exists():
        return True
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    fresh = json.loads(render(build(root)))
    current.pop("generated_at", None)
    fresh.pop("generated_at", None)
    return current != fresh
