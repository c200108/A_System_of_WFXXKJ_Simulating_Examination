import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
// 手机适配放在 Element Plus 样式之后，才盖得住它
import './styles/mobile.css'

// 挂载和第一次导航之前调 initAppBridge：在 APP 里时要先把令牌同步进 localStorage，路由守卫才认得
import { initAppBridge } from './appBridge'
import App from './App.vue'
import router from './router'
import { api } from './api'
import { setSiteConfig } from './siteConfig'
import mobileTable from './directives/mobileTable'

initAppBridge()

const app = createApp(App)
// 图标不再全量注册：整个站只用到两个（UploadFilled、ArrowDown），
// 全注册会把一千多个图标全打进主包，白白多出一百多 KB。
// 用到的那两个在各自页面里单独 import。
app.use(ElementPlus, { locale: zhCn })
app.use(router)
// 手机上把列表表格排成卡片，见 directives/mobileTable.js
app.directive('mtable', mobileTable)
// 先把 config.yaml 的内容取回来再挂载，页面一上来就能用上里面的默认值。
// 取不到也照常启动，各页面回退到内置默认值。
api
  .siteConfig()
  .then(setSiteConfig)
  .catch(() => console.warn('读取 /api/config 失败，改用内置默认值'))
  .finally(() => app.mount('#app'))
