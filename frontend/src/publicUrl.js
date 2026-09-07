/**
 * 拼给学生用的链接前缀。
 *
 * 默认用浏览器当前地址（location.origin），换域名换端口都自动跟上。
 * 但老师如果是在服务器上用 127.0.0.1 打开后台的，那个地址学生访问不到，
 * 复制出去就是废链接 —— 所以后端可以用 PUBLIC_BASE_URL 指定权威地址，
 * 配了就以它为准。
 */
import { api } from './api'

let base = ''

export async function loadPublicBase() {
  try {
    const cfg = await api.siteConfig()
    base = (cfg.public_base_url || '').replace(/\/$/, '')
  } catch {
    base = '' // 取不到就退回 location.origin，不影响使用
  }
}

/** studentLink('/dazi') -> 'https://exam.school.edu.cn/dazi' */
export function studentLink(path) {
  return (base || location.origin) + path
}
