/**
 * 拼给学生用的链接前缀。
 *
 * 按这个顺序取：
 * 1. 后端配了 PUBLIC_BASE_URL（公网地址 / 域名）—— 以它为准；
 * 2. 老师是用学生也能访问的地址打开后台的（公网 IP、域名、局域网 IP）—— 就用浏览器当前地址，
 *    换域名换端口都自动跟上；
 * 3. 老师在服务器本机用 localhost / 127.0.0.1 打开的 —— 那个地址学生访问不到，复制出去就是废链接。
 *    问后端要服务器自己的网卡地址（公网 IP 优先，其次局域网 IPv4），**端口照浏览器实际的端口**。
 *    查到好几个时默认用第一个，老师可以在页面上换一个，换过的记在这台电脑上。
 */
import { api } from './api'

let base = ''
let ips = []
let inContainer = false
const PICK_KEY = 'studentLinkHost'

const LOOPBACK = /^(localhost|127\.\d+\.\d+\.\d+|\[?::1\]?|0\.0\.0\.0)$/i

/** 老师现在是不是在服务器本机用回环地址打开的后台 */
export function onLoopback() {
  return LOOPBACK.test(location.hostname)
}

export async function loadPublicBase() {
  try {
    const cfg = await api.siteConfig()
    base = (cfg.public_base_url || '').replace(/\/$/, '')
  } catch {
    base = '' // 取不到就退回 location.origin，不影响使用
  }
  if (base || !onLoopback()) return
  try {
    const got = await api.serverAddresses() // 要登录；学生页面不会走到这里
    ips = got.ips || []
    inContainer = !!got.in_container
  } catch {
    ips = []
  }
}

function hostOrigin(ip) {
  return `${location.protocol}//${ip}${location.port ? ':' + location.port : ''}`
}

/** 本机打开时可选的几个地址（已按优先级排好），用来让老师换 */
export function hostChoices() {
  return base || !onLoopback() ? [] : ips.map(hostOrigin)
}

/** 本机打开、却一个能用的地址都没查到（多半是 Docker 部署）：要提示老师去配 PUBLIC_BASE_URL */
export function needPublicBase() {
  return !base && onLoopback() && !ips.length
}

export function containerHint() {
  return inContainer
}

export function pickHost(origin) {
  try {
    localStorage.setItem(PICK_KEY, origin)
  } catch {
    /* 存不了就只管这一次 */
  }
}

function origin() {
  if (base) return base
  if (!onLoopback()) return location.origin
  const choices = hostChoices()
  let picked = ''
  try {
    picked = localStorage.getItem(PICK_KEY) || ''
  } catch {
    picked = ''
  }
  if (choices.includes(picked)) return picked
  return choices[0] || location.origin
}

/** studentLink('/dazi') -> 'https://exam.school.edu.cn/dazi' */
export function studentLink(path) {
  return origin() + path
}
