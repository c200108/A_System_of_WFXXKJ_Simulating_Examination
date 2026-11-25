/**
 * 客观题比对答案（2.27.0），和服务端 backend/app/services/answers.py 同一套规矩。
 * 只给教师组卷页的「在线自测」用 —— 学生交卷一律由服务端判分，学生那头拿不到答案。
 *
 *  · 多选题：答案几个字母（ABD），比字母集合，全对才算对
 *  · 填空题：答案按「；」分空，可带「第一空：」；括号里是也算对的说法；按空给分
 */

const PUNCT = /[\s"'“”‘’「」『』《》〈〉()（）[\]【】,，。.、;；:：!！?？·]/g
const norm = s => String(s ?? '').normalize('NFKC').toLowerCase().replace(PUNCT, '')

export function letters(text) {
  const got = new Set(
    String(text ?? '')
      .normalize('NFKC')
      .toUpperCase()
      .split('')
      .filter(c => c >= 'A' && c <= 'Z')
  )
  return [...got].sort().join('')
}

export function isMulti(q) {
  return q.type === '选择题' && letters(q.answer).length > 1
}

export function blankKeys(answer) {
  let text = String(answer || '').trim().replace(/^[（(]?\s*答案\s*[:：]\s*/, '')
  const open = (text.match(/[（(]/g) || []).length
  const close = (text.match(/[）)]/g) || []).length
  if (open < close) text = text.replace(/[）)]\s*$/, '')
  const out = []
  for (let part of text.split(/[；;\n]/)) {
    part = part.trim().replace(/^第[一二三四五六七八九十\d]+空\s*[:：]\s*/, '')
    if (!part) continue
    const alts = []
    alts.push(...part.replace(/[（(][^（）()]*[）)]/g, '').split(/\s*[/／]\s*/))
    for (const m of part.matchAll(/[（(]([^（）()]*)[）)]/g)) {
      alts.push(...m[1].split(/\s*(?:或者|或|也可以|也可|\/|／)\s*/))
    }
    const keys = [...new Set(alts.map(norm).filter(Boolean))]
    if (keys.length) out.push(keys)
  }
  return out
}

export function blankCount(q) {
  return Math.max(1, blankKeys(q.answer).length)
}

function splitBlanks(mine) {
  const raw = String(mine ?? '').trim()
  if (raw.startsWith('[')) {
    try {
      const got = JSON.parse(raw)
      if (Array.isArray(got)) return got.map(v => String(v ?? ''))
    } catch {
      /* 不是数组 */
    }
  }
  return [raw]
}

/** 判一道客观题：{ ok, part }，part 是得分比例（填空题可能是 0.5） */
export function judge(q, mine, correct) {
  if (q.type === '选择题') {
    const ok = !!letters(mine) && letters(mine) === letters(correct)
    return { ok, part: ok ? 1 : 0 }
  }
  if (q.type === '填空题') {
    const keys = blankKeys(correct)
    if (keys.length) {
      const got = splitBlanks(mine)
      const hits = keys.filter((k, i) => k.includes(norm(got[i]))).length
      return { ok: hits === keys.length, part: hits / keys.length }
    }
  }
  const ok = String(mine ?? '').trim() === String(correct ?? '').trim()
  return { ok, part: ok ? 1 : 0 }
}
