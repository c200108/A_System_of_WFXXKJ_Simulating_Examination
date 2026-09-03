"""Excel 题库导入：把原 HTML 里 normType / parseOpts / normAns / handleRows
这套校验规则原样搬到后端，规则不变，只是执行位置从浏览器换成了服务器。"""

import hashlib
import io
import re

from openpyxl import Workbook, load_workbook

from ..constants import IMPORT_HEADERS

_OPT_RE = re.compile(r"^([A-Da-d])\s*[.．、,，:：]?\s*(.+)$")
_IMG_RE = re.compile(r"^(data:image|https?://|/uploads/)")


def stem_hash(stem: str) -> str:
    """题干去掉所有空白后取哈希，用来查重。"""
    normalized = re.sub(r"\s+", "", stem)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def norm_type(value) -> str:
    s = str(value or "").strip()
    if "选择" in s:
        return "选择题"
    if "判断" in s:
        return "判断题"
    if "操作" in s:
        return "操作题"
    if "填空" in s:
        return "填空题"
    return ""


def parse_options(value, qtype: str) -> list[tuple[str, str]]:
    if qtype == "判断题":
        return [("A", "正确"), ("B", "错误")]
    s = "" if value is None else str(value).strip()
    if not s:
        return []
    parts = [x.strip() for x in re.split(r"[\r\n]+", s) if x.strip()]
    out: list[tuple[str, str]] = []
    for i, p in enumerate(parts):
        m = _OPT_RE.match(p)
        if m:
            out.append((m.group(1).upper(), m.group(2).strip()))
        else:
            out.append(("ABCD"[i] if i < 4 else str(i + 1), p))
    return out[:4]


def norm_answer(value, qtype: str) -> str:
    s = "" if value is None else str(value).strip()
    if qtype == "判断题":
        if re.fullmatch(r"(√|对|T|true|正确)", s, re.I):
            return "正确"
        if re.fullmatch(r"(×|x|错|F|false|错误)", s, re.I):
            return "错误"
    return s


def norm_image(value) -> str | None:
    s = str(value or "").strip()
    return s if s and _IMG_RE.match(s) else None


def _rows_to_questions(
    grid: list[list], sheet_name: str, valid_scopes: set[str]
) -> tuple[list[dict], list[dict], int]:
    """逐行校验一张二维表。Excel 的每个工作表和 CSV 都走这里，规则只有一份。"""
    if not grid:
        return [], [], 0

    head = [str(h or "").strip() for h in grid[0]]
    idx = {h: (head.index(h) if h in head else -1) for h in IMPORT_HEADERS}
    if idx["题型"] < 0 or idx["题干"] < 0:
        return [], [{"sheet": sheet_name, "row": 1, "reason": "__headless__"}], 0

    good: list[dict] = []
    errors: list[dict] = []
    rows_seen = 0

    for i, row in enumerate(grid[1:], start=2):
        def get(col: str):
            j = idx[col]
            return row[j] if 0 <= j < len(row) else ""

        stem = str(get("题干") or "").strip()
        if not stem:
            continue  # 空行直接忽略，不算错误
        rows_seen += 1

        qtype = norm_type(get("题型"))
        if not qtype:
            errors.append(
                {"sheet": sheet_name, "row": i,
                 "reason": f"题型「{str(get('题型') or '')}」无法识别"}
            )
            continue

        scope = str(get("知识范围") or "").strip()
        if scope not in valid_scopes:
            errors.append(
                {"sheet": sheet_name, "row": i,
                 "reason": f"知识范围「{scope or '空'}」不在十类之内"}
            )
            continue

        options = parse_options(get("可选项"), qtype)
        answer = norm_answer(get("答案"), qtype)

        if qtype == "选择题":
            if len(options) < 2:
                errors.append(
                    {"sheet": sheet_name, "row": i, "reason": "选择题至少要有两个可选项"}
                )
                continue
            labels = {lb for lb, _ in options}
            if answer and answer.upper() not in labels:
                errors.append(
                    {"sheet": sheet_name, "row": i,
                     "reason": f"答案「{answer}」不在可选项 {'/'.join(sorted(labels))} 之内"}
                )
                continue
            answer = answer.upper()

        good.append(
            {
                "type": qtype,
                "stem": stem,
                "answer": answer,
                "scope": scope,
                "source": "自定义",
                "image_url": norm_image(get("图片")),
                "options": options,
                "sheet": sheet_name,
                "row": i,
            }
        )

    return good, errors, rows_seen


