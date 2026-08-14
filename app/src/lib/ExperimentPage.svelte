<script lang="ts">
  import ContributeCard from './ContributeCard.svelte'
  import DetailsPanel from './DetailsPanel.svelte'
  import PromptPanel from './PromptPanel.svelte'
  import { contributorsOf, formatCost, formatDate, loadExperiment, totalCost } from './data'
  import { listHref } from './router.svelte'
  import type { Experiment } from './types'
  import GalleryView from './views/GalleryView.svelte'
  import HtmlView from './views/HtmlView.svelte'
  import SliderView from './views/SliderView.svelte'
  import SvgView from './views/SvgView.svelte'
  import TableView from './views/TableView.svelte'

  let { id, repo }: { id: string; repo: string } = $props()

  let experiment = $state<Experiment | null>(null)
  let error = $state<string | null>(null)

  // Re-run whenever the route changes to a different experiment.
  $effect(() => {
    const wanted = id
    experiment = null
    error = null
    loadExperiment(wanted)
      .then((loaded) => {
        if (wanted === id) experiment = loaded
      })
      .catch((cause: Error) => {
        if (wanted === id) error = cause.message
      })
  })

  const failed = $derived(experiment?.runs?.filter((run) => run.status === 'error') ?? [])
  const contributors = $derived(experiment ? contributorsOf(experiment) : [])
</script>

<a class="back" href={listHref()}>← All experiments</a>

{#if error}
  <p class="state error">Could not load <code>{id}</code>: {error}</p>
{:else if !experiment}
  <p class="state">Loading…</p>
{:else}
  <header>
    <h1>{experiment.title}</h1>
    {#if experiment.description}
      <p class="description">{experiment.description}</p>
    {/if}
    <div class="meta">
      <span>{formatDate(experiment.created_at)}</span>
      {#if experiment.author}
        <span>
          started by
          {#if experiment.author.github}
            <a href="https://github.com/{experiment.author.github}">{experiment.author.name}</a>
          {:else}
            {experiment.author.name}
          {/if}
        </span>
      {/if}
      {#if contributors.length > 1}
        <span>{contributors.length} contributors</span>
      {/if}
      {#if experiment.updated_at}
        <span>extended {formatDate(experiment.updated_at)}</span>
      {/if}
      <span>{experiment.runs?.length ?? 0} runs</span>
      <span>{formatCost(totalCost(experiment))} total</span>
      {#each experiment.tags ?? [] as tag (tag)}
        <span class="chip">{tag}</span>
      {/each}
    </div>
  </header>

  <PromptPanel prompt={experiment.prompt} />

  <ContributeCard {experiment} {repo} />

  <DetailsPanel {experiment} />

  {#if failed.length}
    <div class="failures">
      <strong>{failed.length} run{failed.length === 1 ? '' : 's'} failed.</strong>
      <ul>
        {#each failed as run (run.id)}
          <li><code>{run.model}</code> — {run.error}</li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if experiment.view === 'gallery'}
    <GalleryView {experiment} />
  {:else if experiment.view === 'slider'}
    <SliderView {experiment} />
  {:else if experiment.view === 'html'}
    <HtmlView {experiment} />
  {:else if experiment.view === 'svg'}
    <SvgView {experiment} />
  {:else}
    <TableView {experiment} />
  {/if}
{/if}

<style>
  .back {
    display: inline-block;
    margin-bottom: 1rem;
    font-size: 0.78rem;
  }

  header {
    margin-bottom: 1.5rem;
    padding-bottom: 0.9rem;
    border-bottom: 3px double var(--border-strong);
  }

  h1 {
    font-size: clamp(1.6rem, 1.1rem + 2vw, 2.3rem);
  }

  .description {
    margin: 0.5rem 0 0;
    color: var(--text-dim);
    font-size: 0.85rem;
    max-width: 55rem;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem 0.9rem;
    margin-top: 0.8rem;
    color: var(--text-dim);
    font-size: 0.75rem;
  }

  .failures {
    margin: 1.25rem 0;
    padding: 0.7rem 0.9rem;
    border: 1px solid var(--error);
    border-left: 5px solid var(--error);
    border-radius: 0;
    background: var(--error-soft);
    font-size: 0.8rem;
  }

  .failures ul {
    margin: 0.4rem 0 0;
    padding-left: 1.2rem;
  }

  .state {
    color: var(--text-dim);
  }

  .state.error {
    color: var(--error);
  }
</style>
