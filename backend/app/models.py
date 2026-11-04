from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# 装得下的大 JSON。**MySQL 的 TEXT 只有 65535 字节**（中文一个字 3 字节），
# 装不下就是 1406「Data too long」——在接口上表现为 500。
#
# 谁会超：一道 win 操作题交上来的终态是**整个考试文件夹的快照**，而一场考试里
# win 题有好几道，每道都带一份。实测 93 个对象的考场 + 11 道操作题，
# answers_json 90 KB、detail_json 108 KB（detail 里还要回抄一遍学生的作答）。
#
# **SQLite 的 TEXT 没有长度上限**，所以开发机和测试永远看不见这件事 ——
# 它只在正式服务器的 MySQL 上炸，而且炸在学生交卷那一刻。
BIG_JSON = Text().with_variant(LONGTEXT, "mysql")

# 所有长文本列都用它（0014 起）。SQLite 的 TEXT 没上限，MySQL 的只有 64 KB ——
# 机房版（SQLite）里建的题目、仿真任务、导入记录导进服务器时，超了就整批导不进去。
# 两边容量一致，互相导才不会出错。
LONG_TEXT = BIG_JSON


def now_local() -> datetime:
    """建记录时的时间：**本机本地时间，精确到秒**。

    时间由程序给，不靠数据库的 now()。两个库的 now() 不是一回事：
    MySQL 的 NOW() 是服务器时区（容器里 TZ=Asia/Shanghai），SQLite 的
    CURRENT_TIMESTAMP 却是 **UTC** —— 机房版（SQLite）里建的每一行都比服务器
    早 8 小时，互相一导，同一张表里就混着两种时间；同一份答卷的 submitted_at
    是 UTC、graded_at（程序给的 datetime.now()）又是北京时间。

    去掉微秒：MySQL 的 DATETIME 只存到秒，而且是**四舍五入** ——
    23:59:59.6 会进到第二天。

    server_default 留着，只给绕过程序、直接写 SQL 插行的情况兜底。

    2.10.0 起再加上 config.yaml 的 time.offset_hours（服务器时钟不准时校正），见 app/clock.py。
    """
    from .clock import now
    return now()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="teacher")  # admin / teacher
    # 老师自己维护的资料，只用于校内联系，不参与任何鉴权
    grade_class: Mapped[str] = mapped_column(String(128), default="")  # 任教年级班级
    contact: Mapped[str] = mapped_column(String(64), default="")  # 联系方式
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 删除公共资源（题库、练习文本、更新日志、打字成绩）的权限。
    # 默认关着：这些东西全校共用，误删一条题目所有人都受影响，
    # 要删得先找管理员开权限。管理员天然有这个权限，不看这个字段。
    can_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())

    classes: Mapped[list["SchoolClass"]] = relationship(
        back_populates="owner", lazy="selectin"
    )


