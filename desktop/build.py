# -*- coding: utf-8 -*-
r"""打包学生端 exe。

    python build.py                 用当前 Python 打
    python build.py --python 路径   指定用哪个 Python 打（决定能跑在哪些系统）
    python build.py --onedir        打成文件夹（调试用，启动快一点）

产物在「发布」文件夹里，**整个文件夹拷到机房机器上，双击就能考**。

## 能跑在哪，由打包用的 Python 版本决定

PyInstaller 打出来的 exe 带着**打包时那个 Python 的运行时**，所以目标系统的
下限就是那个 Python 的下限：

    打包用的 Python      exe 能跑在
    ------------------   -----------------------------
    3.8（最后一个支持 Win7 的）   Win7 SP1 / 8 / 8.1 / 10 / 11   ← 要覆盖 Win7 用这个
    3.9 ~ 3.12                    Win8.1 / 10 / 11
    3.13+                         Win10 / 11

**换目标系统不用改一行代码**，换个 Python 重跑这个脚本就行。

要覆盖 Win7 就装一个 Python 3.8.10（最后一个带 Windows 安装包的 3.8），
**挑 32 位那版**：32 位 exe 在 32 位和 64 位 Windows 上都能跑，机房里总有几台
老机器是 32 位的。装完：

    D:\Python38-32\python.exe -m pip install pyinstaller==5.13.2
    python build.py --python D:\Python38-32\python.exe

（PyInstaller 6.x 要 Python 3.8+ 但已经不再测 Win7，5.13.2 是稳妥的那一版。）

## Win7 上还要注意

· 得打上 SP1 和 KB2999226（通用 C 运行库）。没打的话 exe 双击没反应、也不报错。
  大多数装过更新的机器已经有了。
· 杀毒软件容易把没签名的单文件 exe 拦下来。机房里先加白名单，或者用 --onedir。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "发布"
NAME = "考试客户端"
ENTRY = HERE / "exam_client.py"

# 只排除**第三方**重家伙：打包用的 Python 里装着后端那套依赖，PyInstaller 会
# 顺着依赖把它们拖进来，体积能差好几倍。
#
# **标准库一个都别排。** 排过 email，结果 exe 一开就死在
# `urllib.request` 里的 `import email` —— urllib 要用它组装 HTTP 头。
# 省那几百 KB 换来"学生机上打不开"，不划算；标准库之间的隐式依赖也不是
# 肉眼能数清的。
EXCLUDE = ["numpy", "pandas", "matplotlib", "PIL", "pytest", "setuptools",
           "sqlalchemy", "fastapi", "pydantic", "uvicorn", "alembic"]


def floor_of(version) -> str:
    major, minor = version[0], version[1]
    if (major, minor) <= (3, 8):
        return "Win7 SP1 及以上（含 Win7 / 8 / 8.1 / 10 / 11）"
    if (major, minor) <= (3, 12):
        return "Win8.1 及以上（Win7 跑不了，见 build.py 开头的说明）"
    return "Win10 及以上（Win7 / 8 跑不了）"


def python_info(exe: str) -> tuple:
    out = subprocess.run(
        [exe, "-c", "import sys,struct;print(sys.version_info[0],sys.version_info[1],"
                    "struct.calcsize('P')*8)"],
        capture_output=True, text=True, check=True).stdout.split()
    return int(out[0]), int(out[1]), int(out[2])


def clear_dist():
    """清「发布」，但**别碰「答案包」**。

    学生端默认把 .ans 写在 发布\\答案包 里。谁在收完卷之后顺手重打一次包，
    整个班的卷子就没了 —— 重打 exe 是开发动作，不该有删数据的副作用。
    """
    if not DIST.exists():
        return
    for item in DIST.iterdir():
        if item.name == "答案包":
            continue
        shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink()


def selftest_passes(exe: Path) -> bool:
    """让打出来的 exe 自己跑一遍自检，**过不了就不算打包成功**。

    不能只看"双击之后进程还在"：`--windowed` 的 exe 崩了也会弹一个报错窗，
    从外面看和正常启动一模一样。踩过一次 —— 排除了标准库的 email，exe 一开就
    死在 urllib 里，而"启动检查"显示一切正常，因为它看到的是那个报错弹窗。

    所以验收要**程序自己报告**：退出码 0，外加一份写下来的结果。
    """
    report = Path(tempfile.gettempdir()) / "考试客户端-自检.txt"
    report.unlink(missing_ok=True)
    try:
        # **别接它的 stdout/stderr。** onefile 的 exe 会再开一个子进程干活，
        # 管道握在孙子手里；超时杀掉儿子之后 run() 还要等管道关闭，于是
        # 永远等下去 —— 偏偏就挂在它本来要拦的那种失败上。实测卡过。
        done = subprocess.run([str(exe), "--selftest", str(report)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=120)
        code = done.returncode
    except subprocess.TimeoutExpired:
        # 崩在 import 阶段时，PyInstaller 会弹个报错窗停在那儿等人点，程序不退出
        code = -1
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    if code == 0 and "自检通过" in text:
        for line in text.splitlines():
            print("   " + line if line else "")
        return True

    print("\n打包出来的 exe 跑不起来，这一版不能发。")
    if text:
        print(text)
    elif code == -1:
        print("它卡在那儿没退出 —— 多半是一启动就崩，弹了个报错窗在等人点。"
              "双击它看看窗口里写的是什么。")
    else:
        print(f"退出码 {code}，自检报告也没写出来。")
    print("\n最常见的原因是 EXCLUDE 排掉了不该排的模块（标准库一个都别排）。")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="打包学生端 exe")
    ap.add_argument("--python", default=sys.executable,
                    help="用哪个 Python 打包（决定 exe 能跑在哪些系统）")
    ap.add_argument("--onedir", action="store_true",
                    help="打成文件夹而不是单文件：启动快、杀软少误报，但要整个文件夹一起拷")
    args = ap.parse_args()

    py = args.python
    major, minor, bits = python_info(py)
    print(f"① 用 Python {major}.{minor}（{bits} 位）打包")
    print(f"   打出来的 exe 能跑在：{floor_of((major, minor))}")
    if (major, minor) > (3, 8):
        print("   ⚠ 要覆盖 Win7，得用 Python 3.8 重打一次，见 build.py 开头")
    if bits == 64:
        print("   提示：32 位的 Python 打出来的 exe 在 32 位和 64 位 Windows 上都能跑")

    have = subprocess.run([py, "-c", "import PyInstaller"], capture_output=True)
    if have.returncode != 0:
        print(f"\n这个 Python 里没有 PyInstaller，先装一个：\n    {py} -m pip install pyinstaller")
        return 1

    print("② 打包（第一次会慢一点）")
    # 把构建时间写进去，登录页会显示 —— 机房里"修好的问题怎么还在"，
    # 十有八九是跑了旧 exe，有这个戳一眼就能对上
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    (HERE / "client" / "_build.py").write_text(
        "# -*- coding: utf-8 -*-\n"
        '"""打包时自动生成，不要手改。"""\n'
        f'BUILT_AT = "{stamp}"\n', encoding="utf-8")
    clear_dist()
    cmd = [py, "-m", "PyInstaller", "--clean", "--noconfirm",
           "--onedir" if args.onedir else "--onefile",
           "--windowed",                     # 考试程序不要黑框
           "--name", NAME,
           "--distpath", str(DIST),
           "--workpath", str(HERE / "build"),
           "--specpath", str(HERE / "build"),
           "--paths", str(HERE)]
    for mod in EXCLUDE:
        cmd += ["--exclude-module", mod]
    cmd.append(str(ENTRY))
    if subprocess.run(cmd).returncode != 0:
        return 1

    exe = DIST / (f"{NAME}.exe" if not args.onedir else f"{NAME}/{NAME}.exe")
    (DIST / "考场使用说明.txt").write_text(READ_ME, encoding="gbk", errors="replace")

    print("③ 验收：让打出来的 exe 自己跑一遍自检")
    if not selftest_passes(exe):
        return 1

    size = exe.stat().st_size / 1024 / 1024
    print(f"\n完成：{exe}（{size:.1f} MB）")
    print(f"把整个「{DIST.name}」文件夹拷到机房机器上，双击 {NAME}.exe 即可。")
    print(f"目标系统：{floor_of((major, minor))}")
    print(f"构建标记：{stamp}（登录页左下角会显示，用来分辨机房里跑的是哪一版）")
    return 0


READ_ME = """信息技术考试客户端 —— 考场使用说明

