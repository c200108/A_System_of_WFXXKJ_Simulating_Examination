"""拖拽类操作题：流程图补全、结构图热区、设备归类、本机 IP 查询、程序填空 / 排序。

## 为什么是一份写在代码里的清单

题库里这类题只有一段题干和一张**原考试系统的截图**（素材区烤在图上方，说明
弹窗还挡着半张图），没有任何能拿来判分的结构。所以每道题的结构图、素材、
检查点都在这里**照原图重画一遍**。

清单**按题干认题**，不存进数据库：老师用 data-import 导回旧数据时，题目
一行行被覆盖，题干还是原来那段话，于是认出来的还是同一道题、同一张图、同一套
检查点 —— 导多少次都不会变。这和 stem.py 按题干现算考场文件是同一个道理。

## 题干不全的，补成明确的

有的题干只有「（题干见图）」，有的只有一句「请将符合智能家居的设备拖拽到指定
区域」，学生看了不知道要干什么。这类题在清单里带一段补全后的题干（`stem`），
出卷时替换掉原题干；原题干留在库里不动（改了它，下次导库就对不上了）。

还有两道**库里存的答案和原图自相矛盾**，以原图为准：

- Q323 饮水量：库里写 A=「Water<1500」，可图上 A 的「是」分支通向「达标，继续
  保持!」，那 A 只能是 water>=1500；
- Q326 水费：库里写「water>20」，素材区和题干都是 water>=20（"满 20 吨"）。

## 学生拿到什么、判分看什么

    env     学生看到的：图、热区、素材卡片。**不含答案**，发到学生机上的就是它
    checks  判分用的：哪个热区该放哪张卡片。**等同于答案，只在服务端**

学生交上来的终态：

    {"placed": {"A": ["i1"], "B": ["i3"]}}          拖拽：热区 → 放进去的卡片
    {"ip": "192.168.1.5", "real_ips": ["…"]}        IP 查询：填的地址 + 本机真实地址

素材卡片的 id（i1、i2…）按原图素材区的顺序排，和答案无关，看 id 猜不出答案。
"""

from __future__ import annotations

import copy
import re
from typing import Optional

# 画布大小（逻辑像素）。桌面端按这个画，网页端用 SVG viewBox 按比例缩放
W, H = 720, 400


# ================================================================ 画图的小积木
def box(x, y, w, h, text, shape="rect"):
    """固定的图形：round 起止框 / rect 处理框 / diamond 判断框 / para 输入输出框 /
    cloud 互联网 / circle 控制中心 / device 设备"""
    return {"t": "box", "x": x, "y": y, "w": w, "h": h, "text": text, "shape": shape}


def line(*pts, arrow=True, text="", dash=False):
    return {"t": "line", "pts": [list(p) for p in pts], "arrow": arrow,
            "text": text, "dash": dash}


def zone(x, y, w, h, title):
    """虚线框起来的一片区域（科技楼、应用场景：家庭……），标题写在框的左上角"""
    return {"t": "zone", "x": x, "y": y, "w": w, "h": h, "text": title}


def slot(sid, x, y, w, h, label="", shape="rect", cap=1):
    """热区：学生把卡片拖进来的地方。cap 是最多能放几张（归类题的大框放很多张）"""
    return {"id": sid, "x": x, "y": y, "w": w, "h": h, "label": label or sid,
            "shape": shape, "cap": cap}


def item(iid, text, shape="rect"):
    return {"id": iid, "text": text, "shape": shape}


def put(sid, iid, desc, score=5):
    """检查点：热区 sid 里放的是卡片 iid"""
    return {"desc": desc, "score": score, "assert": {"op": "slot", "slot": sid, "is": [iid]}}


def among(slots, iid, desc, score=5):
    """检查点：卡片 iid 放进了这几个热区里的任意一个（顺序不限的那种）"""
    return {"desc": desc, "score": score,
            "assert": {"op": "in", "slots": list(slots), "item": iid}}


def none_of(slots, iids, desc, score=3):
    """检查点：这几张干扰卡片一张都没放进去"""
    return {"desc": desc, "score": score,
            "assert": {"op": "none_of", "slots": list(slots), "items": list(iids)}}


TIP_DIAGRAM = "从素材区把卡片拖到图中的虚线框（热区）里；放错了可以拖回素材区重放。"
TIP_CODE = "把下面的代码块拖到程序里对应的空位；放错了可以拖回来重放。"


# ================================================================ 流程图的两种骨架
def flow_if_elif_else(inp, yes1, cond2, no2, *, a="A", b="B", out=""):
    """开始 → 输入 → [A 判断] 是→ yes1 ；否→ [cond2] 是→ [B] ；否→ no2 → 结束"""
    shapes = [
        box(190, 8, 120, 32, "开始", "round"),
        box(165, 56, 170, 40, inp, "para"),
        box(190, 226, 120, 38, yes1),
        box(400, 180, 160, 56, cond2, "diamond"),
        box(580, 268, 130, 38, no2),
        box(190, 352, 120, 32, "结束", "round"),
        line((250, 40), (250, 56)),
        line((250, 96), (250, 122)),
        line((250, 184), (250, 226), text="是"),
        line((330, 153), (480, 153), (480, 180), text="否"),
        line((480, 236), (480, 268), text="是"),
        line((560, 208), (645, 208), (645, 268), text="否"),
        line((250, 264), (250, 352)),
        line((480, 306), (480, 330), arrow=False),
        line((645, 306), (645, 330), (250, 330)),
    ]
    slots = [slot(a, 170, 122, 160, 62, a, "diamond"), slot(b, 415, 268, 130, 38, b)]
    return {"mode": "diagram", "w": W, "h": H, "shapes": shapes, "slots": slots}


