<script lang="ts">
  import RunMeta from '../RunMeta.svelte'
  import { assetUrl, displayName, loadAssetText, svgOutputs } from '../data'
  import { downloadDataUrl, svgToPng } from '../rasterize'
  import type { Experiment, Run, SvgOutput } from '../types'

  let { experiment }: { experiment: Experiment } = $props()

  type Drawing = { run: Run; output: SvgOutput; url: string; label: string; file: string }

  const drawings = $derived(
    (experiment.runs ?? []).flatMap((run) => {
      const outputs = svgOutputs(run)
      return outputs.map((output, index) => ({
        run,
        output,
        url: assetUrl(experiment.id, output.path),
        label: outputs.length > 1 ? `${displayName(run)} #${index + 1}` : displayName(run),
        file: `${experiment.id}-${run.id}.png`,
      }))
    }) as Drawing[],
  )

  const MODES = ['svg', 'png', 'code'] as const
  const MODE_LABEL = { svg: 'SVG', png: 'Rendered PNG', code: 'Code' }

  let mode = $state<(typeof MODES)[number]>('svg')
  let selected = $state(0)
  let copied = $state(false)
  let strip = $state<HTMLDivElement | null>(null)

  const current = $derived(drawings[Math.min(selected, drawings.length - 1)])

  // Both are keyed to the current drawing, so switching thumbnails refetches
  // and re-rasterizes without any manual invalidation.
  const source = $derived.by(() =>
    current ? loadAssetText(experiment.id, current.output.path) : Promise.resolve(''),
  )
  const raster = $derived.by(() =>
    current && mode === 'png' ? svgToPng(current.url) : Promise.resolve(''),
  )

  function select(index: number, focus = false) {
    selected = (index + drawings.length) % drawings.length
    if (focus) {
      // Roving focus, so arrow keys keep working after the selection moves.
      queueMicrotask(() =>
        strip?.querySelectorAll('button')[selected]?.focus({ preventScroll: false }),
      )
    }
  }

  function onStripKey(event: KeyboardEvent) {
    if (event.key === 'ArrowRight') select(selected + 1, true)
    else if (event.key === 'ArrowLeft') select(selected - 1, true)
    else return
    event.preventDefault()
  }

  async function copySource() {
    await navigator.clipboard.writeText(await source)
    copied = true
    setTimeout(() => (copied = false), 1500)
  }
</script>

