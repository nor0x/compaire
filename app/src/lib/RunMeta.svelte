<script lang="ts">
  import { formatCost, formatLatency, reasoningTokens } from './data'
  import type { Run } from './types'

  let { run, compact = false }: { run: Run; compact?: boolean } = $props()

  const reasoning = $derived(reasoningTokens(run))
</script>

<div class="meta" class:compact>
  <span class="chip" class:ok={run.status === 'ok'} class:error={run.status === 'error'}>
    {run.status}
  </span>
  {#if run.latency_ms != null}
    <span title="round trip">{formatLatency(run.latency_ms)}</span>
  {/if}
  {#if run.usage?.total_tokens}
    <span title="prompt + completion tokens">{run.usage.total_tokens} tok</span>
  {/if}
  {#if reasoning}
    <span class="reasoning" title="tokens spent thinking, as reported by the provider">
      {reasoning.toLocaleString()} reasoning
    </span>
  {/if}
  {#if run.usage?.cost != null}
    <span title="reported cost">{formatCost(run.usage.cost)}</span>
  {/if}
</div>

<style>
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.45rem;
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 0.7rem;
  }

  .meta.compact {
    gap: 0.35rem;
    font-size: 0.66rem;
  }

  /* Worth spotting at a glance: it is usually where the tokens went. */
  .reasoning {
    padding: 0 0.35em;
    border: 1px solid var(--accent);
    border-radius: 0;
    background: var(--accent-soft);
    color: var(--accent);
  }
</style>
