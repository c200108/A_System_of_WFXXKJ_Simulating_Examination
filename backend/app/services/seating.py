"""在线座次：区域解析 + 随机分座（2.20.0）。

纯计算，不碰数据库，方便测。界面那头（frontend/src/components/SeatSheet.vue）负责
表格本身；「一键导入本班学生」把老师写的区域和选项交到这里，算好「哪个格子放谁」
再填回表格。

## 区域怎么写

任意多段、可以不连续：`B2:B15, A4:H4, A1:D5`，也可以写单格 `C3`。分隔用英文 / 中文
逗号、分号、顿号或空格都行，字母大小写都认。座位顺序：**按区域写的先后，区域里先行后列**
（第一行从左到右，再第二行……）。同一个格子在几段区域里重复出现，只算第一次。

## 排法

- 随机（默认）或按学号顺序；
- 男女交错：相邻座位尽量异性 —— 按表格坐标给每个座位一个「棋盘色」（行号 + 列号的
  奇偶），人多的性别占座位多的那种颜色，左右、上下相邻的就是一男一女；人数不均时
  多出来的人补进剩下的座位，性别没填的当作谁都能坐；
- 学困生分配固定区域：老师在表格上另指定一块区域，学困生优先排进去；区域放不下的
  学困生照常排到别的座位，并提示；区域里剩下的座位再给其他同学。
"""

from __future__ import annotations

import random
import re

MAX_COL = 16384          # Excel 的上限 XFD
MAX_ROW = 1048576
MAX_SEATS = 5000         # 一次最多这么多个座位，防止写成 A1:XFD1048576 把服务器算死

_CELL = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
_SPLIT = re.compile(r"[\s,，;；、]+")


class RangeError(ValueError):
    """区域写得不对。message 是能原样给老师看的中文。"""


def col_index(letters: str) -> int:
    """A → 0，Z → 25，AA → 26。"""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def col_letters(index: int) -> str:
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def cell_name(col: int, row: int) -> str:
    """(0, 0) → A1。"""
    return f"{col_letters(col)}{row + 1}"


def parse_cell(text: str) -> tuple[int, int]:
    """'B2' → (1, 1)（列、行，都从 0 起）。"""
    m = _CELL.match(text.strip().upper())
    if not m:
        raise RangeError(f"「{text}」不是单元格，应写成 B2 这样（列字母 + 行号）")
    col, row = col_index(m.group(1)), int(m.group(2)) - 1
    if col >= MAX_COL or row >= MAX_ROW:
        raise RangeError(f"「{text}」超出了表格范围")
    return col, row


def parse_ranges(text: str) -> list[tuple[int, int, int, int]]:
    """'B2:B15, A4:H4' → [(列1, 行1, 列2, 行2), ...]，左上到右下已经摆正。"""
    out = []
    for part in _SPLIT.split((text or "").strip()):
        if not part:
            continue
        bits = part.replace("：", ":").split(":")
        if len(bits) > 2:
            raise RangeError(f"「{part}」写多了冒号，区域写成 A1:D5 这样")
        c1, r1 = parse_cell(bits[0])
        c2, r2 = parse_cell(bits[-1])
        out.append((min(c1, c2), min(r1, r2), max(c1, c2), max(r1, r2)))
    return out


def cells_of(ranges, skip=()) -> list[str]:
    """区域 → 座位列表（单元格名），按区域先后、区域里先行后列，重复的只留第一次。

    skip：不能当座位的格子（合并单元格里除左上角以外的那些）。"""
    skip = {s.strip().upper() for s in skip}
    seen, out = set(), []
    for c1, r1, c2, r2 in ranges:
        if (c2 - c1 + 1) * (r2 - r1 + 1) > MAX_SEATS:
            raise RangeError(f"区域 {cell_name(c1, r1)}:{cell_name(c2, r2)} 太大了，"
                             f"一次最多 {MAX_SEATS} 个座位")
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                name = cell_name(c, r)
                if name in seen or name in skip:
                    continue
                seen.add(name)
                out.append(name)
                if len(out) > MAX_SEATS:
                    raise RangeError(f"座位太多了，一次最多 {MAX_SEATS} 个")
    return out


def _parity(cell: str) -> int:
    col, row = parse_cell(cell)
    return (col + row) % 2


