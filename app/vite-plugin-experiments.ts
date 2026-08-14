import { cpSync, existsSync, readFileSync, statSync } from 'node:fs'
import { join, normalize, resolve, sep } from 'node:path'
import type { Plugin, ResolvedConfig } from 'vite'

/**
 * Serves the repo's `experiments/` directory to the site.
 *
 * The experiments live at the repository root — that is what contributors add
 * to in a pull request — while the site lives in `app`. Rather than
 * duplicating them into `public/` (or symlinking, which is awkward on Windows),
 * this plugin serves them straight from the root in dev and copies them into
 * the build output on `vite build`.
 */

const MIME: Record<string, string> = {
  '.json': 'application/json; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.toml': 'text/plain; charset=utf-8',
  '.webp': 'image/webp',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
}

const SEGMENT = '/experiments/'

export function experiments(sourceDir: string): Plugin {
  const root = resolve(sourceDir)
  let config: ResolvedConfig

  return {
    name: 'compaire-experiments',

    configResolved(resolved) {
      config = resolved
    },

    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? ''
        const at = url.indexOf(SEGMENT)
        if (at === -1) return next()

        // Everything after `/experiments/`, minus any query string.
        const relative = decodeURIComponent(url.slice(at + SEGMENT.length).split('?')[0])
        const target = normalize(join(root, relative))

        // Requests are untrusted: refuse anything that escapes the directory.
        if (!target.startsWith(root + sep) || !existsSync(target)) {
          res.statusCode = 404
          res.end('not found')
          return
        }
        if (!statSync(target).isFile()) return next()

        const extension = target.slice(target.lastIndexOf('.'))
        res.setHeader('Content-Type', MIME[extension] ?? 'application/octet-stream')
        res.setHeader('Cache-Control', 'no-cache')
        res.end(readFileSync(target))
      })
    },

    closeBundle() {
      if (config.command !== 'build' || !existsSync(root)) return
      cpSync(root, join(config.build.outDir, 'experiments'), { recursive: true })
    },
  }
}
