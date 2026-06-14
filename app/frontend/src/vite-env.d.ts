/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MONITORING_TILE_PROVIDER?: string;
  readonly VITE_MAPTILER_API_KEY?: string;
  readonly VITE_MAPTILER_STYLE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
