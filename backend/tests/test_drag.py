"""拖拽类操作题：流程图、结构图热区、设备归类、本机 IP、程序填空 / 排序。

守三件事：

1. **同一段题干永远认成同一道题**。老师 data-import 导回旧数据，题目行被覆盖，
   题干不变 —— 下面这 24 段就是题库里的原文，认题、画图、判分都得照旧。
2. **发给学生的东西里没有答案**。结构图、热区、素材卡片发出去；哪个热区放哪张
   卡片（检查点）留在服务端。
3. **照着答案做能拿满分，乱放拿不到**。每一道都这么走一遍。
"""

from __future__ import annotations

import json

import pytest

from app.services import drag, sim, stem

REAL_STEMS = {
    'Q306-校园网': '学校大力实施教育信息化2.0工程，用数字技术赋能教育教学，促进信息技术与教学的融合，实现教育资源的数字化、 网络化、智能化。以下是学校网络结构图，其中核心交换机部署在学校科技楼，其它设备部署在教学楼，两栋楼直线距高大约300米，请仔细读图，并补充完善。\n【操作要求】\n从素材区选择合适的设备，拖动到答题区中相应的热区位置，将结构图补充完整。',
    'Q307-终端IP': '使用仿真界面查询教学楼中终端电脑的IP地址并填空。',
    'Q309-社团': '为了丰富学生学习生活，学校给各个社团分配了专用教室和设备。编程社团配备台式电脑，学习Python编程语言；美术社团配备平板，开展数字绘画；舞蹈社团配备触控一体机，开展线上学习。请根据社团的需求，合理配置相应设备。【操作要求】从素材区选择合适的设备拖动到答题区中相应热区位置，形成一个完整的系统。',
    'Q310-本机IP': '请点击"开始操作"进入Windows仿真系统，查询本机IP地址。',
    'Q312-点餐': '信息系统是一个由人、硬件、软件、网络和数据资源的人机交互系统。日常生活中由于工作繁忙。人们经常会利用APP点餐节省做饭、购餐的时间，结合信息系统的相关知识，完善点餐信息系统。\n【操作要求】\n(1)认真分析结构图，确认图中所缺内容。\n(2)从提供的对象集群中拖放合适对象到图中相应热区位置，将结构图补充完整。',
    'Q317-家庭网': '小明家配备了不同类型的信息技术设备，这些设备连接形成家庭局域网并通过光纤接入互联网，请补充完善网络连接结构图。【操作要求】从系统提供的对象群中拖放合适对象到相应热区位置。',
    'Q340-智慧食堂': '根据所给的HTML基础代码，进行简单的网页编辑操作，完成"智慧食堂"宣传页面的制作。\n①修改网页标题为"智慧食堂"；\n②将网页背景色修改为深红色"#980015"；网页中的图片修改为"智慧食堂.jpg"。',
    'Q322-话费': '以下流程图实现的功能是根据通话时长(time)计算话费:满200分钟，为0.2元/分钟；满100分钟，为0.3元/分钟，否则0.5元/分钟。请根据程序功能，将流程图补充完整。(将正确答案拖拽到序号A、B对应位置)',
    'Q323-饮水': '中国营养学会建议青少年每日饮水量应达到1500ml。以下流程图实现的功能是:当每日饮水量(water)达到或超过1500ml，输出"达标，继续保持!"；否则，输出"建议增加饮水量"。请根据以上要求，将流程图补充完整。(将上方正确答案拖拽到A、B对应位置)',
    'Q324-加减': '（题干见图）',
    'Q325-成绩': '输入学生成绩score（0~100分），大于或等于60分，输出"恭喜!成绩达标!"；否则，输出"成绩未达标!"。请根据程序功能，将流程图补充完整。(将正确答案拖拽到A、B对应位置)',
    'Q326-水费': '以下流程图实现的功能是根据用水量(water)计算水费：满20吨，为3元/吨；满10吨，为2元/吨，否则1.5元/吨。请根据程序功能，将流程图补充完整。(将正确答案拖拽到序号A、B对应位置)',
    'Q327-折扣': '以下流程图实现的功能是根据购物金额(money)计算折扣：满500元打8折，满300元打9折，否则无折扣。请根据程序功能，将流程图补充完整。(将正确答案拖拽到A、B对应位置)',
    'Q334-智能家居': '请将符合智能家居的设备拖拽到指定区域。',
    'Q335-李华家': '李华家定制了“智慧舒适家居系统”，可通过手机 APP 远程操控智能窗帘、智能门锁、智能空调、智能音箱等设备，形成联动网络。请结合“智慧舒适家居系统示例图”，回答下列问题。\n1. 请将符合智能家居的设备拖拽到指定区域。\n（按钮：开始操作、重做本题）',
    'Q336-智能大棚': '请将符合智能大棚的设备拖拽到指定区域。',
    'Q337-小鹏家': '随着人们生活水平的逐步提高，小鹏家里的智能设备越来越多。小鹏设计了一个简单的家庭智能系统，家庭成员可以通过手机APP远程访问控制家中的智能设备，如智能摄像头、智能空调、智能热水器等，请仔细阅读，补充完善。\n【操作要求】\n从系统提供的素材区中拖放合适对象到答题区中相应热区位置，将结构图补充完整。',
    'Q338-智能家居归类': '请将符合智能家居的设备拖拽到指定区域。（素材设备：交换机、智能空调、监控云平台、无线路由器、普通非智能空调、智能热水器、智能摄像头、PC电脑、光猫、笔记本电脑、空调云平台、热水器云平台、互联网）',
    'Q339-红绿灯': '智慧交通系统通过高新技术汇集交通信息，使交通系统在区域、城市乃至更广的时空范围具备感知、互联、分析、预测、控制能力，并能整合实时交通数据，实现交通管理、运输调度及公众出行的智能管控。请结合“智慧交通系统示例图”,回答下列问题。\n智慧交通系统需实现"红绿灯自动调节"功能，请通过拖拽操作，将合适的流程拖拽到指定区域。',
    'Q340-智慧食堂': '学校为方便师生快捷就餐，引进了“智慧食堂”管理系统，师生使用带有电子标签的餐盘，通过智能结算台，可精准识别不同餐盘，进行快速结算、“刷脸”支付。家长可以随时随地查看孩子在校的消费信息。后台管理员可查看食材、财务数据等信息。请你仔细读图，将结构图补充完整。\n【操作要求】\n从素材区选择合适的设备，拖动到答题区中相应的热区位置，形成一个完整的“智慧食堂”管理系统。',
    'Q341-智慧农业': '通过手机上的智慧农业监控平台，农民可以实时查看大棚内的温度、湿度、光照强度等环境数据。系统能自动控制灌溉、通风、遮阳等设备，确保作物生长在最佳环境中。如检测到异常干旱或高温，系统会立即发出警报并建议相应操作。请结合“智慧农业系统示例图”,回答下列问题。\n请将符合智慧农业系统的设备拖拽到指定区域。',
    'C0577-体温填空': '人体正常体温平均在36﹣37℃之间（腋窝），高于37℃就是发烧。低烧：37℃≤体温＜38℃，中度发烧：38℃≤体温＜39℃，高烧：39℃≤体温＜41℃，超高烧：体温≥41℃，请根据输入的体温判断体温是否正常。删除横线，补全代码，不要修改其他代码。',
    'C0578-勾股数': '程序设计\n所谓勾股数，一般是指能够构成直角三角形三条边的三个正整数（例如a，b，c）。即a2+b2＝c2，计算出100以内满足a＜b的所有勾股数。',
    'C0579-行李收费': '乘坐飞机时，当乘客行李小于等于20公斤时，按每公斤1.68元收费，大于20公斤时，按每公斤1.98元收费，编程计算收费。',
    'C0580-入校体温': 'Python操作题\n请打开本题工作目录（C：\\EXAM\\Python）中的“exam01.py”文件，完成程序设计操作。\n该程序的功能是：根据开学入校体温要求，小明做了一个小程序，用来检测输入的体温是否正常（正常范围35℃﹣37.2℃）并输出结果。\n将①、②等序号替换成正确代码，调试、完善程序，以实现其功能。\n不要添加或删减程序行，也不要删除注释。\n完成以上操作后，保存、运行并退出Python。',
}


