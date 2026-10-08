/**
 * 教师端安卓 APP 的桥（5.0.0）。
 *
 * APP 是个原生外壳：登录页是原生的，登进去后用 WebView 打开的就是这套教师端网页，
 * 所以网页有的功能 APP 全都有，网页以后加功能 APP 也不用重新发版。
 * 外壳往页面里注入一个 window.WfxxApp 对象（Java 的 @JavascriptInterface），
 * 网页靠它判断"我在 APP 里"，并把浏览器做得到、WebView 做不到的几件事交给外壳：
 *
 * - 登录状态：令牌由 APP 保管和续期，页面启动时从外壳取；
 * - 下载文件：WebView 不认 blob 链接的 <a download>，改成分块把内容交给外壳存进「下载」；
 * - 复制链接：机房服务器多是 http，WebView 里 navigator.clipboard 不可用；
 * - 打印：WebView 里 window.print() 什么都不做，交给系统打印（可另存 PDF）；
 * - 退出登录、登录过期：回到 APP 的原生登录页，而不是网页登录页。
 *
 * 不在 APP 里时（电脑浏览器、手机浏览器）这里所有东西都不生效，网页行为和以前一样。
 */

const bridge = typeof window !== 'undefined' ? window.WfxxApp : undefined

/** 是否运行在教师端 APP 里 */
export const inApp = !!bridge

function call(name, ...args) {
  try {
    if (bridge && typeof bridge[name] === 'function') return bridge[name](...args)
  } catch (e) {
    console.warn(`调用 APP 接口 ${name} 失败`, e)
  }
  return undefined
}

/**
 * 页面启动时调一次（main.js，挂载路由之前）：
 * 把 APP 保管的令牌和账号信息同步进 localStorage，路由守卫和 api.js 照旧从那里读。
 */
export function initAppBridge() {
  if (!inApp) return
  document.documentElement.classList.add('in-app')

  const token = call('getToken')
  if (token) {
    localStorage.setItem('token', token)
    const user = call('getUser')
    if (user) localStorage.setItem('user', user)
  }

  // 外壳续期拿到新令牌后调这个，页面不刷新、正在填的表单不丢
  window.__wfxxSetToken = (t, userJson) => {
    if (t) localStorage.setItem('token', t)
    if (userJson) localStorage.setItem('user', userJson)
  }

  // 复制：http 页面里 navigator.clipboard 是 undefined；https 页面里有，但 WebView 常常
  // 不给权限、静默失败。APP 里一律换成走外壳的
  {
    try {
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: text => {
            call('copyText', String(text ?? ''))
            return Promise.resolve()
          }
        }
      })
    } catch {
      /* 定义不了就算了，页面自己会提示复制失败 */
    }
  }

  // 打印：交给系统打印服务，选「另存为 PDF」就能存成文件
  window.print = () => call('print', document.title || '')

  // 深浅色变了告诉外壳，状态栏跟着换色
  const syncTheme = () =>
    call('setDarkMode', document.documentElement.classList.contains('dark'))
  new MutationObserver(syncTheme).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class']
  })
  syncTheme()
}

/** 退出登录：清掉网页这边的状态，回 APP 的原生登录页 */
export function appLogout() {
  call('logout')
}

/** 自己改了密码：APP 里存的是旧密码，跟着换掉，不然下次自动重新登录会失败 */
export function appPasswordChanged(password) {
  call('onPasswordChanged', password)
}

/** 令牌失效（接口回 401）：让 APP 用保存的账号密码悄悄重新登录，失败了才回登录页 */
export function appAuthExpired() {
  call('onAuthExpired')
}

// 每块 384KB 原始数据（base64 后约 512KB）。整份文件一次塞过桥，
// 几十 MB 的考试包会在 Java 那边一次性分配一个巨型字符串，旧手机直接内存不足。
const CHUNK = 384 * 1024

function toBase64(bytes) {
  let s = ''
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
  }
  return btoa(s)
}

/**
 * 把 blob 交给外壳存进手机的「下载」目录。存好后外壳会弹提示，点一下就能打开。
 * 返回 true 表示已交给外壳处理。
 */
export async function appSaveBlob(blob, filename) {
  if (!inApp) return false
  const id = call('fileBegin', filename, blob.type || 'application/octet-stream')
  if (!id) return false
  const bytes = new Uint8Array(await blob.arrayBuffer())
  for (let i = 0; i < bytes.length; i += CHUNK) {
    if (!call('fileChunk', id, toBase64(bytes.subarray(i, i + CHUNK)))) {
      call('fileAbort', id)
      throw new Error('保存文件失败')
    }
  }
  call('fileEnd', id)
  return true
}