一、装机（只做一次）
  1. 把这个文件夹整个拷到一台考试机器上。
  2. 双击「考试客户端.exe」，在「教师端地址」里填上教师机的地址
     （形如 192.168.1.8:8000，问网管或信息技术老师）。
     填完看下面那行字：显示「已连上教师端」才算通。
  3. 连通之后地址就记在同目录的「客户端设置.json」里了。
     **把整个文件夹 ghost 或拷到全机房**，其他机器就不用再输地址。

二、考前（监考老师）
  1. 确认每台机器都能连上教师端（开程序看那行提示）。
     想批量查，在命令行里跑（不开窗口，结果写进文件）：
         考试客户端.exe --selftest 检查结果.txt --server 192.168.1.8:8000
  2. 提醒学生：考试文件夹是 C:\\EXAM，考试开始时会自动清空重建。
     开考前不要往里面放东西。
  3. 题目不用发：学生登录后，系统会自动把老师在网页后台发布的考试取下来。

三、学生
  1. 双击「考试客户端.exe」。
  2. 输入考号和姓名，点「登录」。
  3. 屏幕上列出今天能考的考试，点「开始考试」。
  4. 客观题直接在窗口里作答；操作题点「打开」按钮，
     在真实的资源管理器 / 记事本 / WPS 里按题目要求操作。
  5. 做完点右上角「交卷」。时间到会自动交卷。

四、考后
  · 交卷时答卷已经传回教师端了，老师直接在网页的成绩页看，操作题系统自动判分。
  · 机器上「答案包」文件夹里那份是备份，正常情况下不用收。

五、意外情况
  · 断电或程序被关掉：重开程序，输同样的考号，会问「要不要接着考」。
  · 提示「上传失败」：卷子已经存在本机了，不会丢。点交卷页上的「重新上传」；
    还不行就先放着，网通了重开程序，登录页上会有「补传」按钮。
  · 连不上教师端：先查网线和教师机。实在不通，让老师从网页后台导出考试包
    （.ekb）拷过来，在登录页点「没有网络？用本地考试包开考」，考完收「答案包」
    文件夹里的 .ans 文件。
  · 打不开程序：Win7 机器要先打 SP1 和 KB2999226 补丁。
"""


if __name__ == "__main__":
    sys.exit(main())
