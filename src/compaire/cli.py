"""The ``compaire`` command line."""

from __future__ import annotations

import asyncio
import sys
import tomllib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from . import __version__, export, indexer
from .config import (
    ASSETS_DIRNAME,
    COST_CONFIRM_THRESHOLD_USD,
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT_S,
    ConfigError,
    Limits,
    api_key,
    autoload_env,
    experiments_dir,
    find_repo_root,
    load_env_file,
)
from .mock import MockProvider
from .openrouter import ModelInfo, OpenRouterClient, Provider
from .runner import RunOutcome, RunPlan, estimate_cost, execute, total_estimate
from .schema import Author, Modality, PromptParams, ViewKind
from .validate import validate_tree
from .writer import (
    PROMPT_FILENAME,
    AssetStore,
    build_experiment,
    build_run,
    prune_unreferenced,
    slugify,
    unique_dir,
    write_experiment,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Run one prompt against many models, then publish the comparison.",
)


def _make_console(*, stderr: bool = False) -> Console:
    """A console that cannot crash on a legacy Windows code page.

    Model names and prompts are arbitrary text; on a cp1252 terminal a single
    unencodable character would otherwise take down a run that already cost
    money.
    """
    stream = sys.stderr if stderr else sys.stdout
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    return Console(stderr=stderr)


console = _make_console()
err_console = _make_console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"compaire {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
    env_file: Annotated[
        Path | None,
        typer.Option(
            "--env-file",
            help="Read environment variables from this file. Defaults to ./.env.",
        ),
    ] = None,
) -> None:
    """Keys live in the environment. A .env file at the repo root is picked up
    automatically, so `OPENROUTER_API_KEY=sk-or-...` in one is enough."""
    if env_file is None:
        autoload_env()
        return
    if not env_file.is_file():
        _fail(f"no env file at {env_file}")
    load_env_file(env_file)


