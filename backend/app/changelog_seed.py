"""更新日志的初始内容 —— 项目从单文件 HTML 到现在的完整轨迹。

规范（Keep a Changelog + 语义化版本）：
- 新版本在前，旧版本在后，每个版本都有发布日期；
- 同版本内按变动类型分组：Added 新增 / Changed 变更 / Deprecated 弃用 /
  Removed 移除 / Fixed 修复 / Security 安全；
- 写给人看，不是给机器看 —— 说清楚"改了什么、对使用者意味着什么"，
  而不是罗列改了哪个函数。

以后每次迭代，把新版本追加到 VERSIONS 最前面即可；已经写进数据库的旧条目
不会被重复插入（见 seed_changelog 的去重）。

注意：去重按（版本号 + 变动类型 + 内容）三者比对，所以**改写**一条已经入库的
旧记录会被当成新记录插进去，库里就留下两条。已经发布出去的条目本来也不该再改
措辞；确实要改，就在「更新日志」页面上把旧的那条删掉。
"""

from datetime import date

# 结构：(版本号, 发布日期, [(变动类型, 内容), ...])
VERSIONS: list[tuple[str, date, list[tuple[str, str]]]] = [
    (
        "1.4.0",
        date(2026, 9, 10),
        [
            ("Added", "平台名称改为「昌邑市实验中学信息科技教学平台」，且可在 config.yaml 里随时修改，重启后端即生效，不用重新构建。"),
            ("Added", "需求反馈模块：师生免登录即可提交建议、问题或表扬，内容公开展示，教师可答复、下架或删除。"),
            ("Added", "更新日志模块：按版本分组展示每次迭代的变动，遵循 Keep a Changelog 规范与语义化版本。"),
            ("Added", "打字练习文本改为在界面上管理，支持逐条增删改，也支持上传 txt 批量导入 —— 可选「一行一段」或「空行分段」，支持 UTF-8 与 GBK，重复内容自动跳过。"),
            ("Added", "页脚显示平台名称与当前版本号，点版本号直接跳到更新日志。"),
            ("Changed", "未登录的访客只看到「反馈」和「更新日志」两个公开入口，右上角显示「教师登录」，不再展示教师菜单。"),
            ("Changed", "打字练习文本从配置文件挪进数据库。config.yaml 里那份退化为首次建库时的初始值，之后以界面上的修改为准。"),
            ("Changed", "内置练习文本从 40 段扩充到 76 段，英文每档 12 段、中文每档 12~14 段，限时练习不容易重复。"),
        ],
    ),
    (
        "1.3.0",
        date(2026, 9, 7),
        [
            ("Added", "打字训练模块：认识键盘、英文打字、中文打字三个练习，学生打开 /dazi 即可使用，无需账号。"),
            ("Added", "打字学情面板：成绩排名、正确率分布、各班平均，支持按班级与模块筛选并导出 Excel。"),
            ("Added", "管理员可以重置教师密码、修改姓名与角色、重新启用被停用的账号。"),
            ("Fixed", "登录后顶栏不显示用户名、管理员看不到「账号」菜单 —— 登录状态读的是 localStorage，没有响应式，只有刷新整页才更新。"),
            ("Security", "打字成绩的速度、正确率、星级改由服务端计算，前端只上报敲击数与用时，并对异常上报做了封顶。"),
        ],
    ),
    (
        "1.2.0",
        date(2026, 9, 4),
        [
            ("Added", "正式考试：把存档试卷发布成考试，学生凭链接作答，判分在服务器完成，成绩自动汇总。"),
            ("Added", "考试四个开关 —— 是否开放、交卷是否看分数、是否看答案、是否允许重考。"),
            ("Added", "成绩导出三张表：成绩汇总、每题正确率分析、操作题原文（供人工评阅）。"),
            ("Security", "发给学生的题目从数据结构上就不含答案字段，判分只在后端进行；同一学号默认只能交卷一次。"),
        ],
    ),
    (
        "1.1.0",
        date(2026, 9, 3),
        [
            ("Added", "组卷补齐原版全部能力：试卷／答案卷／在线自测三种模式、打乱选项、换一批、导出学生答题网页与本卷 Excel。"),
            ("Added", "config.yaml 集中配置：默认题量、及格线、卷头、导入校验规则都可改，不用动代码。"),
            ("Changed", "数据库从 SQLite 迁移到 MySQL，1445 行数据零丢失，「用哪个库」收敛为一行配置。"),
            ("Added", "一键部署脚本与部署指南，含国内镜像加速、端口校验、部署前安全自检。"),
        ],
    ),
    (
        "1.0.0",
        date(2026, 9, 2),
        [
            ("Added", "把原来 2.5 MB 的单文件 HTML 拆成前后端分离架构：Vue 3 + FastAPI + 数据库。"),
            ("Added", "题库进数据库，341 道题去重后入库 331 道，26 张配图落成文件。"),
            ("Added", "教师账号登录、Excel 模板上传解析入库、均衡抽题组卷。"),
            ("Changed", "均衡抽题算法与 Excel 校验规则从原页面原样移植，行为完全一致。"),
        ],
    ),
]


def seed_changelog(db) -> int:
    """把上面的内容灌进数据库。已存在的条目不会重复插入，可反复执行。"""
    from sqlalchemy import select

    from .models import ChangelogEntry

    existing = {
        (v, t, c)
        for v, t, c in db.execute(
            select(
                ChangelogEntry.version,
                ChangelogEntry.change_type,
                ChangelogEntry.content,
            )
        ).all()
    }

    added = 0
    for version, released, items in VERSIONS:
        for i, (change_type, content) in enumerate(items):
            if (version, change_type, content) in existing:
                continue
            db.add(
                ChangelogEntry(
                    version=version,
                    released_on=released,
                    change_type=change_type,
                    content=content,
                    sort_order=i,
                )
            )
            added += 1

    db.commit()
    return added
