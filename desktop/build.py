# -*- coding: utf-8 -*-
r"""打包学生端 exe。

    python build.py                 用当前 Python 打
    python build.py --python 路径   指定用哪个 Python 打（决定能跑在哪些系统）
    python build.py --onedir        打成文件夹（调试用，启动快一点）
    python build.py --name-login    打「姓名登录版」：学生选班级、填中文姓名，初始密码 123456

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
import os
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
# 校徽图标，两枚（见 icon_for）。一枚都没有就用 PyInstaller 的默认图标，
# 不报错 —— 图标是锦上添花，不能因为它打不出包。怎么做见 图标/制作图标.py
ICONS = HERE / "图标"
# 运行时窗口图标读的是这个固定名字（client/shell.py 的 asset），打包前会把选中
# 的那枚改名复制成它，见 stage_icon
ICON_NAME = "考试客户端.ico"

# 只排除**第三方**重家伙：打包用的 Python 里装着后端那套依赖，PyInstaller 会
# 顺着依赖把它们拖进来，体积能差好几倍。
#
# **标准库一个都别排。** 排过 email，结果 exe 一开就死在
# `urllib.request` 里的 `import email` —— urllib 要用它组装 HTTP 头。
# 省那几百 KB 换来"学生机上打不开"，不划算；标准库之间的隐式依赖也不是
# 肉眼能数清的。
EXCLUDE = ["numpy", "pandas", "matplotlib", "PIL", "pytest", "setuptools",
           "sqlalchemy", "fastapi", "pydantic", "uvicorn", "alembic"]


def exe_name(server: str, mark: str = "") -> str:
    r"""打出来的 exe 叫什么：`考试客户端-32位@192.168.1.8_8080.exe`。

    两件事写在文件名里：

    · **位数**（mark）。机房里 32 位和 64 位两版并存，拿到文件的人得一眼看出
      该发哪个 —— 32 位那份两种机器都能跑，64 位那份只能跑 64 位 Windows。
    · **教师端地址**（@ 后面）。这样那一个文件自己说明自己连哪儿，而且教师端
      换了 IP 时网管改个名就完事，不用重新打包。冒号在 Windows 文件名里非法，
      端口前改用下划线。

    地址读回来的是 `client.shell.server_from_name()`，它只认 `@` **之后**那一段
    —— 所以位数标在 `@` 前面，两边才不会打架。**两边的写法必须对得上**，
    tests/test_single_exe.py 守着这条往返。

    带证书的域名（https://）和带路径的地址写进文件名再读回来会走样，那就干脆
    不写地址：地址已经烤在 _build.py 里，文件名只是个可选的覆盖手段。
    """
    host = str(server or "").strip().rstrip("/")
    if host.lower().startswith("http://"):
        host = host[len("http://"):]          # norm() 会把它加回去，丢了不影响
    if not host or "://" in host or "/" in host:
        return f"{NAME}{mark}.exe"
    return f"{NAME}{mark}@{host.replace(':', '_')}.exe"


def icon_for(bits: int) -> Path | None:
    """这一版 exe 用哪枚图标：**32 位用蓝红那枚，64 位用金红那枚。**

    两枚都是校徽：金红是学校自己做的那枚（金底红字，电路、芯片、二进制都在里面），
    蓝红是线描校徽外面套一圈深蓝电路环。长什么样、怎么做，见 图标/制作图标.py。

    **为什么按位数分**：机房里两版 exe 并存，位数虽然写在文件名里，可文件名是会
    被改的（教师端换了 IP，网管改个名就完事）—— 图标不会。拿到手一眼就知道是
    哪一份。发错的后果不对称：64 位那份在 32 位机器上双击根本不出来。

    少了哪一枚就用另一枚顶上，两枚都没有返回 None（用 PyInstaller 的默认图标）。
    """
    first = ICONS / ("考试客户端-蓝红.ico" if bits == 32 else ICON_NAME)
    second = ICONS / (ICON_NAME if bits == 32 else "考试客户端-蓝红.ico")
    for ico in (first, second):
        if ico.is_file():
            return ico
    return None


def stage_icon(icon: Path) -> Path:
    """把选中的那枚图标改名复制一份，再打进包里。

    exe 自己的图标（文件上、任务栏上那个）PyInstaller 认路径，叫什么都行；
    **窗口左上角那个**是运行时从附带文件里按固定名字读的（`asset("考试客户端.ico")`）。
    蓝红那枚在仓库里另有其名，原样打进去运行时就找不着，窗口会退回 Tk 那根羽毛。

    放在 build/图标 下：PyInstaller 的 `--clean` 只清 build/考试客户端，清不到这儿。
    """
    box = HERE / "build" / "图标"
    box.mkdir(parents=True, exist_ok=True)
    out = box / ICON_NAME
    shutil.copyfile(icon, out)
    return out


def ucrt_dir(bits: int) -> Path | None:
    r"""找一份**兼容 Win7 的通用 C 运行库**（UCRT）。

    ## 为什么非要换掉

    PyInstaller 会把打包机上的 `ucrtbase.dll` 和一堆 `api-ms-win-*.dll` 收进包里
    —— 打包机是 Win11，收进去的就是 **Win11 版的 ucrtbase**（10.0.26100）。
    那个版本要用 `api-ms-win-core-sysinfo-l1-2-0.dll` 这类**Win7 上根本不存在**
    的 api-set，而 PyInstaller 又没把它们收进来。于是学生机上：

        64 位 → 无法启动此程序，因为计算机中丢失 api-ms-win-core-sysinfo-l1-2-0.dll
        32 位 → Error loading Python DLL python38.dll，LoadLibrary: 找不到指定的程序

    更糟的是，这堆 DLL 跟在 exe 旁边，**优先级高于系统自己那份** —— 就算机器
    已经打过 KB2999226（装过 Python 3.7 的机器就有），也会被包里这份顶掉。

    ## 换成哪一份

    Windows SDK 里的 UCRT 重分发包（`Redist\ucrt\DLLs\x86|x64`，版本 10.0.10240），
    那正是 KB2999226 装进 Win7 的那一份：只依赖 Win7 有的 api-set，而它缺的那几个
    （file-l1-2-0、synch-l1-2-0 等）重分发包里自带存根。一共 1.9 MB。

    **换完在 Win7 到 Win11 上都能跑** —— 重分发包本来就是为"一份程序发到所有
    Windows"准备的。
    """
    arch = "x64" if bits == 64 else "x86"
    roots = [Path(r"C:\Program Files (x86)\Windows Kits\10\Redist"),
             Path(r"C:\Program Files\Windows Kits\10\Redist")]
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        found.append(root / "ucrt" / "DLLs" / arch)          # 老版 SDK 的摆法
        found += sorted(root.glob(f"*/ucrt/DLLs/{arch}"))    # 新版按 SDK 版本分目录
    for path in found:
        if (path / "ucrtbase.dll").is_file():
            return path
    return None


def write_spec(spec: Path, *, icon: Path | None, ucrt: Path | None,
               onefile: bool) -> Path:
    """写一份 .spec。**只有换运行库这件事非用 spec 不可** —— 命令行没法
    把 PyInstaller 已经收进去的 DLL 换掉，得在 Analysis 之后动 `a.binaries`。"""
    icon_line = f"icon=r'{icon}'," if icon else ""
    data_line = (f"datas=[(r'{icon}', '图标')]," if icon else "datas=[],")
    swap = f"""
