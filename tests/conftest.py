from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from compaire.schema import Experiment, ImageOutput, PromptSpec, Run, TextOutput, Usage


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the model-catalog cache out of the developer's real cache directory.

    Without this a test that fetches the catalog silently reads whatever the
    machine happens to have cached, and passes or fails accordingly.
    """
    monkeypatch.setattr(
        "compaire.openrouter.cache_dir", lambda: tmp_path_factory.mktemp("cache")
    )


@pytest.fixture
def sample_experiment() -> Experiment:
    return Experiment(
        id="demo",
        title="Demo",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        view="table",
        prompt=PromptSpec(text="hello"),
        runs=[
            Run(
                id="a-b__0",
                model="a/b",
                usage=Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3, cost=0.5),
                outputs=[TextOutput(text="hi")],
            ),
            Run(id="c-d__0", model="c/d", status="error", error="boom"),
        ],
    )


@pytest.fixture
def written_experiment(tmp_path: Path, sample_experiment: Experiment) -> Path:
    """A valid experiment directory on disk, ready to be broken by a test."""
    directory = tmp_path / "demo"
    (directory / "assets").mkdir(parents=True)
    (directory / "assets" / "img.webp").write_bytes(_tiny_webp())
    sample_experiment.runs[0].outputs.append(
        ImageOutput(path="assets/img.webp", width=4, height=4)
    )
    (directory / "experiment.json").write_text(
        sample_experiment.model_dump_json(indent=2), encoding="utf-8"
    )
    return directory


def _tiny_webp() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buffer, format="WEBP")
    return buffer.getvalue()
