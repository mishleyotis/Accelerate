/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CACHE_BUSTER?: string;
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __STANDALONE__: boolean;
