from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .siteconfig import site


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- 用户 ----------
class UserOut(ORMModel):
    id: int
    username: str
    name: str
    role: str
    grade_class: str = ""
    contact: str = ""
    is_active: bool
    can_delete: bool = False           # 能否删除题库等公共资源
    class_ids: list[int] = []          # 名下的班，管理员分配
    class_names: list[str] = []
    created_at: datetime | None = None


class UserCreate(BaseModel):
    """长度下限故意不写在这里。

    pydantic 的校验失败会返回 422，detail 是一串英文结构体（"String should have
    at least 3 characters"），界面上只能显示成"请求失败"。用户名和密码的规则改在
    接口里用中文判，返回 400 + 一句人话，老师一眼就知道该怎么改。
    """

    username: str = Field(max_length=64)
    password: str = Field(max_length=64)
    name: str = ""
    role: str = "teacher"


class UserUpdate(BaseModel):
    """管理员改教师资料。字段都可选，只传要改的那几个。

    password 用来重置密码——系统里没存邮箱，老师忘了密码只能管理员帮着重置。
    """

    name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    grade_class: str | None = Field(default=None, max_length=128)
    contact: str | None = Field(default=None, max_length=64)
    can_delete: bool | None = None
    # 传了就整体替换这位老师名下的班级；不传则不动
    class_ids: list[int] | None = None
    password: str | None = Field(default=None, max_length=64)  # 长度在接口里用中文判


class ProfileUpdate(BaseModel):
    """老师改自己的资料。只有这三项 —— 用户名、角色、启停都得管理员来。"""

    name: str | None = Field(default=None, max_length=64)
    grade_class: str | None = Field(default=None, max_length=128)
    contact: str | None = Field(default=None, max_length=64)


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(max_length=64)  # 长度在接口里用中文判


class UserBulkIn(BaseModel):
    """管理员批量处理勾选的账号。delete 是真删，不可恢复。"""

    ids: list[int] = Field(default_factory=list)
    action: Literal["delete", "disable", "enable"]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- 班级 ----------
class ClassOut(ORMModel):
    id: int
    grade: str
    name: str
    display: str = ""          # 「七年级1班」，界面和历史数据里用这个
    owner_id: int | None = None
    owner_name: str = ""
    is_active: bool = True
    student_count: int = 0


class ClassIn(BaseModel):
    grade: str = Field(max_length=16)
    name: str = Field(max_length=32)
    owner_id: int | None = None
    sort_order: int = 0


class ClassUpdate(BaseModel):
    grade: str | None = Field(default=None, max_length=16)
    name: str | None = Field(default=None, max_length=32)
    owner_id: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ClassBatchIn(BaseModel):
    """按年级批量建班：七年级 1~12 班一次建完。"""

    grade: str = Field(max_length=16)
    start: int = Field(default=1, ge=1, le=99)
    end: int = Field(default=12, ge=1, le=99)
    suffix: str = Field(default="班", max_length=8)


# ---------- 学生账号 ----------
class StudentOut(ORMModel):
    id: int
    student_no: str
    name: str
    class_id: int | None = None
    student_class: str = ""
    is_active: bool
    created_at: datetime | None = None


class StudentCreate(BaseModel):
    """学号和密码的规则在接口里用中文判，这里只卡住结构上的长度上限。"""

    student_no: str = Field(max_length=32)
    name: str = Field(max_length=64)
    class_id: int | None = None  # 从下拉里选，不再手打班级名
    password: str = Field(default="", max_length=64)  # 留空则用学号当初始密码


class StudentUpdate(BaseModel):
    """老师改学生资料。学号不在里面 —— 学号是身份，要换只能删了重建。"""

    name: str | None = Field(default=None, max_length=64)
    class_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=64)


class StudentBulkIn(BaseModel):
    ids: list[int] = Field(default_factory=list)
    action: Literal["delete", "disable", "enable", "reset_password"]


class StudentBatchIn(BaseModel):
    """按班级粘一批学生进来，一行一个「学号 姓名」。"""

    class_id: int | None = None
    text: str = Field(max_length=100_000)


class StudentTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    student: StudentOut


class StudentPasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(max_length=64)


class StudentExamOut(BaseModel):
    """学生平台考试列表里的一场考试。没有 token 以外的任何答案线索。"""

    id: int
    title: str
    token: str
    total: int = 0
    submitted: bool = False
    score: int | None = None          # 没交或老师关了看分数就是 None
    show_score: bool = True
    allow_retake: bool = False
    submitted_at: datetime | None = None
    created_at: datetime | None = None


class StudentHomeOut(BaseModel):
    """学生首页要的一小把数字，省得前端串好几个接口。"""

    student: StudentOut
    exam_total: int = 0
    exam_done: int = 0
    typing_count: int = 0
    typing_best_speed: int = 0
    typing_avg_accuracy: int = 0


# ---------- 题目 ----------
class OptionIn(BaseModel):
    label: str
    content: str


class OptionOut(ORMModel):
    label: str
    content: str


