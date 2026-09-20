# -*- coding: utf-8 -*-
"""带图的题，图要跟着进考试包，并且在 exe 里真的显示出来。

题库里 26 道题带配图，**全是 .jpg**，而 Tkinter 只认 PNG 和 GIF。不转的话学生
看到的是一道没有图的带图题 —— 题干说"请仔细读图"，屏幕上什么都没有，这题谁也
做不出来，而且考试当场才会发现。

转换放在服务端（`app/services/images.py`）：学生端因此不用为了解码 JPEG 往 exe
里塞一个图像库，一张图也只转一次。
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services import images
from client import package


def a_jpeg(width=1200, height=900) -> bytes:
    """一张真的 JPEG。故意做得比屏幕大，顺便验缩放。"""
    PIL = pytest.importorskip("PIL.Image", reason="服务端要靠 Pillow 解 JPEG")
    im = PIL.new("RGB", (width, height), (200, 60, 60))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest.fixture
def uploaded(tmp_path, monkeypatch):
    """假装教师上传过一张图。"""
    from app.config import settings
    root = tmp_path / "uploads"
    (root / "images").mkdir(parents=True)
    (root / "images" / "题图.jpg").write_bytes(a_jpeg())
    monkeypatch.setattr(settings, "upload_dir", str(root))
    return root


# ================================================================ 服务端转换
def test_jpeg_becomes_png(uploaded):
    """**这是整件事的关键一步**：Tkinter 不认 JPEG。"""
    got = images.as_png("/uploads/images/题图.jpg")
    assert got, "转换失败，带图题就没有图"
    name, data = got
    assert name.endswith(".png")
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "不是真的 PNG，Tk 照样读不了"


def test_big_pictures_are_shrunk(uploaded):
    """几兆的原图 × 五十台机器一起下载，开考那几秒会很难看。
    缩到题目区装得下就够。"""
    PIL = pytest.importorskip("PIL.Image")
    _name, data = images.as_png("/uploads/images/题图.jpg")
    with PIL.open(io.BytesIO(data)) as im:
        assert im.width <= images.MAX_WIDTH and im.height <= images.MAX_HEIGHT


def test_the_png_is_not_bigger_than_the_jpeg_it_came_from():
    """**PNG 是无损格式，照片直接转过去会比原图大一倍。**

    实测四张真题配图：194 KB 的 JPEG 转成 399 KB 的 PNG，一份考试包因此涨到
    900 KB —— 五十个学生同时开考就是 45 MB 挤一条几兆的上行链路，
    学生那边表现为"点了开始考试转很久"。减到 256 色之后比原图还小。
    """
    PIL = pytest.importorskip("PIL.Image")
    import tempfile
    from pathlib import Path as P
    from app.config import settings

    root = P(tempfile.mkdtemp()) / "uploads"
    (root / "images").mkdir(parents=True)
    photo = PIL.new("RGB", (1400, 1000))
    for x in range(1400):                       # 渐变，比纯色更接近真实照片
        for y in range(0, 1000, 25):
            photo.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    photo.save(root / "images" / "照片.jpg", format="JPEG", quality=85)
    before = (root / "images" / "照片.jpg").stat().st_size

    old = settings.upload_dir
    settings.upload_dir = str(root)
    try:
        _name, data = images.as_png("/uploads/images/照片.jpg")
    finally:
        settings.upload_dir = old
    assert len(data) <= before * 1.2, (
        f"转完 {len(data)//1024} KB，原图才 {before//1024} KB —— 考试包会撑爆")


def test_png_is_passed_through_untouched(tmp_path, monkeypatch):
    """已经是 PNG 的**一个像素都不动** —— 重新编码只会掉质量。"""
    from app.config import settings
    root = tmp_path / "uploads"
    (root / "images").mkdir(parents=True)
    raw = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    (root / "images" / "原图.png").write_bytes(raw)
    monkeypatch.setattr(settings, "upload_dir", str(root))
    assert images.as_png("/uploads/images/原图.png") == ("原图.png", raw)


def test_outside_links_are_not_fetched(uploaded):
    """题目里如果写了外链，**不去下载** —— 考试机可能没有外网，
    考试时去拉外部资源本来也不该发生。"""
    assert images.as_png("http://example.com/a.jpg") is None
    assert images.as_png("/uploads/../../etc/passwd") is None
    assert images.as_png("") is None


def test_a_broken_image_does_not_break_the_export(tmp_path, monkeypatch):
    """图坏了顶多是这道题没图，不能让整场考试导不出来。"""
    from app.config import settings
    root = tmp_path / "uploads"
    (root / "images").mkdir(parents=True)
    (root / "images" / "坏的.jpg").write_bytes("这不是图片".encode("utf-8"))
    monkeypatch.setattr(settings, "upload_dir", str(root))
    assert images.as_png("/uploads/images/坏的.jpg") is None


# ================================================================ 进包 + 显示
def test_the_package_carries_the_picture(server, exam_with_picture, lab):
    from client import api
    raw = api.fetch_exam(server, exam_with_picture["exam"]["token"],
                         lab["out"] / "卷.ekb").read_bytes()
    names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
    assert any(n.startswith("images/") and n.endswith(".png") for n in names), names


def test_the_client_lays_the_picture_out(server, exam_with_picture, lab):
    from client import api
    pack = package.ExamPackage(api.fetch_exam(server, exam_with_picture["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    pics = pack.deploy_images(lab["out"] / "配图")
    assert pics, "配图没摊出来，界面上拿不到文件"
    for name, path in pics.items():
        assert path.exists() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    marked = [q for q in pack.paper if q.get("image")]
    assert marked, "题目上没标是哪张图，界面不知道该贴哪一张"
    assert marked[0]["image"] in pics