# —— 把打包机（Win11）的 UCRT 换成 SDK 里那份兼容 Win7 的 ——
import os
UCRT = r'{ucrt}'
drop = {{n.lower() for n in os.listdir(UCRT)}}
keep = [b for b in a.binaries if os.path.basename(b[0]).lower() not in drop]
a.binaries = keep + [(n, os.path.join(UCRT, n), 'BINARY') for n in os.listdir(UCRT)]
""" if ucrt else ""
    body = f"""# -*- mode: python ; coding: utf-8 -*-
# 这个文件是 build.py 生成的，不要手改。

a = Analysis(
    [r'{ENTRY}'],
    pathex=[r'{HERE}'],
    binaries=[],
    {data_line}
    hiddenimports=[],
    excludes={EXCLUDE!r},
    noarchive=False,
)
{swap}
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='{NAME}',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    upx_exclude=[], runtime_tmpdir=None,
    console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None,
    entitlements_file=None,
    {icon_line}
)
"""
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(body, encoding="utf-8")
    return spec


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


def clear_dist(target: str = ""):
    """清「发布」，但有两样不碰。

    · **答案包**。学生端默认把 .ans 写在 发布\\答案包 里。谁在收完卷之后顺手
      重打一次包，整个班的卷子就没了 —— 重打 exe 是开发动作，不该删数据。
    · **别人的 exe**。32 位和 64 位两版要并存（见 exe_name），打 32 位那次
      不能把 64 位那份顺手删掉。只清这次要重写的那一个（target）。
    """
    if not DIST.exists():
        return
    for item in DIST.iterdir():
        if item.name == "答案包":
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
            continue
        if item.suffix.lower() == ".exe" and item.name != target:
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
    text = report.read_text(encoding="gbk", errors="replace") if report.exists() else ""
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
    ap.add_argument("--ucrt", action="store_true",
                    help="把兼容 Win7 的通用 C 运行库（UCRT）打进 exe。"
                         "学生机没打 KB2999226 补丁也能跑，文件名会多一个「内置运行库」")
    ap.add_argument("--server", default="",
                    help="把教师端地址烤进 exe，如 192.168.1.8:8080。"
                         "烤了之后机房只需要分发这一个 exe，学生双击就能用")
    ap.add_argument("--name-login", action="store_true",
                    help="打「姓名登录版」：登录页先选班级、账号填中文姓名，初始密码统一 123456"
                         "（重名的同学填学号）。文件名会多一个「姓名登录」，和普通版并存")
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
        f'SERVER = "{server}"\n'
        f'NAME_LOGIN = {bool(args.name_login)}\n', encoding="utf-8")
    if args.name_login:
        print("   姓名登录版：学生选班级、填中文姓名，初始密码 123456")
    if server:
        print(f"   教师端地址已烤进 exe：{server}（学生不用再输）")
    # 位数写进文件名：32 位那份两种机器都能跑，64 位那份只能跑 64 位 Windows，
    # 机房里两版并存时得一眼分得出来
    ucrt = ucrt_dir(bits) if args.ucrt else None
    if args.ucrt and not ucrt:
        print("\n找不到 Windows SDK 里的 UCRT 重分发包，没法换运行库。")
        print("装一个 Windows 10 SDK（只勾「Windows SDK for Desktop C++」即可），"
              "或者去掉 --ucrt 用原来的打法。")
        return 1
    mark = (("-姓名登录" if args.name_login else "") + f"-{bits}位"
            + ("-内置运行库" if ucrt else ""))
    final = exe_name(server, mark) if not args.onedir else ""
    clear_dist(final)

    icon = icon_for(bits)
    if icon:
        print(f"   图标：{icon.name}（{bits} 位这版用这枚）")
    else:
        print(f"   没有图标（{ICONS} 里一枚都没有），用 PyInstaller 的默认图标")
    if ucrt:
        n = len(list(ucrt.glob("*.dll")))
        print(f"   运行库：换成 SDK 重分发包里那份（{n} 个文件，兼容 Win7）")

    spec = write_spec(HERE / "build" / f"{NAME}.spec",
                      icon=stage_icon(icon) if icon else None,
                      ucrt=ucrt, onefile=not args.onedir)
    cmd = [py, "-m", "PyInstaller", "--clean", "--noconfirm",
           "--distpath", str(DIST),
           "--workpath", str(HERE / "build"),
           str(spec)]
    packed = subprocess.run(cmd).returncode == 0
    if args.name_login:
        # 打完就把开关拨回去：_build.py 留在源码里，不拨回去的话之后直接跑源码、
        # 跑测试、再打普通版之前，全都悄悄变成了姓名登录版
        built = HERE / "client" / "_build.py"
        built.write_text(built.read_text(encoding="utf-8").replace(
            "NAME_LOGIN = True", "NAME_LOGIN = False"), encoding="utf-8")
    if not packed:
        return 1
    # （exe 里那份 _build 是打包时冻进去的，拨回源码里这份不影响它）

    exe = DIST / (f"{NAME}.exe" if not args.onedir else f"{NAME}/{NAME}.exe")
    if final and final != exe.name:
        exe.replace(DIST / final)
        exe = DIST / final
    (DIST / "考场使用说明.txt").write_text(READ_ME, encoding="gbk", errors="replace")

    print("③ 验收：让打出来的 exe 自己跑一遍自检")
    if not selftest_passes(exe):
        return 1

    # ④ Win7 依赖检查。**自检过不了不算，自检在打包机上跑，机器什么都有** ——
    #    缺的那几个 api-set 只在 Win7 上才暴露出来，所以静态查一遍包里带没带全。
    audit = subprocess.run([py, str(HERE / "tools" / "查Win7依赖.py"), str(exe)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    print("④ Win7 依赖检查")
    for line in (audit.stdout or "").splitlines():
        print("   " + line if line else "")
    if audit.returncode != 0:
        if ucrt:
            print("换过运行库还缺东西，这一版不能发。")
            return 1
        print("   ——（没加 --ucrt。要发到 Win7 机房就加上它重打一次）")

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

    others = sorted(p.name for p in DIST.glob("*.exe") if p.name != exe.name)
    if others:
        print("「发布」里另外还有：" + "、".join(others)
              + "　（各打各的，重打一版不会删掉另一版）")
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