class QuestionBase(BaseModel):
    type: str
    stem: str
    answer: str = ""
    scope: str
    source: str = "自定义"
    image_url: str | None = None
    is_pinned: bool = False


class QuestionCreate(QuestionBase):
    options: list[OptionIn] = []


class QuestionUpdate(BaseModel):
    type: str | None = None
    stem: str | None = None
    answer: str | None = None
    scope: str | None = None
    source: str | None = None
    image_url: str | None = None
    is_pinned: bool | None = None
    options: list[OptionIn] | None = None


class QuestionOut(ORMModel):
    id: int
    code: str | None = None
    type: str
    stem: str
    answer: str
    scope: str
    source: str
    image_url: str | None = None
    is_pinned: bool
    options: list[OptionOut] = []
    created_at: datetime | None = None


class QuestionPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[QuestionOut]


# ---------- 组卷 ----------
class PaperGenerateIn(BaseModel):
    title: str = Field(default_factory=lambda: site.paper.default_title)
    school: str = Field(default_factory=lambda: site.school.name)
    duration: str = Field(default_factory=lambda: site.paper.default_duration)
    counts: dict[str, int] = Field(default_factory=lambda: dict(site.paper.default_counts))
    scopes: list[str] | None = None       # 为空表示全部知识范围
    use_pinned: bool = Field(default_factory=lambda: site.paper.use_pinned)
    require_answer: bool = Field(default_factory=lambda: site.paper.require_answer)
    shuffle_options: bool = Field(default_factory=lambda: site.paper.shuffle_options)
    seed: str | None = None               # 填了就可复现同一套卷子
    save: bool = False


class PaperItemOut(BaseModel):
    """卷子里的一道题：选项和答案是打乱之后的最终样子。"""

    id: int
    code: str | None = None
    type: str
    stem: str
    answer: str = ""
    scope: str
    source: str = ""
    image_url: str | None = None
    options: list[OptionOut] = []


class PaperGroupOut(BaseModel):
    type: str                             # 一道大题（选择题/判断题/操作题）
    items: list[PaperItemOut]


class PaperGenerateOut(BaseModel):
    paper_id: int | None = None
    title: str
    school: str = ""
    duration: str = ""
    code: str = ""                        # 卷号 NO.12345
    seed: str = ""
    total: int
    tally: dict[str, int]                 # 各知识范围实际抽了几题
    warnings: list[str] = []
    groups: list[PaperGroupOut] = []      # 按大题分组，前端照着排版
    questions: list[PaperItemOut] = []    # 同样的题，拉平的顺序


class PaperOut(ORMModel):
    id: int
    title: str
    code: str = ""
    school: str = ""
    created_at: datetime | None = None
    question_count: int = 0


# ---------- 考试 ----------
class ExamCreate(BaseModel):
    paper_id: int
    title: str | None = None              # 不填就用试卷标题
    # 发给哪些班。老师只能填自己名下的班；留空时：
    # 管理员 = 全体学生，老师 = 自己名下的全部班。
    target_class_ids: list[int] = Field(default_factory=list)
    is_open: bool = Field(default_factory=lambda: site.exam.defaults.is_open)
    allow_retake: bool = Field(default_factory=lambda: site.exam.defaults.allow_retake)
    show_score: bool = Field(default_factory=lambda: site.exam.defaults.show_score)
    show_answer: bool = Field(default_factory=lambda: site.exam.defaults.show_answer)


class ExamUpdate(BaseModel):
    title: str | None = None
    target_class_ids: list[int] | None = None
    is_open: bool | None = None
    allow_retake: bool | None = None
    show_score: bool | None = None
    show_answer: bool | None = None


class ExamOut(ORMModel):
    id: int
    paper_id: int
    title: str
    token: str
    is_open: bool
    allow_retake: bool
    show_score: bool
    show_answer: bool
    target_classes: str = ""       # 班级名，逗号分隔；空串表示全体学生
    target_class_ids: list[int] = []
    created_at: datetime | None = None
    submission_count: int = 0
    avg_score: float | None = None
    # 只有管理员看列表时才填，老师看到的都是自己的，不需要这一列
    owner_name: str = ""


class TakeQuestionOut(BaseModel):
    """发给学生的题目——没有 answer 字段，这是刻意的。"""

    id: int
    code: str | None = None
    type: str
    stem: str
    scope: str
    image_url: str | None = None
    options: list[OptionOut] = []


class TakeGroupOut(BaseModel):
    type: str
    items: list[TakeQuestionOut]


class TakePaperOut(BaseModel):
    """学生打开链接看到的东西。"""

    title: str
    school: str = ""
    duration: str = ""
    code: str = ""
    total: int
    groups: list[TakeGroupOut]


class SubmitIn(BaseModel):
    student_name: str = Field(default="", max_length=64)
    student_class: str = Field(default="", max_length=64)
    student_no: str = Field(default="", max_length=64)
    answers: dict[str, str] = {}


