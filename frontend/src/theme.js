/**
 * 全站界面主题、字号（2.22.0）。
 *
 * 系统管理员在「我的账号 → 数据备份与系统更新」里选，存在服务器上（/api/config 的 ui），
 * 所有人打开网页都是这一套。默认主题就是原来的样子（Element Plus 默认蓝），只是字号默认稍大一号。
 *
 * 做法：Element Plus 的颜色、圆角、字号全是 CSS 变量，这里生成一段覆盖它们的 CSS 挂到 <head>。
 * 主色的浅色 / 深色梯度（light-3 … light-9、dark-2）按 Element Plus 自己的算法（和白 / 黑混色）算出来，
 * 按钮悬停、标签底色这些就都跟着主色走。底色、文字色只在浅色模式下改，深色模式仍用 Element Plus 自带的深色。
 *
 * 几套配色参考了常用的开源组件库 / 设计系统（只借配色思路，没有引用它们的代码或资源）：
 * Ant Design、GitHub Primer、Naive UI、Tailwind CSS（Indigo）、Material Design 3，另加一套机房投影用的高对比。
 */

export const THEMES = [
  {
    id: 'default',
    name: '默认',
    desc: '原来的样子：Element Plus 默认蓝，干净中性',
    vars: {}
  },
  {
    id: 'ant',
    name: '明快蓝',
    desc: '参考 Ant Design：亮蓝主色、浅灰底、卡片更分明',
    primary: '#1677ff',
    success: '#52c41a',
    warning: '#faad14',
    danger: '#ff4d4f',
    radius: '6px',
    light: {
      '--el-bg-color-page': '#f0f2f5',
      '--el-border-color': '#d9d9d9',
      '--el-border-color-light': '#e4e7ed',
      '--el-text-color-primary': '#1f1f1f'
    }
  },
  {
    id: 'primer',
    name: '代码灰蓝',
    desc: '参考 GitHub Primer：灰白底、细边框、偏工程风',
    primary: '#0969da',
    success: '#1a7f37',
    warning: '#bf8700',
    danger: '#cf222e',
    radius: '6px',
    light: {
      '--el-bg-color-page': '#f6f8fa',
      '--el-border-color': '#d0d7de',
      '--el-border-color-light': '#d8dee4',
      '--el-border-color-lighter': '#e6eaef',
      '--el-text-color-primary': '#1f2328',
      '--el-text-color-regular': '#424a53',
      '--el-text-color-secondary': '#59636e'
    }
  },
  {
    id: 'naive',
    name: '薄荷绿',
    desc: '参考 Naive UI：清新的绿色主调、圆角稍大',
    primary: '#18a058',
    success: '#18a058',
    warning: '#f0a020',
    danger: '#d03050',
    radius: '8px',
    light: {
      '--el-bg-color-page': '#f4f8f6',
      '--el-border-color': '#d6e2dc',
      '--el-border-color-light': '#e0ebe5',
      '--el-text-color-primary': '#1f2d26'
    }
  },
  {
    id: 'indigo',
    name: '靛紫',
    desc: '参考 Tailwind CSS：靛紫主色、冷灰底、大圆角',
    primary: '#4f46e5',
    success: '#16a34a',
    warning: '#d97706',
    danger: '#dc2626',
    radius: '10px',
    light: {
      '--el-bg-color-page': '#f1f5f9',
      '--el-border-color': '#cbd5e1',
      '--el-border-color-light': '#e2e8f0',
      '--el-text-color-primary': '#0f172a',
      '--el-text-color-regular': '#334155',
      '--el-text-color-secondary': '#64748b'
    }
  },
  {
    id: 'warm',
    name: '暖橙',
    desc: '参考 Material Design 3：暖橙主色、米色底、圆润',
    primary: '#e8590c',
    success: '#2f9e44',
    warning: '#f08c00',
    danger: '#e03131',
    radius: '12px',
    light: {
      '--el-bg-color-page': '#fbf7f2',
      '--el-border-color': '#e6d9cc',
      '--el-border-color-light': '#efe6dc',
      '--el-text-color-primary': '#2b1d12'
    }
  },
  {
    id: 'contrast',
    name: '高对比',
    desc: '机房投影、后排看得清：纯白底、深色字、粗边框',
    primary: '#0040c1',
    success: '#0a7a2f',
    warning: '#a85a00',
    danger: '#c00018',
    radius: '4px',
    light: {
      '--el-bg-color-page': '#ffffff',
      '--el-border-color': '#6b7280',
      '--el-border-color-light': '#8b919a',
      '--el-border-color-lighter': '#a4a9b1',
      '--el-text-color-primary': '#000000',
      '--el-text-color-regular': '#111111',
      '--el-text-color-secondary': '#333333'
    },
    extra: `html:not(.dark) .el-card{border-width:2px}
html:not(.dark) .el-button{font-weight:600}`
  }
]

