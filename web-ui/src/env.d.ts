/// <reference types="vite/client" />

interface ImportMeta {
  glob: (
    pattern: string,
    options?: {
      eager?: boolean
      import?: string
      as?: string
    }
  ) => Record<string, unknown>
}
