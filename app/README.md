# CompAIre website

The Svelte + Vite front end for [CompAIre](../../readme.md). It reads the
`experiments/` directory at the repository root — served in dev and copied into
the build by `vite-plugin-experiments.ts` — and renders each experiment with the
view its manifest asks for.

```bash
npm ci
npm run dev     # http://localhost:5173/compaire/
npm run check   # svelte-check + tsc
npm run build   # static output in dist/
```

`src/lib/types.ts` is generated from the Python schema by
`uv run compaire schema --export`. Do not edit it by hand.

The deployed site lives under `/<repo>/` on GitHub Pages; set `BASE_PATH=/` to
build for a custom domain or user page.
