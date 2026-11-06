// GitHub Pages serves 404.html for unknown paths. Copying the SPA shell there
// makes deep links such as /film/tt0120338 load the app, which then routes client-side.
import { copyFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const dist = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
const index = join(dist, 'index.html')
if (!existsSync(index)) {
  console.error('spa-fallback: dist/index.html not found; run vite build first')
  process.exit(1)
}
copyFileSync(index, join(dist, '404.html'))
console.log('spa-fallback: dist/404.html written')