def perfect(checks: list) -> dict:
    """照着检查点把题做对：这就是标准答案。"""
    placed, state = {}, {}
    for c in checks:
        a = c["assert"]
        if a["op"] == "slot":
            placed[a["slot"]] = [a["is"][0]]
        elif a["op"] == "in":
            free = [s for s in a["slots"] if not placed.get(s)]
            placed.setdefault(free[0] if free else a["slots"][0], []).append(a["item"])
        elif a["op"] == "ip":
            state["ip"] = a["sim_ip"]
    state["placed"] = placed
    return state


def score(key: str, state: dict) -> tuple:
    entry = next(e for e in drag.BANK if e["key"] == key)
    ran = sim.run_checks("drag", entry["checks"], state)
    return ran["score"], ran["full"]


# ================================================================ 1 认题
def test_题库里这24道拖拽题一道不漏():
    assert len(REAL_STEMS) == 24
    assert {e["key"] for e in drag.BANK} == set(REAL_STEMS)


@pytest.mark.parametrize("key", sorted(REAL_STEMS))
def test_同一段题干认成同一道题(key):
    got = stem.auto_sim(REAL_STEMS[key], "")
    assert got and got["kind"] == "drag" and got["key"] == key


def test_只有一句话的题干不会把别的题认走():
    """Q334 的题干只有「请将符合智能家居的设备拖拽到指定区域。」，而 Q335、Q338
    的题干里也有这一句 —— 三道题各认各的。"""
    keys = {stem.auto_sim(REAL_STEMS[k], "")["key"]
            for k in ("Q334-智能家居", "Q335-李华家", "Q338-智能家居归类")}
    assert keys == {"Q334-智能家居", "Q335-李华家", "Q338-智能家居归类"}