/** 字号：Element Plus 的几档字号一起放大。默认「稍大」（比原来大 1 号） */
export const FONTS = [
  { id: 'normal', name: '标准', base: 14 },
  { id: 'large', name: '稍大', base: 15 },
  { id: 'larger', name: '大', base: 16 },
  { id: 'huge', name: '特大', base: 17 }
]

function mix(hex, other, weight) {
  const a = hex.replace('#', '')
  const b = other.replace('#', '')
  const ch = i => {
    const x = parseInt(a.slice(i, i + 2), 16)
    const y = parseInt(b.slice(i, i + 2), 16)
    return Math.round(x * (1 - weight) + y * weight)
      .toString(16)
      .padStart(2, '0')
  }
  return `#${ch(0)}${ch(2)}${ch(4)}`
}

/** 一个颜色的整套梯度变量（和 Element Plus 自己生成的一样：light-N = 和白色混 N/10，dark-2 = 和黑色混 20%） */
function palette(name, color) {
  if (!color) return ''
  const out = [`--el-color-${name}:${color}`]
  for (const n of [3, 5, 7, 8, 9]) out.push(`--el-color-${name}-light-${n}:${mix(color, '#ffffff', n / 10)}`)
  out.push(`--el-color-${name}-dark-2:${mix(color, '#000000', 0.2)}`)
  return out.join(';')
}

export function themeCss(themeId, fontId) {
  const t = THEMES.find(x => x.id === themeId) || THEMES[0]
  const f = FONTS.find(x => x.id === fontId) || FONTS[1]
  const b = f.base
  const parts = []
  // 字号：大字 / 中 / 小 / 更小四档跟着放大（Element Plus 的默认是 16 / 14 / 13 / 12）
  parts.push(
    `:root{--el-font-size-extra-large:${b + 6}px;--el-font-size-large:${b + 4}px;--el-font-size-medium:${b + 2}px;` +
      `--el-font-size-base:${b}px;--el-font-size-small:${b - 1}px;--el-font-size-extra-small:${b - 2}px}`
  )
  parts.push(`body{font-size:${b}px}`)
  if (t.id !== 'default') {
    const colors = [
      palette('primary', t.primary),
      palette('success', t.success),
      palette('warning', t.warning),
      palette('danger', t.danger),
      palette('error', t.danger),
      t.radius ? `--el-border-radius-base:${t.radius};--el-border-radius-small:${t.radius}` : ''
    ]
      .filter(Boolean)
      .join(';')
    parts.push(`:root{${colors}}`)
    if (t.light) {
      const light = Object.entries(t.light)
        .map(([k, v]) => `${k}:${v}`)
        .join(';')
      parts.push(`html:not(.dark){${light}}`)
    }
    if (t.extra) parts.push(t.extra)
  }
  return parts.join('\n')
}

let styleEl = null
export function applyTheme(themeId, fontId) {
  if (!styleEl) {
    styleEl = document.createElement('style')
    styleEl.id = 'ui-theme'
    document.head.appendChild(styleEl)
  }
  styleEl.textContent = themeCss(themeId, fontId)
  document.documentElement.dataset.theme = themeId || 'default'
}
