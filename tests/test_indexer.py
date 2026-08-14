from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from compaire import indexer
from compaire.schema import (
    Author,
    Experiment,
    ImageOutput,
    PromptSpec,
    Run,
    SvgOutput,
    TextOutput,
    Usage,
)


def write(root: Path, experiment: Experiment) -> Path:
    directory = root / experiment.id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "experiment.json").write_text(
        experiment.model_dump_json(indent=2), encoding="utf-8"
    )
    return directory


def make(experiment_id: str, *, day: int = 1, view: str = "gallery") -> Experiment:
    return Experiment(
        id=experiment_id,
        title=experiment_id.title(),
        created_at=datetime(2026, 1, day, tzinfo=UTC),
        view=view,
        prompt=PromptSpec(text="p"),
        runs=[
            Run(
                id="a__0",
                model="a/b",
                usage=Usage(cost=0.25),
                outputs=[TextOutput(text="t"), ImageOutput(path="assets/x.webp")],
            ),
            Run(id="a__1", model="a/b", usage=Usage(cost=0.25), outputs=[TextOutput(text="t2")]),
        ],
    )


def test_entry_summarizes_the_experiment(tmp_path: Path) -> None:
    entry = indexer.to_entry(make("demo"))
    assert entry.models == ["a/b"]  # deduplicated across samples
    assert entry.run_count == 2
    assert entry.thumb == "assets/x.webp"
    assert entry.total_cost == 0.5


def test_a_drawing_can_be_the_card_thumbnail() -> None:
    experiment = make("drawings", view="svg")
    experiment.runs[0].outputs = [SvgOutput(path="assets/icon.svg")]
    assert indexer.to_entry(experiment).thumb == "assets/icon.svg"


def test_index_is_newest_first(tmp_path: Path) -> None:
    write(tmp_path, make("older", day=1))
    write(tmp_path, make("newer", day=5))
    index = indexer.build(tmp_path)
    assert [entry.id for entry in index.experiments] == ["newer", "older"]


def test_a_recently_extended_experiment_sorts_first(tmp_path: Path) -> None:
    """Someone adding their model is news, so activity beats creation date."""
    extended = make("extended", day=1)
    extended.updated_at = datetime(2026, 6, 1, tzinfo=UTC)
    write(tmp_path, extended)
    write(tmp_path, make("newer", day=5))

    index = indexer.build(tmp_path)
    assert [entry.id for entry in index.experiments] == ["extended", "newer"]


def test_entry_reports_contributors_and_update_time() -> None:
    experiment = make("shared")
    experiment.author = Author(name="First")
    experiment.updated_at = datetime(2026, 6, 1, tzinfo=UTC)
    experiment.runs[1].author = Author(name="Second")

    entry = indexer.to_entry(experiment)
    assert entry.contributors == 2
    assert entry.updated_at == datetime(2026, 6, 1, tzinfo=UTC)


def test_entry_contributors_is_at_least_one() -> None:
    """Anonymous experiments still count as one contribution."""
    assert indexer.to_entry(make("anon")).contributors == 1


def test_write_then_check_is_clean(tmp_path: Path) -> None:
    write(tmp_path, make("demo"))
    indexer.write(tmp_path)
    assert not indexer.is_stale(tmp_path)


def test_new_experiment_makes_the_index_stale(tmp_path: Path) -> None:
    write(tmp_path, make("demo"))
    indexer.write(tmp_path)
    write(tmp_path, make("second", day=2))
    assert indexer.is_stale(tmp_path)


def test_staleness_ignores_the_generation_timestamp(tmp_path: Path) -> None:
    write(tmp_path, make("demo"))
    indexer.write(tmp_path, generated_at=datetime(2020, 1, 1, tzinfo=UTC))
    assert not indexer.is_stale(tmp_path)


def test_missing_index_is_stale(tmp_path: Path) -> None:
    assert indexer.is_stale(tmp_path)


def test_directories_without_a_manifest_are_ignored(tmp_path: Path) -> None:
    write(tmp_path, make("demo"))
    (tmp_path / "not-an-experiment").mkdir()
    assert [d.name for d in indexer.iter_experiment_dirs(tmp_path)] == ["demo"]


def test_index_json_is_readable(tmp_path: Path) -> None:
    write(tmp_path, make("demo"))
    path = indexer.write(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["experiments"][0]["id"] == "demo"
    assert payload["schema_version"] == 1