def test_标点空格换行不影响认题():
    """线上库和本地库的同一道题，常见的差别就是全角半角、多个空格、换行。"""
    raw = REAL_STEMS["Q322-话费"]
    variant = raw.replace("，", ",").replace("：", ":").replace("(", "（") + "\n  "
    assert drag.find(variant)["key"] == "Q322-话费"


def test_普通操作题不会被拖拽清单认走():
    for text in ("请打开本题工作目录下的win04文件夹，删除“塔里木盆地”文件夹。",
                 "请用 WPS 打开“孔子.docx”，把标题设置为“标题”样式。"):
        got = stem.auto_sim(text, "")
        assert not got or got["kind"] != "drag", text


# ================================================================ 2 不漏答案
@pytest.mark.parametrize("entry", drag.BANK, ids=lambda e: e["key"])
def test_发给学生的图里没有答案(entry):
    text = json.dumps(entry["env"], ensure_ascii=False)
    for bad in ('"op"', '"assert"', '"checks"', '"is"', '"answer"'):
        assert bad not in text, f"{entry['key']} 的 env 里出现了 {bad}"


@pytest.mark.parametrize("entry", drag.BANK, ids=lambda e: e["key"])
def test_检查点指向的热区和卡片图上都有(entry):
    env = entry["env"]
    slots = {s["id"] for s in env.get("slots") or []}
    items = {i["id"] for i in env.get("items") or []}
    for c in entry["checks"]:
        a = c["assert"]
        for s in ([a["slot"]] if "slot" in a else a.get("slots") or []):
            assert s in slots, f"{entry['key']}：检查点指向不存在的热区 {s}"
        for i in (a.get("is") or []) + ([a["item"]] if "item" in a else []) + (a.get("items") or []):
            assert i in items, f"{entry['key']}：检查点指向不存在的卡片 {i}"
    if env["mode"] == "code":
        inline = {seg["slot"] for row in env["rows"] for seg in row if isinstance(seg, dict)}
        assert inline == slots, f"{entry['key']}：程序里的空位和热区对不上"


# ================================================================ 3 判分
@pytest.mark.parametrize("entry", drag.BANK, ids=lambda e: e["key"])
def test_照答案做满分_什么都不放零分(entry):
    got, full = score(entry["key"], perfect(entry["checks"]))
    assert got == full > 0, f"{entry['key']} 照答案做只得 {got}/{full}"
    empty, _ = score(entry["key"], {"placed": {}})
    # 只有「干扰卡片没放进去」那一条，什么都不放也算对 —— 其余全不得分
    freebies = sum(c["score"] for c in entry["checks"] if c["assert"]["op"] == "none_of")
    assert empty == freebies