def parse_workbook(content: bytes, valid_scopes: set[str]) -> tuple[list[dict], list[dict], int]:
    """返回 (合格题目, 错误明细, 扫描到的数据行数)。多张工作表一起读。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rows_seen = 0
    good: list[dict] = []
    errors: list[dict] = []
    # 说明页、对照表这类没有题干列的工作表先记下来，只有整本都读不出题时才报错，
    # 否则教师用我们自带的模板导入会平白多出一条“失败”。
    headless_sheets: list[str] = []
    usable_sheets = 0

    for sheet in wb.worksheets:
        grid = [list(r) for r in sheet.iter_rows(values_only=True)]
        if not grid:
            continue
        g, e, n = _rows_to_questions(grid, sheet.title, valid_scopes)
        if e and e[0]["reason"] == "__headless__":
            headless_sheets.append(sheet.title)
            continue
        usable_sheets += 1
        good += g
        errors += e
        rows_seen += n

    if usable_sheets == 0:
        for title in headless_sheets:
            errors.append(
                {"sheet": title, "row": 1, "reason": "找不到「题型」「题干」表头，整表跳过"}
            )

    wb.close()
    return good, errors, rows_seen


def parse_csv(content: bytes, valid_scopes: set[str]) -> tuple[list[dict], list[dict], int]:
    """CSV 走和 Excel 完全一样的校验规则，只是读法不同。

    编码依次试 UTF-8(BOM)、UTF-8、GBK —— WPS 和 Excel 存出来的 CSV 多半是 GBK。
    """
    import csv

    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("这个 CSV 的编码认不出来，请另存为 UTF-8 或 xlsx 再传")

    grid = [row for row in csv.reader(io.StringIO(text))]
    good, errors, rows_seen = _rows_to_questions(grid, "CSV", valid_scopes)
    for e in errors:
        if e["reason"] == "__headless__":
            e["reason"] = "找不到「题型」「题干」表头，第一行必须是表头"
    return good, errors, rows_seen


def build_template(scopes: list[str], types: list[str]) -> bytes:
    """生成空白模板：第一张表是填写区，第二张表是对照表。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "题目"
    ws.append(IMPORT_HEADERS)
    ws.append(
        [
            "选择题",
            "在 Windows 中，用于切换当前活动窗口的快捷键是（ ）。",
            "A.Alt+Tab\nB.Ctrl+C\nC.Alt+F4\nD.Win+D",
            "A",
            "Windows系统操作",
            "",
        ]
    )
    ws.append(["判断题", "计算机病毒是一种可以自我复制的程序。", "", "正确", "信息安全与网络道德", ""])
    ws.append(["操作题", "把当前文档另存为 PDF 并命名为「作业.pdf」。", "", "略", "WPS文字操作", ""])
    widths = [10, 60, 40, 12, 22, 30]
    for col, w in zip("ABCDEF", widths):
        ws.column_dimensions[col].width = w

    ws2 = wb.create_sheet("对照表")
    ws2.append(["知识范围（只能填这十类）", "题型"])
    for i in range(max(len(scopes), len(types))):
        ws2.append([scopes[i] if i < len(scopes) else "", types[i] if i < len(types) else ""])
    ws2.column_dimensions["A"].width = 26
    ws2.column_dimensions["B"].width = 14

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
