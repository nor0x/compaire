<script lang="ts">
  import RunMeta from '../RunMeta.svelte'
  import { assetUrl, displayName, visualOutputs } from '../data'
  import type { Experiment, Run } from '../types'

  let { experiment }: { experiment: Experiment } = $props()

  type Side = { run: Run; src: string; alt: string; label: string }

  const sides = $derived(
    (experiment.runs ?? []).flatMap((run) =>
      visualOutputs(run).map((image, sampleIndex) => ({
        run,
        src: assetUrl(experiment.id, image.path),
        alt: image.alt ?? `${displayName(run)} output`,
        label:
          visualOutputs(run).length > 1
            ? `${displayName(run)} #${sampleIndex + 1}`
            : displayName(run),
      })),
    ) as Side[],
  )

  let leftIndex = $state(0)
  let rightIndex = $state(1)
  let position = $state(50)

  const left = $derived(sides[Math.min(leftIndex, sides.length - 1)])
  const right = $derived(sides[Math.min(rightIndex, sides.length - 1)])
</script>

{#if sides.length < 2}
  <p class="empty">
    A slider compares two images; this experiment has {sides.length}. Try the gallery view instead.
  </p>
{:else}
  <div class="pickers">
    <label>
      <span>Left</span>
      <select bind:value={leftIndex}>
        {#each sides as side, index (side.src + index)}
          <option value={index}>{side.label}</option>
        {/each}
      </select>
    </label>
    <label>
      <span>Right</span>
      <select bind:value={rightIndex}>
        {#each sides as side, index (side.src + index)}
          <option value={index}>{side.label}</option>
        {/each}
      </select>
    </label>
  </div>

  <div class="stage" style="--position: {position}%">
    <img class="under" src={right.src} alt={right.alt} />
    <img class="over" src={left.src} alt={left.alt} />

    <div class="divider" aria-hidden="true"><span class="grip"></span></div>

    <!-- A range input keeps the divider usable with a keyboard and a screen
         reader, which a bare pointer-drag handle would not be. -->
    <input
      type="range"
      min="0"
      max="100"
      step="0.5"
      bind:value={position}
      aria-label="Reveal {left.label} on the left, {right.label} on the right"
    />

    <span class="badge left">{left.label}</span>
    <span class="badge right">{right.label}</span>
  </div>

  <div class="legend">
    <div><strong>{left.label}</strong><RunMeta run={left.run} compact /></div>
    <div class="align-right"><strong>{right.label}</strong><RunMeta run={right.run} compact /></div>
  </div>
{/if}

<style>
  .pickers {
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem 1rem;
    margin-bottom: 0.9rem;
    padding: 0.5rem 0.65rem;
    border: 1px solid var(--border);
    background: var(--surface-2);
  }

  .pickers label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.75rem;
    color: var(--text-dim);
  }

  select {
    font: inherit;
    font-family: var(--sans);
    font-size: 0.75rem;
    padding: 0.15rem 0.3rem;
    color: var(--text);
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: 0;
  }

  .stage {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--border-strong);
    border-radius: 0;
    background: var(--surface-2);
    line-height: 0;
    touch-action: pan-y;
  }

  .under,
  .over {
    display: block;
    width: 100%;
  }

  .over {
    position: absolute;
    inset: 0;
    height: 100%;
    object-fit: contain;
    clip-path: inset(0 calc(100% - var(--position)) 0 0);
  }

  .divider {
    position: absolute;
    top: 0;
    bottom: 0;
    left: var(--position);
    width: 3px;
    border-left: 1px solid #000;
    border-right: 1px solid #000;
    background: #fff;
    pointer-events: none;
  }

  /* A square handle with a hard border, not a floating pill. */
  .grip {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 22px;
    height: 30px;
    border: 1px solid #000;
    background: #fff;
  }

  input[type='range'] {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: ew-resize;
  }

  input[type='range']:focus-visible {
    opacity: 1;
    outline-offset: -2px;
  }

  .badge {
    position: absolute;
    bottom: 0.6rem;
    padding: 0.05em 0.5em;
    border: 1px solid #ffffff;
    border-radius: 0;
    background: #101014;
    color: #fff;
    font-family: var(--mono);
    font-size: 0.7rem;
    line-height: 1.7;
    pointer-events: none;
  }

  .badge.left {
    left: 0.6rem;
  }

  .badge.right {
    right: 0.6rem;
  }

  .legend {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin-top: 0.6rem;
    font-size: 0.78rem;
  }

  .legend div {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .align-right {
    align-items: flex-end;
  }

  .empty {
    color: var(--text-dim);
  }
</style>
