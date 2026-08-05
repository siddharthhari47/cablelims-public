import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Dev server binds on 0.0.0.0 so it is reachable from phones on the lab LAN
// (Scientific Assistant PWA), and proxies /api to the local FastAPI backend
// so the frontend can always call same-origin relative paths.
export default defineConfig({
  plugins: [
    react(),
    // Offline support, phase 1: installable app shell only -- precaches the
    // built JS/CSS/HTML so the app loads instantly on repeat visits, with NO
    // API caching yet (that's a later phase, with its own IndexedDB-backed
    // read/write layer, not Workbox's runtime cache). navigateFallbackDenylist
    // is explicit insurance against a future runtimeCaching rule accidentally
    // catching /api/* -- the SPA navigate-fallback itself only ever applies to
    // top-level page navigations, never to axios's fetch/XHR calls, but this
    // keeps that guarantee obvious rather than implicit.
    VitePWA({
      registerType: 'autoUpdate',
      // Registers the real service worker under `npm run dev` too (default
      // is build-only) -- this app is verified against the dev server
      // throughout the project, not a separate preview build, so this needs
      // to be on for that verification workflow to actually exercise it.
      devOptions: { enabled: true, type: 'module' },
      manifest: {
        name: 'CableLIMS — Scientific Assistant',
        short_name: 'CableLIMS',
        description: 'CableLIMS Scientific Assistant — cable conformity testing workflow',
        start_url: '/assistant',
        scope: '/',
        id: '/assistant',
        display: 'standalone',
        background_color: '#0B2447',
        theme_color: '#0B2447',
        orientation: 'portrait',
        icons: [
          { src: '/favicon.svg', sizes: 'any', type: 'image/svg+xml' },
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api/],
      },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
