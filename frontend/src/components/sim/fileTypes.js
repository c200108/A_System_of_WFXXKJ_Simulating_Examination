/**
 * 文件类型表：图标、归类、能不能新建、双击用什么打开。
 *
 * 图标一律是内联 SVG，不引任何图片文件 —— 一个机房五十台机器同时开考，
 * 每多一个图片请求就是五十次往返，而这些图标加起来还不到一张小图的体积。
 *
 * open 决定双击的行为：
 *   notepad  记事本，能改内容（.txt .bat .html .css .js 这些纯文本）
 *   doc      文档查看器，只读（.doc .docx .pdf .wps）
 *   image    图片查看器
 *   media    播放器（音频 / 视频）
 *   archive  压缩包，能看里面有什么
 *   db       数据库，看表
 *   block    考试环境里不执行（.exe .msi .bat 双击时给提示）
 */

const P = (d, fill) => `<path d="${d}" fill="${fill}"/>`

// 文档类图标共用的"一页纸 + 折角"，色块和角标区分类型
function page(accent, mark = '') {
  return `<svg viewBox="0 0 32 32">
    ${P('M7 2h13l6 6v22H7z', '#ffffff')}
    ${P('M7 2h13l6 6v22H7z', 'none')}
    <path d="M7 2h13l6 6v22H7z" fill="#fff" stroke="#9aa7b8" stroke-width="1.2"/>
    <path d="M20 2l6 6h-6z" fill="#dce5f0" stroke="#9aa7b8" stroke-width="1.2"/>
    <rect x="9" y="17" width="16" height="11" rx="1.5" fill="${accent}"/>
    <text x="17" y="26" font-size="8.5" font-family="Arial" font-weight="bold"
          fill="#fff" text-anchor="middle">${mark}</text>
  </svg>`
}

