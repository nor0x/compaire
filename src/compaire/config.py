"""Environment, paths and tunable defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

API_BASE = "https://openrouter.ai/api/v1"
API_KEY_ENV = "OPENROUTER_API_KEY"

#: Sent to OpenRouter so runs show up attributed on their dashboard.
APP_URL = "https://github.com/nor0x/compaire"
APP_TITLE = "CompAIre"

DEFAULT_CONCURRENCY = 4
DEFAULT_TIMEOUT_S = 300.0
DEFAULT_MAX_RETRIES = 3

#: Spend above this triggers a confirmation prompt unless --yes is passed.
COST_CONFIRM_THRESHOLD_USD = 1.0

#: Enforced by `compaire validate`, which is what gates pull requests.
MAX_EXPERIMENT_BYTES = 10 * 1024 * 1024
MAX_ASSET_BYTES = 4 * 1024 * 1024

EXPERIMENTS_DIRNAME = "experiments"
INDEX_FILENAME = "index.json"
EXPERIMENT_FILENAME = "experiment.json"
SPEC_FILENAME = "spec.toml"
ASSETS_DIRNAME = "assets"


class ConfigError(RuntimeError):
    """Raised when the CLI cannot proceed without user action."""


def api_key(explicit: str | None = None, *, required: bool = True) -> str | None:
    """The key, or ``None`` when one is not needed and not configured.

    Browsing the model catalog is a public endpoint, so commands that only read
    it pass ``required=False`` rather than demanding a key for nothing.
    """
    key = explicit or os.environ.get(API_KEY_ENV)
    if not key and required:
        raise ConfigError(
            f"No OpenRouter API key. Either:\n"
            f"  put {API_KEY_ENV}=sk-or-... in a .env file at the repo root\n"
            f"  export {API_KEY_ENV}\n"
            f"  or pass --api-key\n"
            "Get one at https://openrouter.ai/keys — or use --provider mock to try "
            "the tool without spending anything."
        )
    return key


ENV_FILENAME = ".env"


def parse_env_file(text: str) -> dict[str, str]:
    """A deliberately small ``KEY=value`` reader.

    Handles what a key file actually contains — comments, blank lines, an
    ``export`` prefix, and quoted values — and nothing more exotic, rather than
    taking a dependency for twenty lines.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, separator, value = line.partition("=")
        if not separator:
            continue
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name:
            values[name] = value
    return values


def load_env_file(path: Path) -> list[str]:
    """Load ``path`` into the environment, returning the names it set.

    A variable already present in the real environment wins — an explicit
    ``export`` on the command line should not be silently overridden by a file.
    """
    loaded = []
    for name, value in parse_env_file(path.read_text(encoding="utf-8")).items():
        if name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded


def autoload_env(start: Path | None = None) -> Path | None:
    """Load ``.env`` from the working directory or the repo root, if there is one."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current / ENV_FILENAME, find_repo_root(current) / ENV_FILENAME):
        if candidate.is_file():
            load_env_file(candidate)
            return candidate
    return None


def cache_dir() -> Path:
    """Where the model catalog is cached, respecting platform conventions."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    path = Path(base) / "compaire"
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up looking for the project root.

    Lets `compaire index` and `compaire validate` be run from anywhere in the
    checkout, which matters because contributors will run them from wherever
    their shell happens to be.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return current


def experiments_dir(root: Path | None = None) -> Path:
    return find_repo_root(root) / EXPERIMENTS_DIRNAME


@dataclass(slots=True)
class Limits:
    """Size budget applied per experiment. Overridable for tests."""

    max_experiment_bytes: int = MAX_EXPERIMENT_BYTES
    max_asset_bytes: int = MAX_ASSET_BYTES
