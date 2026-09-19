import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/ui/' : '/',
  server: {
    fs: { allow: ['../..'] },
    proxy: Object.fromEntries(['/api', '/login', '/logout', '/oauth', '/social/oauth', '/docs', '/static'].map(path =>
      [path, { target: process.env.TUEKA_DEV_API_ORIGIN || 'http://127.0.0.1:8000' }])),
  },
  build: { outDir: 'dist', emptyOutDir: true, manifest: true, rollupOptions: { output: { manualChunks: { vendor: ['react', 'react-dom', 'react-router-dom'], query: ['@tanstack/react-query'] } } } },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', exclude: ['e2e/**', 'node_modules/**', 'dist/**'] }
}))