def test_流程图放反了拿不到分():
    got, full = score("Q322-话费", {"placed": {"A": ["i3"], "B": ["i1"]}})
    assert got == 0 < full


def test_顺序不限的热区换个位置照样对():
    """智能家居那种「两个热区放两个智能设备」，谁放左边谁放右边都行。"""
    got, full = score("Q334-智能家居", {"placed": {"H1": ["i4"], "H2": ["i2"]}})
    assert got == full


def test_把干扰设备也拖进来要扣分():
    right = perfect(next(e for e in drag.BANK if e["key"] == "Q338-智能家居归类")["checks"])
    right["placed"]["Z"] += ["i1", "i9"]            # 交换机、光猫
    got, full = score("Q338-智能家居归类", right)
    assert 0 < got < full


def test_库里答案和原图矛盾的两道以原图为准():
    """Q323 库里写 A=Water<1500，可图上 A 的「是」通向「达标」；Q326 库里写
    water>20，题干和卡片都是 water>=20。"""
    assert score("Q323-饮水", {"placed": {"A": ["i2"], "B": ["i4"]}})[0] == 10
    assert score("Q323-饮水", {"placed": {"A": ["i1"], "B": ["i4"]}})[0] == 5


def test_IP题_桌面端认真机地址_网页端认仿真地址():
    real = {"ip": "10.9.22.125", "real_ips": ["10.9.22.125", "192.168.228.1"]}
    assert score("Q310-本机IP", real) == (10, 10)
    assert score("Q310-本机IP", {"ip": "192.168.1.108"}) == (10, 10)      # 网页仿真
    assert score("Q310-本机IP", {"ip": "8.8.8.8", "real_ips": ["10.9.22.125"]})[0] == 0
    assert score("Q310-本机IP", {"ip": ""})[0] == 0


def test_IP题_机房里照抄网页仿真地址不算对():
    """网页端仿真命令行里的地址是固定的（Q310 是 192.168.1.108），练过网页版的
    学生都见过。exe 交上来的带着本机真实地址，这时只认真地址。"""
    copied = {"ip": "192.168.1.108", "real_ips": ["10.9.22.125"]}
    got, _ = score("Q310-本机IP", copied)
    assert got == 0, "照抄网页仿真地址"

    # 真机恰好就是这个地址：那就是查对了
    assert score("Q310-本机IP", {"ip": "192.168.1.108", "real_ips": ["192.168.1.108"]})[0] == 10

    # exe 交卷时没查到本机地址（极少见）：判不了，说清楚请老师核对，不冒充"填错了"
    entry = next(e for e in drag.BANK if e["key"] == "Q310-本机IP")
    ran = drag.check(entry["checks"][0]["assert"], {"ip": "10.9.22.125", "real_ips": []})
    assert ran[0] is False and "老师核对" in ran[1]


# ================================================================ 4 出卷
def test_补全的题干替换原题干_旧截图不再显示(client, auth):
    """Q324 的原题干只有「（题干见图）」—— 学生拿到的得是补全后的那段话；
    原图是旧考试系统的截图，结构图已经重画，不再发。原题干留在库里不动。"""
    q = client.post("/api/questions", headers=auth, json={
        "type": "操作题", "stem": REAL_STEMS["Q324-加减"], "answer": "A：a>=b；B：t=a-b",
        "scope": "Python编程基础", "image_url": "/uploads/images/旧截图.jpg",
        "options": []}).json()
    from app.database import SessionLocal
    from app.models import Paper, PaperItem, Question
    from app.services.exam import load_items

    db = SessionLocal()
    try:
        paper = Paper(title="拖拽题出卷", school="昌邑市实验中学", duration="40")
        paper.items.append(PaperItem(question_id=q["id"], order_no=0, section="操作题",
                                     score=10))
        db.add(paper)
        db.commit()
        it = load_items(db, paper)[0]
        assert db.get(Question, q["id"]).stem == REAL_STEMS["Q324-加减"], "库里的原题干不能动"
    finally:
        db.close()

    assert it["stem"].startswith("输入两个正整数 a、b")
    assert it["image_url"] is None
    assert it["sim"]["kind"] == "drag" and it["sim"]["env"]["mode"] == "diagram"
    assert it["sim_checks"], "检查点要有（留在服务端）"