def flow_if_else(inp, *, yes=None, no=None, a="A", b="B", out=""):
    """开始 → 输入 → [A 判断] 是→ yes ；否→ no → (输出) → 结束。
    yes / no 传字符串就是固定的框，传 None 就是热区 B。"""
    shapes = [
        box(190, 8, 120, 32, "开始", "round"),
        box(165, 56, 170, 40, inp, "para"),
        line((250, 40), (250, 56)),
        line((250, 96), (250, 122)),
        line((250, 184), (250, 226), text="是"),
        line((330, 153), (480, 153), (480, 226), text="否"),
    ]
    slots = [slot(a, 170, 122, 160, 62, a, "diamond")]
    if yes is None:
        slots.append(slot(b, 175, 226, 150, 38, b))
    else:
        shapes.append(box(175, 226, 150, 38, yes))
    if no is None:
        slots.append(slot(b, 405, 226, 150, 38, b))
    else:
        shapes.append(box(405, 226, 150, 38, no))
    end_y = 352
    if out:
        shapes += [box(165, 300, 170, 36, out, "para"), line((250, 336), (250, 352))]
        join_y = 290
        shapes.append(line((250, 264), (250, 300)))
    else:
        join_y = 310
        shapes.append(line((250, 264), (250, end_y)))
    shapes += [line((480, 264), (480, join_y), (250, join_y)),
               box(190, end_y, 120, 32, "结束", "round")]
    return {"mode": "diagram", "w": W, "h": H, "shapes": shapes, "slots": slots}


def hub(center_text, spokes, slots_at, *, cx=360, cy=195, r=62):
    """中心控制平台 + 一圈设备的"轮辐图"（智能家居、智慧农业）。
    spokes: {方位: 设备名}，slots_at: {方位: 热区 id}"""
    spots = {"nw": (170, 60), "n": (360, 30), "ne": (550, 60), "e": (600, 195),
             "se": (550, 330), "s": (360, 360), "sw": (170, 330), "w": (120, 195)}
    shapes = [box(cx - r, cy - r, 2 * r, 2 * r, center_text, "circle")]
    slots = []
    for where, text in spokes.items():
        x, y = spots[where]
        shapes.append(line((cx, cy), (x, y), arrow=False))
        shapes.append(box(x - 60, y - 16, 120, 32, text, "device"))
    for where, sid in slots_at.items():
        x, y = spots[where]
        shapes.append(line((cx, cy), (x, y), arrow=False))
        slots.append(slot(sid, x - 60, y - 26, 120, 52, "热区"))
    # 线画在最底下：先画的先被盖住，框压在线上才干净
    shapes.sort(key=lambda s: 0 if s["t"] == "line" else 1)
    return {"mode": "diagram", "w": W, "h": H, "shapes": shapes, "slots": slots}


def code(rows, slots):
    """程序填空 / 排序。rows 每一行是若干段：字符串照原样显示，{"slot": id} 是空位"""
    return {"mode": "code", "rows": rows, "slots": slots}


# ================================================================ 清单
# 每一项：
#   match   题干里**都得有**的几句话（去掉空白和标点再比，全角半角不论）
#   exact   题干除了这句话之外不能再有别的（专门对付那种只有一句话的题干，
#           不然它会把"同一句话 + 更多内容"的别的题也认走）
#   stem    补全后的题干（没有就用原题干）
#   env / checks
#
# **越具体的越往前放**：认题是从上往下找第一条对得上的。
BANK = []


def _add(key, match, env, checks, *, stem="", exact=False, tip="", scope=""):
    env = dict(env)
    env.setdefault("tip", tip or (TIP_CODE if env.get("mode") == "code" else TIP_DIAGRAM))
    BANK.append({"key": key, "match": list(match), "exact": exact, "scope": scope,
                 "stem": stem, "env": env, "checks": checks})


# ---------------------------------------------------------------- 流程图（6 道）
_add("Q322-话费", ["通话时长", "0.2元/分钟", "流程图"],
     dict(flow_if_elif_else("输入时长(time)", "time*0.2", "time>=100", "time*0.5"),
          items=[item("i1", "time>=200", "diamond"), item("i2", "time>=100", "diamond"),
                 item("i3", "time*0.3"), item("i4", "time*0.2")]),
     [put("A", "i1", "A 处的判断是「time>=200」"),
      put("B", "i3", "B 处的计算是「time*0.3」")])

_add("Q323-饮水", ["饮水量", "1500", "流程图"],
     dict(flow_if_else("输入饮水量(water)", yes="达标，继续保持!", no=None),
          items=[item("i1", "water<1500", "diamond"), item("i2", "water>=1500", "diamond"),
                 item("i3", "达标，继续保持!"), item("i4", "建议增加饮水量")]),
     # 库里存的答案写的是 A=Water<1500，和原图矛盾：A 的「是」通向「达标」
     [put("A", "i2", "A 处的判断是「water>=1500」（「是」的分支输出达标）"),
      put("B", "i4", "B 处输出「建议增加饮水量」")])

_add("Q324-加减", ["题干见图"], scope="Python编程基础", exact=True,
     env=
     dict(flow_if_else("输入a、b的值", yes=None, no="t=a+b", out="输出t的值"),
          items=[item("i1", "a>=b", "diamond"), item("i2", "a<=b", "diamond"),
                 item("i3", "t=a-b"), item("i4", "a<=b-a")]),
     checks=[put("A", "i1", "A 处的判断是「a>=b」"),
      put("B", "i3", "B 处的计算是「t=a-b」")],
     stem="输入两个正整数 a、b：如果 a 大于或等于 b，输出 a 减 b 的差；否则，"
          "输出 a 加 b 的和。请根据程序功能，将流程图补充完整（把素材区中正确的"
          "卡片拖到 A、B 两个虚线框里）。")