@app.command()
def run(
    ctx: typer.Context,
    prompt: Annotated[
        str | None, typer.Option("--prompt", "-p", help="The prompt text.")
    ] = None,
    prompt_file: Annotated[
        Path | None,
        typer.Option("--prompt-file", "-f", help="Read the prompt from a file.", exists=True),
    ] = None,
    model: Annotated[
        list[str] | None,
        typer.Option("--model", "-m", help="Model id, repeat for each model to compare."),
    ] = None,
    models_file: Annotated[
        Path | None,
        typer.Option("--models-file", help="File with one model id per line.", exists=True),
    ] = None,
    spec: Annotated[
        Path | None,
        typer.Option("--spec", help="Load inputs from a spec.toml written by a previous run."),
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Experiment title.")] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="One-line summary.")
    ] = None,
    experiment_id: Annotated[
        str | None, typer.Option("--id", help="Directory name. Defaults to a slug of the title.")
    ] = None,
    view: Annotated[
        ViewKind, typer.Option("--view", help="How the website should render the results.")
    ] = "table",
    modality: Annotated[
        Modality, typer.Option("--modality", help="Ask for text or for generated images.")
    ] = "text",
    tag: Annotated[list[str] | None, typer.Option("--tag", help="Tag, repeatable.")] = None,
    author: Annotated[str | None, typer.Option("--author", help="Your name.")] = None,
    github: Annotated[str | None, typer.Option("--github", help="Your GitHub handle.")] = None,
    system: Annotated[str | None, typer.Option("--system", help="System prompt.")] = None,
    samples: Annotated[int, typer.Option("--n", help="Samples per model.")] = 1,
    temperature: Annotated[float | None, typer.Option("--temperature")] = None,
    max_tokens: Annotated[int | None, typer.Option("--max-tokens")] = None,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    concurrency: Annotated[
        int, typer.Option("--concurrency", help="Models called in parallel.")
    ] = DEFAULT_CONCURRENCY,
    timeout: Annotated[
        float, typer.Option("--timeout", help="Per-request timeout, seconds.")
    ] = DEFAULT_TIMEOUT_S,
    out: Annotated[
        Path | None, typer.Option("--out", help="Where to write. Defaults to experiments/<id>.")
    ] = None,
    provider: Annotated[
        str, typer.Option("--provider", help="'openrouter' or 'mock' (offline, no key needed).")
    ] = "openrouter",
    api_key_option: Annotated[
        str | None, typer.Option("--api-key", help="Overrides OPENROUTER_API_KEY.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Price the run and exit without calling anything.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the cost confirmation.")] = False,
    no_index: Annotated[
        bool, typer.Option("--no-index", help="Do not refresh experiments/index.json.")
    ] = False,
) -> None:
    """Send one prompt to several models and write a comparable experiment."""
    settings = _load_spec(spec)
    prompt_text = _resolve_prompt(prompt, prompt_file, spec, settings)
    models = _resolve_models(model, models_file, settings)
    if not models:
        _fail("No models given. Pass --model (repeatable), --models-file or --spec.")

    # A spec fills in what the command line did not say. Comparing against the
    # default would be wrong: `--view table` on a spec that says `gallery` is an
    # explicit choice, so ask the parser what actually came from the user.
    def given(name: str) -> bool:
        source = ctx.get_parameter_source(name)
        return source is not None and source.name == "COMMANDLINE"

    view = view if given("view") else settings.get("view", view)
    modality = modality if given("modality") else settings.get("modality", modality)
    samples = samples if given("samples") else int(settings.get("samples", samples))
    title = title or settings.get("title") or _title_from_prompt(prompt_text)
    description = description or settings.get("description")
    tags = list(tag or settings.get("tags") or [])

    params = PromptParams(
        **{
            **(settings.get("params") or {}),
            **{
                key: value
                for key, value in (
                    ("temperature", temperature),
                    ("max_tokens", max_tokens),
                    ("seed", seed),
                )
                if value is not None
            },
        }
    )
    plan = RunPlan(
        prompt=prompt_text,
        models=models,
        system=system or settings.get("system"),
        params=params,
        modality=modality,
        samples=max(1, samples),
        concurrency=concurrency,
    )

    # A dry run only reads the public catalog, so it should not demand a key —
    # pricing a comparison is exactly what you do before signing up for one.
    backend = _build_provider(provider, view, api_key_option, timeout, needs_key=not dry_run)
    outcomes = asyncio.run(_price_and_call(backend, plan, view, dry_run=dry_run, yes=yes))

    if outcomes is None:
        console.print("\n[dim]Dry run — nothing was sent.[/dim]")
        raise typer.Exit()

    root = experiments_dir().resolve()
    slug = slugify(experiment_id or title)
    if out is not None:
        # Resolve before comparing to `root`, or a relative --out would look
        # like it lives outside the experiments directory and skip the index.
        directory, slug = out.resolve(), slugify(experiment_id or out.name)
        directory.mkdir(parents=True, exist_ok=True)
    else:
        directory, slug = unique_dir(root, slug)

    experiment = build_experiment(
        experiment_id=slug,
        title=title,
        plan=plan,
        outcomes=outcomes,
        directory=directory,
        view=view,
        description=description,
        author=Author(name=author, github=github) if author else None,
        tags=tags,
        created_at=datetime.now(UTC),
    )
    write_experiment(experiment, directory)

    if not no_index and directory.parent == root:
        indexer.write(root)

    _print_results(experiment, directory)


