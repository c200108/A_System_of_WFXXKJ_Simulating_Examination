"""学生姓名的拼音全拼。学生端登录时先选班级，再填拼音全拼。

## 规则

- 全拼、小写、不带声调、字与字之间不加空格：张三 → zhangsan；
- ü 写成 v（键盘上就是这么打的）：吕布 → lvbu；
- 名字里的「·」、空格、字母数字以外的符号都去掉：阿依古丽·买买提 → ayiguliimaimaiti
  这种少数民族名字照样能出拼音；
- **姓氏多音字**按姓氏读：单 shan、曾 zeng、解 xie、仇 qiu、区 ou、朴 piao …
  pypinyin 按常用读音给，「单雄信」会出 danxiongxin。只改第一个字（复姓改前两个），
  名字里的同一个字照常读。

老师在学生列表里能手改拼音 —— 名字里的多音字（「乐」yue / le）程序猜不准，
以老师填的为准。

## 重名

不加任何后缀。登录时先选班级，再在这个班里按拼音找人；同一个班里拼音还重的，
改填学号。

pypinyin 是纯 Python 包（机房版 wheels 里带了一份）。万一没装上，拼音留空、
不挡着建账号 —— 学生仍然可以用学号登录。
"""

import re

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover - 机房没装上依赖时的退路
    lazy_pinyin = None
    Style = None

# 复姓先认，再认单姓。只放读音和常用读音不一样的
COMPOUND_SURNAMES = {
    "尉迟": "yuchi", "万俟": "moqi", "长孙": "zhangsun", "单于": "chanyu",
    "澹台": "tantai", "令狐": "linghu", "皇甫": "huangfu", "宇文": "yuwen",
}
SURNAMES = {
    "单": "shan", "曾": "zeng", "解": "xie", "仇": "qiu", "区": "ou", "朴": "piao",
    "查": "zha", "盖": "ge", "乐": "yue", "尉": "yu", "种": "chong", "覃": "qin",
    "翟": "zhai", "缪": "miao", "秘": "bi", "召": "shao", "句": "gou", "員": "yun",
    "繁": "po", "黑": "he", "那": "na", "隗": "wei", "过": "guo", "华": "hua",
    "纪": "ji", "宁": "ning", "相": "xiang", "臧": "zang", "沈": "shen", "柏": "bai",
    "薄": "bo", "卜": "bu", "折": "she", "冼": "xian", "洗": "xian", "长": "chang",
    "重": "chong", "藏": "zang", "禚": "zhuo", "谌": "chen", "阚": "kan", "郇": "huan",
}

_NOT_LETTER = re.compile(r"[^a-z]")
PINYIN_RE = re.compile(r"^[a-z]{1,64}$")


def _plain(text: str) -> str:
    if not text or lazy_pinyin is None:
        return ""
    got = lazy_pinyin(text, style=Style.NORMAL, errors=lambda s: list(s))
    return _NOT_LETTER.sub("", "".join(got).lower())


def name_pinyin(name: str) -> str:
    """中文姓名 → 拼音全拼（小写、无声调、无空格）。转不出来返回空串。"""
    text = (name or "").strip()
    if not text:
        return ""
    head, rest = "", text
    for two, sound in COMPOUND_SURNAMES.items():
        if text.startswith(two):
            head, rest = sound, text[2:]
            break
    else:
        if text[0] in SURNAMES and len(text) > 1:
            head, rest = SURNAMES[text[0]], text[1:]
    return (head + _plain(rest))[:64]


def norm_pinyin(value: str) -> str:
    """老师手填的拼音：去空格、转小写、ü 当 v。不合规返回空串，由调用方报错。"""
    text = (value or "").strip().lower().replace("ü", "v").replace(" ", "")
    return text if PINYIN_RE.match(text) else ""
