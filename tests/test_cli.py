"""End-to-end CLI runs against the mock provider."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from compaire.cli import app, render_models_file
from compaire.openrouter import ModelInfo

runner = CliRunner()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway checkout so runs never touch the real experiments/."""
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def invoke(*args: str):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output + str(result.exception)
    return result


def test_run_writes_a_complete_experiment(repo: Path) -> None:
    invoke(
        "run",
        "--provider", "mock",
        "-p", "Compare these models",
        "-m", "mock/writer",
        "-m", "mock/painter",
        "--title", "My Comparison",
        "--author", "Tester",
        "--tag", "demo",
        "-y",
    )
    directory = repo / "experiments" / "my-comparison"
    payload = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))

    assert payload["id"] == "my-comparison"
    assert payload["author"] == {"name": "Tester", "github": None, "url": None}
    assert [run["model"] for run in payload["runs"]] == ["mock/writer", "mock/painter"]
    assert (directory / "prompt.txt").is_file()
    assert (directory / "spec.toml").is_file()
    assert (repo / "experiments" / "index.json").is_file()


def test_run_is_validated_and_indexed(repo: Path) -> None:
    invoke("run", "--provider", "mock", "-p", "hi", "-m", "mock/writer", "--title", "T", "-y")
    invoke("validate", "--strict")
    invoke("index", "--check")


def test_gallery_run_produces_images(repo: Path) -> None:
    invoke(
        "run",
        "--provider", "mock",
        "--modality", "image",
        "--view", "gallery",
        "-p", "a fox",
        "-m", "mock/painter",
        "--title", "Foxes",
        "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "foxes" / "experiment.json").read_text(encoding="utf-8")
    )
    image = payload["runs"][0]["outputs"][0]
    assert image["kind"] == "image"
    assert (repo / "experiments" / "foxes" / image["path"]).is_file()


def test_html_run_extracts_pages(repo: Path) -> None:
    invoke(
        "run",
        "--provider", "mock",
        "--view", "html",
        "-p", "a landing page",
        "-m", "mock/writer",
        "--title", "Pages",
        "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "pages" / "experiment.json").read_text(encoding="utf-8")
    )
    assert payload["runs"][0]["outputs"][0]["kind"] == "html"


def test_svg_run_sanitizes_and_records_what_it_removed(repo: Path) -> None:
    invoke(
        "run",
        "--provider", "mock",
        "--view", "svg",
        "-p", "an icon of a lighthouse",
        "-m", "mock/painter",
        "-m", "mock/writer",
        "--title", "Icons",
        "-y",
    )
    directory = repo / "experiments" / "icons"
    payload = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    outputs = {run["model"]: run["outputs"][0] for run in payload["runs"]}

    assert {output["kind"] for output in outputs.values()} == {"svg"}
    assert outputs["mock/painter"]["sanitized"] is False
    # The mock deliberately returns a hostile drawing from this model.
    assert outputs["mock/writer"]["sanitized"] is True
    assert outputs["mock/writer"]["removed"]

    for output in outputs.values():
        stored = (directory / output["path"]).read_text(encoding="utf-8")
        assert "<script" not in stored and "onclick" not in stored

    invoke("validate", "--strict")


def test_reasoning_tokens_reach_the_manifest(repo: Path) -> None:
    invoke(
        "run", "--provider", "mock", "-p", "think hard", "-m", "mock/reasoner",
        "-m", "mock/writer", "--title", "Thinking", "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "thinking" / "experiment.json").read_text(encoding="utf-8")
    )
    usage = {run["model"]: run["usage"] for run in payload["runs"]}

    assert usage["mock/reasoner"]["reasoning_tokens"] > 0
    assert usage["mock/writer"]["reasoning_tokens"] == 0
    assert (
        usage["mock/reasoner"]["total_tokens"]
        == usage["mock/reasoner"]["prompt_tokens"] + usage["mock/reasoner"]["completion_tokens"]
    )


