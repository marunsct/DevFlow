import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        // The app and its API answer on one port, 8000.
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
