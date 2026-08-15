<script lang="ts">
  import ExperimentList from "./lib/ExperimentList.svelte";
  import ExperimentPage from "./lib/ExperimentPage.svelte";
  import ThemeToggle from "./lib/ThemeToggle.svelte";
  import { listHref, router } from "./lib/router.svelte";

  const REPO = "https://github.com/nor0x/compaire";
  let isLogoHovered = false;
</script>

<header>
  <div class="wrap bar">
    <a class="brand" href={listHref()}>
      <img
        src={isLogoHovered ? "./logo_text_hover.svg" : "./logo_text.svg"}
        alt=""
        class="logo-text"
        onpointerenter={() => (isLogoHovered = true)}
        onpointerleave={() => (isLogoHovered = false)}
      />
    </a>
    <nav>
      <a href="{REPO}#contributing">Contribute</a>
      <span class="sep" aria-hidden="true">|</span>
      <a href={REPO}>GitHub</a>
      <ThemeToggle />
    </nav>
  </div>
</header>

<main class="wrap">
  {#if router.current.name === "experiment"}
    <ExperimentPage id={router.current.id} repo={REPO} />
  {:else}
    <ExperimentList />
  {/if}
</main>

<footer>
  <div class="wrap">
    <p>
      Every comparison here was produced with the <code>compaire</code> CLI and
      contributed as a pull request.
      <a href="{REPO}#contributing">Add your own</a>.
    </p>
    <p>
      made by <a href="https://johnnys.page" target="_blank" rel="noopener"
        >Johnny</a
      >
      &copy; {new Date().getFullYear()}
    </p>
  </div>
</footer>

<style>
  /* An opaque banner rule instead of a translucent blurred one: the early web
     had no compositing tricks, only lines. */
  header {
    position: sticky;
    top: 0;
    z-index: 20;
    background: var(--surface-2);
    border-bottom: 3px double var(--border-strong);
  }

  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    height: 54px;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text);
    font-family: var(--serif);
    font-weight: 700;
    font-size: 1.35rem;
    letter-spacing: 0;
    text-decoration: none;
  }

  .brand img {
    height: 1.2rem;
  }

  .brand:visited {
    color: var(--text);
  }

  .brand:hover {
    background: none;
    text-decoration: underline;
  }

  .brand em {
    font-style: normal;
    color: var(--accent);
  }

  .mark {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border: 1px solid var(--border-strong);
    background: var(--accent);
    color: var(--accent-text);
    font-family: var(--mono);
    font-weight: 700;
    font-size: 1rem;
  }

  nav {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 0.8rem;
  }

  nav a {
    color: var(--accent);
  }

  nav a:visited {
    color: var(--accent);
  }

  .sep {
    color: var(--border);
  }

  main {
    padding: 2rem 0 3rem;
    min-height: 70vh;
  }

  footer {
    border-top: 3px double var(--border-strong);
    padding: 1.25rem 0 3rem;
    color: var(--text-dim);
    font-size: 0.78rem;
    text-align: center;
  }

  footer p {
    margin: 0;
  }

  @media (max-width: 560px) {
    nav a,
    .sep {
      display: none;
    }
  }
</style>