_add("Q325-成绩", ["score", "60", "流程图"],
     dict(flow_if_else("输入成绩分数(score)", yes="恭喜！成绩达标", no=None),
          items=[item("i1", "score>=60", "diamond"), item("i2", "score<=60", "diamond"),
                 item("i3", "成绩未达标"), item("i4", "恭喜！成绩达标")]),
     [put("A", "i1", "A 处的判断是「score>=60」"),
      put("B", "i3", "B 处输出「成绩未达标」")])

_add("Q326-水费", ["用水量", "3元/吨", "流程图"],
     dict(flow_if_elif_else("输入用水量(water)", "water*3", "water>=10", "water*1.5"),
          items=[item("i1", "water>=20", "diamond"), item("i2", "water>=10", "diamond"),
                 item("i3", "water*2"), item("i4", "water*3")]),
     # 库里写的是 water>20；题干"满 20 吨"、素材卡片都是 water>=20
     [put("A", "i1", "A 处的判断是「water>=20」"),
      put("B", "i3", "B 处的计算是「water*2」")])

_add("Q327-折扣", ["购物金额", "打8折", "流程图"],
     dict(flow_if_elif_else("输入money", "输出8折实付金额", "money>=300", "输出原金额"),
          items=[item("i1", "money>=500", "diamond"), item("i2", "money>=300", "diamond"),
                 item("i3", "money*0.8"), item("i4", "money*0.9")]),
     [put("A", "i1", "A 处的判断是「money>=500」"),
      put("B", "i4", "B 处的计算是「money*0.9」（9 折）")])


# ---------------------------------------------------------------- 网络 / 信息系统结构图（4 道）
_add("Q306-校园网", ["核心交换机部署在学校科技楼", "300米"],
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          zone(8, 24, 300, 340, "科技楼"), zone(412, 24, 300, 340, "教学楼"),
          box(110, 64, 130, 34, "核心交换机", "device"),
          box(18, 54, 80, 30, "计算机", "device"), box(18, 124, 80, 30, "计算机", "device"),
          box(18, 194, 80, 30, "计算机", "device"),
          line((98, 69), (110, 78), arrow=False), line((98, 139), (120, 98), arrow=False),
          line((98, 209), (140, 98), arrow=False),
          line((175, 98), (175, 200), arrow=False),
          line((240, 81), (320, 81), arrow=False), line((410, 81), (470, 81), arrow=False),
          box(470, 64, 130, 34, "汇聚交换机", "device"),
          box(430, 150, 115, 30, "接入交换机", "device"), box(590, 150, 115, 30, "接入交换机", "device"),
          line((520, 98), (488, 150), arrow=False), line((550, 98), (648, 150), arrow=False),
          box(418, 232, 86, 30, "数字摄像机", "device"),
          line((466, 180), (461, 232), arrow=False), line((505, 180), (555, 222), arrow=False),
          box(608, 232, 90, 30, "数字广播", "device"), box(620, 302, 90, 30, "数字班牌", "device"),
          line((648, 180), (653, 232), arrow=False), line((696, 180), (696, 302), arrow=False),
      ],
      "slots": [slot("H1", 120, 200, 110, 60, "热区1"), slot("H2", 320, 56, 90, 50, "热区2"),
                slot("H3", 512, 222, 86, 54, "热区3")],
      "items": [item("i1", "服务器"), item("i2", "传感器"), item("i3", "光纤"),
                item("i4", "移动终端"), item("i5", "台式计算机")]},
     [put("H1", "i1", "科技楼核心交换机下接「服务器」"),
      put("H2", "i3", "两栋楼相距约 300 米，用「光纤」连接"),
      put("H3", "i5", "教学楼接入交换机下接「台式计算机」")],
     stem="学校大力实施教育信息化2.0工程，用数字技术赋能教育教学。下图是学校网络"
          "结构图：核心交换机部署在科技楼，其它设备部署在教学楼，两栋楼直线距离约 300 米。"
          "请从素材区选择合适的设备，拖到图中三个热区里，把结构图补充完整：热区1 是科技楼"
          "里挂在核心交换机下、存放全校数据的设备；热区2 是连接两栋楼的传输介质；热区3 是"
          "教学楼里接在接入交换机上的终端设备。")

_add("Q309-社团", ["社团", "编程社团配备台式电脑", "舞蹈社团配备触控一体机"],
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          box(300, 6, 120, 44, "互联网", "cloud"),
          zone(210, 64, 300, 84, "服务器监控：所有社团信息"),
          line((360, 50), (445, 74), arrow=False),
          line((445, 134), (360, 176), arrow=False),
          zone(20, 280, 200, 110, "编程社团教室"), zone(262, 280, 200, 110, "舞蹈社团教室"),
          zone(504, 280, 200, 110, "美术社团教室"),
          box(60, 312, 120, 30, "台式电脑", "device"), box(302, 312, 120, 30, "触控一体机", "device"),
          box(622, 318, 70, 30, "平板", "device"),
          line((360, 230), (120, 280), arrow=False), line((360, 230), (362, 280), arrow=False),
          line((360, 230), (604, 280), arrow=False),
      ],
      "slots": [slot("H1", 400, 72, 100, 60, "热区1"), slot("H2", 310, 176, 100, 54, "热区2"),
                slot("H3", 514, 306, 100, 56, "热区3")],
      "items": [item("i1", "手机"), item("i2", "交换机"), item("i3", "摄像头"),
                item("i4", "服务器"), item("i5", "无线路由器")]},
     [put("H1", "i4", "监控所有社团信息的是「服务器」"),
      put("H2", "i2", "把三间社团教室连到一起的是「交换机」"),
      put("H3", "i5", "美术社团的平板上网要「无线路由器」")],
     stem="为了丰富学生学习生活，学校给各个社团分配了专用教室和设备：编程社团配备"
          "台式电脑，学习 Python 编程；美术社团配备平板，开展数字绘画；舞蹈社团配备"
          "触控一体机，开展线上学习。请从素材区选择合适的设备拖到图中三个热区里，形成"
          "一个完整的系统：热区1 负责监控、存放所有社团的信息；热区2 把三间社团教室"
          "连接到一起；热区3 让美术社团的平板能无线上网。")

