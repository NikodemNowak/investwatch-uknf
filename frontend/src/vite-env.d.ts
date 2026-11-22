/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" serves data/fixtures from src/mocks instead of calling the API. */
  readonly VITE_USE_MOCKS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
