from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from compaire.openrouter import ImageBlob, ModelResult
from compaire.runner import RunOutcome, RunPlan
from compaire.schema import INLINE_TEXT_LIMIT, Author, PromptParams
from compaire.writer import (
    AssetStore,
    build_experiment,
    build_outputs,
    build_run,
    encode_webp,
    extract_html,
    extract_svg,
    prune_unreferenced,
    render_spec,
    slugify,
    unique_dir,
    write_experiment,
)


def png(color: tuple[int, int, int] = (200, 40, 40), size: int = 8) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buffer, format="PNG")
    return buffer.getvalue()


def outcome(text: str | None = None, images: list[bytes] | None = None) -> RunOutcome:
    return RunOutcome(
        id="a-b__0",
        model="a/b",
        sample_index=0,
        result=ModelResult(text=text, images=[ImageBlob(data) for data in images or []]),
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Haiku Shootout!", "haiku-shootout"),
        ("  spaced   out  ", "spaced-out"),
        ("Ünïcodé Títle", "unicode-title"),
        ("!!!", "experiment"),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected


def test_unique_dir_avoids_collisions(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo-2").mkdir()
    path, slug = unique_dir(tmp_path, "demo")
    assert (path, slug) == (tmp_path / "demo-3", "demo-3")


def test_extract_html_from_fence() -> None:
    assert extract_html("sure!\n```html\n<h1>hi</h1>\n```\n") == "<h1>hi</h1>"


def test_extract_html_from_bare_document() -> None:
    assert extract_html("<!doctype html><html><body>x</body></html>").startswith("<!doctype")


def test_extract_html_returns_none_for_prose() -> None:
    assert extract_html("just some prose about <html> tags") is None


def test_assets_are_deduplicated_by_content(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / "assets")
    first = store.put(b"same bytes", ".md")
    second = store.put(b"same bytes", ".md")
    assert first == second
    assert len(list((tmp_path / "assets").iterdir())) == 1


def test_encode_webp_reports_dimensions() -> None:
    data, width, height, converted = encode_webp(png(size=12))
    assert (width, height, converted) == (12, 12, True)
    assert data[:4] == b"RIFF"


def test_encode_webp_passes_through_unreadable_bytes() -> None:
    data, width, height, converted = encode_webp(b"not an image")
    assert (data, width, height, converted) == (b"not an image", 0, 0, False)


def test_short_text_is_inlined(tmp_path: Path) -> None:
    outputs = build_outputs(outcome(text="brief"), "table", AssetStore(tmp_path / "assets"))
    assert outputs[0].kind == "text"
    assert outputs[0].text == "brief"
    assert outputs[0].path is None


def test_long_text_becomes_an_asset(tmp_path: Path) -> None:
    outputs = build_outputs(
        outcome(text="x" * (INLINE_TEXT_LIMIT + 1)), "table", AssetStore(tmp_path / "assets")
    )
    assert outputs[0].text is None
    assert outputs[0].path.endswith(".md")
    assert (tmp_path / outputs[0].path).is_file()


def test_html_view_extracts_a_page(tmp_path: Path) -> None:
    outputs = build_outputs(
        outcome(text="```html\n<!doctype html><p>hi</p>\n```"),
        "html",
        AssetStore(tmp_path / "assets"),
    )
    assert [o.kind for o in outputs] == ["html"]
    assert (tmp_path / outputs[0].path).read_text(encoding="utf-8").startswith("<!doctype")


def test_html_view_keeps_prose_as_text(tmp_path: Path) -> None:
    outputs = build_outputs(outcome(text="I cannot do that"), "html", AssetStore(tmp_path / "a"))
    assert [o.kind for o in outputs] == ["text"]


SVG = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 8 8' width='8' height='8'><rect/></svg>"


@pytest.mark.parametrize(
    "answer",
    [
        f"```svg\n{SVG}\n```",
        f"```xml\n{SVG}\n```",
        SVG,
        f"Here you go:\n\n{SVG}\n\nLet me know what you think!",
    ],
)
def test_extract_svg_finds_the_drawing(answer: str) -> None:
    extracted = extract_svg(answer)
    assert extracted is not None
    assert extracted.startswith("<svg") and extracted.endswith("</svg>")


def test_extract_svg_ignores_prose_about_svg() -> None:
    assert extract_svg("You should use an <svg> element for that.") is None


def test_svg_view_stores_a_sanitized_drawing(tmp_path: Path) -> None:
    dirty = SVG.replace("<rect/>", '<rect onclick="steal()"/><script>bad()</script>')
    outputs = build_outputs(
        outcome(text=f"```svg\n{dirty}\n```"), "svg", AssetStore(tmp_path / "assets")
    )
    assert [o.kind for o in outputs] == ["svg"]

    drawing = outputs[0]
    assert drawing.sanitized is True
    assert sorted(drawing.removed) == ["<script>", "onclick"]
    assert (drawing.width, drawing.height) == (8, 8)

    stored = (tmp_path / drawing.path).read_text(encoding="utf-8")
    assert "script" not in stored and "onclick" not in stored


def test_clean_svg_is_not_flagged(tmp_path: Path) -> None:
    outputs = build_outputs(outcome(text=SVG), "svg", AssetStore(tmp_path / "assets"))
    assert outputs[0].sanitized is False
    assert outputs[0].removed == []


def test_svg_view_keeps_prose_as_text(tmp_path: Path) -> None:
    outputs = build_outputs(outcome(text="I cannot draw that"), "svg", AssetStore(tmp_path / "a"))
    assert [o.kind for o in outputs] == ["text"]


def test_svg_image_blob_skips_webp_conversion(tmp_path: Path) -> None:
    """Pillow cannot read SVG, and re-encoding would lose the source."""
    result = ModelResult(images=[ImageBlob(SVG.encode(), media_type="image/svg+xml")])
    outputs = build_outputs(
        RunOutcome(id="a-b__0", model="a/b", sample_index=0, result=result),
        "gallery",
        AssetStore(tmp_path / "assets"),
    )
    assert [o.kind for o in outputs] == ["svg"]
    assert outputs[0].path.endswith(".svg")


def test_unusable_svg_blob_falls_back_to_an_image(tmp_path: Path) -> None:
    result = ModelResult(images=[ImageBlob(b"<not-svg/>", media_type="image/svg+xml")])
    outputs = build_outputs(
        RunOutcome(id="a-b__0", model="a/b", sample_index=0, result=result),
        "gallery",
        AssetStore(tmp_path / "assets"),
    )
    assert [o.kind for o in outputs] == ["image"]


def test_images_are_converted_to_webp(tmp_path: Path) -> None:
    outputs = build_outputs(outcome(images=[png()]), "gallery", AssetStore(tmp_path / "assets"))
    image = outputs[0]
    assert image.kind == "image"
    assert image.path.endswith(".webp")
    assert (image.width, image.height) == (8, 8)


def test_failed_run_produces_no_outputs(tmp_path: Path) -> None:
    failed = RunOutcome(id="x", model="a/b", sample_index=0, status="error", error="nope")
    assert build_outputs(failed, "table", AssetStore(tmp_path / "assets")) == []


def test_write_experiment_produces_a_reproducible_directory(tmp_path: Path) -> None:
    plan = RunPlan(
        prompt="compare these",
        models=["a/b"],
        params=PromptParams(temperature=0.2),
        samples=2,
    )
    experiment = build_experiment(
        experiment_id="demo",
        title="Demo",
        plan=plan,
        outcomes=[outcome(text="hello")],
        directory=tmp_path / "demo",
        view="table",
    )
    write_experiment(experiment, tmp_path / "demo")

    assert (tmp_path / "demo" / "experiment.json").is_file()
    assert (tmp_path / "demo" / "prompt.txt").read_text(encoding="utf-8") == "compare these"

    spec = render_spec(experiment)
    assert 'models = ["a/b"]' in spec
    assert "temperature = 0.2" in spec


def test_spec_describes_the_experiment_not_the_invocation(tmp_path: Path) -> None:
    """A spec taken from the RunPlan would miss whatever a later contributor added."""
    plan = RunPlan(prompt="p", models=["a/b"], samples=2)
    experiment = build_experiment(
        experiment_id="demo",
        title="Demo",
        plan=plan,
        outcomes=[outcome(text="one"), outcome(text="two")],
        directory=tmp_path / "demo",
        view="table",
    )
    experiment.runs[1].model = "c/d"  # as if someone extended the comparison

    spec = render_spec(experiment)
    assert 'models = ["a/b", "c/d"]' in spec
    assert "samples = 1" in spec  # one run each now, not the plan's 2


def test_prune_unreferenced_removes_only_orphans(tmp_path: Path) -> None:
    plan = RunPlan(prompt="p", models=["a/b"])
    experiment = build_experiment(
        experiment_id="demo",
        title="Demo",
        plan=plan,
        outcomes=[outcome(images=[png()])],
        directory=tmp_path / "demo",
        view="gallery",
    )
    kept = (tmp_path / "demo" / experiment.runs[0].outputs[0].path)
    orphan = tmp_path / "demo" / "assets" / "stale.webp"
    orphan.write_bytes(png())

    removed = prune_unreferenced(tmp_path / "demo", experiment)

    assert removed == [orphan]
    assert not orphan.exists()
    assert kept.is_file()


def test_prune_is_a_no_op_without_assets(tmp_path: Path) -> None:
    plan = RunPlan(prompt="p", models=["a/b"])
    experiment = build_experiment(
        experiment_id="demo",
        title="Demo",
        plan=plan,
        outcomes=[outcome(text="short")],
        directory=tmp_path / "demo",
        view="table",
    )
    assert prune_unreferenced(tmp_path / "demo", experiment) == []


def test_runs_carry_their_own_attribution(tmp_path: Path) -> None:
    author = Author(name="Ada", github="ada")
    store = AssetStore(tmp_path / "assets")
    when = datetime(2026, 5, 1, tzinfo=UTC)

    run = build_run(outcome(text="hi"), "table", store, author=author, created_at=when)

    assert run.author == author
    assert run.created_at == when


def test_spec_escapes_quotes() -> None:
    plan = RunPlan(prompt='say "hi"', models=["a/b"])
    experiment = build_experiment(
        experiment_id="demo",
        title='A "quoted" title',
        plan=plan,
        outcomes=[],
        directory=Path("."),
        view="table",
    )
    assert 'title = "A \\"quoted\\" title"' in render_spec(experiment)
