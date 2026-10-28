/**
 * 选择题答案 → 「B. 选项内容」。
 *
 * 答卷里存的只是字母，老师、学生回看时还得往上翻去对选项，多选题更费眼。
 * 判断题（正确/错误）没有选项，原样返回。
 */
export function optionText(options, letters) {
  const raw = String(letters ?? '').trim()
  if (!raw || !Array.isArray(options) || !options.length) return raw
  const picked = raw.replace(/[\s,，、]/g, '').toUpperCase().split('')
  const parts = picked.map(l => {
    const o = options.find(x => String(x.label).toUpperCase() === l)
    return o ? `${o.label}. ${o.content}` : null
  })
  return parts.every(Boolean) ? parts.join('；') : raw
}
