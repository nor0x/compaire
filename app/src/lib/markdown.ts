import DOMPurify from 'dompurify'
import { marked } from 'marked'

/**
 * Render model output as HTML.
 *
 * Everything here comes from a pull request written by someone else and passed
 * through a language model, so it is treated as hostile: markdown is rendered,
 * then sanitized before it ever reaches the DOM.
 */
export function renderMarkdown(source: string): string {
  const html = marked.parse(source, { async: false, gfm: true, breaks: false }) as string
  return DOMPurify.sanitize(html, {
    FORBID_TAGS: ['style', 'form', 'input', 'button', 'iframe', 'object', 'embed'],
    FORBID_ATTR: ['style', 'srcset'],
    ADD_ATTR: ['target', 'rel'],
  })
}

/** Plain-text preview used for cards and collapsed table cells. */
export function excerpt(source: string, limit = 240): string {
  const flat = source
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`|-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return flat.length > limit ? `${flat.slice(0, limit).trimEnd()}…` : flat
}
