# -*- coding: utf-8 -*-
"""考试包和答案包的读写。

## 考试包 .ekb（就是个 zip，改了扩展名，解压能看）

    manifest.json   考试名、时长、题数、满分、服务器地址、口令、路径前缀、名单
    paper.json      题目：题干、选项、分值、大题；**没有答案、没有检查点**
    files/          操作题的初始文件，开考时铺到考试文件夹
    images/         题目配图（PNG）。服务器那边已经从 jpg 转好了 ——
                    Tkinter 只认 PNG，不转的话带图题在学生机上就是没有图

包**由服务器生产**（backend/app/routers/desk.py 的 build_package），客户端只读。
这样"答案不出后端"这条规矩只需要在一个地方守住。

## 答案包 <学号>-<姓名>.ans（也是 zip）

    answer.json     客观题作答、每道操作题的终态、考试口令、考生信息、时间
    snapshot.json   整个考试文件夹的快照，存档用（老师要核学生动了什么文件）

联网时答卷已经直传教师端了，本地这份是**保命用的备份**：断网、服务器没开、
交卷那一下网线被踢掉，卷子还在硬盘上，补传或者收 U 盘都行。

## 客户端为什么不判分

exe 能被反编译，zip 能被解开。判分规则只要不在学生机上，学生能拿到的最多是题目
本身 —— 那本来就印在卷子上。分数在教师端算，这是根本的那道防线。
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path

FORMAT = 1
EXAM_EXT = ".ekb"
ANS_EXT = ".ans"


def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


class ExamPackage:
    """打开考试包。只读。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as z:
            self.manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            raw = z.read("paper.json")
            self.paper: list[dict] = json.loads(raw.decode("utf-8"))
        want = self.manifest.get("paper_sha")
        # 只是挡一下"手工改了包里的题目"，不是加密 —— 真要防篡改得签名，
        # 而那也防不住能改 exe 的人。分数在教师端算才是根本的防线。
        self.tampered = bool(want) and want != _digest(raw)

    @property
    def title(self) -> str:
        return self.manifest.get("title", "考试")

    @property
    def duration_min(self) -> int:
        return int(self.manifest.get("duration_min") or 0)

    @property
    def early_submit(self) -> bool:
        """老师开了「允许提前交卷」：交卷不设一半门槛。旧考试包没有这一项，照旧拦。"""
        return bool(self.manifest.get("early_submit"))

    @property
    def shuffle(self) -> bool:
        """老师开了「选择判断题乱序」：按「考试 + 学号」在本机打乱（client/shuffle.py）。
        旧考试包没有这一项，按原顺序考。"""
        return bool(self.manifest.get("shuffle"))

    @property
    def exam_id(self) -> str:
        return str(self.manifest.get("exam_id") or self.path.stem)

    @property
    def server(self) -> str:
        """交卷要连的教师端地址。空 = 离线包，只能交到本机。"""
        return str(self.manifest.get("server") or "").rstrip("/")

    @property
    def token(self) -> str:
        """这场考试的口令，和网页版学生链接里的是同一个。"""
        return str(self.manifest.get("token") or "")

    @property
    def logical_root(self) -> str:
        """交卷前要给快照路径加的前缀。少了它操作题全班判 0 分。"""
        return str(self.manifest.get("logical_root") or "")

    def roster(self) -> list[dict]:
        """名单。联网开考时用不上（服务器已经认过人了），离线包才靠它核对。"""
        return self.manifest.get("roster") or []

    def deploy_images(self, dest: Path) -> dict:
        """把配图摊到一个临时目录，返回 {包里的文件名: 本地路径}。

        Tkinter 的 PhotoImage 要么读文件、要么读 base64，**不能直接读 zip 里的
        字节**，所以得先落地。放临时目录而不是考试文件夹：配图不是考场素材，
        混进去会被学生当成题目文件，也会被快照拍进去。
        """
        dest = Path(dest)
        out: dict[str, Path] = {}
        with zipfile.ZipFile(self.path) as z:
            for name in z.namelist():
                if not name.startswith("images/") or name.endswith("/"):
                    continue
                rel = name[len("images/"):]
                target = dest / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                out[rel] = target
        return out

    def deploy_files(self, dest: Path) -> int:
        """把 files/ 里的初始文件铺到考试文件夹。返回铺了几个文件。"""
        dest = Path(dest)
        n = 0
        with zipfile.ZipFile(self.path) as z:
            for name in z.namelist():
                if not name.startswith("files/"):
                    continue
                rel = name[len("files/"):]
                if not rel:
                    continue
                target = dest / rel
                if name.endswith("/"):
                    # **空文件夹也要铺**：「在『会徽』文件夹中新建……」这类题，
                    # 会徽本身就是空的，漏了它学生打开就找不到地方
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
                n += 1
        return n


def write_answer(out: Path, pack: "ExamPackage", student: dict, answers: dict,
                 snapshot: dict, started: str, client: str,
                 states: dict | None = None) -> Path:
    """写本机那份备份。

    **每道操作题的终态和考试口令一并写进去**：补传的时候程序早重开过了，考试
    文件夹多半也被下一场清掉了，手上只剩这一个 .ans —— 不把终态存进来就没法
    重新组装答卷。第一版只存了题号，结果"重开程序补传"这条路根本走不通。

    snapshot 是整个考试文件夹的快照，**只作存档**：老师想核学生到底动了什么
    文件时看它，不参与判分（判分看的是 states 里那几份）。
    """
    out = Path(out).with_suffix(ANS_EXT)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "format": FORMAT,
        "exam_id": pack.exam_id,
        "title": pack.title,
        "token": pack.token,
        "logical_root": pack.logical_root,
        "states": dict(states or {}),
        "student": student,
        "answers": answers,
        "started": started,
        "submitted": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "client": client,
    }
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("answer.json", _dump(body))
        z.writestr("snapshot.json", _dump(snapshot))
    return out


def read_answer(path: Path) -> tuple[dict, dict]:
    """返回 (answer.json, snapshot.json)。补传时靠它把作答读回来 ——
    所以考完很久、程序重开过，照样补得上。"""
    with zipfile.ZipFile(path) as z:
        answer = json.loads(z.read("answer.json").decode("utf-8"))
        try:
            shot = json.loads(z.read("snapshot.json").decode("utf-8"))
        except KeyError:
            shot = {}
    return answer, shot
