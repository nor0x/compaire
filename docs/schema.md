# The experiment format

`src/compaire/schema.py` is the source of truth. Everything below is generated
from it — [experiment.schema.json](experiment.schema.json) for validation,
`src/lib/types.ts` for the site — by:

```bash
uv run compaire schema --export
```

CI runs `compaire schema --check` and fails if either file is out of date, so
the CLI and the website can never disagree about the shape of the data.

## On disk

```
experiments/
  index.json                   generated card list for the landing page
  <slug>/
    experiment.json            the manifest
    spec.toml                  inputs, for `compaire run --spec`
    prompt.txt                 the prompt verbatim
    assets/<sha8>.webp|.svg|.md|.html
```

`spec.toml` is derived from the manifest's current state, not from the command
that happened to create it — so after someone extends a comparison, its spec
still lists every model in it.

The directory name, the `id` field and the site's URL (`#/e/<id>`) are the same
string. `compaire validate` enforces that.

## experiment.json

```jsonc
{
  "schema_version": 1,
  "id": "explaining-monads",          // == directory name, [a-z0-9-]
  "title": "Explaining monads",
  "description": "One line shown on the card.",
  "author": { "name": "…", "github": "…", "url": null },
  "created_at": "2026-08-13T19:30:50Z",
  "updated_at": "2026-08-20T08:12:04Z", // set when `compaire extend` appends results
  "view": "table",                    // gallery | slider | table | html | svg | text
  "modality": "text",                 // text | image
  "tags": ["text", "explanation"],
  "prompt": {
    "text": "…",                      // identical for every model
    "system": null,
    "file": "prompt.txt",
    "params": { "temperature": 0.7, "max_tokens": 1024, "seed": null }
  },
  "runs": [ /* see below */ ],
  "tool_version": "0.1.0"
}
```

## A run

One model's answer, or its failure. `id` is `<model with / -> ->__<sample>`.

```jsonc
{
  "id": "openai-gpt-5__0",
  "model": "openai/gpt-5",
  "model_name": "GPT-5",              // from the catalog, for display
  "sample_index": 0,
  "status": "ok",                     // ok | error
  "error": null,
  "latency_ms": 4210,
  "usage": { "prompt_tokens": 12, "completion_tokens": 400, "total_tokens": 412,
             "reasoning_tokens": 180, "cost": 0.0031,
             "completion_tokens_details": { "reasoning_tokens": 180 } },
  "outputs": [ /* see below */ ],
  "generation_id": "gen-…",           // OpenRouter's id, for tracing
  "author": { "name": "…", "github": "…" },  // who contributed this result
  "created_at": "2026-08-20T08:12:04Z"       // when they did
}
```

Failed runs are kept with `status: "error"` and a message. A model that refuses
or times out is part of the comparison, not noise to be dropped.

`usage.cost` is what OpenRouter reported for the call, in USD.

`usage` keeps every key the provider sent — `completion_tokens_details`,
`prompt_tokens_details`, `cost_details` and so on survive untouched. On top of
that, `reasoning_tokens` is lifted out of `completion_tokens_details` so readers
do not have to know the nesting. Two things not to assume about it:

- **It is not a share of `completion_tokens`.** Across real responses some
  providers count reasoning inside the completion total and others report *more*
  reasoning than completion tokens (the completion count gets capped by
  `--max-tokens`, the reasoning count does not). Show it as its own number.
- **Absent is not zero.** `null` means the provider said nothing; `0` means it
  reported none. Results written before the field existed have only the nested
  value, so a reader should fall back to it — the site's `reasoningTokens()`
  does.

`author` and `created_at` are per-run because a comparison grows by pull request:
the experiment's own `author`/`created_at` mean "who started this, when", while a
model appended a month later carries its own. Readers should fall back to the
experiment's author when a run has none — the site's `authorOf()` does.

## Growing an experiment

`compaire extend <dir> -m new/model` appends runs to an existing experiment. It
reads the prompt, system prompt, params, view and modality out of the manifest
and offers no way to change them, so everything in `runs` answers the same
question. It also sets `updated_at`, stamps the new runs with their contributor,
and rewrites `spec.toml`.

