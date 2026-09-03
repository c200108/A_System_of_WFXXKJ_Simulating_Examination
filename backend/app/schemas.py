from datetime import datetime

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
    is_active: bool
    created_at: datetime | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=64)
    name: str = ""
    role: str = "teacher"


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=64)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


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
    is_open: bool = Field(default_factory=lambda: site.exam.defaults.is_open)
    allow_retake: bool = Field(default_factory=lambda: site.exam.defaults.allow_retake)
    show_score: bool = Field(default_factory=lambda: site.exam.defaults.show_score)
    show_answer: bool = Field(default_factory=lambda: site.exam.defaults.show_answer)


class ExamUpdate(BaseModel):
    title: str | None = None
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
    created_at: datetime | None = None
    submission_count: int = 0
    avg_score: float | None = None


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
