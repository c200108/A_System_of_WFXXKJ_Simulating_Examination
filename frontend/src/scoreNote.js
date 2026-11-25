/**
 * 大题标题后面那句「每题几分」（2.28.0）：卷面上一眼看清。
 * 一大题里分值都一样写「每题 3 分」，不一样写「每题 2～3 分」，没设分（老卷子）不写。
 */
export function perQuestion(items) {
  const pts = (items || []).map(q => Number(q.score) || 0).filter(n => n > 0)
  if (!pts.length) return ''
  const lo = Math.min(...pts)
  const hi = Math.max(...pts)
  return lo === hi ? `每题 ${lo} 分` : `每题 ${lo}～${hi} 分`
}