def test_failing_model_is_recorded_not_fatal(repo: Path) -> None:
    invoke(
        "run", "--provider", "mock", "-p", "hi", "-m", "mock/writer", "-m", "mock/fails",
        "--title", "Mixed", "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "mixed" / "experiment.json").read_text(encoding="utf-8")
    )
    statuses = {run["model"]: run["status"] for run in payload["runs"]}
    assert statuses == {"mock/writer": "ok", "mock/fails": "error"}


def test_dry_run_sends_nothing(repo: Path) -> None:
    result = invoke(
        "run", "--provider", "mock", "-p", "hi", "-m", "mock/writer", "--title", "X", "--dry-run"
    )
    assert "Dry run" in result.output
    assert not (repo / "experiments").exists()


def test_relative_out_still_refreshes_the_index(repo: Path) -> None:
    invoke(
        "run", "--provider", "mock", "-p", "hi", "-m", "mock/writer",
        "--id", "custom", "--title", "Custom", "--out", "experiments/custom", "-y",
    )
    index = json.loads((repo / "experiments" / "index.json").read_text(encoding="utf-8"))
    assert [entry["id"] for entry in index["experiments"]] == ["custom"]


def test_spec_round_trip(repo: Path) -> None:
    invoke(
        "run", "--provider", "mock", "-p", "original prompt", "-m", "mock/writer",
        "--title", "First", "--tag", "t1", "-y",
    )
    spec = repo / "experiments" / "first" / "spec.toml"
    invoke(
        "run", "--provider", "mock", "--spec", str(spec),
        "--id", "second", "--title", "Second",
        "--out", str(repo / "experiments" / "second"), "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "second" / "experiment.json").read_text(encoding="utf-8")
    )
    assert payload["prompt"]["text"] == "original prompt"
    assert payload["tags"] == ["t1"]
    assert [run["model"] for run in payload["runs"]] == ["mock/writer"]


def test_explicit_flag_beats_the_spec_even_at_its_default(repo: Path) -> None:
    invoke(
        "run", "--provider", "mock", "--modality", "image", "--view", "gallery",
        "-p", "a fox", "-m", "mock/painter", "--title", "First", "-y",
    )
    spec = repo / "experiments" / "first" / "spec.toml"

    # "table" is also the default for --view, so a naive check would let the
    # spec's "gallery" win here.
    invoke(
        "run", "--provider", "mock", "--spec", str(spec), "--view", "table",
        "--modality", "text", "--id", "second", "--title", "Second",
        "--out", str(repo / "experiments" / "second"), "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "second" / "experiment.json").read_text(encoding="utf-8")
    )
    assert payload["view"] == "table"
    assert payload["modality"] == "text"


def test_spec_supplies_what_the_command_line_omits(repo: Path) -> None:
    invoke(
        "run", "--provider", "mock", "--modality", "image", "--view", "gallery",
        "-p", "a fox", "-m", "mock/painter", "--n", "2", "--title", "First", "-y",
    )
    spec = repo / "experiments" / "first" / "spec.toml"

    invoke(
        "run", "--provider", "mock", "--spec", str(spec), "--id", "second", "--title", "Second",
        "--out", str(repo / "experiments" / "second"), "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "second" / "experiment.json").read_text(encoding="utf-8")
    )
    assert payload["view"] == "gallery"
    assert payload["modality"] == "image"
    assert len(payload["runs"]) == 2


def test_run_without_models_fails_clearly(repo: Path) -> None:
    result = runner.invoke(app, ["run", "--provider", "mock", "-p", "hi"])
    assert result.exit_code == 1
    assert "No models given" in result.output


def test_run_without_a_prompt_fails_clearly(repo: Path) -> None:
    result = runner.invoke(app, ["run", "--provider", "mock", "-m", "mock/writer"])
    assert result.exit_code == 1
    assert "No prompt" in result.output


def test_validate_reports_a_broken_experiment(repo: Path) -> None:
    invoke("run", "--provider", "mock", "-p", "hi", "-m", "mock/writer", "--title", "T", "-y")
    manifest = repo / "experiments" / "t" / "experiment.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["runs"][0]["outputs"][0] = {"kind": "image", "path": "assets/gone.webp"}
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 1


