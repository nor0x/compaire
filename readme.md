# COMPaiRE

... is a tool for comparing the performance of different machine learning models on a given task. It allows users to easily create and run experiments, visualize results, and share findings with others.

I personally use it to compare models on prompts that are of interest to me and to see how new models perform on tasks that I have tested in the past with other models. It's designed to give a very human-friendly view of the results, not so much to be a direct benchmark for model labs.

It is two halves that meet at one standard format:

- a **Python CLI** that sends one prompt to many models through [OpenRouter](https://openrouter.ai) and writes the results as a self-contained directory
- a **Svelte website** that reads those directories and renders them side by side

Contributing a comparison is just a pull request.

# Features

- sending a prompt to a selection of models and comparing their outputs
- visualization of the responses in a user-friendly interface
  - various pre-built visualization types (e.g. image galleries, image sliders, text comparison tables, web pages,...)
- easy sharing of results with others
  - contribution via GitHub pull requests

# Getting Started

## Install

The CLI needs Python 3.11+. With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/nor0x/compaire
```

Or run it straight from a clone:

```bash
uv run compaire --help
```

## Try it without an API key

Every command works against a deterministic offline provider, so you can see the
whole pipeline before spending anything:

```bash
uv run compaire run --provider mock -p "Explain recursion" -m mock/writer -m mock/painter
```

## Run it for real

Set your key. A `.env` file at the repo root is picked up automatically and is
already git-ignored:

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' > .env
```

An exported variable works too and takes precedence over the file, and
`--env-file path/to/other.env` points somewhere else:

```bash
export OPENROUTER_API_KEY=sk-or-...
```

Then compare some models:

```bash
compaire run -p "Explain recursion to a five year old" -m openai/gpt-5 -m anthropic/claude-sonnet-5 -m google/gemini-3-pro
```

## Compare the free models

[models/free.txt](models/free.txt) lists every OpenRouter model that currently
costs nothing, ready to hand to `--models-file`:

```bash
compaire run --models-file models/free.txt -p "Explain recursion to a five year old" --max-tokens 500
```

Free models rotate constantly, so regenerate it before you rely on it — no API
key needed, the catalog is a public endpoint:

```bash
compaire models --free --write models/free.txt
```

Models whose output the format cannot store (audio, video) and OpenRouter's own
routers are kept in the file as comments explaining why, rather than silently
dropped. Free endpoints are rate limited and often busy; expect some runs to come
back as errors, which is fine — they are recorded rather than fatal.

Price it first if you like — `--dry-run` calls nothing, needs no key, and prints
an estimate per model:

```bash
compaire run --dry-run -f prompt.txt --models-file models.txt --max-tokens 2000
```

Generate images instead of text:

```bash
compaire run --modality image --view gallery -p "A lighthouse in a storm, oil painting" -m google/gemini-3-pro-image
```

## Look at the results

```bash
npm ci --prefix app
npm run dev --prefix app
```

Then open the printed URL. The site reads the `experiments/` directory directly,
so your new run shows up immediately.

# Views

Pick one with `--view`; the site renders the experiment accordingly.

| view      | best for                        | what you get                                                   |
| --------- | ------------------------------- | -------------------------------------------------------------- |
| `table`   | prose, code, structured answers | outputs side by side, markdown rendered, expandable             |
| `gallery` | image generation                | a grid per model with a full-screen lightbox                    |
| `slider`  | two images, small differences   | a drag divider that wipes between two results                   |
| `html`    | "build me a page" prompts       | each page in a sandboxed frame at desktop/tablet/mobile widths  |
| `svg`     | icons, logos, diagrams, charts  | a large preview with the other results as thumbnails, and a toggle between the drawing, a PNG rasterized in your browser, and the source |

Drawings get one extra step. An `.svg` in the repository is a live document when
opened directly, so `compaire run` strips scripts, event handlers and external
references before committing one, and records what it removed — the site says so
rather than passing off an edited artifact as the model's answer. `compaire
validate` applies the same rules, which is what stops a hand-edited asset in a
pull request.

# How it works

```
compaire run     ─►  experiments/<slug>/
compaire extend  ─►    experiment.json   the contract the website reads
                       spec.toml         inputs, so anyone can reproduce it
                       prompt.txt        the prompt verbatim
                       assets/<sha8>.*   images, drawings, pages, long text
                             │
                             ▼
                     experiments/index.json  ──►  the website
```

`run` creates a directory; `extend` appends to one. Each result records who
contributed it and when, so a comparison can grow past its original author
without losing track of where anything came from.

`src/compaire/schema.py` is the single source of truth for that format. The JSON
Schema in [docs/experiment.schema.json](docs/experiment.schema.json) and the
TypeScript types the site compiles against are both generated from it with
`compaire schema --export`, and CI fails if either drifts.

Assets are named by the hash of their content, so identical outputs are stored
once. `compaire validate` enforces a 10 MB budget per experiment.

# Contributing

Comparisons are contributed as pull requests — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Add your model to a comparison that already exists

Usually the most useful thing to contribute. `extend` takes the prompt, sampling
parameters, view and modality from the experiment you point it at — there is no
flag to change them, because a result produced from a different prompt would not
be comparable:

```bash
compaire extend experiments/explaining-monads -m your/model --author "Your Name"
```

It appends your results, records that you contributed them, and refreshes the
index. Every experiment page shows the exact command for that experiment together
with the models already covered, so you can see the gap before you spend
anything.

## Or start a new comparison

```bash
compaire run -p "your prompt" -m model/one -m model/two --view table --author "your name"
compaire validate --strict
```

Either way, commit the changed `experiments/<slug>/` directory and open a PR. CI
checks the schema, the assets and the size budget; it never calls a model and
holds no secrets.

# Development

```bash
uv sync
uv run pytest
uv run ruff check .
```

```bash
npm ci --prefix app
npm run check --prefix app
```

# Commands

| command             | what it does                                                     |
| ------------------- | ---------------------------------------------------------------- |
| `compaire run`      | send a prompt to several models and write an experiment           |
| `compaire extend`   | add more models to an experiment that already exists              |
| `compaire models`   | browse the catalog, or `--free --write` a models file (no key)     |
| `compaire validate` | check experiments against the schema and the size budget          |
| `compaire index`    | rebuild `experiments/index.json`                                  |
| `compaire schema`   | print, export or verify the generated schema and TypeScript types |
