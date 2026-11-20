/**
 * 个人云盘（2.25.0）：教师端顶栏「个人云盘」按钮 —— 免登录打开 /cloud/（OpenList）。
 *
 * 后端用存着的云盘密码去 OpenList 换一个令牌，这里把它放进 localStorage 的 wfxxcloud:token，
 * OpenList 页面头上那段脚本会把它当成自己的 token 用（见 backend/app/services/cloud.py 的 HEAD_SCRIPT）。
 * 同一个域名、同一份 localStorage，所以不用跨域传令牌。
 */
import { ElMessageBox } from 'element-plus'
import { api, explainError } from './api'

export async function openCloud() {
  // 先同步开出新标签页再去要令牌：等接口回来再 window.open 会被浏览器当成弹窗拦掉
  const win = window.open('about:blank', '_blank')
  try {
    const r = await api.cloudOpen()
    localStorage.setItem(r.storage_key, r.token)
    if (win) win.location.href = r.url
    else window.location.href = r.url
  } catch (err) {
    win?.close()
    const status = err?.response?.status
    const title = status === 403 ? '无法访问个人云盘' : '个人云盘暂时打不开'
    const msg = status === 401 ? '登录已过期，请重新登录教师端后再打开' : explainError(err)
    ElMessageBox.alert(msg, title, { type: 'warning', confirmButtonText: '知道了' }).catch(() => {})
  }
}

/** 字节 → 「1.5 GB」「320 MB」 */
export function fmtBytes(b) {
  const n = Number(b) || 0
  if (n >= 1024 ** 4) return `${(n / 1024 ** 4).toFixed(2)} TB`
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(n >= 100 * 1024 ** 3 ? 0 : 1)} GB`
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(n >= 100 * 1024 ** 2 ? 0 : 1)} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

/** 用了百分之几，给进度条用，0～100 */
export function usedPct(used, quota) {
  if (!quota) return 0
  return Math.min(100, Math.round((used / quota) * 1000) / 10)
}
