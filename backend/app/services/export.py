"""导出：题库 Excel、本卷 Excel、学生答题网页。

学生答题网页是一个完全独立的单文件 HTML：图片转成 data URI 内嵌，
拿到哪儿都能打开，交卷后在浏览器里直接判分，不依赖本系统的服务器。
"""

import base64
import io
import json
import mimetypes
import os

from openpyxl import Workbook

from ..config import settings

BANK_HEADERS = ["题型", "题干", "可选项", "答案", "知识范围", "来源", "编号"]
BANK_WIDTHS = [8, 60, 34, 26, 16, 10, 9]


def _opts_text(options) -> str:
    parts = []
    for o in options or []:
        label = o["label"] if isinstance(o, dict) else o.label
        content = o["content"] if isinstance(o, dict) else o.content
        parts.append(f"{label}.{content}")
    return "\n".join(parts)


def questions_to_xlsx(rows: list, sheet_name: str = "题库") -> bytes:
    """行可以是 ORM 对象，也可以是组卷返回的字典，字段名一致。"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(BANK_HEADERS)

    for q in rows:
        get = (lambda k: q.get(k)) if isinstance(q, dict) else (lambda k: getattr(q, k, None))
        ws.append(
            [
                get("type"),
                get("stem"),
                _opts_text(get("options")),
                get("answer"),
                get("scope"),
                get("source"),
                get("code") or get("id"),
            ]
        )

    for col, width in zip("ABCDEFG", BANK_WIDTHS):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _embed_image(url: str | None) -> str:
    """把 /uploads/images/x.png 读成 data URI，让导出的网页能独立分发。"""
    if not url:
        return ""
    if url.startswith(("http://", "https://", "data:")):
        return url
    rel = url.replace("/uploads/", "", 1).lstrip("/")
    path = os.path.join(settings.upload_dir, rel)
    if not os.path.isfile(path):
        return ""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")


def student_html(paper: dict) -> str:
    """生成学生答题网页。结构与原 HTML 的 studentHTML() 一致。"""
    items = []
    for group in paper.get("groups") or []:
        for it in group["items"]:
            items.append(
                {
                    "t": it["type"],
                    "q": it["stem"],
                    "o": [[o["label"], o["content"]] for o in it.get("options") or []],
                    "a": it.get("answer") or "",
                    "k": it.get("scope") or "",
                    "img": _embed_image(it.get("image_url")),
                }
            )

    payload = json.dumps(
        {
            "title": paper.get("title") or "信息技术测试卷",
            "school": paper.get("school") or "",
            "time": paper.get("duration") or "",
            "code": paper.get("code") or "",
            "items": items,
        },
        ensure_ascii=False,
    ).replace("<", "\\u003c")

    return _TEMPLATE.replace("__PAYLOAD__", payload).replace(
        "__TITLE__", (paper.get("title") or "信息技术测试卷").replace("<", "&lt;")
    )


_TEMPLATE = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>
:root{--bg:#F4F7F7;--sf:#fff;--line:#D8E2E2;--ink:#12283C;--tx:#22383F;--mut:#61757A;--teal:#166B66;--green:#2A6E4B;--gsoft:#E4F1E9;--red:#B23A22;--rsoft:#FBE9E4;--amber:#8A6100;--asoft:#FBF0D8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.7 'PingFang SC','Microsoft YaHei',sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:24px 18px 110px}
.head{background:var(--sf);border:1px solid var(--line);border-radius:12px;padding:22px;text-align:center}
h1{margin:0 0 6px;font-size:22px;color:var(--ink);font-family:'Heiti SC','SimHei','Microsoft YaHei',sans-serif;letter-spacing:.05em}
.meta{color:var(--mut);font-size:12.5px;font-family:ui-monospace,Consolas,monospace}
.who{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;margin-top:14px}
.who input{border:1px solid var(--line);border-radius:8px;padding:7px 10px;font:inherit;width:150px;background:var(--sf)}
.sect{margin:26px 0 8px;font-family:'Heiti SC','SimHei','Microsoft YaHei',sans-serif;font-size:17px;color:var(--ink)}
.q{background:var(--sf);border:1px solid var(--line);border-radius:10px;padding:15px 17px;margin-bottom:10px}
.stem{font-family:'Songti SC','SimSun',serif;font-size:15.5px;white-space:pre-wrap;color:var(--ink)}
.q img{max-width:100%;border:1px solid var(--line);border-radius:6px;margin-top:9px;background:#fff}
label.op{display:flex;gap:9px;align-items:flex-start;padding:5px 8px;border-radius:7px;cursor:pointer;border:1px solid transparent}
label.op:hover{background:var(--bg)}
label.op input{margin-top:5px;accent-color:var(--teal)}
.L{font-family:ui-monospace,Consolas,monospace;font-weight:600;color:var(--mut);min-width:18px}
textarea{width:100%;min-height:76px;border:1px solid var(--line);border-radius:8px;padding:9px;font:inherit;background:var(--sf);resize:vertical}
.ok{background:var(--gsoft);border-color:var(--green)}.no{background:var(--rsoft);border-color:var(--red)}
.key{margin-top:10px;background:var(--rsoft);border-left:3px solid var(--red);border-radius:0 7px 7px 0;padding:7px 11px;font-size:13.5px;color:var(--red);white-space:pre-wrap;display:none}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--sf);border-top:1px solid var(--line);padding:12px 18px;display:flex;gap:12px;align-items:center;justify-content:center;flex-wrap:wrap}
button{font:inherit;font-weight:600;border:1px solid var(--line);background:var(--sf);color:var(--ink);border-radius:9px;padding:10px 18px;cursor:pointer}
button.p{background:var(--teal);border-color:var(--teal);color:#fff}
.score{font-family:ui-monospace,Consolas,monospace;font-size:19px;font-weight:600;color:var(--teal)}
.badge{font-size:12px;font-weight:600;border-radius:5px;padding:1px 8px;font-family:ui-monospace,Consolas,monospace;margin-left:8px}
.b-ok{background:var(--gsoft);color:var(--green)}.b-no{background:var(--rsoft);color:var(--red)}.b-na{background:var(--asoft);color:var(--amber)}
@media print{.bar{position:static}button{display:none}}
</style></head><body><div class="wrap">
<div class="head"><h1></h1><div class="meta"></div>
<div class="who"><input id="nm" placeholder="姓名"><input id="cl" placeholder="班级"><input id="no" placeholder="学号"></div></div>
<div id="body"></div></div>
<div class="bar"><span class="score" id="sc">未交卷</span><button class="p" id="sub">交卷判分</button><button id="dl">导出成绩单</button><button id="pr">打印</button></div>
<script>
const P = __PAYLOAD__;
document.title = P.title;
document.querySelector('h1').textContent = P.title;
document.querySelector('.meta').textContent = (P.school||'') + (P.time?'　·　'+P.time+' 分钟':'') + '　·　' + P.code;
const E = s => String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let graded = false;
const groups = [];
P.items.forEach(it => { let g = groups.find(x=>x.t===it.t); if(!g){ g={t:it.t, list:[]}; groups.push(g);} g.list.push(it); });
let n = 0; const CNn = ['一','二','三','四','五','六'];
let html = '';
groups.forEach((g,gi) => {
  html += '<div class="sect">' + CNn[gi] + '、' + g.t + '（共 ' + g.list.length + ' 题）</div>';
  g.list.forEach(it => {
    const i = n++;
    let inner = '<div class="stem">' + (i+1) + '. ' + E(it.q) + '</div>';
    if(it.img) inner += '<img src="' + it.img + '" alt="配图">';
    if(it.t === '操作题'){
      inner += '<textarea data-i="' + i + '" placeholder="写下你的操作步骤"></textarea>';
    } else {
      inner += it.o.map(o => '<label class="op" data-i="' + i + '" data-v="' + o[0] + '"><input type="radio" name="q' + i + '" value="' + o[0] + '"><span class="L">' + o[0] + '</span><span>' + E(o[1]) + '</span></label>').join('')
    }
    inner += '<div class="key" data-k="' + i + '"></div>';
    html += '<div class="q" data-q="' + i + '">' + inner + '</div>';
  });
});
document.getElementById('body').innerHTML = html;
const ANS = []; groups.forEach(g => g.list.forEach(it => ANS.push(it)));
function letterOf(it){ const a=(it.a||'').trim(); return it.t==='判断题' ? (a==='正确'?'A':a==='错误'?'B':a) : a; }
document.getElementById('sub').addEventListener('click', () => {
  if(graded) return;
  graded = true; let right=0, obj=0;
  ANS.forEach((it,i) => {
    const box = document.querySelector('[data-q="' + i + '"]');
    const key = box.querySelector('.key'); key.style.display='block';
    if(it.t === '操作题'){
      key.textContent = '答案要点：' + (it.a || '原卷未给答案');
      box.querySelector('textarea').disabled = true;
      const b=document.createElement('span'); b.className='badge b-na'; b.textContent='自评'; box.querySelector('.stem').appendChild(b);
      return;
    }
    if(!(it.a||'').trim()){
      // 原卷没给答案的题不计分，否则「没作答」会被当成答对
      key.textContent = '这道题原卷未给答案，不计分。';
      box.querySelectorAll('input').forEach(x => x.disabled = true);
      const b=document.createElement('span'); b.className='badge b-na'; b.textContent='不计分'; box.querySelector('.stem').appendChild(b);
      return;
    }
    obj++;
    const cl = letterOf(it);
    const sel = box.querySelector('input:checked');
    const val = sel ? sel.value : '';
    if(val === cl) right++;
    box.querySelectorAll('input').forEach(x => x.disabled = true);
    box.querySelectorAll('label.op').forEach(l => {
      if(l.dataset.v === cl) l.classList.add('ok');
      else if(l.dataset.v === val) l.classList.add('no');
    });
    key.textContent = '答案：' + (it.a || '原卷未给答案');
    const b=document.createElement('span'); b.className = 'badge ' + (val===cl?'b-ok':'b-no'); b.textContent = val===cl?'✓':'✕';
    box.querySelector('.stem').appendChild(b);
  });
  document.getElementById('sc').textContent = '客观题 ' + right + ' / ' + obj + '　正确率 ' + (obj?Math.round(right/obj*100):0) + '%';
  window.scrollTo({top:0, behavior:'smooth'});
});
document.getElementById('pr').addEventListener('click', () => window.print());
document.getElementById('dl').addEventListener('click', () => {
  const nm = document.getElementById('nm').value || '未填姓名';
  const cl2 = document.getElementById('cl').value || '';
  const no2 = document.getElementById('no').value || '';
  let txt = P.title + '\r\n' + P.code + '\r\n姓名：' + nm + '\t班级：' + cl2 + '\t学号：' + no2 + '\r\n' + document.getElementById('sc').textContent + '\r\n\r\n';
  ANS.forEach((it,i) => {
    const box = document.querySelector('[data-q="' + i + '"]');
    let mine = '';
    if(it.t === '操作题') mine = (box.querySelector('textarea').value || '').replace(/\s+/g,' ');
    else { const s = box.querySelector('input:checked'); mine = s ? s.value : '未作答'; }
    txt += (i+1) + '. 我的答案：' + mine + '　参考答案：' + (it.a||'—') + '\r\n';
  });
  const blob = new Blob(['﻿' + txt], {type:'text/plain;charset=utf-8'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = nm + '_' + P.code + '_成绩单.txt'; document.body.appendChild(a); a.click(); a.remove();
});
</script></body></html>"""
