import { fileURLToPath } from 'node:url'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'
import { experiments } from './vite-plugin-experiments.js'

const repoRoot = fileURLToPath(new URL('..', import.meta.url))

// Deployed to GitHub Pages under /<repo>/. Override with BASE_PATH=/ for a
// user-page or custom-domain deploy.
const base = process.env.BASE_PATH ?? '/compaire/'

export default defineConfig({
  base,
  plugins: [svelte(), experiments(`${repoRoot}experiments`)],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
