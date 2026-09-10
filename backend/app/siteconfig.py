"""读取项目根目录的 config.yaml，做严格校验后供全系统使用。

设计上的三条约定：
1. 只放"策略"，不放密钥 —— 密钥在 .env，因为本文件要进 Git；
2. 键名拼错、类型不对一律**启动即报错**并指出是哪一项，
   绝不静默用回默认值（"改了没生效"比直接报错难查十倍）；
3. 文件找不到时用内置默认值启动并打印提示，保证新克隆的仓库也能跑起来。
"""

import os
import sys

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _Base(BaseModel):
    # extra="forbid"：写错键名（比如 defalut_counts）会直接报错，而不是被忽略
    model_config = ConfigDict(extra="forbid")


class SiteMeta(_Base):
    """平台的门面文案。改这里不用动代码，重启后端即可。"""

    title: str = "信息科技教学平台"
    brand: str = "信息科技教学平台"
    footer: str = ""


class SchoolConf(_Base):
    name: str = ""


class PaperConf(_Base):
    default_title: str = "信息技术测试卷"
    default_duration: str = ""
    default_counts: dict[str, int] = Field(
        default_factory=lambda: {"选择题": 20, "判断题": 10, "操作题": 3}
    )
    shuffle_options: bool = True
    require_answer: bool = True
    use_pinned: bool = True
    section_numerals: list[str] = Field(
        default_factory=lambda: ["一", "二", "三", "四", "五", "六"]
    )
    code_prefix: str = "NO."


class ExamDefaults(_Base):
    is_open: bool = True
    show_score: bool = True
    show_answer: bool = False
    allow_retake: bool = False


class ExamConf(_Base):
    pass_score: int = Field(default=60, ge=0, le=100)
    token_length: int = Field(default=9, ge=6, le=32)
    defaults: ExamDefaults = Field(default_factory=ExamDefaults)


class BankConf(_Base):
    sync_on_start: bool = False
    scopes: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=lambda: ["选择题", "判断题", "操作题", "填空题"])
    default_source: str = "自定义"


class ImportConf(_Base):
    headers: list[str] = Field(
        default_factory=lambda: ["题型", "题干", "可选项", "答案", "知识范围", "图片"]
    )
    export_headers: list[str] = Field(
        default_factory=lambda: ["题型", "题干", "可选项", "答案", "知识范围", "来源", "编号"]
    )
    export_widths: list[int] = Field(default_factory=lambda: [8, 60, 34, 26, 16, 10, 9])
    type_keywords: dict[str, list[str]] = Field(default_factory=dict)
    judge_answers: dict[str, list[str]] = Field(default_factory=dict)
    judge_options: list[list[str]] = Field(
        default_factory=lambda: [["A", "正确"], ["B", "错误"]]
    )
    option_separators: str = ".．、,，:："
    max_options: int = Field(default=4, ge=2, le=10)


class TypingStarConf(_Base):
    """星级门槛：正确率达到 base+12 且速度够快给三星，达到 base 给两星。"""

    简单: int = 68
    中等: int = 80
    困难: int = 88


class TypingConf(_Base):
    enabled: bool = True
    difficulties: list[str] = Field(default_factory=lambda: ["简单", "中等", "困难"])
    # 限时档位，单位分钟。都必须大于 0 —— "不限时"的需求由自由打字模块承担，
    # 那个模块本来就不计时不评分，不用在这里配一个 0 出来。
    time_limits: list[int] = Field(default_factory=lambda: [1, 2, 3, 5, 10])
    default_difficulty: str = "简单"
    default_limit: int = 3
    # 每次练习从文本库里随机洗牌拼几段，保证限时练习有足够内容
    passages_per_round: list[int] = Field(default_factory=lambda: [7, 9])
    star_thresholds: TypingStarConf = Field(default_factory=TypingStarConf)
    three_star_min_speed: int = 18  # 简单难度之外，三星还要求速度达到这个值
    # 文本库：{难度: [段落, ...]}，改这里不用重新构建，restart backend 即可
    english: dict[str, list[str]] = Field(default_factory=dict)
    chinese: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_limits(self):
        """限时配错了要在启动时就喊出来，别等学生点开页面才发现选不了时间。"""
        bad = [t for t in self.time_limits if t <= 0]
        if bad:
            raise ValueError(f"typing.time_limits 里不能有 0 或负数（发现 {bad}）；不限时请用自由打字模块")
        if self.time_limits and self.default_limit not in self.time_limits:
            raise ValueError(
                f"typing.default_limit={self.default_limit} 不在 time_limits {self.time_limits} 里"
            )
        if self.default_difficulty not in self.difficulties:
            raise ValueError(
                f"typing.default_difficulty={self.default_difficulty!r} 不在 difficulties {self.difficulties} 里"
            )
        return self


class UploadConf(_Base):
    max_mb: int = Field(default=20, ge=1, le=500)
    image_extensions: list[str] = Field(
        default_factory=lambda: [".png", ".jpg", ".jpeg", ".gif", ".webp"]
    )


class SiteConfig(_Base):
    site: SiteMeta = Field(default_factory=SiteMeta)
    school: SchoolConf = Field(default_factory=SchoolConf)
    paper: PaperConf = Field(default_factory=PaperConf)
    exam: ExamConf = Field(default_factory=ExamConf)
    bank: BankConf = Field(default_factory=BankConf)
    import_: ImportConf = Field(default_factory=ImportConf, alias="import")
    upload: UploadConf = Field(default_factory=UploadConf)
    typing: TypingConf = Field(default_factory=TypingConf)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


def _candidate_paths() -> list[str]:
    """按顺序找配置文件：环境变量 → 项目根（本地开发）→ 应用目录（Docker 挂载）。"""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
    root = os.path.dirname(here)  # 项目根
    paths = []
    if os.environ.get("CONFIG_FILE"):
        paths.append(os.environ["CONFIG_FILE"])
    paths.append(os.path.join(root, "config.yaml"))
    paths.append(os.path.join(here, "config.yaml"))
    return paths


def _fail(msg: str) -> None:
    """配置有问题时直接退出，并把话说清楚。"""
    print("\n" + "=" * 68, file=sys.stderr)
    print("配置文件有问题，系统没有启动：", file=sys.stderr)
    print(msg, file=sys.stderr)
    print("=" * 68 + "\n", file=sys.stderr)
    raise SystemExit(1)


def load(path: str | None = None) -> SiteConfig:
    found = path
    if found is None:
        found = next((p for p in _candidate_paths() if os.path.isfile(p)), None)

    if not found:
        print("[配置] 没找到 config.yaml，先用内置默认值运行。", file=sys.stderr)
        return SiteConfig()

    try:
        with open(found, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        _fail(f"  {found}\n  YAML 格式错误（多半是缩进或中英文标点写混了）：\n  {exc}")
    except OSError as exc:
        _fail(f"  {found}\n  读不了这个文件：{exc}")

    if not isinstance(raw, dict):
        _fail(f"  {found}\n  最外层应该是一组 键: 值，现在是 {type(raw).__name__}。")

    try:
        return SiteConfig.model_validate(raw)
    except ValidationError as exc:
        lines = []
        for err in exc.errors():
            where = " → ".join(str(x) for x in err["loc"]) or "(最外层)"
            lines.append(f"    {where}：{err['msg']}")
        _fail(f"  {found}\n  下面这些项填得不对：\n" + "\n".join(lines))


site = load()
