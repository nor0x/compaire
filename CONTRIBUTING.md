# Contributing a comparison

Everything on the site came from someone running the CLI and opening a pull
request. There are two ways in.

## The quick one: add your model to an existing comparison

Start here. It makes an existing comparison more useful instead of creating a
near-duplicate of it, and it is one command:

```bash
compaire extend experiments/explaining-monads -m your/model --author "Your Name"
```

The prompt, system prompt, sampling parameters, view and modality all come from
the experiment you are extending, and there is deliberately no flag to override
them — a result produced from a different prompt is not comparable, which is the
one thing this command must not allow. Your results are appended, recorded as
yours, and the index is refreshed.

Every experiment page shows the exact command for that experiment and the models
already covered, so you can pick one that is missing.

Useful flags: `--n` for several samples (defaults to matching the existing runs),
`--replace` to re-run a model that is already there, `--dry-run` to price it
first.

Then validate and open a pull request as below, from step 5.

## Starting a new comparison

## 1. Set up

```bash
git clone https://github.com/nor0x/compaire
cd compaire
uv sync
```

You need your own OpenRouter key — CI does not have one, and the models are
never called during review. Put it in a `.env` at the repo root, which is
git-ignored and picked up automatically:

```bash
echo 'OPENROUTER_API_KEY=sk-or-...' > .env
```

An exported `OPENROUTER_API_KEY` overrides the file, and `--env-file` reads one
from elsewhere.

## 2. Find models

No key needed for any of these — the catalog is public.

```bash
uv run compaire models --modality image
uv run compaire models claude
```

Broke? Compare the models that cost nothing:

```bash
uv run compaire run --models-file models/free.txt -p "your prompt" --max-tokens 500
```

That list ships in [models/free.txt](models/free.txt) and goes stale quickly, so
refresh it first:

```bash
uv run compaire models --free --write models/free.txt
```

## 3. Price the run before you make it

```bash
uv run compaire run --dry-run -p "your prompt" -m openai/gpt-5 -m anthropic/claude-sonnet-5
```

`--dry-run` calls nothing and needs no key. Anything estimated over $1 asks for
confirmation before it runs for real.

## 4. Run it

```bash
uv run compaire run \
  -p "Explain recursion to a five year old" \
  -m openai/gpt-5 -m anthropic/claude-sonnet-5 \
  --view table \
  --title "Explaining recursion" \
  --description "One sentence on what this comparison shows." \
  --tag text --tag explanation \
  --author "Your Name" --github your-handle
```

Long prompts live in a file:

```bash
uv run compaire run -f prompt.txt --models-file models.txt --view table --title "..."
```

Useful flags: `--n 3` for several samples per model, `--modality image` with
`--view gallery` or `--view slider`, `--view html` for page-building prompts,
`--view svg` for icons, logos and diagrams, `--temperature` / `--max-tokens` /
`--seed` to pin sampling.

If you use `--view svg`, expect the CLI to clean the drawings: scripts, event
handlers and external references are stripped before anything is written, and
the removal is recorded on the output so the site can say the artifact was
altered. That is deliberate — do not undo it by editing the asset, or review
will fail.

## 5. Check it

```bash
uv run compaire validate --strict
```

This is the same gate CI runs. It checks the schema, that every referenced
asset exists and stays inside its directory, that images are readable, and that
the experiment fits the size budget (10 MB per experiment, 4 MB per asset).

Preview it locally:

```bash
npm ci --prefix app
npm run dev --prefix app
```

## 6. Open the pull request

Commit the new `experiments/<slug>/` directory **and** the regenerated
`experiments/index.json`:

```bash
git add experiments
git commit -m "Add <title> comparison"
```

## What reviewers look for

- **The prompt is the same for every model.** That is the point of the tool, and
  both `run` and `extend` enforce it.
- **Extending beats forking.** If a comparison already asks your question, add
  your model to it rather than opening a near-duplicate experiment.
- **Failures stay in.** A model that refused or timed out is a result; do not
  delete the run.
- **Nothing hand-edited.** `experiment.json` is generated. If you need to change
  something, change the flags and re-run — `spec.toml` makes that a one-liner:
  ```bash
  uv run compaire run --spec experiments/<slug>/spec.toml
  ```
- **Keep it small.** Prefer fewer samples over many near-identical images.
- **Nothing private.** Prompts and outputs are published as-is. Do not paste
  anything you would not post publicly, including keys or personal data.

## Contributed content is untrusted

Model output is rendered with that assumption: markdown is sanitized, HTML
results run inside `sandbox="allow-scripts"` frames without `allow-same-origin`,
and drawings are cleaned on write and rendered through an `<img>`, which
executes nothing and fetches nothing. Pull requests that try to weaken this will
not be merged.

## Adding a view

The four views live in `src/lib/views/`. To add one:

1. add the name to `ViewKind` in `src/compaire/schema.py`
2. run `uv run compaire schema --export` to regenerate the JSON Schema and the
   TypeScript types
3. add a component and a branch in `src/lib/ExperimentPage.svelte`
4. teach `_check_view` in `src/compaire/validate.py` what the view needs, so an
   experiment that cannot render fails review instead of the site
