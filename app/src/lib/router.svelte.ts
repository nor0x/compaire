/**
 * A hash router.
 *
 * The site is deployed as static files on GitHub Pages, which cannot rewrite
 * unknown paths to index.html. Hash routes keep deep links working — and
 * shareable — without any server configuration.
 */

export type Route = { name: 'list' } | { name: 'experiment'; id: string }

function parse(hash: string): Route {
  const path = hash.replace(/^#\/?/, '')
  const [section, id] = path.split('/')
  if (section === 'e' && id) return { name: 'experiment', id: decodeURIComponent(id) }
  return { name: 'list' }
}

class Router {
  current = $state<Route>(parse(location.hash))

  constructor() {
    addEventListener('hashchange', () => {
      this.current = parse(location.hash)
      scrollTo({ top: 0 })
    })
  }
}

export const router = new Router()

export function experimentHref(id: string): string {
  return `#/e/${encodeURIComponent(id)}`
}

export function listHref(): string {
  return '#/'
}
