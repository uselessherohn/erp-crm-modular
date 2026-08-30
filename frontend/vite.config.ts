import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'axis-suite-icon.svg', 'axis-suite-logo.svg'],
      manifest: {
        name: 'Axis Suite',
        short_name: 'Axis Suite',
        description: 'ERP/CRM Modular por Paquetes — Axis Suite',
        lang: 'es',
        theme_color: '#1D5FA8',
        background_color: '#FFFFFF',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      // Sin runtime caching de /api ni de rutas del backend — la app
      // depende de datos siempre frescos (RLS multi-tenant, saldos de
      // stock/facturas). Solo se precachea el shell estático de la SPA.
      workbox: {
        navigateFallbackDenylist: [/^\/(auth|contacts|inventory|purchasing|sales|accounting|pipeline|hr|users|roles|companies|internal)\//],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
})
