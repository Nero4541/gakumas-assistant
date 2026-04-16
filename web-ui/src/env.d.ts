/// <reference types="vite/client" />

import 'axios'

declare module 'axios' {
  interface AxiosResponse<T = any, D = any, H = {}> {
    message?: string
  }
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'

  const component: DefineComponent<Record<string, never>, Record<string, never>, any>

  export default component
}

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
