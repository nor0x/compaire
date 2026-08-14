<script lang="ts">
  type Item = { src: string; alt: string; caption: string }

  let {
    items,
    index,
    onclose,
    onnavigate,
  }: {
    items: Item[]
    index: number
    onclose: () => void
    onnavigate: (index: number) => void
  } = $props()

  const current = $derived(items[index])

  function step(delta: number) {
    onnavigate((index + delta + items.length) % items.length)
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') onclose()
    else if (event.key === 'ArrowRight') step(1)
    else if (event.key === 'ArrowLeft') step(-1)
  }
</script>

<svelte:window on:keydown={onkeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
  class="backdrop"
  role="dialog"
  aria-modal="true"
  aria-label={current.caption}
  tabindex="-1"
  onclick={(event) => {
    if (event.target === event.currentTarget) onclose()
  }}
>
  <figure>
    <img src={current.src} alt={current.alt} />
    <figcaption>
      <span>{current.caption}</span>
      <span class="count">{index + 1} / {items.length}</span>
    </figcaption>
  </figure>

  {#if items.length > 1}
    <button type="button" class="nav prev" onclick={() => step(-1)} aria-label="Previous image"
      >‹</button
    >
    <button type="button" class="nav next" onclick={() => step(1)} aria-label="Next image">›</button>
  {/if}
  <button type="button" class="close" onclick={onclose} aria-label="Close">×</button>
</div>

<style>
  /* Flat opaque backdrop — no blur, no translucency. */
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    padding: 2rem 3.5rem;
    background: #101014;
  }

  figure {
    margin: 0;
    max-width: 100%;
    max-height: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  img {
    max-width: 100%;
    max-height: calc(100vh - 8rem);
    object-fit: contain;
    border: 1px solid #d0d0d0;
    border-radius: 0;
    background: #000;
  }

  figcaption {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.15rem 0.35rem;
    border: 1px solid #4a4a4a;
    background: #1c1c1c;
    color: #e6e6e6;
    font-size: 0.75rem;
  }

  .count {
    color: #9a9a9a;
    font-family: var(--mono);
  }

  button {
    position: absolute;
    width: 32px;
    height: 32px;
    display: grid;
    place-items: center;
    border: 1px solid #d0d0d0;
    border-radius: 0;
    background: #1c1c1c;
    color: #ffffff;
    font-family: var(--mono);
    font-size: 1.3rem;
    line-height: 1;
  }

  button:hover {
    background: #ffffff;
    color: #101014;
  }

  .prev {
    left: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
  }

  .next {
    right: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
  }

  .close {
    top: 0.75rem;
    right: 0.75rem;
    font-size: 1.35rem;
  }
</style>
