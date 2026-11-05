/**
 * 选择判断题乱序（2.19.0）：每个学生看到的选择题、判断题顺序和选择题选项顺序各不相同。
 *
 * 规矩（学生端 exe 的 desktop/client/shuffle.py 是同一套）：
 *
 *  · **只在同一大题里换**（按题型组卷时一个大题就是一种题型）：第一大题的选择题
 *    绝不会跑到第四、五大题去。同一大题里选择题和选择题换、判断题和判断题换，
 *    各占原来的位置；操作题一道都不动。
 *  · 选择题的选项也打乱。**交上去的还是原来的选项字母**（o.label），屏幕上显示的
 *    是新位置的字母（o.show）—— 判分、成绩分析、答案卷都按原字母，不受乱序影响。
 *  · 种子是「考试 + 学生」：同一个学生刷新、断线重进看到的顺序不变。
 *    判断题的「正确 / 错误」两个选项不换。
 */

const TYPES = ['选择题', '判断题']

function hash(text) {
  // FNV-1a：把种子字符串折成 32 位整数
  let h = 2166136261 >>> 0
  for (const ch of String(text)) {
    h ^= ch.codePointAt(0)
    h = Math.imul(h, 16777619) >>> 0
  }
  return h
}

function rng(seed) {
  // mulberry32：小而均匀，同一个种子永远出同一串数
  let a = hash(seed)
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function shuffled(list, rand) {
  const out = list.slice()
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

function shuffleOptions(q, rand) {
  const opts = q.options || []
  if (q.type !== '选择题' || opts.length < 2) return q
  const order = shuffled(opts, rand)
  // 第 i 个位置显示第 i 个字母；交卷时交的仍是这个选项原来的 label
  return { ...q, options: order.map((o, i) => ({ ...o, show: opts[i].label })) }
}

/** 按种子打乱一份卷子的大题（groups 原样不动，返回新的）。 */
export function shuffleGroups(groups, seed) {
  const rand = rng(seed)
  return (groups || []).map(g => {
    const items = g.items.slice()
    for (const t of TYPES) {
      const at = []
      items.forEach((q, i) => q.type === t && at.push(i))
      const moved = shuffled(at.map(i => items[i]), rand)
      at.forEach((pos, k) => (items[pos] = moved[k]))
    }
    return { ...g, items: items.map(q => shuffleOptions(q, rand)) }
  })
}

/** 卷子开了乱序就按种子打乱，没开原样返回。 */
export function applyShuffle(paper, seed) {
  if (!paper || !paper.shuffle) return paper
  return { ...paper, groups: shuffleGroups(paper.groups, seed) }
}

/** 公开答题页（/take/xxx）取卷时还不知道是谁：每台浏览器给一个固定种子，
 *  存在本机，刷新还是同一套顺序。存不了（隐私模式）就每次随机 —— 只是不稳定，不会出错。 */
export function browserSeed(token) {
  const key = `take-seed-${token}`
  try {
    const got = localStorage.getItem(key)
    if (got) return got
    const fresh = `${Date.now()}-${Math.random()}`
    localStorage.setItem(key, fresh)
    return fresh
  } catch {
    return `${Date.now()}-${Math.random()}`
  }
}