class SchoolClass(Base):
    """一个教学班。

    原来班级只是 users.grade_class 和 students.student_class 里的一串文字，
    谁都能手打，"七(3)班"和"七3班"就成了两个班。改成一张表之后：
    - 老师和学生都从下拉里选，选出来的是同一个 id，对得上；
    - 班级能明确归属到某位老师，老师只给自己的班发考试。

    一位老师可以带多个班（owner_id 在班这边），换老师只改这一个字段。
    """

    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("grade", "name", name="uq_class_grade_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grade: Mapped[str] = mapped_column(String(16), index=True)  # 七年级 / 八年级 ...
    name: Mapped[str] = mapped_column(String(32))  # 1班 / 2班 ...
    # 班主任／任课老师。为空表示还没分配，只有管理员管得到
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 上机座次表：图片或 Excel，存在 uploads/seats/ 下。seat_file 是磁盘上的文件名，
    # seat_name 是老师上传时的原名（下载时还叫这个名字）
    seat_file: Mapped[str] = mapped_column(String(255), default="", server_default="")
    seat_name: Mapped[str] = mapped_column(String(128), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())

    owner: Mapped["User | None"] = relationship(back_populates="classes")

    @property
    def display(self) -> str:
        """界面和历史数据里用的班级名，如「七年级1班」。"""
        return f"{self.grade}{self.name}"


class Student(Base):
    """学生账号。

    和教师账号（users）**刻意分成两张表**：两边字段不一样，权限也完全不同。
    合在一张表里靠 role 区分的话，任何一处忘了判角色，学生就能调到教师接口 ——
    分表之后这种错误在类型层面就发生不了。
    令牌里也带了身份类型（见 security.create_access_token），学生的令牌
    过不了教师接口的鉴权。

    登录用学号，不是用户名 —— 学号本来就是学校里的唯一标识，学生记得住。
    """

    __tablename__ = "students"
    __table_args__ = (Index("ix_students_class_no", "student_class", "student_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # 学号，登录用
    name: Mapped[str] = mapped_column(String(64), index=True)
    # class_id 是正主；student_class 是它的显示名，冗余存一份 ——
    # 成绩单、打字记录、导出的 Excel 都直接用这个字符串，
    # 而且班级改名或删班之后，历史数据里的班级名不该跟着变。
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("classes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    student_class: Mapped[str] = mapped_column(String(64), index=True, default="")
    # 男 / 女 / 空。选填 —— 名单里没写就留空，不挡着建账号。
    # 存中文而不是 0/1：导出的 Excel 老师要直接看，存数字还得再对照一遍。
    gender: Mapped[str] = mapped_column(String(8), default="")
    # 班干部：班长 / 组长 / 空。一个班只有一位班长，组长可以有好几位
    class_role: Mapped[str] = mapped_column(String(8), default="")
    password_hash: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())


class DictItem(Base):
    """枚举配置表：知识范围、题型都放这里，加一类不用改代码。"""

    __tablename__ = "dict_items"
    __table_args__ = (UniqueConstraint("category", "name", name="uq_dict_category_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), index=True)  # scope / qtype
    name: Mapped[str] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        Index("ix_questions_type_scope", "type", "scope", "is_deleted"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 展示用编号 C001
    type: Mapped[str] = mapped_column(String(16), index=True)
    stem: Mapped[str] = mapped_column(LONG_TEXT)
    stem_hash: Mapped[str] = mapped_column(String(64), unique=True)  # 查重
    answer: Mapped[str] = mapped_column(LONG_TEXT, default="")
    scope: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="自定义")
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 难度 1~5，只用数字。历史题目由 0010 迁移按题型和题干长度估了一个初值，
    # 老师看着不对随时改（见 services/difficulty.py）。组卷时按它分摊分数。
    difficulty: Mapped[int] = mapped_column(Integer, default=3, index=True)
    # 挂上仿真任务的操作题，学生在网页里做完，服务端按检查点自动判分
    # （见 services/sim.py）。为空就是老规矩：老师在成绩页人工给分。
    sim_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("sim_tasks.id", ondelete="SET NULL"), nullable=True
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)  # 必出题
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now(), onupdate=now_local
    )

    # 选 selectin：题库列表一次几十道题，惰性加载会变成几十条 SQL
    sim_task: Mapped["SimTask | None"] = relationship(lazy="selectin")
    options: Mapped[list["Option"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Option.sort_order",
        lazy="selectin",
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(8))
    content: Mapped[str] = mapped_column(LONG_TEXT)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped[Question] = relationship(back_populates="options")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    school: Mapped[str] = mapped_column(String(128), default="")
    duration: Mapped[str] = mapped_column(String(16), default="")  # 考试时长（分钟）
    code: Mapped[str] = mapped_column(String(32), default="")  # 卷号 NO.12345
    config_json: Mapped[str] = mapped_column(LONG_TEXT, default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())

    items: Mapped[list["PaperItem"]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperItem.order_no",
        lazy="selectin",
    )


class PaperItem(Base):
    __tablename__ = "paper_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    order_no: Mapped[int] = mapped_column(Integer, default=0)
    # 这道题归哪个大题（「选择题」「物联网实践与探索」……）。大题不等于题型，
    # 所以必须单独存 —— 光看题型分不出「物联网」里那三道选择题该排在第六大题。
    section: Mapped[str] = mapped_column(String(64), default="")
    # 这道题在这份卷子里值几分。0 表示这份卷子没设分（2.4.0 之前的老卷子），
    # 判分时会退回按正确率折百分制的老算法。
    score: Mapped[int] = mapped_column(Integer, default=0)
    # 打乱选项后这道题在这份卷子里的最终样子（选项顺序 + 跟着变的答案），
    # 存下来重新打开历史试卷才和当初印出去的一模一样
    snapshot_json: Mapped[str] = mapped_column(LONG_TEXT, default="")

    paper: Mapped[Paper] = relationship(back_populates="items")


class Exam(Base):
    """把一份存档试卷发布成考试：学生凭 token 链接作答，判分在后端做。"""

    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # 学生链接里的口令
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)  # 关掉后学生打不开
    allow_retake: Mapped[bool] = mapped_column(Boolean, default=False)  # 同一学号能否重考
    show_score: Mapped[bool] = mapped_column(Boolean, default=True)  # 交卷后给不给学生看分数
    show_answer: Mapped[bool] = mapped_column(Boolean, default=False)  # 交卷后给不给看对错和答案
    # 允许提前交卷：不受「时间过一半、答完一半的题」的交卷门槛限制
    early_submit: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # 哪些班能在学生平台上看到这场考试，逗号分隔；留空表示所有班都能看。
    # 只影响学生平台的列表，凭链接直接答题的老路子不受它限制。
    target_classes: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())

    paper: Mapped[Paper] = relationship(lazy="selectin")
    submissions: Mapped[list["ExamSubmission"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", lazy="selectin"
    )


class ExamSubmission(Base):
    """一份学生答卷。学生的原始作答留着，方便老师看操作题和复查。"""

    __tablename__ = "exam_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    # 学生平台上交的卷子会记到账号上；凭链接匿名交的仍然是 None，两条路都保留
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True
    )
    student_name: Mapped[str] = mapped_column(String(64), default="")
    student_class: Mapped[str] = mapped_column(String(64), default="")
    student_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    # 这两列用 BIG_JSON：操作题交上来的是整个考试文件夹的快照，TEXT 装不下
    answers_json: Mapped[str] = mapped_column(BIG_JSON, default="{}")  # {题目id: 学生作答}
    detail_json: Mapped[str] = mapped_column(BIG_JSON, default="[]")  # 每题判分明细
    right_count: Mapped[int] = mapped_column(Integer, default=0)
    objective_count: Mapped[int] = mapped_column(Integer, default=0)
    # 总分 = 客观题得分 + 主观题得分。老卷子（没设分）时仍是百分制折算值。
    score: Mapped[int] = mapped_column(Integer, default=0)
    # 交卷时就能算出来的那部分，以及它的满分
    objective_score: Mapped[int] = mapped_column(Integer, default=0)
    objective_total: Mapped[int] = mapped_column(Integer, default=0)
    # 操作题这类要老师看的部分。学生交完卷先看到客观题得分，
    # 老师在成绩页逐题给分之后，总分自动补上。
    subjective_score: Mapped[int] = mapped_column(Integer, default=0)
    subjective_total: Mapped[int] = mapped_column(Integer, default=0)
    manual_json: Mapped[str] = mapped_column(LONG_TEXT, default="{}")  # {题目id: 老师给的分}
    graded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    graded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())

    exam: Mapped[Exam] = relationship(back_populates="submissions")


class TypingRecord(Base):
    """一次打字练习的成绩。

    两条来路：学生平台上练完自动记到账号（student_id 有值），
    或者从公开的 /dazi 页面免登录练完手填班级姓名（student_id 为空）。
    班级姓名两边都存一份，这样导表和统计不用关心是哪条路来的。
    """

    __tablename__ = "typing_records"
    __table_args__ = (Index("ix_typing_cls_name", "student_class", "student_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True
    )
    student_name: Mapped[str] = mapped_column(String(64), index=True)
    student_class: Mapped[str] = mapped_column(String(64), index=True)
    module: Mapped[str] = mapped_column(String(16), index=True)  # 键盘 / 英文 / 中文
    difficulty: Mapped[str] = mapped_column(String(16), default="")
    speed: Mapped[int] = mapped_column(Integer, default=0)  # 字/分，键盘模块为 0
    accuracy: Mapped[int] = mapped_column(Integer, default=0)  # 百分比
    duration: Mapped[int] = mapped_column(Integer, default=0)  # 秒
    typed_chars: Mapped[int] = mapped_column(Integer, default=0)  # 实际敲了多少
    stars: Mapped[int] = mapped_column(Integer, default=0)  # 0~3
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now(), index=True
    )


class ImportLog(Base):
    """谁在什么时候导了什么文件、成功几条失败几条，出问题可追溯。"""

    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))
    total: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    detail_json: Mapped[str] = mapped_column(LONG_TEXT, default="[]")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())


