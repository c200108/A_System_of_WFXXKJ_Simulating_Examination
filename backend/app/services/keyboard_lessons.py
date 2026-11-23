"""打字入门（原「认识键盘」，2.25.3）：一课一课地练指法。

每课服务端出一段「按键序列」（会话的原文，计分照旧按服务端存的原文比），再带一份给页面显示用的
units：[{text: 显示的字, keys: 要按的键}, …]。拼音短句那课 text 是汉字、keys 是它的拼音，
页面在汉字上方标拼音、一个键一个键地提示；指法课 text 和 keys 一样。

键只用小写字母、数字、空格和 `;,./` —— 都在键盘图上，学生不用按 Shift。
"""

from __future__ import annotations

import random

# 拼音里没有 ü：lü / nü 要打成 lv / nv，初学者容易卡住，这里一句都不收
SENTENCES = [
    ("我爱学习", "wo ai xue xi"),
    ("天天向上", "tian tian xiang shang"),
    ("好好学习", "hao hao xue xi"),
    ("春天来了", "chun tian lai le"),
    ("我们是好朋友", "wo men shi hao peng you"),
    ("认真听讲", "ren zhen ting jiang"),
    ("电脑真好用", "dian nao zhen hao yong"),
    ("打字要用正确指法", "da zi yao yong zheng que zhi fa"),
    ("眼睛看屏幕", "yan jing kan ping mu"),
    ("手指放在基准键上", "shou zhi fang zai ji zhun jian shang"),
    ("今天天气很好", "jin tian tian qi hen hao"),
    ("学习信息科技", "xue xi xin xi ke ji"),
    ("保护好眼睛", "bao hu hao yan jing"),
    ("坐姿要端正", "zuo zi yao duan zheng"),
    ("先求准再求快", "xian qiu zhun zai qiu kuai"),
    ("熟能生巧", "shu neng sheng qiao"),
    ("一分耕耘一分收获", "yi fen geng yun yi fen shou huo"),
    ("书山有路勤为径", "shu shan you lu qin wei jing"),
    ("少壮不努力", "shao zhuang bu nu li"),
    ("读书破万卷", "du shu po wan juan"),
    ("温故而知新", "wen gu er zhi xin"),
    ("三人行必有我师", "san ren xing bi you wo shi"),
    ("不积跬步无以至千里", "bu ji kui bu wu yi zhi qian li"),
    ("勤学好问", "qin xue hao wen"),
    ("我是中国人", "wo shi zhong guo ren"),
    ("祖国山河多美丽", "zu guo shan he duo mei li"),
    ("网络安全很重要", "wang luo an quan hen zhong yao"),
    ("文明上网", "wen ming shang wang"),
]

LESSONS = [
    {"id": "home", "title": "基准键", "keys": "asdfjkl;",
     "desc": "八个手指放在 A S D F 和 J K L ; 上，只练这一排，手指不离开原位"},
    {"id": "gh", "title": "基准键加G和H", "keys": "asdfghjkl;",
     "desc": "左手食指往右伸一格按 G，右手食指往左伸一格按 H，按完马上回到 F、J"},
    {"id": "top", "title": "上排", "keys": "qwertyuiopasdfjkl;",
     "desc": "手指从基准键往左上方伸一格：A→Q、S→W、D→E、F→R/T，右手同理，按完回到基准键"},
    {"id": "bottom", "title": "下排", "keys": "zxcvbnm,./asdfjkl;",
     "desc": "手指从基准键往右下方伸一格：A→Z、S→X、D→C、F→V/B，右手 J→N/M、K→,、L→.、;→/"},
    {"id": "numbers", "title": "数字排", "keys": "1234567890asdfjkl;",
     "desc": "数字排离基准键最远，眼睛别看键盘，凭手指位置去找；按完回到基准键"},
    {"id": "pinyin", "title": "拼音短句", "keys": "",
     "desc": "照着汉字上方的拼音打，一个音节打完按一下空格（大拇指）"},
]
BY_ID = {x["id"]: x for x in LESSONS}


def listing() -> list[dict]:
    return [{"id": x["id"], "title": x["title"], "desc": x["desc"]} for x in LESSONS]


def _drill(keys: str, rng: random.Random, groups: int = 14) -> list[str]:
    """指法练习：每组 3～5 个键。先挑这一课新加的键（基准键那课就是基准键）各连按三下，再随机组合。"""
    new = [k for k in keys if k not in "asdfjkl;"] or list(keys)
    out = [k * 3 for k in rng.sample(new, min(4, len(new)))]
    while len(out) < groups:
        out.append("".join(rng.choice(keys) for _ in range(rng.randint(3, 5))))
    return out


def build(lesson_id: str, rng: random.Random | None = None) -> tuple[str, list[dict], str]:
    """出一段练习：(按键序列, 显示用 units, 课名)。不认识的课当基准键。"""
    rng = rng or random.Random()
    lesson = BY_ID.get(lesson_id) or BY_ID["home"]
    units: list[dict] = []
    if lesson["id"] == "pinyin":
        for n, (hanzi, py) in enumerate(rng.sample(SENTENCES, 3)):
            for i, (ch, syl) in enumerate(zip(hanzi, py.split())):
                if units:
                    units.append({"text": "", "keys": " "})
                units.append({"text": ch, "keys": syl})
    else:
        for g in _drill(lesson["keys"], rng):
            if units:
                units.append({"text": "", "keys": " "})
            units.append({"text": g, "keys": g})
    target = "".join(u["keys"] for u in units)
    return target, units, lesson["title"]
