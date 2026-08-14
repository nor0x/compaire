<script lang="ts">
  import OutputCell from '../OutputCell.svelte'
  import RunMeta from '../RunMeta.svelte'
  import { displayName } from '../data'
  import type { Experiment } from '../types'

  let { experiment }: { experiment: Experiment } = $props()

  const runs = $derived(experiment.runs ?? [])

  // Columns work up to a handful of models; beyond that the cells get too
  // narrow to read and stacked rows are the better comparison.
  let layout = $state<'columns' | 'rows'>('columns')
  const effective = $derived(runs.length > 4 ? 'rows' : layout)
</script>

{#if runs.length === 0}
  <p class="empty">This experiment has no runs.</p>
{:else}
  {#if runs.length <= 4}
    <div class="toolbar">
      <span class="toolbar-label">Layout:</span>
      <div class="group" role="group" aria-label="Layout">
        <button
          type="button"
          class:active={layout === 'columns'}
          onclick={() => (layout = 'columns')}
        >
          Side by side
        </button>
        <button type="button" class:active={layout === 'rows'} onclick={() => (layout = 'rows')}>
          Stacked
        </button>
      </div>
    </div>
  {/if}

  <div class="board" class:rows={effective === 'rows'} style="--columns: {runs.length}">
    {#each runs as run (run.id)}
      <article>
        <header>
          <div class="title">
            <h2>{displayName(run)}</h2>
            {#if run.model_name}<code>{run.model}</code>{/if}
          </div>
          <RunMeta {run} compact />
        </header>
        <div class="cell">
          <OutputCell {run} experimentId={experiment.id} />
        </div>
      </article>
    {/each}
  </div>
{/if}

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .toolbar-label {
    font-size: 0.72rem;
    color: var(--text-dim);
  }

  .board {
    display: grid;
    grid-template-columns: repeat(var(--columns), minmax(18rem, 1fr));
    gap: 1rem;
    align-items: start;
    overflow-x: auto;
    padding-bottom: 0.5rem;
  }

  .board.rows {
    grid-template-columns: 1fr;
    overflow-x: visible;
  }

  article {
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 0;
    overflow: hidden;
  }

  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.4rem 0.7rem;
    border-bottom: 1px solid var(--border-strong);
    background: var(--surface-2);
  }

  .title {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }

  h2 {
    font-size: 1rem;
  }

  .title code {
    color: var(--text-dim);
    font-size: 0.68rem;
  }

  .cell {
    padding: 0.75rem 0.85rem;
  }

  .empty {
    color: var(--text-dim);
  }

  @media (max-width: 720px) {
    .board {
      grid-template-columns: 1fr;
      overflow-x: visible;
    }
  }
</style>
