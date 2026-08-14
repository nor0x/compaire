<script lang="ts">
  import RunMeta from '../RunMeta.svelte'
  import { assetUrl, displayName, htmlOutputs } from '../data'
  import type { Experiment, Run } from '../types'

  let { experiment }: { experiment: Experiment } = $props()

  type Page = { run: Run; url: string; label: string }

  const pages = $derived(
    (experiment.runs ?? []).flatMap((run) =>
      htmlOutputs(run).map((output) => ({
        run,
        url: assetUrl(experiment.id, output.path),
        label: displayName(run),
      })),
    ) as Page[],
  )

  const WIDTHS = { desktop: '100%', tablet: '820px', mobile: '390px' } as const
  let device = $state<keyof typeof WIDTHS>('desktop')
  let columns = $state(2)
</script>

{#if pages.length === 0}
  <p class="empty">No pages were produced for this experiment.</p>
{:else}
  <div class="toolbar">
    <span class="toolbar-label">Width:</span>
    <div class="group" role="group" aria-label="Viewport width">
      {#each Object.keys(WIDTHS) as name (name)}
        <button
          type="button"
          class:active={device === name}
          onclick={() => (device = name as keyof typeof WIDTHS)}
        >
          {name}
        </button>
      {/each}
    </div>
    {#if pages.length > 1}
      <label class="columns">
        <span>Columns:</span>
        <input type="range" min="1" max="3" step="1" bind:value={columns} />
        <span class="count mono">{columns}</span>
      </label>
    {/if}
  </div>

  <div class="pages" style="--columns: {columns}">
    {#each pages as page (page.url)}
      <figure>
        <figcaption>
          <div class="title">
            <strong>{page.label}</strong>
            <code>{page.run.model}</code>
          </div>
          <div class="right">
            <RunMeta run={page.run} compact />
            <a href={page.url} target="_blank" rel="noopener noreferrer">open</a>
          </div>
        </figcaption>

        <!-- Contributed pages are arbitrary HTML from a pull request. The
             sandbox deliberately omits allow-same-origin, so scripts inside
             run in an opaque origin and cannot reach this page, its storage or
             the network as us. -->
        <iframe
          src={page.url}
          title="{page.label} result"
          sandbox="allow-scripts"
          referrerpolicy="no-referrer"
          loading="lazy"
          style="width: {WIDTHS[device]}"
        ></iframe>
      </figure>
    {/each}
  </div>
{/if}

<style>
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem 1rem;
    margin-bottom: 1rem;
  }

  .toolbar-label {
    font-size: 0.72rem;
    color: var(--text-dim);
  }

  .columns {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.72rem;
    color: var(--text-dim);
  }

  .columns input {
    width: 5rem;
  }

  .count {
    min-width: 1ch;
    color: var(--text);
  }

  .pages {
    display: grid;
    grid-template-columns: repeat(var(--columns), minmax(0, 1fr));
    gap: 1rem;
  }

  figure {
    margin: 0;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 0;
    overflow: hidden;
  }

  figcaption {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.35rem 0.7rem;
    border-bottom: 1px solid var(--border-strong);
    background: var(--surface-2);
    font-size: 0.8rem;
  }

  .title {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }

  .title code {
    color: var(--text-dim);
    font-size: 0.68rem;
  }

  .right {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.7rem;
  }

  /* The frame gets a hairline of its own so a white page still reads as an
     embedded document rather than part of ours. */
  iframe {
    display: block;
    height: 34rem;
    max-width: 100%;
    margin-inline: auto;
    border: 0;
    border-left: 1px solid var(--border);
    border-right: 1px solid var(--border);
    background: #fff;
  }

  @media (max-width: 860px) {
    .pages {
      grid-template-columns: 1fr;
    }
  }
</style>