@pytest.mark.parametrize("entry", drag.BANK, ids=lambda e: e["key"])
def test_桌面端要显示的字在Win7上都有字形(entry):
    """exe 在 Win7 上跑：GBK 装不下的字符（比如 ² 上标），中文 Windows 的字体里
    很可能没有字形，考场上显示成方框。能编进 GBK 的就一定显示得出来。"""
    text = json.dumps({"stem": entry["stem"], "env": entry["env"]}, ensure_ascii=False)
    bad = sorted({ch for ch in text if ord(ch) > 127 and not _gbk(ch)})
    assert not bad, f"{entry['key']} 里有 Win7 上显示不了的字符：{bad}"


def test_题干是纯文本_没有markdown记号():
    for e in drag.BANK:
        assert "**" not in e["stem"], f"{e['key']} 的题干里有 **，学生会看到两个星号"


def _gbk(ch: str) -> bool:
    try:
        ch.encode("gbk")
        return True
    except UnicodeEncodeError:
        return False


# ================================================================ 不能抢别的题
# 规则认得出的题，清单一概不碰。联调时真出过：清单里「智慧食堂」结构图那一项
# 只拿「智慧食堂」四个字认题，结果把一道做「智慧食堂」宣传网页的 HTML 题认走了，
# 题干整段换成了管理系统结构图的那一段话。
NOT_DRAG = {
    "html": '根据所给的HTML基础代码，进行简单的网页编辑操作，完成"智慧食堂"宣传页面的制作。\n'
            '①修改网页标题为"智慧食堂"；\n②将网页背景色修改为深红色"#980015"；网页中的图片修改为"智慧食堂.jpg"。',
}


@pytest.mark.parametrize("kind", sorted(NOT_DRAG))
def test_规则认得出的题清单不抢(kind):
    got = stem.auto_sim(NOT_DRAG[kind], "计算机网络基础")
    assert got and got["kind"] == kind, got and got.get("key")


@pytest.mark.parametrize("text", [
    "请用 WPS 写一篇介绍智能大棚的短文，标题设为二号黑体。",
    "打开「智慧农业.docx」，给标题加粗。",
    "编写程序，输出 100 以内的所有素数。",
])
def test_只沾了关键词的题不会被认成拖拽题(text):
    assert drag.find(text) is None


def test_题干见图那种短题干要对上知识范围():
    assert drag.find(REAL_STEMS["Q324-加减"], "Python编程基础")["key"] == "Q324-加减"
    assert drag.find(REAL_STEMS["Q324-加减"], "物联网") is None


# ================================================================ 旧版 exe
def test_旧版exe交上来的空作答留给老师评阅_不自动判零分():
    """机房里的 4.7 版 exe 画不出拖拽题，交卷时只会交一个 {"state": {}}（它的
    state_for() 不认 drag，返回空的）。新服务端要是照常判，就是一个标着"自动判分"
    的 0 分 —— 学生根本没机会做。这种留给老师评阅。

    别的"没做"照常判 0 分，和别的操作题一样：新版 exe 一张没放交的是
    {"placed": {}}，网页端没碰过的题交的是空串。"""
    from app.services.exam import grade

    entry = next(e for e in drag.BANK if e["key"] == "Q322-话费")
    item = {"id": 1, "type": "操作题", "score": 10, "stem": entry["stem"], "answer": "",
            "sim": {"kind": "drag", "env": entry["env"]}, "sim_checks": entry["checks"]}

    old = grade([item], {"1": json.dumps({"state": {}})})["detail"][0]
    assert not old.get("auto") and "老师评阅" in old["reason"], old

    blank = grade([item], {"1": json.dumps({"state": {"placed": {}}})})["detail"][0]
    assert blank.get("auto") and blank["earned"] == 0, "新版 exe 一张没放：判 0 分"

    for web in ({"1": ""}, {}):                     # 网页端没碰过 / 压根没交这一题
        got = grade([item], web)["detail"][0]
        assert got.get("auto") and got["earned"] == 0, (web, got)

    right = grade([item], {"1": json.dumps({"state": perfect(entry["checks"])})})["detail"][0]
    assert right["earned"] == 10
