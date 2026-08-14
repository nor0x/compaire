<script lang="ts">
  import type { PromptSpec } from './types'

  let { prompt }: { prompt: PromptSpec } = $props()

  let expanded = $state(false)
  let copied = $state(false)

  const long = $derived(prompt.text.length > 420 || prompt.text.split('\n').length > 8)

  // Only the parameters that were actually set are worth showing.
  const params = $derived(
    Object.entries(prompt.params ?? {}).filter(([, value]) => value !== null && value !== undefined),
  )

  async function copy() {
    await navigator.clipboard.writeText(prompt.text)
    copied = true
    setTimeout(() => (copied = false), 1500)
  }
</script>

<section class="panel">
  <div class="head">
    <h2>Prompt</h2>
    <div class="actions">
      {#each params as [key, value] (key)}
        <span class="chip mono">{key}: {value}</span>
      {/each}
      <button type="button" class="btn" onclick={copy}>{copied ? 'copied' : 'copy'}</button>
    </div>
  </div>

  {#if prompt.system}
    <p class="system"><span class="label">system</span>{prompt.system}</p>
  {/if}

  <pre class:clamped={long && !expanded}>{prompt.text}</pre>

  {#if long}
    <button type="button" class="more" onclick={() => (expanded = !expanded)}>
      {expanded ? 'Show less' : 'Show full prompt'}
    </button>
  {/if}
</section>

<style>
  /* A titled box: caption bar on top, content beneath — the panel idiom of the
     table-layout era. */
  .panel {
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 0;
    padding: 0.85rem 0.95rem;
    margin-bottom: 1.5rem;
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin: -0.85rem -0.95rem 0.75rem;
    padding: 0.35rem 0.95rem;
    border-bottom: 1px solid var(--border-strong);
    background: var(--surface-2);
  }

  h2 {
    font-family: var(--sans);
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
  }

  .system {
    margin: 0 0 0.6rem;
    color: var(--text-dim);
    font-size: 0.8rem;
  }

  .label {
    display: inline-block;
    margin-right: 0.5rem;
    padding: 0 0.35em;
    border: 1px solid var(--border);
    background: var(--surface-2);
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 0.68rem;
  }

  pre {
    margin: 0;
    padding: 0;
    font-family: var(--mono);
    font-size: 0.85rem;
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  pre.clamped {
    display: -webkit-box;
    -webkit-line-clamp: 6;
    line-clamp: 6;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .more {
    margin-top: 0.6rem;
    padding: 0;
    border: 0;
    background: none;
    color: var(--accent);
    font-size: 0.78rem;
    text-decoration: underline;
  }
</style>