_add("Q312-点餐", ["点餐", "信息系统", "热区"],
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          box(295, 6, 130, 44, "INTERNET", "cloud"),
          box(110, 78, 120, 34, "调制解调器", "device"),
          line((170, 78), (320, 42), arrow=False),
          zone(30, 160, 310, 120, "应用场景：家庭（顾客点餐）"),
          line((170, 220), (210, 220)),
          line((260, 190), (190, 112)),
          box(470, 78, 140, 34, "点餐系统服务器", "device"),
          line((540, 78), (410, 44), arrow=False),
          zone(430, 150, 285, 235, "应用场景：商家"),
          line((540, 112), (540, 166)),
          box(445, 272, 120, 32, "商铺1客服端", "device"),
          box(585, 272, 120, 32, "商铺2客服端", "device"),
          line((540, 222), (505, 272)), line((540, 222), (645, 272)),
          box(585, 336, 120, 30, "打印机", "device"),
          line((645, 304), (645, 336)),
      ],
      "slots": [slot("H1", 60, 190, 110, 60, "热区1"), slot("H2", 210, 190, 110, 60, "热区2"),
                slot("H3", 490, 166, 100, 56, "热区3")],
      "items": [item("i1", "服务器"), item("i2", "交换机"), item("i3", "路由器"),
                item("i4", "手机终端"), item("i5", "网卡")]},
     [put("H1", "i4", "顾客用「手机终端」点餐"),
      put("H2", "i3", "家里的「路由器」把手机接到调制解调器"),
      put("H3", "i2", "商家用「交换机」把服务器和各客服端连起来")],
     stem="信息系统是由人、硬件、软件、网络和数据资源组成的人机交互系统。人们经常用"
          "手机 APP 点餐来节省做饭、购餐的时间。下图是点餐信息系统的结构图，请结合信息"
          "系统的相关知识，从素材区选择合适的设备拖到三个热区里，把它补充完整：家庭里，"
          "顾客用热区1 的设备点餐，经热区2 的设备连到调制解调器上网；商家那边，热区3 的"
          "设备把点餐系统服务器和各个客服端连接起来。")

_add("Q317-家庭网", ["小明家", "光纤接入互联网", "热区"],
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          box(200, 150, 120, 36, "无线路由器", "device"),
          box(450, 146, 100, 44, "互联网", "cloud"),
          line((320, 168), (338, 168), arrow=False), line((428, 168), (450, 168), arrow=False),
          box(600, 50, 100, 30, "服务器", "device"), box(600, 150, 100, 30, "服务器", "device"),
          box(600, 250, 100, 30, "服务器", "device"),
          line((550, 160), (600, 65), arrow=False), line((550, 168), (600, 165), arrow=False),
          line((550, 176), (600, 265), arrow=False),
          box(30, 40, 100, 28, "数字摄像头", "device"), box(150, 20, 100, 28, "扫地机器人", "device"),
          box(20, 110, 100, 28, "智能手环", "device"), box(20, 180, 100, 28, "平板电脑", "device"),
          box(150, 330, 110, 28, "笔记本电脑", "device"),
          line((230, 150), (80, 68), arrow=False, dash=True),
          line((245, 150), (200, 48), arrow=False, dash=True),
          line((220, 160), (120, 124), arrow=False, dash=True),
          line((200, 176), (120, 194), arrow=False, dash=True),
          line((220, 186), (100, 250), arrow=False, dash=True),
          line((250, 186), (205, 330), arrow=False, dash=True),
          line((290, 186), (290, 262), arrow=False),
      ],
      "slots": [slot("H1", 338, 140, 90, 56, "热区1"), slot("H2", 40, 250, 100, 56, "热区2"),
                slot("H3", 245, 262, 100, 56, "热区3")],
      "items": [item("i1", "台式电脑"), item("i2", "无线路由器"), item("i3", "智能手机"),
                item("i4", "ADSL调制解调器"), item("i5", "光猫（PON）")]},
     [put("H1", "i5", "家里通过光纤接入互联网，路由器和互联网之间是「光猫」"),
      put("H2", "i3", "和平板、手环一起无线连接的是「智能手机」"),
      put("H3", "i1", "用网线接在路由器上的是「台式电脑」")],
     stem="小明家配备了不同类型的信息技术设备，这些设备连接形成家庭局域网，并通过"
          "光纤接入互联网。请从素材区选择合适的设备拖到三个热区里，把网络连接结构图"
          "补充完整：热区1 在无线路由器和互联网之间；热区2 和平板电脑、智能手环一样用无线"
          "连接；热区3 用网线直接接在路由器上。（图中虚线表示无线连接，实线表示有线连接）")


# ---------------------------------------------------------------- 物联网（8 道）
_add("Q335-李华家", ["李华家", "智慧舒适家居系统"],
     dict(hub("智能家居控制中心",
              {"nw": "智能空调", "e": "智能门锁", "se": "手机", "sw": "智能摄像头"},
              {"n": "H1", "w": "H2"}),
          items=[item("i1", "智能音箱"), item("i2", "传统电饭煲"), item("i3", "智能窗帘"),
                 item("i4", "传统电视")]),
     [among(("H1", "H2"), "i1", "「智能音箱」接入了智能家居系统"),
      among(("H1", "H2"), "i3", "「智能窗帘」接入了智能家居系统"),
      none_of(("H1", "H2"), ("i2", "i4"), "传统电饭煲、传统电视不能联网控制，没有放进去")],
     stem="李华家定制了「智慧舒适家居系统」，可通过手机 APP 远程操控智能窗帘、智能门锁、"
          "智能空调、智能音箱等设备，形成联动网络。请从素材区选出能接入这套系统的智能"
          "设备，拖到图中两个空着的热区里（传统家电不能联网控制，不要拖进去）。")

