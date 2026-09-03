import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：默认 8000，端口被占用时用 VITE_API_TARGET 换一个，
// 例如 set VITE_API_TARGET=http://127.0.0.1:8001 && npm run dev
const target = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    proxy: {
      // 开发时前后端分两个端口，靠代理避免跨域
      '/api': { target, changeOrigin: true },
      '/uploads': { target, changeOrigin: true }
    }
  }
})
