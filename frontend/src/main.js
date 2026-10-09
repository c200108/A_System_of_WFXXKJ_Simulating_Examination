import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from './App.vue'
import router from './router'
import { api } from './api'
import { setSiteConfig } from './siteConfig'

const app = createApp(App)
// 图标不再全量注册：整个站只用到两个（UploadFilled、ArrowDown），
// 全注册会把一千多个图标全打进主包，白白多出一百多 KB。
// 用到的那两个在各自页面里单独 import。
app.use(ElementPlus, { locale: zhCn })
app.use(router)
// 先把 config.yaml 的内容取回来再挂载，页面一上来就能用上里面的默认值。
// 取不到也照常启动，各页面回退到内置默认值。
api
  .siteConfig()
  .then(setSiteConfig)
  .catch(() => console.warn('读取 /api/config 失败，改用内置默认值'))
  .finally(() => app.mount('#app'))
