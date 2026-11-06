/// <reference types="vite/client" />

/** ISO timestamp of the build, injected by Vite `define` (see vite.config.ts). */
declare const __BUILD_DATE__: string

declare module '*.sql?raw' {
  const sql: string
  export default sql
}
