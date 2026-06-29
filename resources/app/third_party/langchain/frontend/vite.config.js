import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5199,
    proxy: {
      '/workflow': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/rewrite-styles': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/generated': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/uploads': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
