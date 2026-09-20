# -*- coding: utf-8 -*-
r"""打包学生端 exe。

    python build.py                 用当前 Python 打
    python build.py --python 路径   指定用哪个 Python 打（决定能跑在哪些系统）
    python build.py --onedir        打成文件夹（调试用，启动快一点）

产物在「发布」文件夹里。**只需要把 exe 一个文件拷到学生机**：运行数据写在
`%LOCALAPPDATA%\信息技术考试客户端\`，exe 旁边不会生成任何东西。

教师端地址三种带法，任选一种：

    python build.py --server 192.168.1.8:8080   烤进 exe，学生双击就能用
    把 exe 改名成 考试客户端@192.168.1.8_8080.exe（换 IP 不用重新打包）
    学生在登录页输一次，这台机器记住

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


def exe_name(server: str) -> str:
    r"""打出来的 exe 叫什么。

    **地址写进文件名**，这样机房里拿到的那一个文件自己说明自己连哪儿，而且
    教师端换了 IP 时网管改个名就完事，不用重新打包。冒号在 Windows 文件名里
    非法，端口前改用下划线：`考试客户端@192.168.1.8_8080.exe`。

    读回来的是 `client.shell.server_from_name()`，**两边的写法必须对得上** ——
    tests/test_single_exe.py 守着这条往返。带证书的域名（https://）和带路径的
    地址写进文件名再读回来会走样，那就干脆不写：地址已经烤在 _build.py 里，
    文件名只是个可选的覆盖手段。
    """
    host = str(server or "").strip().rstrip("/")
    if host.lower().startswith("http://"):
        host = host[len("http://"):]          # norm() 会把它加回去，丢了不影响
    if not host or "://" in host or "/" in host:
        return f"{NAME}.exe"
    return f"{NAME}@{host.replace(':', '_')}.exe"


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
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
            continue
        try:
            item.unlink()
        except PermissionError:
            # **上一版还开着**（自己在调试，或者杀软正在扫）。运行中的 exe 删不掉，
            # 但改得了名 —— 挪开就行，别让"忘了关窗口"把整次打包顶回去。
            # 挪开的那份等它不占着了，下次打包顺手就清掉。
            if item.name.endswith(".上一版"):
                continue
            try:
                item.replace(item.with_suffix(item.suffix + ".上一版"))
            except OSError:
                print(f"   {item.name} 删不掉也挪不开（还开着？），先关掉它再打包")
                raise


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
    # Windows 的控制台默认是 GBK，一个编不出来的字符就让整个打包崩在 print 上
    # （撞过：一个 ⚠ 把打包停在第一步）。**打包脚本不该因为一行提示语失败。**
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):                # 老 Python / 被重定向了
        pass

    ap = argparse.ArgumentParser(description="打包学生端 exe")
    ap.add_argument("--python", default=sys.executable,
                    help="用哪个 Python 打包（决定 exe 能跑在哪些系统）")
    ap.add_argument("--onedir", action="store_true",
                    help="打成文件夹而不是单文件：启动快、杀软少误报，但要整个文件夹一起拷")
    ap.add_argument("--server", default="",
                    help="把教师端地址烤进 exe，如 192.168.1.8:8080。"
                         "烤了之后机房只需要分发这一个 exe，学生双击就能用")
    args = ap.parse_args()

    py = args.python
    major, minor, bits = python_info(py)
    print(f"① 用 Python {major}.{minor}（{bits} 位）打包")
    print(f"   打出来的 exe 能跑在：{floor_of((major, minor))}")
    if (major, minor) > (3, 8):
        print("   注意：要覆盖 Win7，得用 Python 3.8 重打一次，见 build.py 开头")
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
    server = args.server.strip().rstrip("/")
    (HERE / "client" / "_build.py").write_text(
        "# -*- coding: utf-8 -*-\n"
        '"""打包时自动生成，不要手改。"""\n'
        f'BUILT_AT = "{stamp}"\n'
        f'SERVER = "{server}"\n', encoding="utf-8")
    if server:
        print(f"   教师端地址已烤进 exe：{server}（学生不用再输）")
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
    if server and not args.onedir:
        named = DIST / exe_name(server)
        if named.name != exe.name:
            exe.replace(named)
            exe = named
    (DIST / "考场使用说明.txt").write_text(READ_ME, encoding="gbk", errors="replace")

    print("③ 验收：让打出来的 exe 自己跑一遍自检")
    if not selftest_passes(exe):
        return 1

    size = exe.stat().st_size / 1024 / 1024
    print(f"\n完成：{exe}（{size:.1f} MB）")
    print(f"目标系统：{floor_of((major, minor))}")
    print(f"构建标记：{stamp}（登录页左下角会显示，用来分辨机房里跑的是哪一版）")
    if server:
        print(f"内置地址：{server}")
    else:
        print("提示：加 --server 192.168.1.8:8080 可以把地址烤进去，"
              "机房就只需要分发这一个 exe")
    print(f"\n**只需要发 {exe.name} 这一个文件**：单独拷到学生机即可，"
          "运行数据写在 %LOCALAPPDATA%，exe 旁边不生成任何东西。")
    return 0


READ_ME = """信息技术考试客户端 —— 考场使用说明