_add("Q338-智能家居归类", ["素材设备", "热水器云平台"],
     {"mode": "diagram", "w": W, "h": 260,
      "shapes": [box(20, 10, 680, 30, "小鹏家：家庭成员用手机 APP，经各设备的云平台远程控制家中的智能设备",
                     "note")],
      "slots": [slot("Z", 20, 56, 680, 190, "智能家居系统（受手机 APP 远程控制的智能设备及其云平台）",
                     cap=13)],
      "items": [item("i1", "交换机"), item("i2", "智能空调"), item("i3", "监控云平台"),
                item("i4", "无线路由器"), item("i5", "普通非智能空调"), item("i6", "智能热水器"),
                item("i7", "智能摄像头"), item("i8", "PC电脑"), item("i9", "光猫"),
                item("i10", "笔记本电脑"), item("i11", "空调云平台"), item("i12", "热水器云平台"),
                item("i13", "互联网")]},
     [among(("Z",), "i2", "「智能空调」属于智能家居系统", 2),
      among(("Z",), "i6", "「智能热水器」属于智能家居系统", 2),
      among(("Z",), "i7", "「智能摄像头」属于智能家居系统", 2),
      among(("Z",), "i3", "「监控云平台」属于智能家居系统", 2),
      among(("Z",), "i11", "「空调云平台」属于智能家居系统", 2),
      among(("Z",), "i12", "「热水器云平台」属于智能家居系统", 2),
      none_of(("Z",), ("i1", "i4", "i5", "i8", "i9", "i10", "i13"),
              "网络设备、普通电脑和普通空调没有拖进来", 4)],
     stem="小鹏设计了一个家庭智能系统：家庭成员可以用手机 APP，经过各设备的云平台远程"
          "控制家中的智能设备。请把属于这套智能家居系统的智能设备和云平台拖进下面的"
          "大框里；交换机、路由器、光猫、互联网这类网络设施，普通电脑，以及不能联网控制"
          "的普通家电都不要拖进去。")

_add("Q334-智能家居", ["请将符合智能家居的设备拖拽到指定区域"],
     dict(hub("智能家居控制中心",
              {"nw": "智能空调", "w": "门窗控制系统", "sw": "智能安防系统", "se": "人脸识别系统"},
              {"n": "H1", "ne": "H2"}),
          items=[item("i1", "传统电视机"), item("i2", "智能灯"), item("i3", "波轮洗衣机"),
                 item("i4", "影音控制系统")]),
     [among(("H1", "H2"), "i2", "「智能灯」接入了智能家居系统"),
      among(("H1", "H2"), "i4", "「影音控制系统」接入了智能家居系统"),
      none_of(("H1", "H2"), ("i1", "i3"), "传统电视机、波轮洗衣机不能联网控制，没有放进去")],
     exact=True,
     stem="下图是一套智能家居系统：各种智能设备都连在中间的智能家居控制中心上，可以联动、"
          "远程控制。请从素材区选出符合智能家居要求的设备，拖到图中两个空着的热区里"
          "（不能联网控制的传统家电不要拖进去）。")

_add("Q336-智能大棚", ["请将符合智能大棚的设备拖拽到指定区域"], exact=True,
     env=
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          box(270, 150, 110, 100, "智能大棚\n控制中心", "circle"),
          zone(420, 16, 280, 120, "温湿度自动控制区"),
          box(436, 58, 100, 32, "智能风机", "device"),
          zone(20, 136, 220, 120, "自动补光设备区"),
          box(34, 176, 90, 32, "照明灯", "device"), box(132, 176, 100, 32, "光敏传感器", "device"),
          zone(420, 260, 280, 120, "智能灌溉设备控制区"),
          box(432, 302, 116, 32, "智能滴灌设备", "device"),
          line((370, 175), (420, 90), arrow=False), line((270, 200), (240, 196), arrow=False),
          line((370, 225), (420, 320), arrow=False),
      ],
      "slots": [slot("H1", 560, 44, 124, 60, "热区1"), slot("H2", 562, 288, 124, 60, "热区2")],
      "items": [item("i1", "温湿度传感器"), item("i2", "重力传感器"), item("i3", "土壤湿度传感器"),
                item("i4", "红外传感器")]},
     checks=[put("H1", "i1", "温湿度自动控制区要「温湿度传感器」"),
      put("H2", "i3", "智能灌溉设备控制区要「土壤湿度传感器」")],
     stem="智能大棚由控制中心按传感器采集的数据自动控制各种设备。请从素材区选择合适的"
          "传感器拖到两个热区里：温湿度自动控制区需要感知空气温湿度来控制智能风机；"
          "智能灌溉设备控制区需要感知土壤干湿来控制滴灌设备。")

