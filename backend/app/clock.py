"""系统时钟：服务器时间 + config.yaml 里的 time.offset_hours。

    python -m app.clock          启动前跑一次：校正值改了，就把已记下的时间一起挪（改过就跳过）

## 为什么要有它

有的服务器时钟不准又改不了（租的机器、别人管的机器）：页面上的交卷时间比北京时间
快 8 小时。config.yaml 里写 `time.offset_hours: -8`，整个系统的"现在"就往回拨 8 小时。

**程序里取"现在"一律用 clock.now()**，不要直接 datetime.now() —— 不然校正对那一处
不起作用，页面上会出现两种时间。登录令牌的过期时间例外（security.py 用 UTC），
那是同一台服务器自己签、自己验，和显示无关。

## 已经记下的时间怎么办

"所有显示时间的地方都是服务器时间 + 校正值"对老数据也得成立，所以校正值变了，
已有记录的时间要一起挪同样的差值。挪在启动的时候做一次（seed 里、服务开始接请求
之前），app_meta 里记着上次挪到了多少：

    上次 0，现在 -8     → 全部时间列 -8 小时，记成 -8
    上次 -8，现在 -8    → 什么都不做
    上次 -8，现在 -7    → 全部 +1 小时，记成 -7

app_meta 不跟着数据导出导入 —— 它说的是**这台机器**的时钟，不是数据本身。
导出来的时间已经是校正过的，导到别的机器上就是对的。
"""

from datetime import date, datetime, timedelta

from sqlalchemy import DateTime, bindparam, select, update

from .siteconfig import site

KEY = "time_offset_applied"


def offset() -> timedelta:
    return timedelta(hours=site.time.offset_hours)


def now() -> datetime:
    """系统的"现在"：服务器时间 + 校正值，精确到秒。

    去掉微秒：MySQL 的 DATETIME 只存到秒，而且是四舍五入 —— 23:59:59.6 会进到第二天。
    """
    return (datetime.now() + offset()).replace(microsecond=0)


def today() -> date:
    return now().date()


def rebase(db) -> float:
    """校正值变了就把所有时间列挪到新的基准上。返回挪了多少小时（0 = 没动）。"""
    from .models import AppMeta, Base

    want = float(site.time.offset_hours)
    row = db.get(AppMeta, KEY)
    had = float(row.value) if row and row.value not in (None, "") else 0.0
    if row is not None and had == want:
        return 0.0

    delta = want - had
    if delta:
        shift = timedelta(hours=delta)
        for table in Base.metadata.sorted_tables:
            cols = [c for c in table.columns if isinstance(c.type, DateTime)]
            if not cols or "id" not in table.c or table.name == AppMeta.__tablename__:
                continue
            rows = db.execute(select(table.c.id, *cols)).all()
            if not rows:
                continue
            # 所有时间列一起写 —— 不然 updated_at 的 onupdate 会被触发，改成"现在"
            stmt = (update(table).where(table.c.id == bindparam("_id"))
                    .values({c.name: bindparam("v_" + c.name) for c in cols}))
            params = [{"_id": r[0], **{"v_" + c.name: (v + shift if v is not None else None)
                                        for c, v in zip(cols, r[1:])}}
                      for r in rows]
            db.execute(stmt, params)
            print(f"[时钟] {table.name:<20} {len(rows):>6} 行的时间挪了 {delta:+g} 小时")

    if row is None:
        db.add(AppMeta(key=KEY, value=str(want)))
    else:
        row.value = str(want)
    db.commit()
    return delta


def main() -> int:
    from .database import SessionLocal
    db = SessionLocal()
    try:
        moved = rebase(db)
    finally:
        db.close()
    if moved:
        print(f"[时钟] 校正值改成了 {site.time.offset_hours:+g} 小时，已有记录的时间一起挪了 {moved:+g} 小时")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
