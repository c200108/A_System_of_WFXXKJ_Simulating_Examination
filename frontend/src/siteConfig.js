/**
 * 前端这一侧的 config.yaml 副本。
 *
 * main.js 启动时调 /api/config 取回来写进这里，各页面直接读。
 * 下面的默认值只是后端连不上时的兜底，正常情况下都会被服务端的值覆盖。
 */
import { reactive } from 'vue'

export const siteConfig = reactive({
  school: '',
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

export function setSiteConfig(data) {
  if (!data) return
  Object.assign(siteConfig, data)
}
