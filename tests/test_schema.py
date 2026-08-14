from __future__ import annotations

import pytest
from pydantic import ValidationError

from compaire.schema import Experiment, ImageOutput, Run, TextOutput


@pytest.mark.parametrize(
    "path",
    [
        "../secrets.txt",
        "/etc/passwd",
        "C:/Windows/system.ini",
        "assets\\win.webp",
        "assets//img.webp",
        "assets/./img.webp",
    ],
)
def test_asset_paths_stay_inside_the_experiment(path: str) -> None:
    with pytest.raises(ValidationError):
        ImageOutput(path=path)


def test_relative_asset_path_is_accepted() -> None:
    assert ImageOutput(path="assets/a1b2c3d4.webp").path == "assets/a1b2c3d4.webp"


@pytest.mark.parametrize("value", ["Upper", "has space", "trailing-", "double--dash", ""])
def test_invalid_experiment_ids_are_rejected(value: str, sample_experiment: Experiment) -> None:
    payload = {**sample_experiment.model_dump(mode="json"), "id": value}
    with pytest.raises(ValidationError):
        Experiment.model_validate(payload)


def test_text_output_needs_exactly_one_source() -> None:
    with pytest.raises(ValidationError):
        TextOutput()
    with pytest.raises(ValidationError):
        TextOutput(text="hi", path="assets/a.md")


def test_failed_run_must_explain_itself() -> None:
    with pytest.raises(ValidationError):
        Run(id="r", model="a/b", status="error")


def test_unknown_fields_are_rejected(sample_experiment: Experiment) -> None:
    payload = sample_experiment.model_dump(mode="json")
    payload["surprise"] = True
    with pytest.raises(ValidationError):
        Experiment.model_validate(payload)


def test_round_trips_through_json(sample_experiment: Experiment) -> None:
    restored = Experiment.model_validate_json(sample_experiment.model_dump_json())
    assert restored == sample_experiment
    assert restored.total_cost == 0.5
