import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端地址：默认 8000，端口被占用时用 VITE_API_TARGET 换一个，
// 例如 set VITE_API_TARGET=http://127.0.0.1:8001 && npm run dev
const target = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  build: {
    // 机房里五十台机器同时开考，首屏体积就是五十份流量。把第三方库拆出来
    // 单独成块：它们的内容几乎不变，浏览器缓存一次能用很久，
    // 以后改业务代码只会让业务那一块的指纹变，库那几块继续命中缓存。
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('element-plus')) return 'el'
          // 图表库只有「成绩分析」页用，单独一块、跟着那一页按需加载 ——
          // 混进 vendor 的话每个页面（包括五十台机器同时打开的考试页）都得先下它
          if (id.includes('echarts') || id.includes('zrender')) return 'charts'
          // 在线座次的表格库（2.20.0）：只有打开「在线座次」才下载，别混进 vendor
          if (id.includes('exceljs')) return 'excel'
          if (id.includes('jspreadsheet') || id.includes('jsuites')) return 'sheet'
          if (id.includes('vue') || id.includes('pinia')) return 'vue'
          return 'vendor'
        }
      }
    }
  },
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    proxy: {
      // 开发时前后端分两个端口，靠代理避免跨域
      '/api': { target, changeOrigin: true },
      '/uploads': { target, changeOrigin: true }
    }
  }
})
