/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev/preview proxy to a local backend so the SPA can use same-origin relative URLs.
// Override with GRIDSTORM_API_PROXY (e.g. http://127.0.0.1:8010). Production uses VITE_API_BASE_URL.
const apiTarget = process.env.GRIDSTORM_API_PROXY ?? 'http://127.0.0.1:8000'
const proxy = {
  '/api': { target: apiTarget, changeOrigin: true },
  '/health': { target: apiTarget, changeOrigin: true },
  '/ready': { target: apiTarget, changeOrigin: true },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 1500,
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
  },
})