`--replace` re-runs a model that is already present, which orphans its old
assets; the command prunes them, because validate treats an unreferenced asset as
an error under `--strict`.

## Outputs

A tagged union on `kind`. The tag is always present — pydantic will not parse a
member without it, and the TypeScript types narrow on it.

```jsonc
{ "kind": "text",  "text": "…", "bytes": 457, "format": "markdown" }
{ "kind": "text",  "path": "assets/ab12cd34.md", "bytes": 9000, "format": "markdown" }
{ "kind": "image", "path": "assets/ab12cd34.webp", "width": 1024, "height": 1024, "bytes": 140132, "alt": "…" }
{ "kind": "html",  "path": "assets/cd34ef56.html", "bytes": 2048 }
{ "kind": "svg",   "path": "assets/ef56ab78.svg", "width": 200, "height": 200, "bytes": 812,
                   "alt": "…", "sanitized": true, "removed": ["<script>", "onclick"] }
```

- Text under 4 KB is inlined; anything larger becomes a `.md` asset. Readers
  should handle both — the site's `loadText()` does.
- Images are re-encoded to WebP on write, with the original dimensions recorded.
- HTML outputs are extracted from a fenced ```html block, or from a bare
  document, when the experiment uses `--view html`.
- SVG outputs are extracted the same way under `--view svg` (a fenced ```svg or
  ```xml block, or the `<svg>…</svg>` sliced out of whatever the model wrapped it
  in), and can also arrive directly from the images endpoint as
  `image/svg+xml`. They skip the WebP conversion — Pillow cannot read vector
  data, and the code view needs the source intact.

## The SVG sanitization contract

`compaire run` cleans every drawing before committing it, because an `.svg` in
the repository is a live same-origin document the moment someone opens its URL —
unlike HTML assets, which the site only ever loads inside a sandboxed frame.

Removed by `src/compaire/svg.py`: `<script>` and `<foreignObject>`, every `on*`
attribute, any `href`/`xlink:href` that is not a `#fragment` or a `data:image/*`
URI, `@import` inside `<style>`, and SMIL animations that target `href` or an
event handler. A missing `xmlns` is added back, since a standalone SVG without
it does not render in an `<img>`.

When anything is removed, `sanitized` is `true` and `removed` lists it. The site
shows that on the drawing, because the committed file is then **not** byte-for-byte
what the model returned, and this project is about showing model output
faithfully.

`compaire validate` re-runs the same rules over the committed bytes. The
sanitizer is idempotent, so a clean file produces no findings and a hand-edited
one fails the pull request.

## Asset paths

Always relative to the experiment directory, always forward slashes. Absolute
paths, drive letters, `..` and empty segments are rejected by the schema and
again by `compaire validate`, because these files arrive from pull requests.

Names are `sha256(content)[:8]` plus the extension, so two models returning
identical output share one file.

## index.json

Generated by `compaire index`, most recent activity first — sorted on
`updated_at` falling back to `created_at`, so a comparison someone just extended
surfaces. It carries only what the landing page needs, so the list never fetches
a full experiment:

```jsonc
{
  "schema_version": 1,
  "generated_at": "2026-08-13T19:31:00Z",
  "experiments": [
    {
      "id": "explaining-monads",
      "title": "Explaining monads",
      "description": "…",
      "author": { "name": "…" },
      "created_at": "…",
      "updated_at": "…",
      "view": "table",
      "modality": "text",
      "tags": ["text"],
      "models": ["openai/gpt-5", "anthropic/claude-sonnet-5"],
      "run_count": 3,
      "contributors": 2,
      "thumb": "assets/58f7ded9.webp",
      "total_cost": 0.0064
    }
  ]
}
```

`generated_at` is ignored when checking staleness, so a rebuild that changes
nothing else does not fail CI.

## Changing the format

Bump `SCHEMA_VERSION` when a change would stop older files from loading.
`compaire validate` rejects any manifest whose `schema_version` it does not
recognize, which is the signal to migrate the committed experiments in the same
pull request.
