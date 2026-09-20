# -*- coding: utf-8 -*-
r"""学生端考试程序 —— 打包成 exe 的就是这个。

    考试客户端.exe                        正常开考
    考试客户端.exe --server 10.0.0.8:8000 指定教师端地址（第一次用，或教师机换了 IP）
    考试客户端.exe --root D:\KSWJJ        换考试文件夹
    考试客户端.exe --out \\服务器\收卷    本机备份直接写到共享目录

默认：考试文件夹 C:\EXAM，本机备份和设置写到
`%LOCALAPPDATA%\信息技术考试客户端\`，**exe 旁边不生成任何文件**。

机房里只需要分发这一个 exe。教师端地址有三种带法，任选：

  · 打包时烤进去      python build.py --server 192.168.1.8:8080
  · 写在 exe 文件名里  考试客户端@192.168.1.8_8080.exe
  · 学生在登录页输一次，之后这台机器记住
"""

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):                  # 直接跑脚本时也能找到 client 包
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from client.store import data_dir              # noqa: E402


def selftest(report: Path, server: str = "") -> int:
    """自检：**不开窗口**，把该导的都导一遍、该跑的跑一小段，然后退出。

    两个用处：

    · **打包验收**。`--windowed` 打出来的 exe 崩了也会弹一个窗，从外面看
      "进程还活着"和"程序跑起来了"长得一模一样 —— 踩过一次：排除了标准库的
      email，exe 一开就死在 urllib 里，而"启动检查"显示一切正常，因为它看到的
      是那个报错弹窗。所以验收必须是**程序自己报告**：退出码 0 + 一份写下来的
      结果。build.py 打完就跑这个，不过不了就不算打包成功。

    · **机房排障**。给上 --server，它会真去连一次教师端，把结果写进报告：

          考试客户端.exe --selftest 结果.txt --server 192.168.1.8:8000

      装机时挨台跑一遍，比一台台开窗口看那行小字快得多。
    """
    lines = []
    try:
        # ① 该导的模块一个不落（email 那次就是死在这一步）
        from client import api, package, snapshot, store, ui        # noqa: F401
        import tkinter, urllib.request, zipfile, json, hashlib      # noqa: F401
        lines.append("✓ 模块都导进来了")

        # ② 真建一次窗口再关掉：Tk 的运行时没打进去的话，这里会炸
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        lines.append("✓ Tkinter 能建窗口")

        # ③ 真发一次 HTTP：urllib 的依赖（email / http / ssl）缺一个都不行。
        #    连不上没关系 —— 要的是"能走到连不上"，而不是 ImportError
        api.ping("http://127.0.0.1:9")
        lines.append("✓ 网络那条路走得通")

        # ④ 拍一次真快照 + 写一次 zip：判分和存卷全靠这两样
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            box = Path(tmp) / "考场"
            (box / "子目录").mkdir(parents=True)
            (box / "子目录" / "a.txt").write_bytes("测试".encode("gbk"))
            shot = snapshot.snapshot(box)
            assert shot["fs"], "快照是空的"
            assert "a.txt" in str(shot["fs"]), "快照没看见文件"
            lines.append(f"✓ 快照能拍（{shot['meta']['count']} 个对象）")
            zipfile.ZipFile(Path(tmp) / "t.zip", "w").close()
            lines.append("✓ 能写压缩包")

        # ⑤ 这台机器会连哪儿。**装机时最常被问的就是这一句。**
        #    地址有三个来源（exe 文件名、本机记录、打包时烤进去的），机房里很容易
        #    对不上 —— 比如网管改了文件名，但这台机器上还留着上学期的记录。
        #    三个都写出来，谁盖住谁一目了然。
        from client.shell import baked_server, server_from_name
        from client.ui import default_server
        picked = server or default_server()
        lines.append("")
        lines.append(f"教师端地址：{api.norm(picked) if picked else '没有（学生要自己输）'}")
        lines.append(f"    文件名 {server_from_name() or '无'}"
                     f"　｜　本机记录 {store.remembered_server() or '无'}"
                     f"　｜　打包内置 {baked_server() or '无'}")

        lines.append("")
        lines.append("自检通过")
        code = 0

        # ⑤ 给了地址就真去连一次教师端。**连不上不算自检失败** ——
        #    打包好不好和机房网通不通是两回事，混在一起会让人误判。
        if server:
            if api.ping(server):
                lines.insert(-2, f"✓ 连得上教师端 {api.norm(server)}")
            else:
                lines.insert(-2, f"✗ 连不上教师端 {api.norm(server)}"
                                 "（地址写错了？教师机没开？防火墙？）")
    except Exception as exc:                            # noqa: BLE001
        import traceback
        lines.append("")
        lines.append(f"自检失败：{type(exc).__name__}: {exc}")
        lines.append(traceback.format_exc())
        code = 1

    text = "\n".join(lines)
    try:
        Path(report).write_text(text, encoding="utf-8")
    except OSError:
        pass
    # **别指望 stdout。** 打包成窗口程序（--windowed）之后 sys.stdout 是 None，
    # 一句 print 就抛 AttributeError，于是 PyInstaller 弹个报错窗停在那儿等人点，
    # 调它的脚本就一直挂着。结果写在文件里，退出码说明成败，这两样才靠得住。
    if sys.stdout is not None:
        try:
            print(text)
        except Exception:                               # noqa: BLE001
            pass
    return code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="信息技术考试客户端")
    ap.add_argument("--root", default=r"C:\EXAM", help=r"考试文件夹，默认 C:\EXAM")
    ap.add_argument("--out", default="",
                    help=r"本机备份写到哪，默认 %LOCALAPPDATA%\信息技术考试客户端\答案包")
    ap.add_argument("--server", default="", help="教师端地址，如 192.168.1.8:8000")
    ap.add_argument("--selftest", default="", metavar="结果文件",
                    help="自检：不开窗口，验一遍能不能跑，结果写到这个文件；"
                         "配合 --server 还会真连一次教师端（机房装机排障用）")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest(Path(args.selftest), args.server)

    # 界面在这儿才导：放在文件顶上的话，client.ui 一旦出问题，程序还没走到
    # 自检就崩了，弹个窗谁也看不懂。放这儿，--selftest 能把原因写成一句人话。
    from client.ui import ExamApp

    # **不往 exe 旁边写。** 写在那儿的话，"只发一个 exe"就不成立了 ——
    # 程序一跑就在 exe 边上长出「答案包」文件夹；exe 要是放在只读位置
    # （网络共享、被锁的桌面），还会直接写失败。
    out = Path(args.out) if args.out else data_dir() / "答案包"
    out.mkdir(parents=True, exist_ok=True)
    ExamApp(Path(args.root), out, args.server).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