{#if drawings.length === 0}
  <p class="empty">No drawings were produced for this experiment.</p>
{:else}
  <div class="toolbar">
    <div class="group" role="group" aria-label="Preview mode">
      {#each MODES as name (name)}
        <button type="button" class:active={mode === name} onclick={() => (mode = name)}>
          {MODE_LABEL[name]}
        </button>
      {/each}
    </div>

    <div class="current">
      <strong>{current.label}</strong>
      <code>{current.run.model}</code>
      <RunMeta run={current.run} compact />
    </div>
  </div>

  {#if current.output.sanitized}
    <p class="sanitized">
      <strong>Sanitized.</strong> This drawing is not byte-for-byte what the model returned —
      {current.output.removed?.join(', ')}
      {(current.output.removed?.length ?? 0) === 1 ? 'was' : 'were'} removed before it was committed.
    </p>
  {/if}

  <div class="stage">
    {#if mode === 'svg'}
      <!-- Rendered as an image, never inlined into the page: an <img> executes
           no scripts, fetches nothing external, and cannot leak the drawing's
           own CSS into the site around it. -->
      <img src={current.url} alt={current.output.alt ?? `${current.label} drawing`} />
    {:else if mode === 'png'}
      {#await raster}
        <p class="note">Rasterizing…</p>
      {:then dataUrl}
        <img src={dataUrl} alt="{current.label} rendered to PNG" />
        <button
          type="button"
          class="btn download"
          onclick={() => downloadDataUrl(dataUrl, current.file)}
        >
          Download PNG
        </button>
      {:catch error}
        <p class="note error">Could not rasterize this drawing: {error.message}</p>
      {/await}
    {:else}
      {#await source}
        <p class="note">Loading source…</p>
      {:then text}
        <div class="code">
          <button type="button" class="btn copy" onclick={copySource}
            >{copied ? 'Copied' : 'Copy'}</button
          >
          <pre>{text}</pre>
        </div>
      {:catch error}
        <p class="note error">Could not load the source: {error.message}</p>
      {/await}
    {/if}
  </div>

  {#if drawings.length > 1}
    <div
      class="thumbs"
      bind:this={strip}
      role="listbox"
      aria-label="Results"
      tabindex="-1"
      onkeydown={onStripKey}
    >
      {#each drawings as drawing, index (drawing.url + index)}
        <button
          type="button"
          role="option"
          aria-selected={index === selected}
          class:active={index === selected}
          onclick={() => select(index)}
        >
          <img src={drawing.url} alt="" loading="lazy" />
          <span>{drawing.label}</span>
          {#if drawing.output.sanitized}
            <span class="flag" title="Sanitized before it was committed">!</span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
{/if}

<style>
  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem 1rem;
    margin-bottom: 1rem;
  }

  .current {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8rem;
  }

  .current code {
    color: var(--text-dim);
    font-size: 0.7rem;
  }

  .sanitized {
    margin: 0 0 1rem;
    padding: 0.6rem 0.8rem;
    border: 1px solid var(--border-strong);
    border-left: 5px solid var(--accent);
    border-radius: 0;
    background: var(--accent-soft);
    font-size: 0.78rem;
  }

  .stage {
    position: relative;
    display: grid;
    place-items: center;
    min-height: 22rem;
    padding: 1.5rem;
    border: 1px solid var(--border-strong);
    border-radius: 0;
    background:
      linear-gradient(45deg, var(--surface-2) 25%, transparent 25%) -8px 0 / 16px 16px,
      linear-gradient(-45deg, var(--surface-2) 25%, transparent 25%) -8px 0 / 16px 16px,
      linear-gradient(45deg, transparent 75%, var(--surface-2) 75%) -8px 0 / 16px 16px,
      linear-gradient(-45deg, transparent 75%, var(--surface-2) 75%) -8px 0 / 16px 16px,
      var(--surface);
  }

  .stage > img {
    max-width: 100%;
    max-height: 34rem;
  }

  .download {
    position: absolute;
    right: 0.9rem;
    bottom: 0.9rem;
  }

  .code {
    position: relative;
    width: 100%;
    align-self: stretch;
  }

  .code pre {
    margin: 0;
    padding: 0.6rem;
    max-height: 32rem;
    overflow: auto;
    border: 1px solid var(--border);
    background: var(--surface);
    font-family: var(--mono);
    font-size: 0.78rem;
    line-height: 1.5;
    tab-size: 2;
  }

  .copy {
    position: absolute;
    top: 0.35rem;
    right: 0.9rem;
  }

  .thumbs {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.75rem;
    padding-bottom: 0.4rem;
    overflow-x: auto;
  }

  .thumbs button {
    position: relative;
    flex: 0 0 auto;
    width: 8rem;
    padding: 0.4rem;
    border: 1px solid var(--border);
    border-radius: 0;
    background: var(--surface);
    color: var(--text-dim);
    text-align: center;
  }

  .thumbs button:hover {
    border-color: var(--border-strong);
    background: var(--surface-2);
    color: var(--text);
  }

  /* Selected thumbnail is inverted rather than tinted, so it reads at a glance
     on a page of hairline boxes. */
  .thumbs button.active {
    border-color: var(--accent);
    background: var(--accent);
    color: var(--accent-text);
  }

  .thumbs img {
    display: block;
    width: 100%;
    aspect-ratio: 1;
    object-fit: contain;
  }

  .thumbs span {
    display: block;
    margin-top: 0.3rem;
    font-size: 0.68rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .flag {
    position: absolute;
    top: 0;
    right: 0;
    display: grid;
    place-items: center;
    width: 1.1rem;
    height: 1.1rem;
    border-left: 1px solid var(--border-strong);
    border-bottom: 1px solid var(--border-strong);
    background: var(--error);
    color: #fff;
    font-family: var(--mono);
    font-size: 0.7rem;
    font-weight: 700;
  }

  .note {
    margin: 0;
    color: var(--text-dim);
    font-size: 0.875rem;
  }

  .note.error {
    color: var(--error);
  }

  .empty {
    color: var(--text-dim);
  }
</style>
