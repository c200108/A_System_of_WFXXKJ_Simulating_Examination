"""「AI 专用提示词」：老师把它整段交给 AI，让 AI 做出的教学网页直接接上这个 API（2.16.1）。

网页版和 APP 共用这一份（GET /api/data-apis/{id}/ai-prompt），改提示词只改这里。

写给 AI 看的，所以要：
- 硬性要求写死（字段名、提交函数、学生身份栏），AI 照抄就能对上平台的统计；
- 每个用途给一份完整的 JSON 例子 —— AI 最容易在字段名上自由发挥（studentName、scoreTotal……），
  平台虽然认一部分别名，但按标准信封送才能进逐题正确率、自评互评雷达图；
- 老师没给接收地址时也能用：CONFIG 里地址留空就是「预留接口」，页面照常能用，数据先存在本机。

**不放读取密钥**：提示词会贴进网页、发给 AI，读取密钥能看到全部数据。
"""

from __future__ import annotations

import json

from ..models import DataApi
from . import dataapi as svc

# 每个用途：要 AI 做成什么样、数据怎么填、一份完整例子
_PURPOSE = {
    "answer": {
        "what": "答题回收：学生在网页上做题（选择、判断、填空、拖拽、小游戏关卡都算），提交每题作答、对错、得分。",
        "rules": [
            "type 固定写 \"answer\"。",
            "answers 每题一项：q 题号（字符串，同一道题在所有学生那里必须一致，建议 \"1\" \"2\" … 或稳定的题目编号）、"
            "answer 学生的作答（多选用逗号连成字符串，如 \"A,C\"）、correct 是否答对（true/false，主观题判不了就不写这一项）、"
            "score 本题得分、max 本题满分、time_ms 本题用时（毫秒，可选）。",
            "score / max_score 是整份的总分 / 满分。不写 score 时平台按 answers 里每题的 score 自动加总。",
            "判分在网页里做好再送；平台按 correct 算每题正确率、列出答错的学生。",
        ],
        "example": {
            "type": "answer",
            "student": {"no": "20250101", "name": "张三", "class": "七年级1班"},
            "activity": {"id": "L3-T1", "name": "第3课 任务1"},
            "score": 8, "max_score": 10,
            "answers": [
                {"q": "1", "answer": "B", "correct": True, "score": 5, "max": 5, "time_ms": 5300},
                {"q": "2", "answer": "A,C", "correct": False, "score": 3, "max": 5, "time_ms": 12800},
            ],
            "data": {"用时秒": 18, "尝试次数": 1},
        },
    },
    "self_eval": {
        "what": "自我评价：学生按几个维度给自己打分（星级、滑块、量表都行），再写几句反思。",
        "rules": [
            "type 固定写 \"self_eval\"。",
            "ratings 每个维度一项：item 维度名（所有学生必须一致，不要带序号、表情）、score 打的分、max 这个维度的满分。",
            "反思、收获、困惑写进 comment（一段文字）；有多个问答框的，主要的一段放 comment，其余放 data。",
            "不需要 answers；如果整份有总分，可以写 score / max_score。",
        ],
        "example": {
            "type": "self_eval",
            "student": {"no": "20250101", "name": "张三", "class": "七年级1班"},
            "activity": {"id": "L3-T1", "name": "第3课 任务1"},
            "ratings": [
                {"item": "参与度", "score": 4, "max": 5},
                {"item": "合作交流", "score": 5, "max": 5},
                {"item": "任务完成", "score": 3, "max": 5},
            ],
            "comment": "这节课我学会了用循环画图形，但调试花了很久。",
        },
    },
    "peer_eval": {
        "what": "同伴互评：学生给同组（或全班）同学按几个维度打分、写评语。一个学生评几个人，就送几条。",
        "rules": [
            "type 固定写 \"peer_eval\"。",
            "student 是评价人（正在用网页的这个学生），target 是被评人：target 里同样写 no 学号、name 姓名。",
            "每评一个同学送一条（不要把几个被评人塞进一条），平台据此画「评价人 × 被评人」矩阵、算每人收到的平均分。",
            "ratings 每个维度一项：item 维度名（所有人一致）、score、max；评语写进 comment。",
            "被评人名单：老师在要求里给了就做成下拉；没给就让学生自己填被评人的学号和姓名。不要让学生评自己。",
        ],
        "example": {
            "type": "peer_eval",
            "student": {"no": "20250101", "name": "张三", "class": "七年级1班"},
            "target": {"no": "20250102", "name": "李四"},
            "activity": {"id": "L3-G2", "name": "第3课 小组2互评"},
            "ratings": [
                {"item": "合作交流", "score": 4, "max": 5},
                {"item": "贡献度", "score": 5, "max": 5},
            ],
            "comment": "分工很清楚，讲解也很耐心。",
        },
    },
    "survey": {
        "what": "问卷调查：课堂问卷、投票、意见收集，选项题和填空题都有。",
        "rules": [
            "type 固定写 \"survey\"。",
            "answers 每题一项：q 写题目本身（如 \"你喜欢这节课吗\"，所有人一致，平台按它统计每个选项选了多少人），"
            "answer 写选中的选项文字（不要只写 A/B，写选项原文；多选用逗号连起来）。问卷不判对错，不写 correct、score。",
            "量表题（1~5 分）也可以放进 ratings：item 题目、score 分、max 满分，平台会画雷达图。",
            "匿名问卷：老师要求匿名时 student 只写 class（班级），不写学号姓名。",
        ],
        "example": {
            "type": "survey",
            "student": {"no": "20250101", "name": "张三", "class": "七年级1班"},
            "activity": {"id": "S-1103", "name": "第3课 课后问卷"},
            "answers": [
                {"q": "你喜欢这节课吗", "answer": "喜欢"},
                {"q": "最难的部分（可多选）", "answer": "循环,调试"},
                {"q": "还想学什么", "answer": "做一个小游戏"},
            ],
            "ratings": [{"item": "难度", "score": 3, "max": 5}],
        },
    },
    "custom": {
        "what": "自定义：交互课件、模拟实验、操作记录、作品提交等，平台不限制内容。",
        "rules": [
            "type 自己起一个英文小写名字（如 \"experiment\"、\"event\"），同一类数据一直用同一个；"
            "平台认得的 answer / self_eval / peer_eval / survey 能用就用（统计更全）。",
            "能对上的就放标准字段：有分数就写 score / max_score，有逐题就写 answers，有文字感想就写 comment。",
            "其余任意内容放进 data（一层对象，键用中文或英文都行，值尽量是数字或短文字，不要整段 HTML、不要图片的 base64）。"
            "data 里的每个键会在平台「数据表单」里自动成为一列。",
            "记录操作过程的，每个关键步骤送一条 type \"event\"，data 里写 step、用时等；不要每次点击都送。",
        ],
        "example": {
            "type": "experiment",
            "student": {"no": "20250101", "name": "张三", "class": "七年级1班"},
            "activity": {"id": "L5-LAB", "name": "第5课 电路模拟实验"},
            "score": 9, "max_score": 10,
            "comment": "串联时灯泡变暗了",
            "data": {"实验次数": 3, "用时秒": 245, "最终电压": 4.5, "结论": "串联分压"},
        },
    },
}