def _place(people: list[dict], seats: list[str], alternate: bool) -> tuple[dict, list[dict]]:
    """把 people 排进 seats。返回 ({格子: 人}, 没排上的人)。"""
    if not alternate:
        got = dict(zip(seats, people))
        return got, people[len(seats):]

    males = [p for p in people if p.get("gender") == "男"]
    females = [p for p in people if p.get("gender") == "女"]
    others = [p for p in people if p.get("gender") not in ("男", "女")]
    even = sum(1 for s in seats if _parity(s) == 0)
    odd = len(seats) - even
    # 人多的性别占座位多的那种颜色，这样交错得最完整
    male_parity = 0 if (len(males) >= len(females)) == (even >= odd) else 1

    got: dict = {}
    for seat in seats:
        if not (males or females or others):
            break
        want, alt = (males, females) if _parity(seat) == male_parity else (females, males)
        queue = want or others or alt
        got[seat] = queue.pop(0)
    return got, males + females + others


def plan(students: list[dict], ranges: str, *, zone: str = "", alternate: bool = False,
         struggling_zone: bool = False, shuffle: bool = True, seed: str | None = None,
         content: str = "name", skip=()) -> dict:
    """算出一份座位表。

    students：[{id, student_no, name, gender, struggling}]（只给在用的）。
    返回 {seats, assignments: [{cell, student_id, text}], unplaced: [姓名], empty, warnings}。
    """
    seat_ranges = parse_ranges(ranges)
    if not seat_ranges:
        raise RangeError("先写要放学生的区域，比如 B2:B15, A4:H4")
    seats = cells_of(seat_ranges, skip)
    if not seats:
        raise RangeError("这些区域里没有可用的座位（都在合并单元格里？）")

    people = sorted(students, key=lambda s: str(s.get("student_no") or ""))
    if shuffle:
        random.Random(seed).shuffle(people)

    warnings: list[str] = []
    taken: dict = {}
    weak: list[dict] = []
    if struggling_zone:
        zone_ranges = parse_ranges(zone)
        if not zone_ranges:
            raise RangeError("勾了「学困生分配固定区域」，要写上那块区域，比如 A1:D2")
        in_zone = set(cells_of(zone_ranges, skip))
        zone_seats = [s for s in seats if s in in_zone]
        if not zone_seats:
            warnings.append("学困生区域不在要排的座位里，学困生照常排")
        weak = [p for p in people if p.get("struggling")]
        people = [p for p in people if not p.get("struggling")]
        if not weak:
            warnings.append("本班还没有标记学困生（在「学生管理」里设），学困生区域没用上")
        got, left = _place(weak, zone_seats, alternate)
        taken.update(got)
        if left and zone_seats:
            warnings.append(f"学困生区域只有 {len(zone_seats)} 个座位，还有 {len(left)} 位学困生"
                            "排到了区域外")
            people = left + people

    rest = [s for s in seats if s not in taken]
    got, unplaced = _place(people, rest, alternate)
    taken.update(got)

    def text(p):
        return f"{p.get('student_no', '')} {p.get('name', '')}" if content == "no_name" \
            else str(p.get("name", ""))

    order = {s: i for i, s in enumerate(seats)}
    assignments = [{"cell": c, "student_id": p.get("id"), "text": text(p)}
                   for c, p in sorted(taken.items(), key=lambda kv: order[kv[0]])]
    if unplaced:
        warnings.append(f"座位比学生少 {len(unplaced)} 个，没排到："
                        + "、".join(str(p.get("name", "")) for p in unplaced[:20])
                        + ("…" if len(unplaced) > 20 else ""))
    empty = len(seats) - len(assignments)
    if empty:
        warnings.append(f"座位比学生多 {empty} 个，多出来的留空")
    return {
        "seats": len(seats),
        "assignments": assignments,
        "unplaced": [str(p.get("name", "")) for p in unplaced],
        "empty": empty,
        "warnings": warnings,
    }


def adjacent_same_gender(assignments: list[dict], genders: dict) -> int:
    """左右、上下相邻的同性对数（测试和界面提示用）。genders: {student_id: 男/女}。"""
    at = {}
    for a in assignments:
        at[parse_cell(a["cell"])] = genders.get(a["student_id"], "")
    bad = 0
    for (c, r), g in at.items():
        if g not in ("男", "女"):
            continue
        for dc, dr in ((1, 0), (0, 1)):
            if at.get((c + dc, r + dr)) == g:
                bad += 1
    return bad
