"""Key resolution and .env loading."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from compaire.config import (
    API_KEY_ENV,
    ConfigError,
    api_key,
    autoload_env,
    load_env_file,
    parse_env_file,
)


def test_parse_handles_what_a_key_file_actually_contains() -> None:
    parsed = parse_env_file(
        "\n".join(
            [
                "# a comment",
                "",
                "export OPENROUTER_API_KEY=sk-or-plain",
                'QUOTED="double"',
                "SINGLE='single'",
                "  SPACED  =  padded  ",
                "EMPTY=",
                "not a pair",
            ]
        )
    )
    assert parsed == {
        "OPENROUTER_API_KEY": "sk-or-plain",
        "QUOTED": "double",
        "SINGLE": "single",
        "SPACED": "padded",
        "EMPTY": "",
    }


def test_values_containing_equals_survive() -> None:
    assert parse_env_file("TOKEN=abc=def==")["TOKEN"] == "abc=def=="


def test_load_sets_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    path = tmp_path / ".env"
    path.write_text(f"{API_KEY_ENV}=sk-or-from-file", encoding="utf-8")

    assert load_env_file(path) == [API_KEY_ENV]
    assert api_key() == "sk-or-from-file"


def test_the_real_environment_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit export should not be silently overridden by a file."""
    monkeypatch.setenv(API_KEY_ENV, "sk-or-from-shell")
    path = tmp_path / ".env"
    path.write_text(f"{API_KEY_ENV}=sk-or-from-file", encoding="utf-8")

    assert load_env_file(path) == []
    assert api_key() == "sk-or-from-shell"


def test_autoload_finds_the_file_beside_you(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    (tmp_path / ".env").write_text(f"{API_KEY_ENV}=sk-or-here", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert autoload_env() == tmp_path / ".env"
    assert os.environ[API_KEY_ENV] == "sk-or-here"


def test_autoload_finds_the_file_at_the_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contributors run the CLI from wherever they happen to be."""
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text(f"{API_KEY_ENV}=sk-or-root", encoding="utf-8")
    nested = tmp_path / "experiments" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert autoload_env() == tmp_path / ".env"
    assert os.environ[API_KEY_ENV] == "sk-or-root"


def test_autoload_is_fine_with_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert autoload_env() is None


def test_missing_key_explains_every_option(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(ConfigError) as excinfo:
        api_key()

    message = str(excinfo.value)
    assert ".env" in message
    assert "--api-key" in message
    assert "--provider mock" in message


def test_key_is_optional_when_not_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    assert api_key(required=False) is None