def seed(repo: Path, *models: str, view: str = "table", samples: str = "1") -> Path:
    invoke(
        "run", "--provider", "mock", "-p", "the original prompt",
        "--system", "be terse", "--temperature", "0.3", "--n", samples,
        "--view", view, "--title", "Base", "--author", "First", "-y",
        *[arg for model in (models or ("mock/writer",)) for arg in ("-m", model)],
    )
    return repo / "experiments" / "base"


def manifest(directory: Path) -> dict:
    return json.loads((directory / "experiment.json").read_text(encoding="utf-8"))


def test_extend_appends_a_result_with_its_own_attribution(repo: Path) -> None:
    directory = seed(repo)
    before = manifest(directory)

    invoke(
        "extend", str(directory), "--provider", "mock",
        "-m", "mock/vector", "--author", "Second", "--github", "second", "-y",
    )
    after = manifest(directory)

    assert [run["model"] for run in after["runs"]] == ["mock/writer", "mock/vector"]
    added = after["runs"][-1]
    assert added["author"] == {"name": "Second", "github": "second", "url": None}
    assert added["created_at"] is not None
    # The original result and the experiment's own authorship are untouched.
    assert after["runs"][0] == before["runs"][0]
    assert after["author"]["name"] == "First"
    assert after["updated_at"] is not None
    assert before["updated_at"] is None


def test_extend_inherits_the_prompt_exactly(repo: Path) -> None:
    """A result produced from a different prompt would not be comparable."""
    directory = seed(repo)
    invoke("extend", str(directory), "--provider", "mock", "-m", "mock/vector", "-y")
    after = manifest(directory)

    assert after["prompt"]["text"] == "the original prompt"
    assert after["prompt"]["system"] == "be terse"
    assert after["prompt"]["params"]["temperature"] == 0.3


def test_extend_refuses_a_model_already_present(repo: Path) -> None:
    directory = seed(repo)
    result = runner.invoke(
        app, ["extend", str(directory), "--provider", "mock", "-m", "mock/writer", "-y"]
    )
    assert result.exit_code == 1
    assert "already in this comparison" in result.output
    assert "--replace" in result.output


def test_replace_reruns_a_model_and_leaves_no_orphans(repo: Path) -> None:
    directory = seed(repo, "mock/painter", view="gallery")
    original = {path.name for path in (directory / "assets").iterdir()}

    invoke(
        "extend", str(directory), "--provider", "mock",
        "-m", "mock/painter", "--replace", "--author", "Second", "-y",
    )
    after = manifest(directory)

    assert [run["model"] for run in after["runs"]] == ["mock/painter"]
    assert after["runs"][0]["author"]["name"] == "Second"
    # Deterministic mock output means the asset is reproduced identically here;
    # what matters is that nothing unreferenced is left behind.
    referenced = {
        Path(output["path"]).name
        for run in after["runs"]
        for output in run["outputs"]
        if output.get("path")  # short text outputs are inlined, not stored
    }
    assert {path.name for path in (directory / "assets").iterdir()} == referenced
    assert original  # the seed really did write assets
    invoke("validate", "--strict")


def test_extend_matches_the_existing_sample_count(repo: Path) -> None:
    directory = seed(repo, "mock/writer", samples="3")
    invoke("extend", str(directory), "--provider", "mock", "-m", "mock/vector", "-y")
    after = manifest(directory)
    counts = {model: 0 for model in ("mock/writer", "mock/vector")}
    for run in after["runs"]:
        counts[run["model"]] += 1
    assert counts == {"mock/writer": 3, "mock/vector": 3}


def test_extend_regenerates_the_spec_with_every_model(repo: Path) -> None:
    directory = seed(repo)
    invoke("extend", str(directory), "--provider", "mock", "-m", "mock/vector", "-y")
    spec = (directory / "spec.toml").read_text(encoding="utf-8")
    assert 'models = ["mock/writer", "mock/vector"]' in spec


