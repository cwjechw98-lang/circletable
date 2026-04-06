import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxyTarget = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'
const wsTarget = proxyTarget.replace('http://', 'ws://').replace('https://', 'wss://')

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': proxyTarget,
      '/ws': {
        target: wsTarget,
        ws: true,
      },
    },
  },
})
