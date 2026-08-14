import type {
  Author,
  Experiment,
  ImageOutput,
  IndexEntry,
  Run,
  SvgOutput,
  TextOutput,
} from './types'

const BASE = import.meta.env.BASE_URL
const ROOT = `${BASE}experiments`

/** Experiments never change while the page is open, so one fetch each is enough. */
const experimentCache = new Map<string, Promise<Experiment>>()
const textCache = new Map<string, Promise<string>>()

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} — ${url}`)
  return (await response.json()) as T
}

export async function loadIndex(): Promise<IndexEntry[]> {
  const index = await getJson<{ experiments?: IndexEntry[] }>(`${ROOT}/index.json`)
  return index.experiments ?? []
}

export function loadExperiment(id: string): Promise<Experiment> {
  let pending = experimentCache.get(id)
  if (!pending) {
    pending = getJson<Experiment>(`${ROOT}/${id}/experiment.json`)
    // A failed load must not be cached, or a retry can never succeed.
    pending.catch(() => experimentCache.delete(id))
    experimentCache.set(id, pending)
  }
  return pending
}

/** Absolute URL of an asset referenced by an experiment. */
export function assetUrl(experimentId: string, path: string): string {
  return `${ROOT}/${experimentId}/${path}`
}

/** Fetch an asset as text, once per URL. Used for long outputs and for SVG source. */
export function loadAssetText(experimentId: string, path: string): Promise<string> {
  const url = assetUrl(experimentId, path)
  let pending = textCache.get(url)
  if (!pending) {
    pending = fetch(url).then((response) => {
      if (!response.ok) throw new Error(`${response.status} — ${url}`)
      return response.text()
    })
    pending.catch(() => textCache.delete(url))
    textCache.set(url, pending)
  }
  return pending
}

/**
 * Text outputs are inlined when small and stored as files when large; callers
 * should not have to care which.
 */
export function loadText(experimentId: string, output: TextOutput): Promise<string> {
  if (output.text != null) return Promise.resolve(output.text)
  if (!output.path) return Promise.resolve('')
  return loadAssetText(experimentId, output.path)
}

export function textOutputs(run: Run): TextOutput[] {
  return (run.outputs ?? []).filter((output): output is TextOutput => output.kind === 'text')
}

export function imageOutputs(run: Run): ImageOutput[] {
  return (run.outputs ?? []).filter((output): output is ImageOutput => output.kind === 'image')
}

export function svgOutputs(run: Run): SvgOutput[] {
  return (run.outputs ?? []).filter((output): output is SvgOutput => output.kind === 'svg')
}

/**
 * Everything an `<img>` can render. Galleries and sliders do not care whether a
 * result arrived as a raster or as a drawing.
 */
export function visualOutputs(run: Run): (ImageOutput | SvgOutput)[] {
  return (run.outputs ?? []).filter(
    (output): output is ImageOutput | SvgOutput => output.kind === 'image' || output.kind === 'svg',
  )
}

export function htmlOutputs(run: Run) {
  return (run.outputs ?? []).filter((output) => output.kind === 'html')
}

export function displayName(run: Run): string {
  return run.model_name || run.model
}

/**
 * Who contributed a result. Runs written before per-run attribution existed
 * fall back to whoever started the comparison.
 */
export function authorOf(run: Run, experiment: Experiment): Author | null {
  return run.author ?? experiment.author ?? null
}

/** Distinct contributors, the experiment's own first. */
export function contributorsOf(experiment: Experiment): Author[] {
  const seen = new Map<string, Author>()
  for (const author of [experiment.author, ...(experiment.runs ?? []).map((run) => run.author)]) {
    if (author && !seen.has(author.name)) seen.set(author.name, author)
  }
  return [...seen.values()]
}

/** Every model in the comparison, in the order it was added. */
export function modelsOf(experiment: Experiment): string[] {
  return [...new Set((experiment.runs ?? []).map((run) => run.model))]
}

export function totalCost(experiment: Experiment): number {
  return (experiment.runs ?? []).reduce((sum, run) => sum + (run.usage?.cost ?? 0), 0)
}

export function totalTokens(experiment: Experiment): number {
  return (experiment.runs ?? []).reduce((sum, run) => sum + (run.usage?.total_tokens ?? 0), 0)
}

/**
 * Tokens the model spent thinking, as the provider reported them.
 *
 * Falls back to the provider's nested `completion_tokens_details`, so results
 * committed before the CLI promoted the field still show their reasoning. No
 * arithmetic relationship to the completion count is assumed: some providers
 * count reasoning inside it, others report more reasoning than completion.
 */
export function reasoningTokens(run: Run): number {
  const usage = run.usage
  if (!usage) return 0
  if (typeof usage.reasoning_tokens === 'number') return usage.reasoning_tokens

  const details = usage.completion_tokens_details
  if (details && typeof details === 'object') {
    const nested = (details as Record<string, unknown>).reasoning_tokens
    if (typeof nested === 'number') return nested
  }
  return 0
}

export function totalReasoningTokens(experiment: Experiment): number {
  return (experiment.runs ?? []).reduce((sum, run) => sum + reasoningTokens(run), 0)
}

/** Whether any model in the comparison reported reasoning tokens at all. */
export function hasReasoning(experiment: Experiment): boolean {
  return (experiment.runs ?? []).some((run) => reasoningTokens(run) > 0)
}

/** Samples each model contributed, or null when it varies between models. */
export function samplesPerModel(experiment: Experiment): number | null {
  const counts = modelsOf(experiment).map(
    (model) => (experiment.runs ?? []).filter((run) => run.model === model).length,
  )
  return new Set(counts).size === 1 ? counts[0] : null
}

/** Runs of the same model are grouped so multi-sample experiments stay readable. */
export function groupByModel(runs: Run[]): { model: string; name: string; runs: Run[] }[] {
  const groups = new Map<string, { model: string; name: string; runs: Run[] }>()
  for (const run of runs) {
    const existing = groups.get(run.model)
    if (existing) existing.runs.push(run)
    else groups.set(run.model, { model: run.model, name: displayName(run), runs: [run] })
  }
  return [...groups.values()]
}

export function formatCost(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value === 0) return 'free'
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`
}

export function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function formatLatency(ms: number | null | undefined): string {
  if (ms == null) return '—'
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}