def test_extend_refreshes_the_index(repo: Path) -> None:
    directory = seed(repo)
    invoke("extend", str(directory), "--provider", "mock", "-m", "mock/vector", "-y")
    invoke("index", "--check")

    entry = json.loads((repo / "experiments" / "index.json").read_text(encoding="utf-8"))
    entry = entry["experiments"][0]
    assert entry["models"] == ["mock/writer", "mock/vector"]
    assert entry["updated_at"] is not None
    assert entry["contributors"] == 1  # the extend above passed no --author


def test_extend_counts_distinct_contributors(repo: Path) -> None:
    directory = seed(repo)
    invoke(
        "extend", str(directory), "--provider", "mock", "-m", "mock/vector",
        "--author", "Second", "-y",
    )
    index = json.loads((repo / "experiments" / "index.json").read_text(encoding="utf-8"))
    assert index["experiments"][0]["contributors"] == 2


def test_extend_dry_run_changes_nothing(repo: Path) -> None:
    directory = seed(repo)
    before = (directory / "experiment.json").read_bytes()
    result = invoke(
        "extend", str(directory), "--provider", "mock", "-m", "mock/vector", "--dry-run"
    )
    assert "Dry run" in result.output
    assert (directory / "experiment.json").read_bytes() == before


def test_extend_needs_a_real_experiment(repo: Path) -> None:
    result = runner.invoke(
        app, ["extend", str(repo / "nope"), "--provider", "mock", "-m", "mock/vector", "-y"]
    )
    assert result.exit_code == 1
    assert "cannot read an experiment" in result.output


def test_extend_needs_models(repo: Path) -> None:
    directory = seed(repo)
    result = runner.invoke(app, ["extend", str(directory), "--provider", "mock", "-y"])
    assert result.exit_code == 1
    assert "No models given" in result.output


def test_extended_experiment_stays_valid(repo: Path) -> None:
    directory = seed(repo)
    invoke(
        "extend", str(directory), "--provider", "mock", "-m", "mock/vector",
        "--author", "Second", "-y",
    )
    invoke("validate", "--strict")


def test_models_command_lists_the_catalog(repo: Path) -> None:
    result = invoke("models", "--provider", "mock")
    assert "mock/writer" in result.output