@app.command()
def extend(
    path: Annotated[Path, typer.Argument(help="The experiment directory to add results to.")],
    model: Annotated[
        list[str] | None, typer.Option("--model", "-m", help="Model id to add, repeatable.")
    ] = None,
    models_file: Annotated[
        Path | None,
        typer.Option("--models-file", help="File with one model id per line.", exists=True),
    ] = None,
    samples: Annotated[
        int | None,
        typer.Option("--n", help="Samples per model. Defaults to matching the existing runs."),
    ] = None,
    replace: Annotated[
        bool, typer.Option("--replace", help="Re-run models that are already present.")
    ] = False,
    author: Annotated[str | None, typer.Option("--author", help="Your name.")] = None,
    github: Annotated[str | None, typer.Option("--github", help="Your GitHub handle.")] = None,
    concurrency: Annotated[int, typer.Option("--concurrency")] = DEFAULT_CONCURRENCY,
    timeout: Annotated[float, typer.Option("--timeout")] = DEFAULT_TIMEOUT_S,
    provider: Annotated[
        str, typer.Option("--provider", help="'openrouter' or 'mock' (offline, no key needed).")
    ] = "openrouter",
    api_key_option: Annotated[str | None, typer.Option("--api-key")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Price the run and exit without calling anything.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the cost confirmation.")] = False,
    no_index: Annotated[bool, typer.Option("--no-index")] = False,
) -> None:
    """Add your own model's results to an existing comparison.

    The prompt, system prompt, sampling parameters, view and modality all come
    from the experiment you are extending, and cannot be overridden — a result
    produced from a different prompt would not be comparable, which is the whole
    point of the comparison.
    """
    directory = path.resolve()
    try:
        existing = indexer.load_experiment(directory)
    except (OSError, ValueError) as exc:
        _fail(f"cannot read an experiment at {path}: {exc}")
        return

    models = _resolve_models(model, models_file, {})
    if not models:
        _fail("No models given. Pass --model (repeatable) or --models-file.")

    already = set(existing.models)
    clashes = [name for name in models if name in already]
    if clashes and not replace:
        _fail(
            f"{', '.join(clashes)} already in this comparison. Pick another model, "
            "or pass --replace to run it again."
        )

    plan = RunPlan(
        prompt=existing.prompt.text,
        models=models,
        system=existing.prompt.system,
        params=existing.prompt.params,
        modality=existing.modality,
        samples=samples or existing.samples_per_model or 1,
        concurrency=concurrency,
    )

    backend = _build_provider(
        provider, existing.view, api_key_option, timeout, needs_key=not dry_run
    )

    def preamble() -> None:
        console.print(f"Extending [bold]{existing.title}[/bold] ({existing.id})")
        console.print(f"[dim]inherited prompt: {_one_line(existing.prompt.text)}[/dim]")

    outcomes = asyncio.run(
        _price_and_call(
            backend, plan, existing.view, dry_run=dry_run, yes=yes, preamble=preamble
        )
    )

    if outcomes is None:
        console.print("\n[dim]Dry run — nothing was sent.[/dim]")
        raise typer.Exit()

    now = datetime.now(UTC)
    store = AssetStore(directory / ASSETS_DIRNAME)
    contributor = Author(name=author, github=github) if author else None
    fresh = [
        build_run(outcome, existing.view, store, author=contributor, created_at=now)
        for outcome in outcomes
    ]

    kept = [run for run in existing.runs if run.model not in set(models)]
    existing.runs = kept + fresh
    existing.updated_at = now

    write_experiment(existing, directory)
    # --replace leaves the old model's assets behind, which validate rejects
    # under --strict.
    for orphan in prune_unreferenced(directory, existing):
        console.print(f"[dim]pruned {orphan.name}[/dim]")

    root = experiments_dir().resolve()
    if not no_index and directory.parent == root:
        indexer.write(root)

    _print_results(existing, directory)


@app.command()
def models(
    search: Annotated[str | None, typer.Argument(help="Filter by id, name or description.")] = None,
    modality: Annotated[
        str | None, typer.Option("--modality", help="Only models that output 'text' or 'image'.")
    ] = None,
    free: Annotated[
        bool, typer.Option("--free", help="Only models that cost nothing to call.")
    ] = False,
    write: Annotated[
        Path | None,
        typer.Option("--write", help="Write the matches as a --models-file instead of a table."),
    ] = None,
    refresh: Annotated[bool, typer.Option("--refresh", help="Bypass the 24h cache.")] = False,
    provider: Annotated[str, typer.Option("--provider")] = "openrouter",
    api_key_option: Annotated[str | None, typer.Option("--api-key")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 40,
) -> None:
    """Browse the OpenRouter catalog. No API key needed — the catalog is public."""
    backend = _build_provider(
        provider, "table", api_key_option, DEFAULT_TIMEOUT_S, needs_key=False
    )

    async def fetch() -> list[ModelInfo]:
        async with _session(backend) as client:
            return await _fetch_models(client, refresh=refresh)

    catalog = asyncio.run(fetch())

    needle = (search or "").lower()
    matches = [
        info
        for info in catalog
        if (not needle or needle in f"{info.id} {info.name} {info.description}".lower())
        and (not modality or modality in info.output_modalities)
        and (not free or info.free)
    ]
    matches.sort(key=lambda info: info.id)

    if write is not None:
        write.parent.mkdir(parents=True, exist_ok=True)
        write.write_text(render_models_file(matches, free=free), encoding="utf-8", newline="\n")
        usable = sum(1 for info in matches if _usable(info))
        console.print(
            f"[green]Wrote[/green] {write} — {usable} usable model(s)"
            f"{f', {len(matches) - usable} commented out' if len(matches) > usable else ''}"
        )
        console.print(f"[dim]Use it with: compaire run --models-file {write} -p '…'[/dim]")
        return

    table = Table(title=f"{len(matches)} models", box=None, pad_edge=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("name")
    table.add_column("in / out", style="dim")
    table.add_column("$/M in", justify="right")
    table.add_column("$/M out", justify="right")
    for info in matches[:limit]:
        table.add_row(
            info.id,
            info.name,
            f"{'+'.join(info.input_modalities or ['text'])} / {'+'.join(info.output_modalities)}",
            f"{info.prompt_price * 1e6:.2f}" if info.prompt_price else "-",
            f"{info.completion_price * 1e6:.2f}" if info.completion_price else "-",
        )
    console.print(table)
    if len(matches) > limit:
        console.print(f"[dim]…and {len(matches) - limit} more. Use --limit to see them.[/dim]")


@app.command(name="index")
def index_command(
    path: Annotated[Path | None, typer.Argument(help="Experiments directory.")] = None,
    check: Annotated[
        bool, typer.Option("--check", help="Fail if the checked-in index is out of date.")
    ] = False,
) -> None:
    """Rebuild experiments/index.json."""
    root = path or experiments_dir()
    if check:
        if indexer.is_stale(root):
            _fail("experiments/index.json is out of date — run `compaire index` and commit it.")
        console.print("[green]index.json is up to date.[/green]")
        return
    written = indexer.write(root)
    count = len(indexer.iter_experiment_dirs(root))
    console.print(f"[green]Wrote[/green] {written} ({count} experiments)")


@app.command(name="validate")
def validate_command(
    path: Annotated[
        Path | None, typer.Argument(help="Experiment or experiments directory.")
    ] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Treat warnings as errors.")] = False,
    max_experiment_mb: Annotated[float | None, typer.Option("--max-experiment-mb")] = None,
    max_asset_mb: Annotated[float | None, typer.Option("--max-asset-mb")] = None,
) -> None:
    """Check experiments against the schema and the size budget."""
    root = path or experiments_dir()
    limits = Limits()
    if max_experiment_mb is not None:
        limits.max_experiment_bytes = int(max_experiment_mb * 1024 * 1024)
    if max_asset_mb is not None:
        limits.max_asset_bytes = int(max_asset_mb * 1024 * 1024)

    issues = validate_tree(root, limits=limits, strict=strict)
    errors = [issue for issue in issues if issue.is_error]
    for issue in issues:
        style = "red" if issue.is_error else "yellow"
        err_console.print(f"[{style}]{issue.level}[/{style}] {issue.where}: {issue.message}")

    count = len(indexer.iter_experiment_dirs(root))
    if errors:
        _fail(f"{len(errors)} problem(s) in {count} experiment(s).")
    console.print(f"[green]OK[/green] — {count} experiment(s) valid.")


@app.command(name="schema")
def schema_command(
    export_flag: Annotated[
        bool, typer.Option("--export", help="Write the JSON Schema and TypeScript types.")
    ] = False,
    check: Annotated[
        bool, typer.Option("--check", help="Fail if the generated files are out of date.")
    ] = False,
) -> None:
    """Export or verify the generated schema artifacts."""
    root = find_repo_root()
    if not export_flag and not check:
        console.print_json(data=export.json_schema())
        return
    changed = export.write(root)
    if check and changed:
        for path in changed:
            err_console.print(f"[red]out of date[/red] {path.relative_to(root)}")
        _fail("Generated files changed — run `compaire schema --export` and commit the result.")
    for path in changed:
        console.print(f"[green]Wrote[/green] {path.relative_to(root)}")
    if not changed:
        console.print("[green]Generated files are up to date.[/green]")


# --- helpers ------------------------------------------------------------------


def _fail(message: str) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=1)


def _build_provider(
    name: str, view: ViewKind, key: str | None, timeout: float, *, needs_key: bool = True
) -> Provider:
    if name == "mock":
        return MockProvider(view=view)
    if name != "openrouter":
        _fail(f"Unknown provider {name!r}. Use 'openrouter' or 'mock'.")
    try:
        return OpenRouterClient(api_key(key, required=needs_key), timeout=timeout)
    except ConfigError as exc:
        _fail(str(exc))
        raise  # unreachable, keeps type checkers happy


@asynccontextmanager
async def _session(backend: Provider) -> AsyncIterator[Provider]:
    """Own the provider's connection pool for one whole command.

    Everything a command does over the network has to happen inside a single
    `asyncio.run`, sharing one client: an HTTP client belongs to the event loop
    that created it, and closing it after the catalog fetch would leave the
    actual model calls with nothing to send on.
    """
    if isinstance(backend, OpenRouterClient):
        async with backend:
            yield backend
    else:
        yield backend


async def _fetch_models(backend: Provider, *, refresh: bool = False) -> list[ModelInfo]:
    """The catalog, or an empty list — it is a convenience, not a requirement."""
    try:
        if isinstance(backend, OpenRouterClient):
            return await backend.models(refresh=refresh)
        return await backend.models()
    except Exception as exc:  # noqa: BLE001
        err_console.print(f"[yellow]warning[/yellow] could not load the model catalog: {exc}")
        return []


async def _catalog(backend: Provider, *, refresh: bool = False) -> dict[str, ModelInfo]:
    return {info.id: info for info in await _fetch_models(backend, refresh=refresh)}


async def _execute_with_progress(
    backend: Provider, plan: RunPlan, catalog: dict[str, ModelInfo]
) -> list[RunOutcome]:
    names = {model_id: info.name for model_id, info in catalog.items()}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("calling models", total=len(plan.calls()))

        def done(outcome: RunOutcome) -> None:
            progress.advance(task)
            mark = "[green]ok[/green]" if outcome.ok else "[red]failed[/red]"
            detail = f" — {outcome.error}" if outcome.error else f" ({outcome.latency_ms} ms)"
            progress.console.print(f"  {mark} {outcome.model}{detail}")

        return await execute(backend, plan, model_names=names, on_done=done)


async def _price_and_call(
    backend: Provider,
    plan: RunPlan,
    view: ViewKind,
    *,
    dry_run: bool,
    yes: bool,
    preamble: Callable[[], None] | None = None,
) -> list[RunOutcome] | None:
    """Price the plan, confirm it, then run it — all on one connection pool.

    Returns ``None`` for a dry run, which is the caller's cue to stop.
    """
    async with _session(backend) as client:
        catalog = await _catalog(client)
        if preamble:
            preamble()
        estimates = estimate_cost(plan, catalog)
        _print_plan(plan, view, estimates)

        if dry_run:
            return None

        total = total_estimate(estimates)
        if total > COST_CONFIRM_THRESHOLD_USD and not yes:
            typer.confirm(f"This run is estimated at ${total:.2f}. Continue?", abort=True)

        return await _execute_with_progress(client, plan, catalog)


def _load_spec(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        _fail(f"cannot read spec {path}: {exc}")
        return {}


def _resolve_prompt(
    prompt: str | None, prompt_file: Path | None, spec: Path | None, settings: dict[str, Any]
) -> str:
    if prompt:
        return prompt
    if prompt_file:
        return prompt_file.read_text(encoding="utf-8").strip()
    if settings.get("prompt"):
        return str(settings["prompt"]).strip()
    if spec is not None:
        # Spec files point at a sibling prompt file so long prompts stay readable.
        candidate = spec.parent / str(settings.get("prompt_file") or PROMPT_FILENAME)
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    _fail("No prompt. Pass --prompt, --prompt-file or a --spec that references one.")
    return ""


def _resolve_models(
    models: list[str] | None, models_file: Path | None, settings: dict[str, Any]
) -> list[str]:
    collected = list(models or [])
    if models_file:
        collected += [
            line.strip()
            for line in models_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    if not collected:
        collected = [str(item) for item in settings.get("models") or []]
    return list(dict.fromkeys(collected))


def _title_from_prompt(prompt: str) -> str:
    first = prompt.strip().splitlines()[0].strip()
    return first if len(first) <= 60 else first[:57].rstrip() + "…"


def _unusable_reason(info: ModelInfo) -> str | None:
    """Why this model should not go into a comparison, if it should not."""
    if info.id.startswith("openrouter/"):
        return "routes to a model of its own choosing, so the result is not attributable"
    if not info.storable:
        emits = " and ".join(info.unstorable_modalities)
        return f"emits {emits}, which the experiment format cannot store"
    return None


def _usable(info: ModelInfo) -> bool:
    return _unusable_reason(info) is None


def render_models_file(matches: list[ModelInfo], *, free: bool) -> str:
    """A `--models-file`: one id per line, with the rejects kept as comments.

    Models the tool cannot use are commented out rather than dropped, so the
    file explains itself instead of looking arbitrarily incomplete.
    """
    what = "free models" if free else "models"
    command = "compaire models" + (" --free" if free else "") + " --write <this file>"
    lines = [
        f"# OpenRouter {what}, captured {datetime.now(UTC):%Y-%m-%d}.",
        "#",
        f"# Regenerate with:  {command}",
        "# Use with:         compaire run --models-file <this file> -p 'your prompt'",
    ]
    if free:
        lines += [
            "#",
            "# Free models come and go, and free endpoints are rate limited and",
            "# often heavily loaded. Re-generate this file before relying on it,",
            "# and expect some runs to come back as errors.",
        ]
    lines.append("")

    usable = [info for info in matches if _usable(info)]
    rejected = [info for info in matches if not _usable(info)]

    for info in usable:
        lines.append(info.id)

    if rejected:
        lines += ["", "# Excluded:"]
        for info in rejected:
            lines.append(f"# {info.id} — {_unusable_reason(info)}")

    return "\n".join(lines) + "\n"


def _one_line(text: str, limit: int = 90) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else f"{flat[:limit].rstrip()}…"


def _print_plan(
    plan: RunPlan, view: ViewKind, estimates: list[tuple[str, float | None]]
) -> None:
    table = Table(box=None, pad_edge=False)
    table.add_column("model", style="cyan")
    table.add_column("calls", justify="right")
    table.add_column("est. cost", justify="right")
    for model, value in estimates:
        table.add_row(
            model,
            str(plan.samples),
            f"${value:.4f}" if value is not None else "[dim]unknown[/dim]",
        )
    console.print(table)
    total = total_estimate(estimates)
    console.print(
        f"[dim]{len(plan.calls())} call(s), {plan.modality} -> {view} view, "
        f"estimated ${total:.4f}[/dim]"
    )


def _print_results(experiment: Any, directory: Path) -> None:
    failed = [run for run in experiment.runs if run.status == "error"]
    table = Table(box=None, pad_edge=False)
    table.add_column("model", style="cyan")
    table.add_column("status")
    table.add_column("latency", justify="right")
    table.add_column("tokens", justify="right")
    table.add_column("cost", justify="right")
    for run in experiment.runs:
        usage = run.usage
        table.add_row(
            run.model,
            "[green]ok[/green]" if run.status == "ok" else "[red]error[/red]",
            f"{run.latency_ms} ms" if run.latency_ms else "-",
            str(usage.total_tokens) if usage and usage.total_tokens else "-",
            f"${usage.cost:.4f}" if usage and usage.cost else "-",
        )
    console.print()
    console.print(table)
    console.print(f"\n[green]Wrote[/green] {directory}  (total ${experiment.total_cost:.4f})")
    if failed:
        console.print(f"[yellow]{len(failed)} run(s) failed[/yellow] and are recorded as errors.")
    console.print(
        "\nNext: [bold]compaire validate[/bold], then commit the directory and open a pull request."
    )
