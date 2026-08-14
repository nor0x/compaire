<script lang="ts">
  import Lightbox from '../Lightbox.svelte'
  import RunMeta from '../RunMeta.svelte'
  import { assetUrl, displayName, groupByModel, visualOutputs } from '../data'
  import type { Experiment, Run } from '../types'

  let { experiment }: { experiment: Experiment } = $props()

  type Shot = { run: Run; src: string; alt: string; caption: string }

  const groups = $derived(
    groupByModel((experiment.runs ?? []).filter((run) => visualOutputs(run).length > 0)).map(
      (group) => ({
        ...group,
        shots: group.runs.flatMap((run) =>
          visualOutputs(run).map((image) => ({
            run,
            src: assetUrl(experiment.id, image.path),
            alt: image.alt ?? `${displayName(run)} output`,
            caption: displayName(run),
          })),
        ),
      }),
    ),
  )

  // One flat list so the lightbox can page through every image in order.
  const all = $derived(groups.flatMap((group) => group.shots) as Shot[])

  let lightboxIndex = $state<number | null>(null)
</script>

{#if all.length === 0}
  <p class="empty">No images were produced for this experiment.</p>
{:else}
  {#each groups as group (group.model)}
    <section>
      <header>
        <h2>{group.name}</h2>
        <code>{group.model}</code>
        <RunMeta run={group.runs[0]} compact />
      </header>

      <div class="shots">
        {#each group.shots as shot (shot.src)}
          <button
            type="button"
            class="shot"
            onclick={() => (lightboxIndex = all.findIndex((candidate) => candidate.src === shot.src))}
            aria-label="Open {shot.alt} full size"
          >
            <img src={shot.src} alt={shot.alt} loading="lazy" />
          </button>
        {/each}
      </div>
    </section>
  {/each}

  {#if lightboxIndex !== null}
    <Lightbox
      items={all}
      index={lightboxIndex}
      onclose={() => (lightboxIndex = null)}
      onnavigate={(next) => (lightboxIndex = next)}
    />
  {/if}
{/if}

<style>
  section {
    margin-bottom: 2.25rem;
  }

  /* Section rule with the model name sitting on it, like a chapter heading. */
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 0.5rem 0.8rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.35rem;
    border-bottom: 3px double var(--border-strong);
  }

  h2 {
    font-size: 1.2rem;
  }

  header code {
    color: var(--text-dim);
    font-size: 0.72rem;
  }

  .shots {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 14rem), 1fr));
    gap: 0.75rem;
  }

  .shot {
    padding: 0;
    border: 1px solid var(--border-strong);
    border-radius: 0;
    overflow: hidden;
    background: var(--surface-2);
    line-height: 0;
  }

  .shot:hover {
    box-shadow: var(--shadow);
    outline: 1px solid var(--accent);
    outline-offset: -1px;
  }

  .shot img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: cover;
    display: block;
  }

  .empty {
    color: var(--text-dim);
  }
</style>
