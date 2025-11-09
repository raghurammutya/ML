import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    host: true,           // bind 0.0.0.0
    port: 3000,
    strictPort: true,
    proxy: {
      // ───── Your core chart endpoints ─────
      '/history': {
        target: 'http://tv-backend-dev:8000',  // <-- dev backend container by name
        changeOrigin: true,
      },
      '/marks': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },
      // If your chart also calls this TradingView endpoint, keep it:
      '/timescale_marks': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },

      // ───── Dashboard health/stats (optional) ─────
      '/health': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },
      '/stats': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },
      
      // ───── Labels API endpoint ─────
      '/api/labels': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },
      
      // ───── Monitor endpoints ─────
      '/monitor': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },

      // ───── F&O Analytics endpoints ─────
      '/fo': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },

      // ───── Instruments API endpoints ─────
      '/instruments': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },

      // ───── Indicators API endpoints ─────
      '/indicators': {
        target: 'http://tv-backend-dev:8000',
        changeOrigin: true,
      },

      // ───── Keep any other routes you actually use ─────
      // Example: if you have a config endpoint:
      // '/config': {
      //   target: 'http://127.0.0.1:8082',
      //   changeOrigin: true,
      // },
      //
      // If you really need an '/api' umbrella, you can keep it,
      // but DO NOT rewrite /history or /marks through it unless your backend expects that.
      // '/api': {
      //   target: 'http://127.0.0.1:8082',
      //   changeOrigin: true,
      //   // rewrite: (path: string) => path.replace(/^\/api/, ''),
      // },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