_TYPE_HINT = "；".join(f"{k} {v}" for k, v in svc.TYPE_NAMES.items() if k != "data")

_HELPER = r"""// ======== 本平台数据接口（原样保留，不要改函数名和字段名）========
const WFXX = {
  ENDPOINT: '«EP»',   // 接收地址；留空 = 预留接口：页面照常能用，提交的数据先存在本机
  TOKEN: '«TOKEN»',   // 写入密钥（只能写入，看不到数据，可以写在网页里）
  ACTIVITY: { id: '«ACT_ID»', name: '«ACT_NAME»' },   // 这个网页是哪节课哪个任务
};
const WFXX_QKEY = 'wfxx-queue-' + (WFXX.ENDPOINT.split('/').pop() || 'local');

function wfxxId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
}
function wfxxLoad() { try { return JSON.parse(localStorage.getItem(WFXX_QKEY) || '[]'); } catch (e) { return []; } }
function wfxxSave(q) { try { localStorage.setItem(WFXX_QKEY, JSON.stringify(q.slice(-500))); } catch (e) {} }
function wfxxKeep(body) { const q = wfxxLoad(); q.push(body); wfxxSave(q); }
function wfxxPrep(record) {
  return Object.assign({
    client_id: wfxxId(),            // 每条一个编号：断网重发不会重复入库
    activity: WFXX.ACTIVITY,
    page: location.href,
    submitted_at: new Date().toISOString(),
  }, record);
}
async function wfxxPost(body) {
  const res = await fetch(WFXX.ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Api-Key': WFXX.TOKEN },
    body: JSON.stringify(body),
  });
  let r;
  try { r = await res.json(); } catch (e) { r = { ok: false, code: 'HTTP_' + res.status, message: '服务器返回了看不懂的内容' }; }
  r.status = res.status;
  r.retryAfter = Number(res.headers.get('Retry-After')) || 0;
  return r;
}
// 提交一条（或一个数组批量，最多 500 条）。返回回执 {ok, code, message, ...}，永远不会抛异常
async function wfxxSend(record) {
  const body = Array.isArray(record) ? record.map(wfxxPrep) : wfxxPrep(record);
  if (!WFXX.ENDPOINT) {
    [].concat(body).forEach(wfxxKeep);
    return { ok: false, code: 'NOT_CONNECTED', queued: true, message: '还没接入平台，数据先存在本机' };
  }
  try {
    const r = await wfxxPost(body);
    if (r.status >= 500 || r.status === 429) { [].concat(body).forEach(wfxxKeep); r.queued = true; }
    return r;
  } catch (e) {
    [].concat(body).forEach(wfxxKeep);
    return { ok: false, code: 'OFFLINE', queued: true, message: '网络不通，已暂存，联网后自动补发' };
  }
}
// 补发暂存的数据（打开页面、重新联网时自动调用）
async function wfxxFlush() {
  const q = wfxxLoad();
  if (!WFXX.ENDPOINT || !q.length) return 0;
  try {
    const part = q.slice(0, 500);
    const r = await wfxxPost(part);
    if (r.status < 500 && r.status !== 429) { wfxxSave(wfxxLoad().slice(part.length)); return part.length; }
  } catch (e) {}
  return 0;
}
// 关页面的那一刻也要送出去时用（如记录停留时长）：sendBeacon 带不了请求头，密钥放在 _token 里
function wfxxBeacon(record) {
  if (!WFXX.ENDPOINT || !navigator.sendBeacon) return false;
  const body = Object.assign(wfxxPrep(record), { _token: WFXX.TOKEN });
  return navigator.sendBeacon(WFXX.ENDPOINT, new Blob([JSON.stringify(body)], { type: 'text/plain' }));
}
window.addEventListener('online', wfxxFlush);
setTimeout(wfxxFlush, 1500);
// ======== 平台数据接口结束 ========"""

