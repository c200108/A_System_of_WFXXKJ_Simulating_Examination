"""题干里的工作目录、文件名要和考场里实际铺出来的一致（2.12.0）。

报上来的：题干写「本题工作目录:D:\\EXAM windows操作02　请打开本题工作目录下的系统基本操作
文件夹」，考场却铺在 C:\\EXAM\\系统基本操作；WPS 题说「外卖小哥夺冠.wps」，考场里是 .docx；
六道题都叫「系统基本操作」，放进同一张卷子就挤在一个文件夹里。

题干照抄自题库（机房版库里的第 289、291、292、290、342、318、334 题）。
"""

import io
import json
import zipfile

from app.services import stem as S
from app.services.exam import separate_workdirs

WIN_A = ('本题工作目录:D:\\EXAM windows操作02\n请打开本题工作目录下的系统基本操作文件夹，按要求完成以下操作:\n'
         '①新建一个名为"鉴赏"的文件夹。\n②将文件"双松平远图.jpg"移动到"中国名画"文件夹中。')
WIN_B = ('本题工作目录:D:\\EXAM\\windows操作\n请打开本题工作目录下的系统基本操作文件夹，按要求完成以下操作:\n'
         '①在"动物"文件夹中新建一个名为"珍稀动物"的文件夹。\n②将"爱护动物.jpg"文件复制到"动物世界"文件夹中。')
WIN_PATH = ('Win操作题\n请打开本题工作目录（C：\\EXAM\\Win操作）按照要求进行作答。\n'
            '（1）在“素材”文件夹中新建一个名为“图片”的文件夹。')
WPS = ('本题工作目录:D:\\EXAM WPS文字\n请打开本题工作目录中的"职业教育大有可为.docx"，请完成以下操作:\n'
       '①将正文中所有的"qingchun"替换为"青春"。')
WPS_WPS = ('WPS文字\n请打开本题工作目录（C：\\EXAM\\WPS文字）下名为“00后，自我崛起的一代.wps”的WPS文字文件，'
           '并完成以下操作。\n（1）将文章题目“00后，自我崛起的一代”，设置字体为楷体，字号为二号。')
AI = ('本题工作目录:D:\\EXAM生成式人工智能\n请使用给定的AI工具完成以下操作:\n'
      '①请对"树树皆秋色，山山唯落晖。"这句诗，生成一段鉴赏文本。')


def shown(text, scope=""):
    got = S.auto_sim(text, scope)
    return S.student_stem(text, got["kind"], got["env"]), got


def test_Windows题_题干路径换成考场里的():
    text, got = shown(WIN_A)
    assert text.startswith("本题工作目录:C:\\EXAM\n请打开本题工作目录下的系统基本操作文件夹")
    assert "D:" not in text and "windows操作02" not in text
    assert any(k.startswith("C:/EXAM/系统基本操作/") for k in got["env"]["fs"]), "考场确实铺在这儿"


def test_只给了完整路径的_保留那一层文件夹():
    text, got = shown(WIN_PATH)
    assert "（C:\\EXAM\\Win操作）" in text
    assert any(k.startswith("C:/EXAM/Win操作/") for k in got["env"]["fs"])


def test_WPS题_工作目录是考试根_扩展名按实际的():
    text, _ = shown(WPS)
    assert text.startswith("本题工作目录:C:\\EXAM\n")
    text, got = shown(WPS_WPS)
    assert "（C:\\EXAM）" in text and "“00后，自我崛起的一代.docx”" in text and ".wps”" not in text


def test_AI题不铺文件_那句工作目录去掉():
    text, _ = shown(AI)
    assert "工作目录" not in text and text.startswith("请使用给定的AI工具")


def test_改写题干不影响环境和检查点():
    """环境、检查点按库里的原题干算；改写只动学生看到的字，换回去算出来的一模一样。"""
    for raw in (WIN_A, WIN_B, WIN_PATH, WPS, WPS_WPS):
        got = S.auto_sim(raw, "")
        again = S.auto_sim(S.student_stem(raw, got["kind"], got["env"]), "")
        assert again["env"] == got["env"] and again["checks"] == got["checks"], raw[:30]


def _item(qid, text):
    got = S.auto_sim(text, "")
    return {"id": qid, "stem": S.student_stem(text, got["kind"], got["env"]),
            "sim": {"kind": got["kind"], "env": got["env"], "title": ""},
            "sim_checks": got["checks"]}


def test_同一张卷子上重名的工作目录自动编号():
    items = separate_workdirs([_item(1, WIN_A), _item(2, WIN_B), _item(3, WIN_A)])
    tops = [{k.split("/")[2] for k in it["sim"]["env"]["fs"]} for it in items]
    assert tops == [{"系统基本操作"}, {"系统基本操作2"}, {"系统基本操作3"}]
    for it, top in zip(items, ("系统基本操作", "系统基本操作2", "系统基本操作3")):
        assert f"打开本题工作目录下的{top}文件夹" in it["stem"]
        paths = [c["assert"]["path"] for c in it["sim_checks"] if "path" in c.get("assert", {})]
        assert paths and all(p.startswith(f"C:/EXAM/{top}/") for p in paths), "检查点跟着改"


def test_不重名的一个都不动():
    items = separate_workdirs([_item(1, WIN_A), _item(2, WIN_PATH)])
    assert "系统基本操作文件夹" in items[0]["stem"] and "（C:\\EXAM\\Win操作）" in items[1]["stem"]


def test_只给完整路径的重名题_题干路径跟着改():
    items = separate_workdirs([_item(1, WIN_PATH), _item(2, WIN_PATH)])
    assert "（C:\\EXAM\\Win操作2）" in items[1]["stem"]


def test_考试包里的题干和文件对得上(client, auth):
    """整条链路：出卷 → 考试包。包里题干说的文件夹，包里就有这个文件夹。"""
    for old in client.get("/api/questions?pinned=true&page_size=200", headers=auth).json()["items"]:
        client.put(f"/api/questions/{old['id']}", json={"is_pinned": False}, headers=auth)
    q = client.post("/api/questions", json={
        "type": "操作题", "stem": WIN_A, "answer": "略", "scope": "Windows系统操作",
        "is_pinned": True, "options": []}, headers=auth).json()
    paper = client.post("/api/papers/generate", json={
        "title": "工作目录", "by_sections": True, "use_pinned": True, "save": True},
        headers=auth).json()
    client.put(f"/api/questions/{q['id']}", json={"is_pinned": False}, headers=auth)
    exam = client.post("/api/exams", json={"paper_id": paper["paper_id"]}, headers=auth).json()
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/desk/export/{exam['id']}", headers=auth).content))
    rows = [r for g in json.loads(z.read("paper.json"))["groups"] for r in g["items"]
            if r["id"] == str(q["id"])] if "groups" in json.loads(z.read("paper.json")) else \
        [r for r in json.loads(z.read("paper.json")) if r["id"] == str(q["id"])]
    assert rows and rows[0]["stem"].startswith("本题工作目录:C:\\EXAM\n")
    assert any(n.startswith("files/系统基本操作/") for n in z.namelist()), z.namelist()[:10]
    client.delete(f"/api/questions/{q['id']}", headers=auth)
