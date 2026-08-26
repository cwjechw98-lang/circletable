import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:43117'
const wsTarget = proxyTarget.replace('http://', 'ws://').replace('https://', 'wss://')

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
  server: {
    host: '127.0.0.1',
    port: 43118,
    proxy: {
      '/api': proxyTarget,
      '/ws': {
        target: wsTarget,
        ws: true,
      },
    },
  },
})