class TypingTheme(Base):
    """打字练习文本的主题（2.15.0）：信息生活、……，老师可以自己加。

    学生取文本时**先随机挑一个启用的主题，再只在这个主题里抽几段拼起来** ——
    一篇文章前后讲的是同一件事，读起来通顺；开了好几个主题时，每次随机换着来。
    内置的「信息生活」删不掉（升级前的老文本全归它）；文本的 theme_id 为空时也当它算。
    """

    __tablename__ = "typing_themes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())


class TypingText(Base):
    """打字练习文本。原来写在 config.yaml 里，挪进数据库后老师能在界面上增删改。

    首次启动时会把 config.yaml 的内置文本灌进来（见 seed.py），
    之后以数据库为准 —— 界面上加的、导入的都不会被启动流程覆盖。
    """

    __tablename__ = "typing_texts"
    __table_args__ = (Index("ix_typing_texts_pick", "mode", "difficulty", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(16), index=True)  # english / chinese
    difficulty: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(LONG_TEXT)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)  # 查重
    source: Mapped[str] = mapped_column(String(32), default="自定义")  # 内置 / 自定义 / 导入
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # 所属主题。为空 = 内置的「信息生活」（删掉某个主题时它下面的文本就置空，回收站还原时再接回去）
    theme_id: Mapped[int | None] = mapped_column(
        ForeignKey("typing_themes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())


class Feedback(Base):
    """需求反馈。学生和老师都能提，公开展示在反馈区。"""

    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author: Mapped[str] = mapped_column(String(64))
    contact: Mapped[str] = mapped_column(String(64), default="")  # 选填，方便回访
    category: Mapped[str] = mapped_column(String(16), default="建议", index=True)
    content: Mapped[str] = mapped_column(LONG_TEXT)
    # 配图：本地上传的路径或外链，JSON 数组存一列。一条最多几张，不值得单开一张表。
    images: Mapped[str] = mapped_column(LONG_TEXT, default="[]")
    # 审核状态：pending 待审核 / approved 已通过 / rejected 已拒绝。
    # **新提交的一律是 pending**，管理员审过才出现在公开区 ——
    # 评论区谁都能发，先发后审的话不当内容会有一段时间挂在首页上。
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(String(255), default="")  # 拒绝原因，只给管理端看
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now(), index=True)

    replies: Mapped[list["FeedbackReply"]] = relationship(
        back_populates="feedback", cascade="all, delete-orphan", lazy="selectin",
        order_by="FeedbackReply.id",
    )
    likes: Mapped[list["FeedbackLike"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class FeedbackReply(Base):
    """一条回复。老师各回各的，不会互相覆盖；作者姓名冗余存一份，
    这样改了名或停用了账号，历史回复的署名仍然对得上。"""

    __tablename__ = "feedback_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("feedbacks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    author: Mapped[str] = mapped_column(String(64), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # 回复时是不是管理员
    content: Mapped[str] = mapped_column(LONG_TEXT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())

    feedback: Mapped[Feedback] = relationship(back_populates="replies")


class FeedbackLike(Base):
    """一个老师给一条反馈点的赞。唯一约束保证点不重，再点一次就是取消。"""

    __tablename__ = "feedback_likes"
    __table_args__ = (UniqueConstraint("feedback_id", "user_id", name="uq_feedback_like"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("feedbacks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())


class ChangelogEntry(Base):
    """更新日志的一条。按 Keep a Changelog 规范：一个版本下按变动类型分组。"""

    __tablename__ = "changelog_entries"
    __table_args__ = (Index("ix_changelog_version", "version", "sort_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), index=True)  # 语义化版本，如 1.3.0
    released_on: Mapped[date] = mapped_column(Date, index=True)
    # Added / Changed / Deprecated / Removed / Fixed / Security
    change_type: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(LONG_TEXT)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())


class SimTask(Base):
    """一道仿真操作题的题面环境和判分规则。

    env_json    初始环境：学生打开时看到的文件夹 / 文档 / 代码
    checks_json 检查点：每小问一条针对**最终状态**的断言和一档分

    checks_json 等同于答案，只在服务端读；发给学生的接口走
    sim.sim_for_student()，那里只带 env。
    """

    __tablename__ = "sim_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)      # win / wps / html
    title: Mapped[str] = mapped_column(String(128), default="")
    env_json: Mapped[str] = mapped_column(LONG_TEXT, default="{}")
    checks_json: Mapped[str] = mapped_column(LONG_TEXT, default="[]")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now(), onupdate=now_local
    )


class RateHit(Base):
    """「这台电脑」做过的一次限频动作（打字交成绩、换文本），见 services/throttle.py。

    后端开了好几个工作进程，计数放内存里各算各的等于没限，所以落库。
    只留最近一小时，**不跟着数据导出导入**。
    """

    __tablename__ = "rate_hits"
    __table_args__ = (Index("ix_rate_hits_lookup", "action", "who", "at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(16))
    who: Mapped[str] = mapped_column(String(80))
    at: Mapped[datetime] = mapped_column(DateTime)


class AppMeta(Base):
    """这台机器自己的几项状态（键值对）。**不跟着数据导出导入**（见 tools/export_data.py）。

    time_offset_applied：已有记录的时间挪到了哪个校正值上（见 app/clock.py）。
    """

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), default="", server_default="")


class RecycleItem(Base):
    """数据回收站：删掉的东西先在这里放 7 天，可以原样还原，过期才真的从库里删掉。

    payload 是删除那一刻拍下的快照（见 services/recycle.py）：被删的行（连同跟着一起
    删的子表行，比如考试下的答卷），以及被置空的引用（比如删班级时学生的 class_id），
    还原时原样插回去、再接上。
    """

    __tablename__ = "recycle_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)       # exam / paper / question ...
    title: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(String(255), default="")
    payload: Mapped[str] = mapped_column(LONG_TEXT, default="{}")
    deleted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_by_name: Mapped[str] = mapped_column(String(64), default="")
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


# ================================================================ 教师端「API」：收第三方教学网页的数据（2.16.0）
class DataApi(Base):
    """老师建的一个数据接收接口。

    老师自己做的答题网页、自评互评表、问卷，把数据 POST 到 /api/hook/{key}，
    平台存下来给老师看表、看图，学生在名单里的还汇总进「学情」。

    **严格按老师隔离**：只有 owner 和管理员看得到。和考试不一样 —— 管理员建的 API
    普通老师也看不到。写入密钥会写进学生网页里（等于半公开），它只能往这一个 API 里写，
    看不到任何数据。
    """

    __tablename__ = "data_apis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), default="")
    # answer / self_eval / peer_eval / survey / custom：只决定默认图表和示例代码，不限制能收什么
    template: Mapped[str] = mapped_column(String(16), default="custom")
    key: Mapped[str] = mapped_column(String(24), unique=True, index=True)      # 接收地址里的公开编号
    write_token: Mapped[str] = mapped_column(String(64))
    read_token: Mapped[str] = mapped_column(String(64), default="", server_default="")
    status: Mapped[str] = mapped_column(String(8), default="active")             # active / paused
    accept_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accept_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    allowed_origins: Mapped[str] = mapped_column(String(1000), default="", server_default="")  # 一行一个
    dedupe: Mapped[str] = mapped_column(String(8), default="all")               # all / latest
    allow_get: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # 学生网页能不能用写入密钥读「全班平均」这类不含个人信息的汇总
    public_summary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    class_ids: Mapped[str] = mapped_column(String(255), default="", server_default="")  # 逗号分隔
    # {字段路径: {"label": 中文名, "kind": number/text/choice, "hidden": bool}}
    field_meta: Mapped[str] = mapped_column(LONG_TEXT, default="{}")
    record_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, server_default=func.now(), onupdate=now_local
    )


class DataRecord(Base):
    """第三方送来的一条数据。原样留在 payload 里，常用的几样拆成列方便筛选统计。"""

    __tablename__ = "data_records"
    __table_args__ = (
        UniqueConstraint("api_id", "client_id", name="uq_data_records_client"),
        Index("ix_data_records_api_time", "api_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_id: Mapped[int] = mapped_column(ForeignKey("data_apis.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # 第三方给的唯一号，防重发
    type: Mapped[str] = mapped_column(String(32), default="", index=True)
    activity_id: Mapped[str] = mapped_column(String(64), default="")
    activity_name: Mapped[str] = mapped_column(String(128), default="")
    page: Mapped[str] = mapped_column(String(255), default="", index=True)      # 来源网页（去掉 ? 和 #）
    student_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    student_name: Mapped[str] = mapped_column(String(64), default="")
    class_name: Mapped[str] = mapped_column(String(64), default="")
    # 按学号（或班级+姓名）对上平台里的学生；对不上就是空，只在 API 里显示
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_no: Mapped[str] = mapped_column(String(64), default="")
    target_name: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT, "mysql"), default="")
    payload: Mapped[str] = mapped_column(BIG_JSON, default="{}")
    source_ip: Mapped[str] = mapped_column(String(64), default="")
    device_id: Mapped[str] = mapped_column(String(80), default="")
    origin: Mapped[str] = mapped_column(String(255), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    flag: Mapped[str] = mapped_column(String(8), default="normal")             # normal / invalid
    # 「只算最新一条」时，同一学生同一活动更早的提交标成被替代：表里照样能看，统计不算
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, server_default=func.now())


class DataRecordItem(Base):
    """一条数据里的逐题作答（answer）和评价维度（rating），拆出来按题、按维度统计。"""

    __tablename__ = "data_record_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("data_records.id", ondelete="CASCADE"), index=True)
    api_id: Mapped[int] = mapped_column(Integer, index=True)       # 冗余一份，按 API 统计时不用连表
    kind: Mapped[str] = mapped_column(String(8))                    # answer / rating
    item: Mapped[str] = mapped_column(String(64), default="")       # 题号或评价维度
    answer: Mapped[str] = mapped_column(String(255), default="")
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
