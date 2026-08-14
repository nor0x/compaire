<script lang="ts">
  import { theme } from './theme.svelte'

  const label = $derived(
    { system: 'Theme: system', light: 'Theme: light', dark: 'Theme: dark' }[theme.current],
  )
</script>

<button type="button" onclick={() => theme.cycle()} title={label} aria-label={label}>
  {#if theme.current === 'system'}
    <svg viewBox="0 0 24 24" aria-hidden="true"
      ><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8" /></svg
    >
  {:else if theme.current === 'light'}
    <svg viewBox="0 0 24 24" aria-hidden="true"
      ><circle cx="12" cy="12" r="4.5" /><path
        d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"
      /></svg
    >
  {:else}
    <svg viewBox="0 0 24 24" aria-hidden="true"
      ><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" /></svg
    >
  {/if}
</button>

<style>
  button {
    display: grid;
    place-items: center;
    width: 28px;
    height: 26px;
    padding: 0;
    border: 1px solid var(--border-strong);
    border-radius: 0;
    background: var(--surface);
    color: var(--text);
  }

  button:hover {
    background: var(--surface-3);
  }

  button:active {
    background: var(--border-strong);
    color: var(--bg);
  }

  svg {
    width: 15px;
    height: 15px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.6;
    stroke-linecap: square;
    stroke-linejoin: miter;
  }
</style>
