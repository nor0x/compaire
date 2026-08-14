<script lang="ts">
  import { assetUrl, imageOutputs, loadText, textOutputs } from './data'
  import { renderMarkdown } from './markdown'
  import type { Run } from './types'

  let { run, experimentId }: { run: Run; experimentId: string } = $props()

  let expanded = $state(false)
  let copied = $state(false)

  const texts = $derived(textOutputs(run))
  const images = $derived(imageOutputs(run))

  // Large outputs live in their own file, so the text may still be arriving.
  const body = $derived.by(async () =>
    (await Promise.all(texts.map((output) => loadText(experimentId, output)))).join('\n\n'),
  )

  async function copy(source: string) {
    await navigator.clipboard.writeText(source)
    copied = true
    setTimeout(() => (copied = false), 1500)
  }
</script>

{#if run.status === 'error'}
  <p class="failed">{run.error}</p>
{:else}
  {#if images.length}
    <div class="images">
      {#each images as image (image.path)}
        <a href={assetUrl(experimentId, image.path)} target="_blank" rel="noopener noreferrer">
          <img src={assetUrl(experimentId, image.path)} alt={image.alt ?? ''} loading="lazy" />
        </a>
      {/each}
    </div>
  {/if}

  {#await body}
    <p class="loading">Loading output…</p>
  {:then text}
    {#if text.trim()}
      <div class="text">
        <div class="prose" class:clamped={text.length > 900 && !expanded}>
          {@html renderMarkdown(text)}
        </div>
        <div class="tools">
          {#if text.length > 900}
            <button type="button" class="btn" onclick={() => (expanded = !expanded)}>
              {expanded ? 'Collapse' : 'Expand'}
            </button>
          {/if}
          <button type="button" class="btn" onclick={() => copy(text)}>
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
    {:else if !images.length}
      <p class="loading">No output.</p>
    {/if}
  {:catch error}
    <p class="failed">Could not load the output: {error.message}</p>
  {/await}
{/if}

<style>
  .failed {
    margin: 0;
    color: var(--error);
    font-size: 0.8rem;
  }

  .loading {
    margin: 0;
    color: var(--text-dim);
    font-size: 0.8rem;
  }

  .images {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .images img {
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 0;
    display: block;
  }

  .text {
    font-size: 0.82rem;
  }

  .clamped {
    max-height: 22rem;
    overflow: hidden;
    -webkit-mask-image: linear-gradient(to bottom, #000 78%, transparent);
    mask-image: linear-gradient(to bottom, #000 78%, transparent);
  }

  .tools {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.6rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border);
  }
</style>
