/**
 * v-mtable：手机上把 el-table 的每一行排成一张卡片（5.0.0）。
 *
 * 为什么不给每个页面另写一套手机列表：教师端二十来张表，各写一遍就是两套界面，
 * 以后加一列要改两处，迟早对不上。这里只给表格加一层「换个排法」：
 * 列还是那些列、按钮还是那些按钮，电脑上完全不变；窄屏时表头藏起来，
 * 每个单元格前面贴上它的列名（data-label），排成「列名：内容」一行一行的卡片。
 *
 * 做法：表头的 th 和表体的 td 带着同一个列类名（el-table_1_column_3），
 * 按它把表头文字抄到每个 td 的 data-label 上；表格内容一变（翻页、筛选）
 * MutationObserver 再抄一遍。真正的排版全在 styles/mobile.css 里。
 */
import { watch } from 'vue'
import { isMobile } from '../mobile'

const COL = /^el-table_\d+_column_\d+$/

function colClass(cell) {
  for (const c of cell.classList) if (COL.test(c)) return c
  return ''
}

function stamp(el) {
  const labels = {}
  el.querySelectorAll('.el-table__header-wrapper th').forEach(th => {
    const c = colClass(th)
    if (c) labels[c] = (th.innerText || '').trim()
  })
  el.querySelectorAll('.el-table__body-wrapper td.el-table__cell').forEach(td => {
    const c = colClass(td)
    if (!c) return
    const label = labels[c] || ''
    if (td.dataset.label !== label) td.dataset.label = label
    // 「操作」列单独排在卡片底部，按钮靠右
    // 列名叫「操作」，或者没列名、里面全是按钮的那一列
    const actions = label === '操作' || (!label && !!td.querySelector('.el-button'))
    if (td.classList.contains('m-actions') !== actions) td.classList.toggle('m-actions', actions)
    // 什么都没有的格子（空答案、没配图写着「—」的不算空）卡片里不占行
    const empty =
      !td.classList.contains('el-table-column--selection') &&
      !(td.innerText || '').trim() &&
      !td.querySelector('img, input, button, .el-switch, .el-tag, .el-progress')
    if (td.classList.contains('m-empty') !== empty) td.classList.toggle('m-empty', empty)
  })
  // 每行第一个有字的格子当卡片标题
  el.querySelectorAll('.el-table__body-wrapper tr.el-table__row').forEach(tr => {
    const first = [...tr.children].find(
      td => !td.classList.contains('el-table-column--selection') && !td.classList.contains('m-empty')
    )
    tr.querySelectorAll('td.m-first').forEach(td => td !== first && td.classList.remove('m-first'))
    if (first && !first.classList.contains('m-first')) first.classList.add('m-first')
  })
}

function apply(el) {
  if (el.classList.contains('m-stack') !== isMobile.value) el.classList.toggle('m-stack', isMobile.value)
  if (isMobile.value) stamp(el)
}

export default {
  mounted(el) {
    let queued = false
    const schedule = () => {
      if (queued) return
      queued = true
      requestAnimationFrame(() => {
        queued = false
        apply(el)
      })
    }
    // 行增删、文字变化、class 被 Vue 重绘冲掉（el-table 根元素和格子的 class 都是绑定出来的，
    // 一重绘就整串覆盖，m-stack、m-actions 跟着没了）都要重贴一遍。
    // 不会自己触发自己：apply/stamp 里每一处改动都先比对，值相同就不碰 DOM。
    el._mtableObserver = new MutationObserver(schedule)
    el._mtableObserver.observe(el, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['class']
    })
    el._mtableStop = watch(isMobile, schedule)
    schedule()
  },
  unmounted(el) {
    el._mtableObserver?.disconnect()
    el._mtableStop?.()
  }
}