_SUMMARY_HELPER = r"""// 全班汇总（不含任何学生个人信息）：{ok, records 条数, people 人数, avg_score 平均分, avg_rate 平均得分率%,
//   max_score, min_score, questions:[{q, n, rate 正确率%}], dimensions:[{item, self, peer}], distribution}
async function wfxxSummary() {
  if (!WFXX.ENDPOINT) return { ok: false, code: 'NOT_CONNECTED' };
  const a = WFXX.ACTIVITY.id || WFXX.ACTIVITY.name;
  try {
    const res = await fetch(WFXX.ENDPOINT + '/summary' + (a ? '?activity=' + encodeURIComponent(a) : ''),
      { headers: { 'X-Api-Key': WFXX.TOKEN } });
    return await res.json();
  } catch (e) { return { ok: false, code: 'OFFLINE' }; }
}"""


def _js_str(s: str) -> str:
    """放进 JS 单引号字符串里。"""
    return (s or "").replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ").replace("\r", "")


def build(api: DataApi, endpoint: str, class_names: list[str] | None = None) -> str:
    """生成整段提示词。endpoint 是学生网页能访问到的接收地址（调用方按对外地址拼好）。"""
    class_names = [c for c in (class_names or []) if c]
    purpose = _PURPOSE.get(api.template) or _PURPOSE["custom"]
    act_id = f"API{api.id}"
    act_name = api.name
    helper = (_HELPER.replace("«EP»", _js_str(endpoint)).replace("«TOKEN»", _js_str(api.write_token))
              .replace("«ACT_ID»", _js_str(act_id)).replace("«ACT_NAME»", _js_str(act_name)))
    example = json.dumps(purpose["example"], ensure_ascii=False, indent=2)
    origins = [x for x in (api.allowed_origins or "").splitlines() if x.strip()]

    out: list[str] = []
    w = out.append
    w("# 给 AI 的任务：做一个接入教学平台的教学网页")
    w("")
    w("你是一名擅长做课堂互动网页的前端工程师。请按我在最后「老师的要求」里写的内容，做一个**单文件 HTML 网页**"
      "（HTML、CSS、JavaScript 都写在一个 .html 文件里，不依赖构建工具，双击或放到任意网站上都能打开），"
      "并且**严格按下面的规则**把学生的数据提交到我们学校的教学平台。平台会按这些字段自动统计"
      "（逐题正确率、自评互评雷达图、成绩分布、谁还没交），学号对得上学校名单的学生，数据还会汇总进他的个人学情。"
      "字段名写错，平台就统计不出来。")
    w("")
    w("## 一、这个接口是干什么的")
    w("")
    w(f"- 接口名称：{api.name}")
    if (api.description or "").strip():
        w(f"- 老师的说明：{api.description.strip()}")
    w(f"- 用途：{purpose['what']}")
    w(f"- 接收地址：{endpoint or '（还没给，按「预留接口」做，见第七节）'}")
    w(f"- 写入密钥：{api.write_token}（只能往这个接口写数据，看不到任何数据，可以写在网页代码里）")
    w("")
    w("## 二、提交代码：原样放进网页的 <script> 里")
    w("")
    w("下面这段已经处理好密钥、去重编号、断网暂存与自动补发，**原样复制，不要改函数名、字段名、请求方式**，"
      "也不要换成别的写法（不要用 axios、不要改成表单提交）。网页里要提交数据时只调用 `wfxxSend(记录)`。"
      "唯一可以改的是 `WFXX.ACTIVITY`：一个网页里有几个任务、几个关卡的，按任务填不同的 id 和 name"
      "（在 wfxxSend 的记录里写 `activity: {id, name}` 会覆盖默认值）。")
    w("")
    w("```js")
    w(helper)
    if api.public_summary:
        w("")
        w(_SUMMARY_HELPER)
    w("```")
    w("")
    w("## 三、学生身份（必须有）")
    w("")
    w("1. 页面开始答题前，先让学生填**学号、姓名、班级**，三项都填了才能开始（老师要求匿名的除外）。")
    if class_names:
        opts = "、".join(f"「{c}」" for c in class_names)
        w(f"2. 班级做成**下拉框**，选项只有：{opts}。选项文字一字不改（平台按它对名单）。")
    else:
        w("2. 班级用输入框，提示学生按学校的写法填，如「七年级1班」（平台按「班级 + 姓名」对名单，写法不一致就对不上）。")
    w("3. 学号去掉首尾空格，按字符串保存（不要转成数字，前导 0 会丢）。")
    w("4. 填过的身份存进 localStorage，下次打开自动带出，页面上显示「当前：张三（20250101）」并给一个「不是我」按钮重新填。")
    w("5. 每条提交都带上 `student: {no: 学号, name: 姓名, class: 班级}`。")
    w("")
    w("## 四、数据怎么填（这个接口的用途）")
    w("")
    for i, r in enumerate(purpose["rules"], 1):
        w(f"{i}. {r}")
    w("")
    w("一条完整的例子（真正提交时 `client_id`、`page`、`submitted_at` 由 wfxxSend 自动补上，不用自己写）：")
    w("")
    w("```json")
    w(example)
    w("```")
    w("")
    w("全部可用字段（每一项都可以不填，但填了就要按这个名字和类型）：")
    w("")
    w("| 字段 | 类型 | 说明 |")
    w("|---|---|---|")
    w(f"| type | 字符串 | 数据类型：{_TYPE_HINT}，或自定义英文名 |")
    w("| student | 对象 | `{no 学号, name 姓名, class 班级}`，都是字符串 |")
    w("| activity | 对象 | `{id 任务编号, name 任务名称}`，同一个任务的编号永远不变 |")
    w("| score / max_score | 数字 | 整份的得分 / 满分 |")
    w("| answers | 数组 | 逐题：`{q 题号, answer 作答, correct 对错, score 得分, max 满分, time_ms 用时毫秒}` |")
    w("| ratings | 数组 | 评价维度：`{item 维度名, score 分, max 满分}` |")
    w("| target | 对象 | 互评的被评人 `{no, name}` |")
    w("| comment | 字符串 | 评语、反思、感想 |")
    w("| data | 对象 | 其他任意内容，一层键值，每个键在平台上自动成为一列 |")
    w("")
    w("不要另起名字（不要写 studentName、stuNo、totalScore、questions 之类），不要把整份数据转成字符串再塞进某个字段。"
      "单条不超过 256 KB；不要提交图片、音频的 base64。")
    w("")
    w("## 五、提交时机与回执")
    w("")
    w("- 学生点「提交」时调用一次 `wfxxSend`；按钮在等待回执期间禁用，防止连点。"
      "需要过程数据的，可以在每个关卡结束时各送一条（activity 区分关卡）。")
    w("- 同一份作答允许学生改了再交：每次重交都是新的一条（wfxxSend 会生成新的 client_id）。"
      + ("这个接口设置了「同一学生同一活动只算最新一条」，平台只统计最后一次。" if api.dedupe == "latest"
         else "平台会把每次提交都计入统计，如果只想留最后一次，在网页上提示学生「确认后再提交」。"))
    w("- 回执处理，按 `r.ok` 和 `r.code`：")
    w("  - `r.ok === true`：显示「提交成功」；`r.duplicate === true` 也算成功（之前交过同一条）。")
    w("  - `r.queued === true`（OFFLINE 断网、服务器忙、NOT_CONNECTED 还没接入）：显示「已保存在本机，联网后自动补交」，不要让学生重复提交。")
    w("  - 429 `RATE_LIMITED`：提交太快，提示「请 r.retryAfter 秒后再试」。")
    w("  - 423 `PAUSED` / `OUT_OF_WINDOW`：老师暂停了接收或不在接收时间段，把 `r.message` 显示给学生。")
    w("  - 507 `QUOTA_FULL`：这个接口存满了，提示「请告诉老师清理数据」。")
    w("  - 401 `TOKEN_INVALID`、403 `ORIGIN_DENIED`、404 `API_NOT_FOUND`：接入配置有问题，显示「提交失败：r.message，请告诉老师」。")
    w("  - 其他：显示 `r.message`，保留学生的作答，允许再点一次提交。")
    w("- 提交成功后在页面上给学生看结果（得分、对错、评价摘要），不要只弹一个 alert 就清空页面。")
    if api.public_summary:
        w("- 提交成功后可以调用 `wfxxSummary()` 显示「全班已交 N 人、平均得分率 X%」，或每题全班正确率。它不含任何学生个人信息。")
    w("")
    w("## 六、页面要求")
    w("")
    w("- 适配电脑和手机（机房电脑、平板、手机都能用），中文界面，字号不小于 16px，按钮够大。")
    w("- 不依赖外网资源也能运行：不要引用国外 CDN；确实要用的库（如图表）选 cdn.jsdelivr.net 或直接写原生代码。")
    w("- 页面上不要显示接收地址和密钥；不要在网页里读取或展示其他同学的数据。")
    w("- 题目、选项、答案、评价维度放在代码最上面一个配置对象里，方便老师以后自己改。")
    w("")
    w("## 七、预留接口（还没拿到地址时）")
    w("")
    w("如果 `WFXX.ENDPOINT` 是空的，网页必须照常能用：提交后显示「已保存在本机（还没接入平台）」，数据由 wfxxSend 自动暂存。"
      "以后老师只要把接收地址和写入密钥填进 `WFXX` 两行，暂存的数据会在下次打开页面时自动补交，其他代码一行都不用改。")
    w("")
    w("## 八、注意")
    w("")
    if origins:
        w(f"- 这个接口只接收这些网站上的网页提交：{'、'.join(origins)}。网页必须放到这些网站上；"
          "直接双击打开（file://）或放在别的网站上，提交会被拒绝（403 ORIGIN_DENIED）。")
    if endpoint.startswith("http://"):
        w("- 接收地址是 http 的：网页如果放在 https 的网站上，浏览器会拦截提交（混合内容）。"
          "这时把网页放在 http 网站上、直接双击打开，或者请老师给平台开 HTTPS。")
    w("- 不要使用读取密钥，也不要尝试调用 /records 之类的读取接口。")
    w(f"- 每个接口最多存 {svc.MAX_RECORDS} 条，不要做自动循环提交、定时轮询提交。")
    w("")
    w("## 九、交付前自检（逐条确认后再给我代码）")
    w("")
    w("1. 第二节的提交代码原样在网页里，`WFXX.ENDPOINT`、`WFXX.TOKEN` 和上面给的一致。")
    w("2. 所有提交都走 `wfxxSend`，字段名和第四节完全一致，type 是 \"" + purpose["example"]["type"] + "\"（或第四节说明的取值）。")
    w("3. 每条都带 `student`，学号是字符串；班级" + ("来自下拉框。" if class_names else "按学校写法填写。"))
    w("4. answers 的 q、ratings 的 item 对所有学生都一样，不随题目乱序而变。")
    w("5. 断网时点提交不会丢数据、不会报错，页面提示已暂存。")
    w("6. 回执的成功、暂存、失败三种情况页面上都有明确提示。")
    w("7. 只有一个 .html 文件，打开就能用。")
    w("")
    w("## 老师的要求")
    w("")
    w("（老师在这里写要做什么网页，例如：做一个「第3课 循环结构」的 10 道选择题闯关网页，每关 2 题，答对才能进下一关，"
      "最后显示得分和每题解析。）")
    w("")
    return "\n".join(out)
