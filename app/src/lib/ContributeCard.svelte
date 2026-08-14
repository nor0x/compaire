<script lang="ts">
  import { modelsOf } from './data'
  import type { Experiment } from './types'

  let { experiment, repo }: { experiment: Experiment; repo: string } = $props()

  const models = $derived(modelsOf(experiment))
  const command = $derived(
    `compaire extend experiments/${experiment.id} -m your/model --author "Your Name"`,
  )

  let copied = $state(false)

  async function copy() {
    await navigator.clipboard.writeText(command)
    copied = true
    setTimeout(() => (copied = false), 1500)
  }
</script>

<section>
  <div class="head">
    <h2>Add your model to this comparison</h2>
    <a href="{repo}/blob/main/CONTRIBUTING.md">How contributing works</a>
  </div>

  <p>
    The prompt, sampling parameters and view are taken from this experiment, so your result lands
    directly comparable to the ones below. Run it, then open a pull request with the changed
    directory.
  </p>

  <div class="command">
    <code>{command}</code>
    <button type="button" class="btn" onclick={copy}>{copied ? 'Copied' : 'Copy'}</button>
  </div>

  <p class="covered">
    <span>Already covered:</span>
    {#each models as model (model)}
      <span class="chip mono">{model}</span>
    {/each}
  </p>
</section>

<style>
  section {
    padding: 0.85rem 0.95rem;
    margin-bottom: 1.5rem;
    border: 1px solid var(--border-strong);
    border-left: 5px solid var(--accent);
    border-radius: 0;
    background: var(--surface);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem 1rem;
  }

  h2 {
    font-size: 1.15rem;
  }

  .head a {
    font-size: 0.75rem;
  }

  p {
    margin: 0.5rem 0 0;
    color: var(--text-dim);
    font-size: 0.8rem;
    max-width: 48rem;
  }

  .command {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-top: 0.85rem;
    padding: 0.4rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 0;
    background: var(--surface-2);
  }

  .command code {
    flex: 1;
    font-size: 0.78rem;
    overflow-x: auto;
    white-space: nowrap;
  }

  .command .btn {
    flex: 0 0 auto;
  }

  .covered {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.3rem;
    margin-top: 0.85rem;
    font-size: 0.75rem;
  }
</style>
