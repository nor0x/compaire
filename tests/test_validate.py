from __future__ import annotations

import json
from pathlib import Path

from compaire.config import Limits
from compaire.validate import validate_experiment, validate_tree


def errors(issues) -> list[str]:
    return [issue.message for issue in issues if issue.is_error]


def edit(directory: Path, mutate) -> None:
    path = directory / "experiment.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_a_good_experiment_passes(written_experiment: Path) -> None:
    experiment, issues = validate_experiment(written_experiment)
    assert experiment is not None
    assert errors(issues) == []


def test_missing_asset_is_an_error(written_experiment: Path) -> None:
    (written_experiment / "assets" / "img.webp").unlink()
    _, issues = validate_experiment(written_experiment)
    assert any("missing" in message for message in errors(issues))


def test_id_must_match_the_directory(written_experiment: Path) -> None:
    edit(written_experiment, lambda payload: payload.update(id="something-else"))
    _, issues = validate_experiment(written_experiment)
    assert any("directory name" in message for message in errors(issues))


def test_outputs_must_state_their_kind(written_experiment: Path) -> None:
    """The generated TypeScript narrows on `kind`, so it may never be missing."""

    def drop_kind(payload: dict) -> None:
        payload["runs"][0]["outputs"][0].pop("kind")

    edit(written_experiment, drop_kind)
    experiment, issues = validate_experiment(written_experiment)
    assert experiment is None
    assert errors(issues)


def test_path_traversal_is_rejected(written_experiment: Path) -> None:
    def escape(payload: dict) -> None:
        payload["runs"][0]["outputs"][1]["path"] = "../../secrets.txt"

    edit(written_experiment, escape)
    _, issues = validate_experiment(written_experiment)
    # The schema itself refuses the path, so the run never reaches the filesystem.
    assert errors(issues)


def test_unknown_schema_version_is_rejected(written_experiment: Path) -> None:
    edit(written_experiment, lambda payload: payload.update(schema_version=99))
    _, issues = validate_experiment(written_experiment)
    assert any("schema_version" in message for message in errors(issues))


def test_oversized_asset_is_rejected(written_experiment: Path) -> None:
    (written_experiment / "assets" / "img.webp").write_bytes(b"x" * 2048)
    _, issues = validate_experiment(written_experiment, limits=Limits(max_asset_bytes=1024))
    assert any("per-asset limit" in message for message in errors(issues))


def test_oversized_experiment_is_rejected(written_experiment: Path) -> None:
    _, issues = validate_experiment(
        written_experiment, limits=Limits(max_experiment_bytes=10, max_asset_bytes=10_000)
    )
    assert any("budget" in message for message in errors(issues))


def test_unreferenced_asset_warns_and_fails_under_strict(written_experiment: Path) -> None:
    (written_experiment / "assets" / "orphan.md").write_text("stray", encoding="utf-8")
    _, issues = validate_experiment(written_experiment)
    assert any("not referenced" in issue.message and not issue.is_error for issue in issues)

    strict = validate_tree(written_experiment.parent, strict=True)
    assert any("not referenced" in message for message in errors(strict))


def test_gallery_view_needs_images(written_experiment: Path) -> None:
    def to_gallery(payload: dict) -> None:
        payload["view"] = "gallery"
        payload["runs"][0]["outputs"] = [payload["runs"][0]["outputs"][0]]

    edit(written_experiment, to_gallery)
    _, issues = validate_experiment(written_experiment)
    assert any("needs image or svg outputs" in message for message in errors(issues))


CLEAN_SVG = b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 8 8'><rect/></svg>"


def add_svg(directory: Path, data: bytes = CLEAN_SVG, *, view: str = "svg") -> None:
    (directory / "assets" / "drawing.svg").write_bytes(data)

    def mutate(payload: dict) -> None:
        payload["view"] = view
        payload["runs"][0]["outputs"] = [{"kind": "svg", "path": "assets/drawing.svg"}]

    edit(directory, mutate)


def test_a_clean_svg_passes(written_experiment: Path) -> None:
    (written_experiment / "assets" / "img.webp").unlink()
    add_svg(written_experiment)
    _, issues = validate_experiment(written_experiment)
    assert errors(issues) == []


def test_hand_edited_svg_is_rejected(written_experiment: Path) -> None:
    """The whole point of re-checking: a PR cannot smuggle a handler back in."""
    (written_experiment / "assets" / "img.webp").unlink()
    add_svg(written_experiment, CLEAN_SVG.replace(b"<rect/>", b'<rect onload="steal()"/>'))
    _, issues = validate_experiment(written_experiment)
    assert any("onload" in message for message in errors(issues))


def test_malformed_svg_is_rejected(written_experiment: Path) -> None:
    (written_experiment / "assets" / "img.webp").unlink()
    add_svg(written_experiment, b"<svg>never closed")
    _, issues = validate_experiment(written_experiment)
    assert any("not a usable SVG" in message for message in errors(issues))


def test_svg_view_without_svg_outputs_is_rejected(written_experiment: Path) -> None:
    edit(written_experiment, lambda payload: payload.update(view="svg"))
    _, issues = validate_experiment(written_experiment)
    assert any("needs svg outputs" in message for message in errors(issues))


def test_gallery_accepts_drawings(written_experiment: Path) -> None:
    (written_experiment / "assets" / "img.webp").unlink()
    add_svg(written_experiment, view="gallery")
    _, issues = validate_experiment(written_experiment)
    assert errors(issues) == []


def test_broken_image_bytes_are_rejected(written_experiment: Path) -> None:
    (written_experiment / "assets" / "img.webp").write_bytes(b"definitely not an image")
    _, issues = validate_experiment(written_experiment)
    assert any("not a readable image" in message for message in errors(issues))


def test_malformed_json_is_reported_once(written_experiment: Path) -> None:
    (written_experiment / "experiment.json").write_text("{ nope", encoding="utf-8")
    experiment, issues = validate_experiment(written_experiment)
    assert experiment is None
    assert len(errors(issues)) == 1


def test_duplicate_ids_across_experiments(written_experiment: Path, tmp_path: Path) -> None:
    twin = tmp_path / "twin"
    twin.mkdir()
    payload = json.loads((written_experiment / "experiment.json").read_text(encoding="utf-8"))
    payload["runs"][0]["outputs"] = [payload["runs"][0]["outputs"][0]]
    (twin / "experiment.json").write_text(json.dumps(payload), encoding="utf-8")

    issues = validate_tree(tmp_path)
    assert any("duplicate experiment id" in message for message in errors(issues))