def test_missing_api_key_is_explained(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = runner.invoke(app, ["run", "-p", "hi", "-m", "openai/gpt-5", "-y"])
    assert result.exit_code == 1
    assert "OPENROUTER_API_KEY" in result.output


def test_dry_run_needs_no_api_key(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pricing a comparison is what you do *before* signing up for a key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("compaire.cli._fetch_models", _no_catalog)

    result = runner.invoke(app, ["run", "-p", "hi", "-m", "openai/gpt-5", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output


def test_browsing_models_needs_no_api_key(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("compaire.cli._fetch_models", _no_catalog)

    result = runner.invoke(app, ["models"])
    assert result.exit_code == 0


async def _no_catalog(*args, **kwargs) -> list:
    """Stand-in for the catalog fetch, so no test reaches the network."""
    return []


def test_models_file_lists_ids_and_explains_exclusions() -> None:
    catalog = [
        ModelInfo(id="a/free-one", name="One", free=True, output_modalities=["text"]),
        ModelInfo(id="b/free-two", name="Two", free=True, output_modalities=["text", "image"]),
        ModelInfo(id="c/sings", name="Sings", free=True, output_modalities=["text", "audio"]),
        ModelInfo(id="openrouter/free", name="Router", free=True, output_modalities=["text"]),
    ]
    rendered = render_models_file(catalog, free=True)
    body = [line for line in rendered.splitlines() if line and not line.startswith("#")]

    assert body == ["a/free-one", "b/free-two"]
    assert "# c/sings — emits audio, which the experiment format cannot store" in rendered
    assert "# openrouter/free — routes to a model of its own choosing" in rendered
    assert "compaire models --free --write" in rendered


def test_models_file_round_trips_into_a_run(repo: Path, tmp_path: Path) -> None:
    """The generated file has to be readable by --models-file, comments and all."""
    path = tmp_path / "free.txt"
    path.write_text(
        render_models_file(
            [
                ModelInfo(id="mock/writer", name="W", free=True, output_modalities=["text"]),
                ModelInfo(id="mock/vector", name="V", free=True, output_modalities=["text"]),
                ModelInfo(id="x/sings", name="S", free=True, output_modalities=["audio"]),
            ],
            free=True,
        ),
        encoding="utf-8",
    )

    invoke(
        "run", "--provider", "mock", "--models-file", str(path),
        "-p", "hi", "--title", "From file", "-y",
    )
    payload = json.loads(
        (repo / "experiments" / "from-file" / "experiment.json").read_text(encoding="utf-8")
    )
    assert [run["model"] for run in payload["runs"]] == ["mock/writer", "mock/vector"]


def fake_openrouter(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    """Drive the real OpenRouterClient over a mock transport.

    Every other CLI test uses --provider mock, which never touches the HTTP
    client at all — so the whole OpenRouter path went unexercised until a
    closed-connection bug shipped.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "a/b",
                            "name": "A B",
                            "pricing": {"prompt": "0", "completion": "0"},
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "choices": [{"message": {"content": "an answer"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            },
        )

    # Swap the transport, not the client: passing a client in would set
    # `_owns_client = False`, which turns aclose() into a no-op and hides the
    # very lifecycle bug this is here to catch. The CLI must build and own the
    # client exactly as it does in production.
    real_client = httpx.AsyncClient

    def mock_transport_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("compaire.openrouter.httpx.AsyncClient", mock_transport_client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")


def test_a_real_run_survives_the_catalog_fetch(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the catalog fetch used to close the client the run needed.

    Pricing and calling happen in one command; if they do not share one live
    connection pool, every model comes back as "client has been closed".
    """
    calls: list[str] = []
    fake_openrouter(monkeypatch, calls)

    invoke("run", "-p", "hi", "-m", "a/b", "--title", "Real", "-y")

    payload = json.loads(
        (repo / "experiments" / "real" / "experiment.json").read_text(encoding="utf-8")
    )
    assert [run["status"] for run in payload["runs"]] == ["ok"]
    assert payload["runs"][0]["outputs"][0]["text"] == "an answer"
    assert payload["runs"][0]["model_name"] == "A B"  # the catalog was read too
    assert [path.rsplit("/", 1)[-1] for path in calls] == ["models", "completions"]


def test_a_real_extend_survives_the_catalog_fetch(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(repo)
    calls: list[str] = []
    fake_openrouter(monkeypatch, calls)

    invoke("extend", str(repo / "experiments" / "base"), "-m", "a/b", "-y")

    payload = manifest(repo / "experiments" / "base")
    added = payload["runs"][-1]
    assert (added["model"], added["status"]) == ("a/b", "ok")


def test_env_file_supplies_the_key(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("compaire.cli._fetch_models", _no_catalog)
    (repo / ".env").write_text("OPENROUTER_API_KEY=sk-or-from-file", encoding="utf-8")

    # Without a key this run stops before it calls anything; getting as far as
    # the provider proves the file was read.
    result = runner.invoke(
        app, ["--env-file", str(repo / ".env"), "run", "-p", "hi", "-m", "a/b", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "OPENROUTER_API_KEY" not in result.output


def test_env_file_is_found_without_being_named(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("compaire.cli._fetch_models", _no_catalog)
    (repo / ".env").write_text("OPENROUTER_API_KEY=sk-or-auto", encoding="utf-8")

    result = runner.invoke(app, ["run", "-p", "hi", "-m", "a/b", "-y", "--provider", "mock"])
    assert result.exit_code == 0
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-auto"


def test_a_named_env_file_must_exist(repo: Path) -> None:
    result = runner.invoke(app, ["--env-file", str(repo / "gone.env"), "models"])
    assert result.exit_code == 1
    assert "no env file" in result.output


def test_write_reports_where_it_went(repo: Path, tmp_path: Path) -> None:
    result = invoke("models", "--provider", "mock", "--free", "--write", str(tmp_path / "f.txt"))
    assert "Wrote" in result.output
    assert (tmp_path / "f.txt").is_file()
