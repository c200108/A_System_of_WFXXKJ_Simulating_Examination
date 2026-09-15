"""学生名单的解析与入库 —— 「上传表格」和「粘贴名单」共用这一套。

两个入口以前各写各的：表格认四列、粘贴只认两列，班级归属、性别、错误提示
全都不一样，老师换个入口就得重新适应一遍。现在统一成：

    解析（表格 / 粘贴各一个函数，产出同一种结构）
        ↓
    ingest()  —— 校验、查班级、归一性别、建账号、汇总错误

于是两边的规则、报错措辞、跳过策略完全一致，改一处两边都变。

## 一行有哪四列

    学号    姓名    班级（选填）    性别（选填）

班级要和「班级」页面完全一致；留空则归到调用方指定的那个班。
性别填男/女，认不出就留空，不挡着建账号。

## 多工作表

上传的 Excel 里**每一张表都会读**，一个年级一张表这种排法很常见。
认不出是学生名单的表（比如模板自带的「填写说明」「可用班级」）自动跳过，
不会因为它们报一堆错。
"""

import csv
import io
import re

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SchoolClass, Student

# 一行解析出来的东西：(来源表名, 行号, [单元格...])
# 来源表名给多工作表用，粘贴名单时是空串。
Row = tuple[str, int, list[str]]

STUDENT_NO_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# 性别只认男女两种，别的写法尽量认出来。认不出的当没填 —— 它是补充信息，
# 不该因为写法花哨就把整个学生挡在门外。
GENDER_ALIASES = {
    "男": "男", "男生": "男", "m": "男", "male": "男", "boy": "男", "1": "男",
    "女": "女", "女生": "女", "f": "女", "female": "女", "girl": "女", "2": "女",
}

HINTS = {
    "split": "每行至少要有「学号」和「姓名」两部分。"
             "从 Excel 复制粘贴过来的自带制表符分隔，直接粘就行；"
             "手打的话用空格隔开，例如：20260101 张三",
    "no": "学号只能用字母、数字和 _ . -，不能有空格或中文，最长 32 位",
    "empty": "学号和姓名都必须填，空一个整行就导不进来",
}


def norm_gender(value) -> str:
    """认出来就返回「男」或「女」，认不出（含空）返回空串。"""
    text = str(value or "").strip()
    return GENDER_ALIASES.get(text.lower(), "") if text else ""


def clip(text: str, width: int = 16) -> str:
    """错误信息里回显用户填的内容时截一下，免得十几条堆起来没法看。"""
    value = (text or "").strip()
    return value if len(value) <= width else value[:width] + "…"


