/**
 * 窄屏判断（5.0.0）：手机浏览器和教师端 APP 里，教师后台换成「顶栏 + 底部标签栏」的手机布局。
 *
 * 用 matchMedia 而不是监听 resize 自己算：只在跨过分界线时触发一次，
 * 不会拖动窗口时一秒触发几十次。全站共用这一个 ref，各组件直接读。
 */
import { ref } from 'vue'

const query = typeof window !== 'undefined' ? window.matchMedia('(max-width: 768px)') : null

export const isMobile = ref(!!query?.matches)

query?.addEventListener?.('change', e => {
  isMobile.value = e.matches
})