_add("Q337-小鹏家", ["小鹏", "家庭智能系统", "智能热水器", "热区"],
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          zone(12, 30, 200, 330, "云平台"),
          box(28, 150, 168, 40, "空调云平台", "device"), box(28, 230, 168, 40, "热水器云平台", "device"),
          box(250, 160, 100, 46, "互联网", "cloud"),
          line((212, 190), (250, 183), arrow=False),
          box(258, 290, 84, 30, "手机", "device"),
          line((300, 290), (300, 206), arrow=False, dash=True),
          zone(380, 16, 332, 370, "小鹏家"),
          box(398, 160, 90, 34, "光猫", "device"),
          line((350, 183), (398, 177), arrow=False), line((488, 177), (520, 177), arrow=False),
          box(396, 56, 108, 30, "智能摄像头", "device"), box(512, 56, 108, 30, "智能热水器", "device"),
          line((555, 150), (453, 86), arrow=False, dash=True),
          line((570, 150), (575, 86), arrow=False, dash=True),
          line((600, 150), (650, 110), arrow=False, dash=True),
          box(636, 230, 70, 30, "PC电脑", "device"), box(626, 290, 80, 30, "笔记本电脑", "device"),
          line((620, 190), (650, 230), arrow=False), line((610, 206), (650, 290), arrow=False),
      ],
      "slots": [slot("H1", 28, 60, 168, 60, "热区1"), slot("H2", 520, 150, 100, 56, "热区2"),
                slot("H3", 632, 52, 76, 58, "热区3")],
      "items": [item("i1", "智能空调"), item("i2", "监控云平台"), item("i3", "普通冰箱（非智能）"),
                item("i4", "交换机"), item("i5", "无线路由器")]},
     [put("H1", "i2", "云平台里还缺「监控云平台」（智能摄像头用它）"),
      put("H2", "i5", "光猫后面既接无线设备又接电脑的是「无线路由器」"),
      put("H3", "i1", "和摄像头、热水器一样无线接入的是「智能空调」")],
     stem="小鹏设计了一个简单的家庭智能系统，家庭成员可以用手机 APP 通过互联网远程控制"
          "家中的智能摄像头、智能空调、智能热水器等设备。请从素材区选择合适的对象拖到"
          "三个热区里，把结构图补充完整：热区1 在云平台里（每种智能设备都有自己的云平台）；"
          "热区2 接在光猫后面，既无线连接智能设备（虚线），又用网线连接电脑（实线）；"
          "热区3 是和摄像头、热水器一样无线接入的智能设备。")

_add("Q339-红绿灯", ["智慧交通", "红绿灯自动调节", "拖拽"],
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          box(20, 150, 140, 70, "检测车流量"),
          line((160, 185), (200, 185)), line((340, 185), (380, 185)), line((520, 185), (560, 185)),
          box(560, 150, 140, 70, "恢复正常"),
      ],
      "slots": [slot("H1", 200, 150, 140, 70, "热区1"), slot("H2", 380, 150, 140, 70, "热区2")],
      "items": [item("i1", "判断拥堵情况"), item("i2", "调整红绿灯时长")]},
     [put("H1", "i1", "检测到车流量之后，先「判断拥堵情况」"),
      put("H2", "i2", "判断出拥堵，再「调整红绿灯时长」")],
     stem="智慧交通系统汇集交通信息，能对交通进行感知、分析、预测和控制。现在要实现"
          "「红绿灯自动调节」功能，请把素材区的两个处理步骤按先后顺序拖到流程图的"
          "两个热区里。")

_add("Q340-智慧食堂", ["智慧食堂", "智能结算台", "热区"],
     {"mode": "diagram", "w": W, "h": H,
      "shapes": [
          box(90, 8, 130, 36, "云服务器", "device"),
          box(330, 6, 130, 44, "INTERNET", "cloud"),
          line((220, 26), (330, 28), arrow=False),
          box(340, 78, 110, 32, "路由器", "device"),
          line((395, 50), (395, 78), arrow=False), line((395, 110), (395, 140), arrow=False),
          zone(12, 110, 290, 116, "管理员"),
          box(26, 146, 80, 34, "管理员", "device"),
          line((106, 163), (160, 163)), line((270, 165), (340, 168), arrow=False),
          zone(470, 110, 240, 116, "家"),
          box(622, 146, 76, 34, "家长", "device"),
          line((622, 163), (590, 163)),
          line((450, 40), (540, 130), arrow=False),
          zone(40, 244, 650, 140, "食堂"),
          box(140, 310, 160, 36, "教工智能结算台", "device"),
          box(430, 310, 160, 36, "学生智能结算台", "device"),
          line((395, 196), (220, 310), arrow=False), line((395, 196), (510, 310), arrow=False),
      ],
      "slots": [slot("H1", 340, 140, 110, 56, "热区1"), slot("H2", 160, 134, 110, 60, "热区2"),
                slot("H3", 482, 134, 108, 60, "热区3")],
      "items": [item("i1", "管理电脑"), item("i2", "传感器"), item("i3", "调制解调器"),
                item("i4", "手机终端"), item("i5", "交换机")]},
     [put("H1", "i5", "把管理员、各结算台连到路由器上的是「交换机」"),
      put("H2", "i1", "后台管理员用「管理电脑」查看食材、财务数据"),
      put("H3", "i4", "家长用「手机终端」随时查看孩子的消费信息")],
     stem="学校引进了「智慧食堂」管理系统：师生使用带电子标签的餐盘，智能结算台可以精准"
          "识别餐盘、快速结算；家长可以随时随地查看孩子在校的消费信息；后台管理员可以查看"
          "食材、财务数据。请从素材区选择合适的设备拖到三个热区里，把结构图补充完整："
          "热区1 把管理员和各结算台连到路由器上；热区2 是管理员使用的设备；热区3 是家长"
          "使用的设备。")

_add("Q341-智慧农业", ["智慧农业系统的设备拖拽到指定区域"],
     dict(hub("智慧农业控制平台",
              {"ne": "通风设备", "s": "智能摄像头", "se": "手机"},
              {"nw": "H1", "sw": "H2"}),
          items=[item("i1", "温湿度传感器"), item("i2", "灌溉控制器"), item("i3", "电视"),
                 item("i4", "洗衣机")]),
     [among(("H1", "H2"), "i1", "「温湿度传感器」接入了智慧农业系统"),
      among(("H1", "H2"), "i2", "「灌溉控制器」接入了智慧农业系统"),
      none_of(("H1", "H2"), ("i3", "i4"), "电视、洗衣机和农业大棚无关，没有放进去")],
     stem="农民用手机上的智慧农业监控平台，可以实时查看大棚内的温度、湿度、光照等环境"
          "数据，系统还能自动控制灌溉、通风、遮阳等设备。请从素材区选出属于智慧农业"
          "系统的设备，拖到图中两个空着的热区里。")