def _cell(value) -> str:
    """单元格转成字符串。

    学号在 Excel 里常被存成数字，直接 str() 会得到 "20260101.0"，
    末尾那个 .0 会让学号对不上，所以整数值要特判。
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _looks_like_header(cells: list[str]) -> bool:
    head = "".join(cells[:4])
    return "学号" in head or "姓名" in head


def _looks_like_student(cells: list[str]) -> bool:
    """这一行像不像一条学生记录：第一格是合规学号，第二格非空。"""
    if len(cells) < 2:
        return False
    return bool(cells[0]) and bool(cells[1]) and STUDENT_NO_RE.match(cells[0]) is not None


def sheet_rows(filename: str, raw: bytes) -> tuple[list[Row], list[str]]:
    """把上传的文件读成一行行单元格。返回 (数据行, 跳过的表名)。

    **每一张工作表都读** —— 一个年级一张表、或者按班分表都很常见。
    但模板自带「填写说明」「可用班级」两页，那两页不能当名单读，否则一上传
    就是一堆莫名其妙的错误。判断办法：一张表要么第一行是表头（含"学号"或
    "姓名"），要么第一条非空行长得像学生记录，两样都不沾就整表跳过。
    """
    lower = (filename or "").lower()

    if lower.endswith((".csv", ".txt")):
        text = _decode_csv(raw)
        grid = [[c.strip() for c in row] for row in csv.reader(io.StringIO(text))]
        return _take_sheet("", grid), []

    if not lower.endswith((".xlsx", ".xlsm")):
        raise ValueError("只支持 .xlsx 和 .csv 文件")

    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"这个 Excel 打不开，确认是 .xlsx 格式（{exc}）") from exc

    rows: list[Row] = []
    skipped: list[str] = []
    try:
        for ws in wb.worksheets:
            grid = [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]
            # 只有一张表时不标表名，报错里写「第 3 行」比「「Sheet1」第 3 行」清爽
            label = ws.title if len(wb.worksheets) > 1 else ""
            taken = _take_sheet(label, grid)
            if taken:
                rows += taken
            elif any(any(c for c in g) for g in grid):
                skipped.append(ws.title)
    finally:
        wb.close()
    return rows, skipped


def _take_sheet(label: str, grid: list[list[str]]) -> list[Row]:
    """认得出是名单就把数据行摘出来，认不出返回空列表。"""
    first = next((i for i, g in enumerate(grid) if any(c for c in g)), None)
    if first is None:
        return []

    start = first
    if _looks_like_header(grid[first]):
        start = first + 1
    elif not _looks_like_student(grid[first]):
        return []  # 既不是表头也不像学生记录 —— 多半是说明页

    return [
        (label, i + 1, list(g))
        for i, g in enumerate(grid)
        if i >= start and any(c for c in g)
    ]


def _decode_csv(raw: bytes) -> str:
    """老师用 Excel 另存的 CSV 多半是 GBK，UTF-8 解不出来就换一种试。"""
    for encoding in ("utf-8-sig", "gbk", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("这个 CSV 的编码认不出来，建议另存为 .xlsx 再传")


_MULTI_SPACE = re.compile(r"\s{2,}")


def split_pasted(line: str) -> list[str]:
    """把粘贴的一行拆成单元格。

    列分隔符按可靠程度依次尝试：制表符 → 逗号 → 连续两个以上空格。
    **单个空格不当列分隔符** —— 姓名里带空格（「钱 七」）比多列粘贴常见得多，
    拿单空格拆会把人家的名字劈成两半。从 Excel 复制出来天然是制表符分隔，
    所以「学号 姓名 班级 性别」四列直接粘就能正确认出来。
    """
    for sep in ("\t", "，", ","):
        if sep in line:
            return [c.strip() for c in line.split(sep)]
    if _MULTI_SPACE.search(line):
        return [c.strip() for c in _MULTI_SPACE.split(line)]

    parts = line.split()
    if len(parts) <= 2:
        return parts
    # 单空格分隔又超过两段：第一段是学号，剩下全算姓名
    return [parts[0], " ".join(parts[1:])]


def paste_rows(text: str) -> list[Row]:
    out: list[Row] = []
    for lineno, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        cells = split_pasted(line)
        # 第一行写了表头也认，和上传表格一个规矩
        if lineno == 1 and _looks_like_header(cells):
            continue
        out.append(("", lineno, cells))
    return out


def where(label: str, lineno: int) -> str:
    return f"「{label}」第 {lineno} 行" if label else f"第 {lineno} 行"


# 批量建账号时每攒多少条提交一次，以及提交后歇多久（按这批实际耗时的比例）。
# 建一个账号要算一次 bcrypt（约 190 毫秒），1500 人近 5 分钟 —— 不主动让出
# CPU 的话，机房里正在答题的学生会明显卡。0.25 = 每干 4 秒歇 1 秒。
CHUNK = 100
THROTTLE = 0.25


def ingest(db: Session, rows: list[Row], me_id: int, fallback: SchoolClass | None,
           *, make_password, hash_it) -> dict:
    """把解析好的行灌进库。上传表格和粘贴名单共用这一段。

    make_password / hash_it 由调用方传进来，纯粹为了让这个模块不依赖
    security 和业务常量，测试时也能塞个快的假实现进来。
    """
    import time

    # 班级按显示名查。键上去掉空格，「七年级 1班」这种手滑也能认出来；
    # 但别的差异（七(3)班 vs 七年级3班）一律算写错，照实报出来让人改对 ——
    # 猜来猜去反而会把学生塞进错的班。
    all_classes = list(db.scalars(select(SchoolClass)))
    by_name = {c.display.replace(" ", ""): c for c in all_classes}
    valid_hint = "、".join(c.display for c in all_classes[:6]) or "（还没有建班级）"

    existing = set(db.scalars(select(Student.student_no)))
    added = skipped = pending = 0
    bad: list[str] = []
    kinds: set[str] = set()
    bad_classes: set[str] = set()
    bad_gender: list[str] = []
    used_classes: set[str] = set()

    started = time.perf_counter()
    for label, lineno, cells in rows:
        # 按列位置取，不要先把空单元格挤掉 —— 学号和姓名之间空一格的话，
        # 挤掉之后班级会被当成姓名
        no, name, cls_name, sex = (list(cells) + ["", "", "", ""])[:4]
        no, name = no.strip(), name.strip()
        cls_name, sex = cls_name.strip(), sex.strip()
        at = where(label, lineno)

        if not no and not name:
            continue
        if not no or not name:
            kinds.add("split" if not name else "empty")
            bad.append(f"{at}「{clip(no or name)}」：分不出学号和姓名")
            continue
        if not STUDENT_NO_RE.match(no) or len(no) > 32:
            kinds.add("no")
            bad.append(f"{at}「{clip(no)}」：学号不合规")
            continue

        # 性别认不出只记一笔、留空，不挡着建账号
        gender = norm_gender(sex)
        if sex and not gender:
            bad_gender.append(at)

        if cls_name:
            cls = by_name.get(cls_name.replace(" ", ""))
            if cls is None:
                # 只说"哪一行、错在哪"，"该怎么改"整批在末尾给一次 ——
                # 每行都跟一遍的话，错十几行就刷十几遍同样的话
                bad_classes.add(cls_name)
                bad.append(f"{at}：没有「{clip(cls_name)}」这个班")
                continue
        else:
            cls = fallback

        if no in existing:
            skipped += 1
            continue

        db.add(
            Student(
                student_no=no,
                name=name[:64],
                class_id=cls.id if cls else None,
                student_class=cls.display if cls else "",
                gender=gender,
                password_hash=hash_it(make_password(no)),
                created_by=me_id,
            )
        )
        if cls:
            used_classes.add(cls.display)
        existing.add(no)
        added += 1
        pending += 1

        # 分批提交并主动歇一下，歇多久按这批实际花的时间算 ——
        # 机器快就少歇、慢就多歇，不用改代码去适配
        if pending >= CHUNK:
            db.commit()
            pending = 0
            if THROTTLE > 0:
                time.sleep(min((time.perf_counter() - started) * THROTTLE, 2.0))
            started = time.perf_counter()

    db.commit()

    tips = [HINTS[k] + "。" for k in ("split", "empty", "no") if k in kinds]
    if bad_classes:
        wrong = "、".join(sorted(bad_classes)[:5])
        tips.append(
            f"表里这些班级名系统里没有：{wrong}。"
            f"班级名要和「班级」页面完全一致，例如：{valid_hint}。"
            "模板第三页「可用班级」里有现成的，照抄就不会错。"
        )
    if bad_gender:
        spots = "、".join(bad_gender[:8]) + ("…" if len(bad_gender) > 8 else "")
        tips.append(
            f"{spots} 的性别没认出来，这几位的性别先留空了（账号已正常建好）。"
            "性别填「男」或「女」即可，也可以之后在学生列表里补。"
        )

    return {
        "added": added,
        "skipped": skipped,
        "errors": bad[:20],
        "error_count": len(bad),
        "hint": "\n".join(tips),
        "classes": sorted(used_classes),
        "student_class": fallback.display if fallback else "",
    }
