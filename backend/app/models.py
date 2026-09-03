from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="teacher")  # admin / teacher
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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
    stem: Mapped[str] = mapped_column(Text)
    stem_hash: Mapped[str] = mapped_column(String(64), unique=True)  # 查重
    answer: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="自定义")
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)  # 必出题
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

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
    content: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped[Question] = relationship(back_populates="options")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128))
    school: Mapped[str] = mapped_column(String(128), default="")
    duration: Mapped[str] = mapped_column(String(16), default="")  # 考试时长（分钟）
    code: Mapped[str] = mapped_column(String(32), default="")  # 卷号 NO.12345
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

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
    # 打乱选项后这道题在这份卷子里的最终样子（选项顺序 + 跟着变的答案），
    # 存下来重新打开历史试卷才和当初印出去的一模一样
    snapshot_json: Mapped[str] = mapped_column(Text, default="")

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
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    paper: Mapped[Paper] = relationship(lazy="selectin")
    submissions: Mapped[list["ExamSubmission"]] = relationship(
        back_populates="exam", cascade="all, delete-orphan", lazy="selectin"
    )


class ExamSubmission(Base):
    """一份学生答卷。学生的原始作答留着，方便老师看操作题和复查。"""

    __tablename__ = "exam_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"), index=True)
    student_name: Mapped[str] = mapped_column(String(64), default="")
    student_class: Mapped[str] = mapped_column(String(64), default="")
    student_no: Mapped[str] = mapped_column(String(64), default="", index=True)
    answers_json: Mapped[str] = mapped_column(Text, default="{}")  # {题目id: 学生作答}
    detail_json: Mapped[str] = mapped_column(Text, default="[]")  # 每题判分明细
    right_count: Mapped[int] = mapped_column(Integer, default=0)
    objective_count: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)  # 百分制
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    exam: Mapped[Exam] = relationship(back_populates="submissions")


class ImportLog(Base):
    """谁在什么时候导了什么文件、成功几条失败几条，出问题可追溯。"""

    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255))
    total: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    detail_json: Mapped[str] = mapped_column(Text, default="[]")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