class SubmitOut(BaseModel):
    submitted: bool = True
    message: str = ""
    score: int | None = None              # show_score 关掉时为 None
    right_count: int | None = None
    objective_count: int | None = None
    detail: list[dict] = []               # show_answer 关掉时为空


class SubmissionOut(ORMModel):
    id: int
    student_name: str
    student_class: str
    student_no: str
    right_count: int
    objective_count: int
    score: int
    submitted_at: datetime | None = None


# ---------- 导入 ----------
class ImportRowError(BaseModel):
    sheet: str
    row: int
    reason: str


class ImportResult(BaseModel):
    filename: str
    total: int
    success: int
    failed: int
    skipped: int
    by_type: dict[str, int]
    errors: list[ImportRowError]


class ImportLogOut(ORMModel):
    id: int
    filename: str
    total: int
    success: int
    failed: int
    skipped: int
    created_at: datetime | None = None
    operator: str = ""


# ---------- 字典 ----------
class DictItemOut(ORMModel):
    id: int
    category: str
    name: str
    sort_order: int
    is_active: bool


class DictItemIn(BaseModel):
    category: str
    name: str
    sort_order: int = 0


class StatsOut(BaseModel):
    total: int
    by_type: dict[str, int]
    by_scope: dict[str, int]
    with_image: int
    pinned: int = 0
    sources: list[str] = []               # 题库里出现过的「来源」，供筛选下拉用


# ---------- 打字训练 ----------
class TypingConfigOut(BaseModel):
    """学生页开局要的配置。不含文本，文本按需从 /passage 取。"""

    school: str = ""
    difficulties: list[str] = []
    time_limits: list[int] = []
    default_difficulty: str = "简单"
    default_limit: int = 0


class TypingRecordIn(BaseModel):
    """学生上报的原始量。速度/正确率/星级都由后端算，前端不参与。"""

    student_name: str = Field(max_length=64)
    student_class: str = Field(max_length=64)
    module: str                      # 键盘 / 英文 / 中文
    difficulty: str = ""
    typed_chars: int = Field(ge=0)   # 实际敲了多少（键盘模块是按键次数）
    correct_chars: int = Field(ge=0) # 其中对了多少
    duration: float = Field(ge=0)    # 秒


class TypingResultOut(BaseModel):
    module: str
    difficulty: str = ""
    speed: int
    accuracy: int
    duration: int
    stars: int


class TypingRecordOut(ORMModel):
    id: int
    student_name: str
    student_class: str
    module: str
    difficulty: str
    speed: int
    accuracy: int
    duration: int
    typed_chars: int
    stars: int
    created_at: datetime | None = None


class TypingStatsOut(BaseModel):
    total: int = 0
    students: int = 0
    avg_accuracy: int = 0
    avg_speed: int = 0
    avg_duration: int = 0
    by_module: dict[str, int] = {}
    accuracy_buckets: dict[str, int] = {}
    by_class: list[dict] = []


class TypingTextIn(BaseModel):
    mode: str = Field(pattern="^(english|chinese)$")
    difficulty: str
    content: str


class TypingTextUpdate(BaseModel):
    difficulty: str | None = None
    content: str | None = None
    is_active: bool | None = None


class TypingTextOut(ORMModel):
    id: int
    mode: str
    difficulty: str
    content: str
    source: str
    is_active: bool
    created_at: datetime | None = None


class TypingTextBulkIn(BaseModel):
    """批量处理勾选的文本。action 限死这三个，别的一律拒绝。"""

    ids: list[int] = Field(default_factory=list)
    action: Literal["delete", "enable", "disable"]


# ---------- 需求反馈 ----------
class FeedbackIn(BaseModel):
    author: str = Field(max_length=64)
    contact: str = Field(default="", max_length=64)
    category: str = "建议"
    content: str = Field(max_length=2000)


class FeedbackReplyOut(ORMModel):
    """一条回复。is_admin 用来在界面上给管理员的回复加个标记。"""

    id: int
    author: str
    is_admin: bool = False
    content: str
    created_at: datetime | None = None


class FeedbackOut(ORMModel):
    """公开展示用。**故意不含 contact** —— 联系方式只给管理端看。"""

    id: int
    author: str
    category: str
    content: str
    replies: list[FeedbackReplyOut] = []
    like_count: int = 0
    liked_by_me: bool = False
    created_at: datetime | None = None


class FeedbackReplyIn(BaseModel):
    reply: str = Field(default="", max_length=2000)


# ---------- 更新日志 ----------
class ChangelogEntryIn(BaseModel):
    version: str = Field(max_length=32)
    released_on: date | None = None
    change_type: str                 # Added / Changed / Deprecated / Removed / Fixed / Security
    content: str = Field(max_length=1000)
    sort_order: int = 0


class ChangelogEntryOut(ORMModel):
    id: int
    version: str
    released_on: date
    change_type: str
    content: str
    sort_order: int


class ChangelogVersionOut(BaseModel):
    """一个版本一组，组内再按变动类型分。"""

    version: str
    released_on: date
    groups: list[dict] = []
