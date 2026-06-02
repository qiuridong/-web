/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MANAGER_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