export const ICONS = {
  folder: `<svg viewBox="0 0 32 32">
    ${P('M3 7h9l3 3h14v17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', '#f5b74c')}
    ${P('M3 12h26v15a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', '#ffd076')}
  </svg>`,
  folderOpen: `<svg viewBox="0 0 32 32">
    ${P('M3 7h9l3 3h14v6H3z', '#e0a63f')}
    ${P('M3 16h26l-3 12a2 2 0 0 1-2 1.5H5A2 2 0 0 1 3 27z', '#ffd076')}
  </svg>`,
  txt: page('#9aa7b8', 'TXT'),
  doc: page('#2b579a', 'W'),
  pdf: page('#c8332b', 'PDF'),
  ppt: page('#c55a2b', 'P'),
  xls: page('#1f7245', 'X'),
  web: `<svg viewBox="0 0 32 32">
    <circle cx="16" cy="16" r="12" fill="#4a90d9"/>
    <path d="M4 16h24M16 4c4 4 4 20 0 24M16 4c-4 4-4 20 0 24" stroke="#fff"
          stroke-width="1.4" fill="none"/>
  </svg>`,
  image: `<svg viewBox="0 0 32 32">
    <rect x="3" y="6" width="26" height="20" rx="2" fill="#fff" stroke="#9aa7b8" stroke-width="1.3"/>
    <circle cx="11" cy="13" r="2.6" fill="#f2c14e"/>
    ${P('M5 24l7-8 5 5 4-3 6 6z', '#4f9d5a')}
  </svg>`,
  audio: `<svg viewBox="0 0 32 32">
    ${P('M12 20V7l12-3v13', '#7a5bd6')}
    <path d="M12 20V7l12-3v13" stroke="#5a3fb0" stroke-width="1.4" fill="none"/>
    <circle cx="9" cy="21" r="4" fill="#7a5bd6"/><circle cx="21" cy="17" r="4" fill="#7a5bd6"/>
  </svg>`,
  video: `<svg viewBox="0 0 32 32">
    <rect x="3" y="7" width="26" height="18" rx="2" fill="#3a3f4a"/>
    <g fill="#fff"><rect x="5" y="9" width="3" height="3"/><rect x="5" y="14" width="3" height="3"/>
      <rect x="5" y="19" width="3" height="3"/><rect x="24" y="9" width="3" height="3"/>
      <rect x="24" y="14" width="3" height="3"/><rect x="24" y="19" width="3" height="3"/></g>
    ${P('M13 11l8 5-8 5z', '#ffd076')}
  </svg>`,
  archive: `<svg viewBox="0 0 32 32">
    ${P('M4 6h24v22a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z', '#e0a63f')}
    ${P('M4 6h24v6H4z', '#c98f32')}
    <rect x="14" y="4" width="4" height="18" fill="#fff8e6" stroke="#8a6a1f" stroke-width="0.8"/>
    <rect x="13" y="20" width="6" height="6" rx="1" fill="#ffe9b0" stroke="#8a6a1f" stroke-width="0.9"/>
  </svg>`,
  exe: `<svg viewBox="0 0 32 32">
    <rect x="3" y="5" width="26" height="22" rx="2" fill="#4a90d9"/>
    <rect x="3" y="5" width="26" height="5" fill="#2f6bb0"/>
    <circle cx="6.5" cy="7.5" r="1" fill="#fff"/><circle cx="10" cy="7.5" r="1" fill="#fff"/>
    ${P('M10 14h12v3H10zm0 5h8v3h-8z', '#eaf3ff')}
  </svg>`,
  db: `<svg viewBox="0 0 32 32">
    <ellipse cx="16" cy="8" rx="11" ry="4" fill="#8fbf5a"/>
    ${P('M5 8v16c0 2.2 4.9 4 11 4s11-1.8 11-4V8', '#a9d472')}
    <ellipse cx="16" cy="8" rx="11" ry="4" fill="none" stroke="#5f8a34" stroke-width="1.2"/>
    <path d="M5 16c0 2.2 4.9 4 11 4s11-1.8 11-4" stroke="#5f8a34" stroke-width="1.2" fill="none"/>
  </svg>`,
  unknown: page('#b8c1cc', '?'),
  computer: `<svg viewBox="0 0 32 32">
    <rect x="4" y="5" width="24" height="16" rx="1.5" fill="#dfe7f0" stroke="#7f8c9b" stroke-width="1.2"/>
    <rect x="6" y="7" width="20" height="12" fill="#4a90d9"/>
    ${P('M11 23h10l2 4H9z', '#c7d2de')}
  </svg>`,
  recycle: `<svg viewBox="0 0 32 32">
    ${P('M8 9h16l-1.6 18a2 2 0 0 1-2 1.8h-8.8a2 2 0 0 1-2-1.8z', '#b9c6d4')}
    ${P('M8 9h16l-1.6 18a2 2 0 0 1-2 1.8h-8.8a2 2 0 0 1-2-1.8z', 'none')}
    <path d="M12 13v13M16 13v13M20 13v13" stroke="#7f8c9b" stroke-width="1.3"/>
    <rect x="6" y="5" width="20" height="4" rx="1.6" fill="#8fa1b4"/>
  </svg>`,
  docs: `<svg viewBox="0 0 32 32">
    ${P('M3 7h9l3 3h14v17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', '#f5b74c')}
    <rect x="9" y="4" width="14" height="13" rx="1" fill="#fff" stroke="#9aa7b8" stroke-width="1.1"/>
    <path d="M11 8h10M11 11h10M11 14h7" stroke="#9aa7b8" stroke-width="1.1"/>
    ${P('M3 13h26v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', '#ffd076')}
  </svg>`
}

