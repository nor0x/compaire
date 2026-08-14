/** Theme preference: follow the OS unless the visitor has chosen otherwise. */

export type Theme = 'system' | 'light' | 'dark'

const KEY = 'compaire-theme'

function stored(): Theme {
  const value = localStorage.getItem(KEY)
  return value === 'light' || value === 'dark' ? value : 'system'
}

function apply(theme: Theme): void {
  if (theme === 'system') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.setAttribute('data-theme', theme)
}

class ThemeStore {
  current = $state<Theme>(stored())

  constructor() {
    apply(this.current)
  }

  cycle(): void {
    const order: Theme[] = ['system', 'light', 'dark']
    this.set(order[(order.indexOf(this.current) + 1) % order.length])
  }

  set(theme: Theme): void {
    this.current = theme
    localStorage.setItem(KEY, theme)
    apply(theme)
  }
}

export const theme = new ThemeStore()