# ---------------------------------------------------------------- 本机 IP 查询（2 道）
IP_TIP = "打开命令提示符（开始 → 运行 → 输入 cmd 回车），输入 ipconfig 回车，找到「IPv4 地址」那一行。"

_add("Q307-终端IP", ["教学楼中终端电脑的IP地址"],
     {"mode": "ip", "sim_ip": "192.168.10.25", "mask": "255.255.255.0",
      "gateway": "192.168.10.1", "host": "JXL-TERM-25", "tip": IP_TIP},
     [{"desc": "查到并填对这台电脑的 IP 地址", "score": 10,
       "assert": {"op": "ip", "sim_ip": "192.168.10.25"}}],
     stem="你正在使用的这台电脑，就是教学楼里的一台终端电脑。请查询它的 IP 地址，"
          "填到下面的方框里。" + IP_TIP)

_add("Q310-本机IP", ["进入Windows仿真系统", "查询本机IP地址"],
     {"mode": "ip", "sim_ip": "192.168.1.108", "mask": "255.255.255.0",
      "gateway": "192.168.1.1", "host": "STUDENT-PC", "tip": IP_TIP},
     [{"desc": "查到并填对本机 IP 地址", "score": 10,
       "assert": {"op": "ip", "sim_ip": "192.168.1.108"}}],
     stem="查询本机的 IP 地址，并填到下面的方框里。" + IP_TIP)


# ---------------------------------------------------------------- Python（4 道）
_add("C0577-体温填空", ["腋窝", "低烧", "补全代码"],
     dict(code([['tw = float(input("请输入体温（℃）："))'],
           ["if tw < 37:"], ['    print("体温正常")'],
           ["elif ", {"slot": "1"}, ":"], ['    print("低烧")'],
           ["elif tw < 39:"], ['    print("中度发烧")'],
           ["elif tw < 41:"], ['    print("高烧")'],
           [{"slot": "2"}, ":"], ['    print("超高烧")']],
          [slot("1", 0, 0, 110, 28, "①"), slot("2", 0, 0, 110, 28, "②")]),
          items=[item("i1", "tw<38"), item("i2", "tw>=38"), item("i3", "else"),
                  item("i4", "elif"), item("i5", "tw<37")]),
     [put("1", "i1", "① 处是「tw<38」（37℃≤体温＜38℃ 是低烧）"),
      put("2", "i3", "② 处是「else」（其余情况都是超高烧）")],
     stem="人体正常体温平均在 36～37℃之间（腋窝），37℃及以上就是发烧：低烧 37℃≤体温＜38℃，"
          "中度发烧 38℃≤体温＜39℃，高烧 39℃≤体温＜41℃，超高烧 体温≥41℃。下面的程序根据"
          "输入的体温判断发烧程度，请把正确的代码块拖到 ①、② 两处，补全程序（其它代码不要改）。")

_add("C0580-入校体温", ["开学入校体温", "exam01.py"],
     dict(code([["# 开学入校体温检测：正常范围 35℃～37.2℃"],
           ["t = ", {"slot": "1"}, '(input("请输入体温："))'],
           ["if 35 <= t <= 37.2:"], ['    print("体温正常，可以入校")'],
           [{"slot": "2"}, ":"], ['    print("体温异常，请到观察区复测")']],
          [slot("1", 0, 0, 90, 28, "①"), slot("2", 0, 0, 90, 28, "②")]),
          items=[item("i1", "int"), item("i2", "float"), item("i3", "str"),
                  item("i4", "elif"), item("i5", "else")]),
     [put("1", "i2", "① 处是「float」（体温带小数，要转成小数）"),
      put("2", "i5", "② 处是「else」（不在正常范围就是异常）")],
     stem="开学入校要测体温，小明做了一个小程序，检测输入的体温是否正常（正常范围 "
          "35℃～37.2℃）并输出结果。请把正确的代码块拖到程序中 ①、② 两处，把程序补充"
          "完整（不要添加或删减程序行）。")

_add("C0579-行李收费", ["行李", "1.68元", "1.98元"],
     dict(code([["1  ", {"slot": "L1"}], ["2  ", {"slot": "L2"}], ["3  ", {"slot": "L3"}],
           ["4  ", {"slot": "L4"}], ["5  ", {"slot": "L5"}], ["6  ", {"slot": "L6"}]],
          [slot(f"L{i}", 0, 0, 440, 28, f"第{i}行") for i in range(1, 7)]),
          items=[item("i1", "    money = w * 1.98"), item("i2", "if w <= 20:"),
                  item("i3", 'print("收费：", money, "元")'), item("i4", "if w < 20:"),
                  item("i5", 'w = float(input("请输入行李重量（公斤）："))'),
                  item("i6", "else:"), item("i7", "    money = w * 1.68"),
                  item("i8", "money = w * 1.98")]),
     [put("L1", "i5", "第 1 行：输入行李重量", 2), put("L2", "i2", "第 2 行：if w <= 20:", 2),
      put("L3", "i7", "第 3 行：按 1.68 元/公斤计费", 2), put("L4", "i6", "第 4 行：else:", 2),
      put("L5", "i1", "第 5 行：按 1.98 元/公斤计费", 2), put("L6", "i3", "第 6 行：输出收费", 2)],
     stem="乘坐飞机时，乘客行李小于等于 20 公斤时按每公斤 1.68 元收费，大于 20 公斤时"
          "按每公斤 1.98 元收费。下面给出了计算收费程序的代码行（其中有两行是多余的），"
          "请把它们按正确的顺序拖到第 1～6 行，组成完整的程序（行首的空格表示缩进）。")