/** 扩展名 → 怎么显示、怎么打开 */
export const TYPES = {
  // ---- 文本 ----
  txt: { name: '文本文档', icon: 'txt', open: 'notepad', newable: true, cat: '文本' },
  log: { name: '日志文件', icon: 'txt', open: 'notepad', cat: '文本' },
  // ---- 文档 ----
  doc: { name: 'Word 文档', icon: 'doc', open: 'doc', newable: true, cat: '文档' },
  docx: { name: 'Word 文档', icon: 'doc', open: 'doc', newable: true, cat: '文档' },
  wps: { name: 'WPS 文字文档', icon: 'doc', open: 'doc', newable: true, cat: '文档' },
  pdf: { name: 'PDF 文档', icon: 'pdf', open: 'doc', cat: '文档' },
  ppt: { name: '演示文稿', icon: 'ppt', open: 'doc', cat: '文档' },
  pptx: { name: '演示文稿', icon: 'ppt', open: 'doc', cat: '文档' },
  xls: { name: '电子表格', icon: 'xls', open: 'doc', cat: '文档' },
  xlsx: { name: '电子表格', icon: 'xls', open: 'doc', cat: '文档' },
  et: { name: 'WPS 表格', icon: 'xls', open: 'doc', cat: '文档' },
  // ---- 网页 ----
  htm: { name: 'HTML 文档', icon: 'web', open: 'notepad', cat: '网页' },
  html: { name: 'HTML 文档', icon: 'web', open: 'notepad', newable: true, cat: '网页' },
  css: { name: '样式表', icon: 'web', open: 'notepad', cat: '网页' },
  js: { name: '脚本文件', icon: 'web', open: 'notepad', cat: '网页' },
  // ---- 图像 ----
  jpg: { name: 'JPEG 图像', icon: 'image', open: 'image', cat: '图像' },
  jpeg: { name: 'JPEG 图像', icon: 'image', open: 'image', cat: '图像' },
  png: { name: 'PNG 图像', icon: 'image', open: 'image', cat: '图像' },
  gif: { name: 'GIF 动画', icon: 'image', open: 'image', cat: '图像' },
  bmp: { name: '位图图像', icon: 'image', open: 'image', newable: true, cat: '图像' },
  // ---- 音频 ----
  mp3: { name: 'MP3 音频', icon: 'audio', open: 'media', cat: '音频' },
  wav: { name: 'WAV 音频', icon: 'audio', open: 'media', cat: '音频' },
  flac: { name: 'FLAC 音频', icon: 'audio', open: 'media', cat: '音频' },
  // ---- 视频 ----
  mp4: { name: 'MP4 视频', icon: 'video', open: 'media', cat: '视频' },
  avi: { name: 'AVI 视频', icon: 'video', open: 'media', cat: '视频' },
  wmv: { name: 'WMV 视频', icon: 'video', open: 'media', cat: '视频' },
  // ---- 压缩 ----
  zip: { name: 'ZIP 压缩文件', icon: 'archive', open: 'archive', newable: true, cat: '压缩包' },
  rar: { name: 'RAR 压缩文件', icon: 'archive', open: 'archive', cat: '压缩包' },
  '7z': { name: '7Z 压缩文件', icon: 'archive', open: 'archive', cat: '压缩包' },
  // ---- 程序 ----
  exe: { name: '应用程序', icon: 'exe', open: 'block', cat: '程序' },
  msi: { name: '安装程序包', icon: 'exe', open: 'block', cat: '程序' },
  bat: { name: '批处理文件', icon: 'exe', open: 'block', cat: '程序' },
  // ---- 数据库 ----
  mdb: { name: 'Access 数据库', icon: 'db', open: 'db', cat: '数据库' },
  accdb: { name: 'Access 数据库', icon: 'db', open: 'db', cat: '数据库' }
}

export const UNKNOWN = { name: '文件', icon: 'unknown', open: 'block', cat: '其他' }

export function extOf(name) {
  const i = String(name || '').lastIndexOf('.')
  return i > 0 ? String(name).slice(i + 1).toLowerCase() : ''
}

export function typeOf(name) {
  return TYPES[extOf(name)] || UNKNOWN
}

/** 「新建」菜单里列哪些。顺序照着 XP 那个菜单来 */
export const NEW_MENU = [
  { ext: '', label: '文件夹', dir: true },
  { ext: 'txt', label: '文本文档' },
  { ext: 'docx', label: 'Word 文档' },
  { ext: 'wps', label: 'WPS 文字文档' },
  { ext: 'bmp', label: 'BMP 图像' },
  { ext: 'html', label: 'HTML 文档' },
  { ext: 'zip', label: 'ZIP 压缩文件' }
]

/** 假的文件大小：同一个名字每次算出来都一样，看着像真的又不用真存内容 */
export function fakeSize(path, node) {
  if (!node || node.type === 'dir') return ''
  const text = String(node.content || '')
  if (text) return `${Math.max(1, Math.ceil(new Blob([text]).size / 1024))} KB`
  let h = 0
  for (let i = 0; i < path.length; i++) h = (h * 31 + path.charCodeAt(i)) >>> 0
  const cat = typeOf(path).cat
  const base = { 图像: 260, 音频: 4200, 视频: 18000, 压缩包: 1500, 程序: 900, 数据库: 640 }[cat] || 24
  const kb = base + (h % Math.max(8, Math.round(base / 3)))
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`
}
