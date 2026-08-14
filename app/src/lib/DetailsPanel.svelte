<script lang="ts">
  import {
    assetUrl,
    authorOf,
    displayName,
    formatCost,
    formatDate,
    formatLatency,
    hasReasoning,
    modelsOf,
    reasoningTokens,
    samplesPerModel,
    totalCost,
    totalReasoningTokens,
    totalTokens,
  } from './data'
  import type { Experiment } from './types'

  let { experiment }: { experiment: Experiment } = $props()

  const runs = $derived(experiment.runs ?? [])
  const samples = $derived(samplesPerModel(experiment))
  const reasoning = $derived(hasReasoning(experiment))
  const facts = $derived([
    ['Created', formatDate(experiment.created_at)],
    ['Last extended', experiment.updated_at ? formatDate(experiment.updated_at) : '—'],
    ['View', experiment.view],
    ['Modality', experiment.modality],
    ['Models', String(modelsOf(experiment).length)],
    ['Results', String(runs.length)],
    ['Samples per model', samples === null ? 'varies' : String(samples)],
    ['Total cost', formatCost(totalCost(experiment))],
    ['Total tokens', totalTokens(experiment) ? totalTokens(experiment).toLocaleString() : '—'],
    ...(reasoning
      ? ([['Reasoning tokens', totalReasoningTokens(experiment).toLocaleString()]] as const)
      : []),
    ['Built with', experiment.tool_version ? `compaire ${experiment.tool_version}` : '—'],
    ['Format version', String(experiment.schema_version ?? 1)],
  ] as const)
</script>

<details>
  <summary>
    Details and provenance
    <span class="hint">prompt file, spec, and who contributed which result</span>
  </summary>

  <div class="body">
    <dl>
      {#each facts as [label, value] (label)}
        <div>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      {/each}
    </dl>

    <p class="files">
      <a href={assetUrl(experiment.id, 'spec.toml')} target="_blank" rel="noopener noreferrer">
        spec.toml
      </a>
      <a href={assetUrl(experiment.id, 'prompt.txt')} target="_blank" rel="noopener noreferrer">
        prompt.txt
      </a>
      <span class="note">Re-run the whole thing with <code>compaire run --spec spec.toml</code></span>
    </p>

    <div class="scroll">
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Contributed by</th>
            <th>When</th>
            <th>Status</th>
            <th class="right">Latency</th>
            {#if reasoning}
              <th class="right" title="tokens spent thinking, as reported by the provider">
                Reasoning
              </th>
            {/if}
            <th class="right">Cost</th>
          </tr>
        </thead>
        <tbody>
          {#each runs as run (run.id)}
            {@const author = authorOf(run, experiment)}
            <tr>
              <td>
                {displayName(run)}
                {#if run.model_name}<code>{run.model}</code>{/if}
              </td>
              <td>
                {#if author?.github}
                  <a href="https://github.com/{author.github}">{author.name}</a>
                {:else if author}
                  {author.name}
                {:else}
                  <span class="dim">unattributed</span>
                {/if}
              </td>
              <td>{run.created_at ? formatDate(run.created_at) : formatDate(experiment.created_at)}</td>
              <td>
                <span class="chip" class:ok={run.status === 'ok'} class:error={run.status === 'error'}>
                  {run.status}
                </span>
              </td>
              <td class="right">{formatLatency(run.latency_ms)}</td>
              {#if reasoning}
                <td class="right">
                  {reasoningTokens(run) ? reasoningTokens(run).toLocaleString() : '—'}
                </td>
              {/if}
              <td class="right">{formatCost(run.usage?.cost)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
</details>

<style>
  details {
    margin-bottom: 1.5rem;
    border: 1px solid var(--border-strong);
    border-radius: 0;
    background: var(--surface);
  }

  summary {
    padding: 0.4rem 0.95rem;
    background: var(--surface-2);
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 700;
  }

  summary:hover {
    background: var(--surface-3);
  }

  .hint {
    margin-left: 0.5rem;
    color: var(--text-dim);
    font-weight: 400;
    font-size: 0.75rem;
  }

  details[open] summary {
    border-bottom: 1px solid var(--border-strong);
  }

  .body {
    padding: 0.9rem 0.95rem;
  }

  /* Fact pairs laid out as a bordered grid — the closest thing the era had to a
     definition list was a table, so it reads like one. */
  dl {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
    gap: 1px;
    margin: 0 0 1.1rem;
    border: 1px solid var(--border);
    background: var(--border);
  }

  dl > div {
    padding: 0.35rem 0.55rem;
    background: var(--surface);
  }

  dt {
    color: var(--text-dim);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  dd {
    margin: 0.1rem 0 0;
    font-size: 0.82rem;
  }

  .files {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem 1rem;
    margin: 0 0 1.1rem;
    font-size: 0.78rem;
  }

  .files a {
    font-family: var(--mono);
  }

  .note {
    color: var(--text-dim);
  }

  .scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
  }

  th {
    text-align: left;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text);
    background: var(--surface-2);
    font-weight: 700;
  }

  th,
  td {
    padding: 0.35rem 0.55rem;
    border: 1px solid var(--border);
    white-space: nowrap;
  }

  tbody tr:hover td {
    background: var(--surface-2);
  }

  td code {
    margin-left: 0.4rem;
    color: var(--text-dim);
    font-size: 0.68rem;
  }

  .right {
    text-align: right;
  }

  .dim {
    color: var(--text-dim);
  }
</style>
