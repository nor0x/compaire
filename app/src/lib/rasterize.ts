/**
 * Flatten an SVG to a PNG in the browser.
 *
 * Done here rather than in the CLI so contributors need no native rasterizer
 * and nothing extra gets committed. It also shows the flattening honestly: a
 * missing font or a reference the sanitizer dropped shows up in the raster,
 * which is often exactly what you want to see when comparing drawings.
 *
 * The asset is same-origin, so the canvas is never tainted and `toDataURL`
 * works. Scripts inside the SVG do not run — an <img> is an image, not a
 * document.
 */
export async function svgToPng(url: string, scale = 2): Promise<string> {
  const image = await loadImage(url)

  // An SVG with only a viewBox reports zero intrinsic size in some browsers.
  const width = Math.round((image.naturalWidth || 512) * scale)
  const height = Math.round((image.naturalHeight || 512) * scale)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height

  const context = canvas.getContext('2d')
  if (!context) throw new Error('this browser refused to provide a 2D canvas')
  context.drawImage(image, 0, 0, width, height)

  return canvas.toDataURL('image/png')
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('the drawing could not be rendered'))
    image.src = url
  })
}

/** Turn a data URL into a save prompt without leaving the page. */
export function downloadDataUrl(dataUrl: string, filename: string): void {
  const link = document.createElement('a')
  link.href = dataUrl
  link.download = filename
  link.click()
}
