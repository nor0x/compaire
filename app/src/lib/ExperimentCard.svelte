<script lang="ts">
  import { assetUrl, formatDate } from './data'
  import { experimentHref } from './router.svelte'
  import type { IndexEntry } from './types'

  let { entry }: { entry: IndexEntry } = $props()

  const VIEW_LABEL: Record<string, string> = {
    gallery: 'gallery',
    slider: 'slider',
    table: 'table',
    html: 'pages',
    svg: 'drawings',
    text: 'text',
  }
</script>

<a class="card" href={experimentHref(entry.id)}>
  <div class="thumb" class:empty={!entry.thumb}>
    {#if entry.thumb}
      <img src={assetUrl(entry.id, entry.thumb)} alt="" loading="lazy" />
    {:else}
      <span class="glyph">{entry.run_count ?? 0}</span>
    {/if}
    <span class="chip view">{VIEW_LABEL[entry.view] ?? entry.view}</span>
  </div>

  <div class="body">
    <h2>{entry.title}</h2>
    {#if entry.description}
      <p class="description">{entry.description}</p>
    {/if}

    <ul class="models">
      {#each (entry.models ?? []).slice(0, 3) as model (model)}
        <li class="mono">{model}</li>
      {/each}
      {#if (entry.models ?? []).length > 3}
        <li class="more">+{(entry.models ?? []).length - 3}</li>
      {/if}
    </ul>

    <div class="meta">
      <span>{entry.run_count} run{entry.run_count === 1 ? '' : 's'}</span>
      <span class="dot" aria-hidden="true">·</span>
      <span>
        {entry.updated_at
          ? `extended ${formatDate(entry.updated_at)}`
          : formatDate(entry.created_at)}
      </span>
      {#if (entry.contributors ?? 1) > 1}
        <span class="dot" aria-hidden="true">·</span>
        <span>{entry.contributors} contributors</span>
      {:else if entry.author}
        <span class="dot" aria-hidden="true">·</span>
        <span>{entry.author.name}</span>
      {/if}
    </div>
  </div>
</a>

<style>
  .card {
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 0;
    overflow: hidden;
    color: var(--text);
    text-decoration: none;
  }

  .card:visited {
    color: var(--text);
  }

  /* No lift, no soft shadow — a hard offset block, the way a table cell with a
     drop shadow GIF used to read. */
  .card:hover {
    background: var(--surface-2);
    box-shadow: var(--shadow);
  }

  .card:hover h2 {
    text-decoration: underline;
  }

  .thumb {
    position: relative;
    aspect-ratio: 16 / 9;
    background: var(--surface-2);
    border-bottom: 1px solid var(--border-strong);
    overflow: hidden;
  }

  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .thumb.empty {
    display: grid;
    place-items: center;
    background: var(--surface-2);
  }

  .glyph {
    font-family: var(--mono);
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--border);
  }

  .chip.view {
    position: absolute;
    top: 0;
    left: 0;
    border-top: 0;
    border-left: 0;
    background: var(--surface);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.8rem 0.9rem 0.9rem;
    flex: 1;
  }

  h2 {
    font-size: 1.15rem;
    color: var(--accent);
  }

  .description {
    margin: 0;
    color: var(--text-dim);
    font-size: 0.8rem;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .models {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
    margin: 0.15rem 0 0;
    padding: 0;
    list-style: none;
    font-size: 0.68rem;
  }

  .models li {
    padding: 0 0.35em;
    border: 1px solid var(--border);
    background: var(--surface-2);
    color: var(--text-dim);
  }

  .models .more {
    border-color: transparent;
    background: transparent;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.4rem;
    margin-top: auto;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
    color: var(--text-dim);
    font-size: 0.7rem;
  }

  .dot {
    color: var(--border);
  }
</style>
