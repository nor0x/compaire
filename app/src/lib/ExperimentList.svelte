<script lang="ts">
  import ExperimentCard from './ExperimentCard.svelte'
  import { loadIndex } from './data'
  import type { IndexEntry } from './types'

  let entries = $state<IndexEntry[]>([])
  let error = $state<string | null>(null)
  let loading = $state(true)

  let query = $state('')
  let activeTag = $state<string | null>(null)

  loadIndex()
    .then((loaded) => (entries = loaded))
    .catch((cause: Error) => (error = cause.message))
    .finally(() => (loading = false))

  const tags = $derived(
    [...new Set(entries.flatMap((entry) => entry.tags ?? []))].sort((a, b) => a.localeCompare(b)),
  )

  const visible = $derived.by(() => {
    const needle = query.trim().toLowerCase()
    return entries.filter((entry) => {
      if (activeTag && !(entry.tags ?? []).includes(activeTag)) return false
      if (!needle) return true
      const haystack = [entry.title, entry.description ?? '', ...(entry.models ?? [])]
        .join(' ')
        .toLowerCase()
      return haystack.includes(needle)
    })
  })
</script>

<section class="hero">
  <h1>See how models actually differ.</h1>
  <p>
    One prompt, many models, side by side. Every comparison below is reproducible from the
    <code>spec.toml</code> committed next to it.
  </p>
</section>

{#if loading}
  <p class="state">Loading experiments…</p>
{:else if error}
  <p class="state error">Could not load the experiment index: {error}</p>
{:else if entries.length === 0}
  <p class="state">
    No experiments yet. Run <code>compaire run</code> and open a pull request to add the first one.
  </p>
{:else}
  <div class="controls">
    <label class="search">
      <span>Find:</span>
      <input
        type="search"
        bind:value={query}
        placeholder="titles, descriptions, models…"
        aria-label="Search experiments"
      />
    </label>
    {#if tags.length}
      <div class="tags">
        <span class="tags-label">Tags:</span>
        <button
          type="button"
          class="btn"
          class:selected={activeTag === null}
          onclick={() => (activeTag = null)}>all</button
        >
        {#each tags as tag (tag)}
          <button
            type="button"
            class="btn"
            class:selected={activeTag === tag}
            onclick={() => (activeTag = activeTag === tag ? null : tag)}>{tag}</button
          >
        {/each}
      </div>
    {/if}
  </div>

  {#if visible.length === 0}
    <p class="state">Nothing matches that filter.</p>
  {:else}
    <div class="grid">
      {#each visible as entry (entry.id)}
        <ExperimentCard {entry} />
      {/each}
    </div>
  {/if}
{/if}

<style>
  /* A masthead block, ruled off from the listing below it. */
  .hero {
    margin-bottom: 1.75rem;
    padding-bottom: 1.25rem;
    border-bottom: 1px solid var(--border);
    text-align: center;
  }

  .hero h1 {
    font-size: clamp(1.9rem, 1.2rem + 2.6vw, 2.9rem);
    margin-bottom: 0.5rem;
  }

  .hero p {
    max-width: 42rem;
    margin: 0 auto;
    color: var(--text-dim);
    font-size: 0.85rem;
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem 1rem;
    margin-bottom: 1.25rem;
    padding: 0.6rem 0.75rem;
    border: 1px solid var(--border);
    background: var(--surface-2);
  }

  .search {
    display: flex;
    flex: 1 1 18rem;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.78rem;
    color: var(--text-dim);
  }

  input[type='search'] {
    flex: 1;
    min-width: 0;
    padding: 0.3rem 0.5rem;
    font: inherit;
    font-size: 0.8rem;
    color: var(--text);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 0;
  }

  input[type='search']:focus {
    outline: 1px solid var(--accent);
    outline-offset: -2px;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
  }

  .tags-label {
    margin-right: 0.15rem;
    font-size: 0.78rem;
    color: var(--text-dim);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 19rem), 1fr));
    gap: 1rem;
  }

  .state {
    color: var(--text-dim);
  }

  .state.error {
    color: var(--error);
  }
</style>