_add("C0578-勾股数", ["勾股数", "100以内"],
     dict(code([["1  ", {"slot": "L1"}], ["2  ", {"slot": "L2"}], ["3  ", {"slot": "L3"}],
           ["4  ", {"slot": "L4"}], ["5  ", {"slot": "L5"}]],
          [slot(f"L{i}", 0, 0, 470, 28, f"第{i}行") for i in range(1, 6)]),
          items=[item("i1", "        if c <= 100 and a * a + b * b == c * c:"),
                  item("i2", "    for b in range(a + 1, 101):"),
                  item("i3", "            print(a, b, c)"),
                  item("i4", "    for b in range(1, a):"),
                  item("i5", "for a in range(1, 101):"),
                  item("i6", "        c = int((a * a + b * b)  0.5)"),
                  item("i7", "        if a * a + b * b == 100:")]),
     [put("L1", "i5", "第 1 行：a 从 1 到 100", 2),
      put("L2", "i2", "第 2 行：b 从 a+1 起（保证 a<b）", 2),
      put("L3", "i6", "第 3 行：算出 c", 2),
      put("L4", "i1", "第 4 行：c 不超过 100 且满足 a×a+b×b=c×c", 2),
      put("L5", "i3", "第 5 行：输出这组勾股数", 2)],
     stem="所谓勾股数，是指能够构成直角三角形三条边的三个正整数 a、b、c，即 a×a+b×b=c×c。"
          "下面给出了「找出 100 以内满足 a＜b 的所有勾股数」程序的代码行（其中有两行是"
          "多余的），请把它们按正确的顺序拖到第 1～5 行，组成完整的程序（行首的空格表示缩进）。")


# ================================================================ 认题
_PUNCT = re.compile(r"[\s，,。．.、；;：:！!？?“”\"'‘’（）()【】\[\]《》<>「」『』\-—_~～·]")


def _flat(text: str) -> str:
    """去掉空白和标点，全角字母数字转半角。认题只看字，不看标点和换行。"""
    s = "".join(chr(ord(c) - 0xFEE0) if "！" <= c <= "～" else c for c in str(text or ""))
    return _PUNCT.sub("", s).lower()


def find(stem: str, scope: str = "") -> Optional[dict]:
    """题干对应清单里哪一项。认不出返回 None（这道题就还是老样子：占位、老师评阅）。

    认题的几句话要**挑这道题独有的**：只写「智慧食堂」的话，一道做「智慧食堂」
    宣传网页的 HTML 题也会被认走。题干短到没什么可挑的（「（题干见图）」），
    就再加上知识范围。
    """
    flat = _flat(stem)
    if not flat:
        return None
    for entry in BANK:
        keys = [_flat(m) for m in entry["match"]]
        if not all(k in flat for k in keys):
            continue
        if entry["scope"] and scope and entry["scope"] != scope:
            continue
        # 只有一句话的题干：除了那句话，最多再带个「（按钮：开始操作）」之类的尾巴
        if entry["exact"] and len(flat) > sum(len(k) for k in keys) + 12:
            continue
        return entry
    return None


def auto(stem: str, scope: str = "") -> Optional[dict]:
    """给 stem.auto_sim 用：认得出就返回一道完整的拖拽题。"""
    entry = find(stem, scope)
    if not entry:
        return None
    return {"kind": "drag", "env": copy.deepcopy(entry["env"]),
            "checks": copy.deepcopy(entry["checks"]),
            "stem": entry["stem"] or "", "key": entry["key"]}


# ================================================================ 判分
def check(a: dict, state: dict) -> tuple:
    """一条检查点对不对。返回 (对不对, 给老师看的一句话)。"""
    placed = {str(k): [str(x) for x in (v or [])]
              for k, v in ((state or {}).get("placed") or {}).items()}
    op = a.get("op")

    if op == "slot":
        got = placed.get(str(a.get("slot")), [])
        want = [str(x) for x in a.get("is") or []]
        if not got:
            return False, f"热区「{a.get('slot')}」是空的"
        if len(got) == 1 and got[0] in want:
            return True, f"热区「{a.get('slot')}」放对了"
        return False, f"热区「{a.get('slot')}」放的不对"

    if op == "in":
        want = str(a.get("item"))
        inside = {x for s in a.get("slots") or [] for x in placed.get(str(s), [])}
        return (True, "放进去了") if want in inside else (False, "没有放进去")

    if op == "none_of":
        bad = {str(x) for x in a.get("items") or []}
        inside = {x for s in a.get("slots") or [] for x in placed.get(str(s), [])}
        wrong = bad & inside
        return (False, f"放进了 {len(wrong)} 个不该放的") if wrong else (True, "没有放进不该放的")

    if op == "ip":
        typed = re.sub(r"\s+", "", str((state or {}).get("ip") or ""))
        if not typed:
            return False, "没有填 IP 地址"
        # 桌面端：学生在真机上查，交卷时客户端顺手记下本机的真实地址（real_ips），
        # 填的得是其中一个。**只认真地址**：网页端仿真命令行里那个 sim_ip 是固定的，
        # 练过网页版的学生都见过，在机房里照抄它不能算查过了
        if "real_ips" in (state or {}):
            real = {str(x) for x in state.get("real_ips") or []}
            if typed in real:
                return True, f"填的是 {typed}，是本机的地址"
            if not real:
                return False, f"填的是 {typed}，但交卷时没查到本机地址，请老师核对"
            return False, f"填的是 {typed}，不是本机的 IP 地址（本机：{'、'.join(sorted(real))}）"
        # 网页端：没有真机，仿真命令行里显示的是 sim_ip，填的得是它
        if typed == str(a.get("sim_ip") or ""):
            return True, f"填的是 {typed}，对"
        return False, f"填的是 {typed}，不是本机的 IP 地址"

    return False, f"不认识的检查方式：{op}"
