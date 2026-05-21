import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // REST API calls are proxied to the FastAPI backend in development
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // WebSocket connections are proxied to the FastAPI backend in development
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
