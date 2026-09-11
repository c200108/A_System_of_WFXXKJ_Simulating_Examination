/**
 * 前端这一侧的 config.yaml 副本。
 *
 * main.js 启动时调 /api/config 取回来写进这里，各页面直接读。
 * 下面的默认值只是后端连不上时的兜底，正常情况下都会被服务端的值覆盖。
 */
import { reactive } from 'vue'

export const siteConfig = reactive({
  school: '',
  // 平台门面：名称、标签页图标、页脚备注。改 config.yaml 重启后端即生效。
  site: { title: '信息科技教学平台', brand: '信息科技教学平台', footer: '', favicon: '' },
  // 最新版本号，页脚显示。来自更新日志，不在 config.yaml 里。
  version: '',
  paper: {
    default_title: '信息技术测试卷',
    default_duration: '',
    default_counts: {},
    shuffle_options: true,
    require_answer: true,
    use_pinned: true,
    section_numerals: ['一', '二', '三', '四', '五', '六']
  },
  exam: {
    pass_score: 60,
    defaults: { is_open: true, show_score: true, show_answer: false, allow_retake: false }
  },
  upload: { max_mb: 20, image_extensions: [] }
})

/** 当前年份，页脚的版权年用它，跨年自动变，不用每年改代码。 */
export const year = new Date().getFullYear()

function applyFavicon(href) {
  if (!href) return // 留空就用 index.html 里那个内置图标
  let link = document.querySelector("link[rel~='icon']")
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  // 换了校徽但文件名没变时浏览器会拿缓存里的旧图，加个时间戳绕开
  link.href = href + (href.includes('?') ? '&' : '?') + 'v=' + Date.now()
  link.removeAttribute('type') // 让浏览器按实际内容判断，png/svg/ico 都能用
}

export function setSiteConfig(data) {
  if (!data) return
  Object.assign(siteConfig, data)
  // 标题和图标在挂载前就设好，学生的答题页、打字页也跟着生效 ——
  // 那两个页面不套教师界面的框，放在 App.vue 里做就漏掉了。
  if (siteConfig.site?.title) document.title = siteConfig.site.title
  applyFavicon(siteConfig.site?.favicon)
}