**只需要发「考试客户端.exe」这一个文件。** 拷到学生机任意位置（桌面就行），
双击即可，不用安装、不用管理员权限、exe 旁边不会生成任何文件。
设置和答案备份写在 %LOCALAPPDATA%\\信息技术考试客户端\\ 里。

一、教师端地址怎么来（三选一，装机时定好）
  1. 打包时已经烤进 exe —— 学生双击就能用，地址栏自动填好。
  2. 文件名里写地址 —— 把 exe 改名成
         考试客户端@192.168.1.8_8080.exe
     （冒号在文件名里非法，端口前用下划线）。教师端换了 IP 时改个名就行，
     不用重新打包。
  3. 学生在登录页输一次 —— 这台机器会记住，以后开机直接连。

二、考前（监考老师）
  1. 开一台机器试一下：看登录页下方是否显示「已连上教师端」。
  2. 想批量查，在命令行里跑（不开窗口，结果写进文件）：
         考试客户端.exe --selftest 检查结果.txt --server 192.168.1.8:8080
  3. 提醒学生：考试文件夹是 C:\\EXAM，考试开始时会自动清空重建。
     开考前不要往里面放东西。
  4. 题目不用发：学生登录后自动获取老师在网页后台发布的考试。

三、学生
  1. 双击「考试客户端.exe」。
  2. 输入学号和密码（初始密码就是学号），点「登录」。
  3. 左侧菜单：首页、考试、打字练习。在「考试」里点「开始考试」。
  4. 客观题在窗口里作答；操作题点「打开」按钮，
     在真实的资源管理器 / 记事本 / WPS 里按题目要求操作。
  5. 做完点右上角「交卷」。时间到会自动交卷。

四、考后
  · 交卷时答卷已经传回教师端，老师在网页成绩页查看，操作题自动判分。
  · 考试文件夹会自动清空，可直接交给下一位考生。
  · 本机备份（.ans）和考试记录在
        %LOCALAPPDATA%\\信息技术考试客户端\\答案包\\
    正常情况下不用收。

五、意外情况
  · 断电或程序被关掉：重开程序，用同样的学号登录，会问「要不要接着考」。
  · 提示「上传失败」：卷子已经存在本机，不会丢。点交卷页的「重新上传」；
    还不行就先放着，网通了重开程序，登录页上会有「补传」按钮。
  · 连不上教师端：先查网线和教师机。实在不通，让老师从网页后台导出考试包
    （.ekb）拷过来，在登录页点「没有网络？用本地考试包开考」，
    考完到上面那个答案包目录收 .ans 文件。
  · 打不开程序：Win7 机器要先打 SP1 和 KB2999226 补丁。
  · 不确定机器上跑的是哪一版：看登录页左下角的构建时间。
"""


if __name__ == "__main__":
    sys.exit(main())
