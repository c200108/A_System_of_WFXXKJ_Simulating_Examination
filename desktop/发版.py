# -*- coding: utf-8 -*-
r"""学生端发版：打齐八个 exe，发到 GitHub Releases。

    python 发版.py 4.8.0 --同期 3.5.0 --机房版目录 ..\..\WFXXKJ考试平台-Win7版\发布
                                                  打包 + 发布（标签 v4.8.0 打在 HEAD 上）
    python 发版.py 4.8.0 --同期 3.5.0 --试算     只打印要发的说明和文件，不打包、不发布
    python 发版.py 4.8.0 --不打包                「发布」里已经是这一版的 exe，直接发
    python 发版.py 4.7.0 --提交 59bdac9 --发布目录 <那一版的 desktop\发布> --不打包

## 每一版发四个（再加姓名登录版四个）

| 文件 | 适用 |
|---|---|
| 32 位 · 内置运行库 | Win7 学生机发这个：32 / 64 位 Windows 都能跑，不用装补丁 |
| 64 位 · 内置运行库 | 64 位 Windows |
| 32 位 / 64 位 · 不含运行库 | Win8.1 以上，或装过 KB2999226 的 Win7 |

**文件名换成英文**：GitHub 会把附件名里的中文换成别的字符，「考试客户端-32位@…」
传上去就面目全非了。页面上显示的中文说明走附件的 label。文件名里也不带 `@地址` ——
exe 打包时已经把地址烤进去了（`--server`），改名只是换地址的另一条路，见 client/shell.py。

## 机房版也发在这儿

机房版仓库是私有的，它的学生端「检查更新」查的是**联网版这个公开仓库**的 Release。所以每次发版
把机房版打好的 exe 也带上：`--机房版目录 <机房版仓库>\发布`。附件名带 `exam-client-lan-` 前缀，
机房版学生端只认这一组，联网版只认不带前缀的（client/update.py）。版本号两版同一套。

发之前每个 exe 都跑一遍自检，核对烤进去的版本号（`--不核对` 跳过）。

## 说明从哪来

发布说明按 `backend/app/changelog_seed.py` 里这一版（和 `--同期` 的服务端版本）的条目
拼出来，再附上 `docs/更新日志/<版本>.md` 的链接。所以**先记好更新日志、提交推送，
再发版** —— 标签打在提交上，链接指向那个标签下的文档。

## 打包要两个 3.8

Win7 能跑的 exe 只能用 Python 3.8 打（3.9 起 python3X.dll 要 Win7 没有的组件）。
32 位、64 位各一个 3.8.10，都装了 PyInstaller 5.13.2。默认路径见 PY32 / PY64，
不在那儿就用 --py32 / --py64 指。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _find_py38(folder: str) -> str:
    """Python 3.8.10 装在哪。不写死用户名 —— 换台电脑、换个账号照样找得到。

    只给当前用户装的在 %LOCALAPPDATA%\\Programs\\Python，给所有用户装的在 Program Files。
    都找不到就返回第一个候选，打包时会报"找不到"，那时用 --py32 / --py64 指。
    """
    candidates = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / folder,
                  Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / folder,
                  Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / folder,
                  Path("C:/") / folder]
    for c in candidates:
        if (c / "python.exe").is_file():
            return str(c / "python.exe")
    return str(candidates[0] / "python.exe")


PY32 = _find_py38("Python38-32")
PY64 = _find_py38("Python38")
SERVER = "111.170.33.3:3315"

# (build.py 产物的文件名前缀, 附件名后缀, 页面上的说明)
VARIANTS = [
    ("考试客户端-32位-内置运行库@", "win32-runtime", "32 位 · 内置运行库（Win7 学生机发这个）"),
    ("考试客户端-64位-内置运行库@", "win64-runtime", "64 位 · 内置运行库"),
    ("考试客户端-32位@", "win32", "32 位 · 不含运行库（Win8.1+，或装过 KB2999226 的 Win7）"),
    ("考试客户端-64位@", "win64", "64 位 · 不含运行库（Win8.1+，或装过 KB2999226 的 Win7）"),
]
# 姓名登录版（build.py --name-login）：同样四个，先选班级、账号填中文姓名、初始密码 123456
VARIANTS += [("考试客户端-姓名登录-" + prefix.split("-", 1)[1], "name-login-" + suffix,
              "姓名登录版 · " + label) for prefix, suffix, label in VARIANTS]
LAN_PREFIX = "exam-client-lan-"    # 和 client/update.py 的 LAN_PREFIX 对得上
KINDS = {"Added": "新增", "Changed": "变更", "Fixed": "修复", "Removed": "移除",
         "Security": "安全", "Deprecated": "弃用"}


def run(*cmd, **kw) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True,
                          encoding="utf-8", **kw).stdout.strip()


def entries(version: str):
    sys.path.insert(0, str(ROOT / "backend"))
    from app.changelog_seed import VERSIONS
    for v, day, items in VERSIONS:
        if v == version:
            return day, items
    raise SystemExit(f"changelog_seed.py 里没有 {version} —— 先记更新日志再发版")


def section(version: str, title: str) -> list:
    day, items = entries(version)
    out = [f"## {title} {version}（{day:%Y-%m-%d}）", ""]
    for kind, word in KINDS.items():
        got = [text for k, text in items if k == kind]
        if got:
            out += [f"**{word}**", ""] + [f"- {t}" for t in got] + [""]
    return out


def notes(version: str, peers: list, repo_url: str, tag: str, commit: str,
          lan: list = ()) -> str:
    lines = section(version, "学生端")
    for peer in peers:
        lines += section(peer, "同期服务端")
        lines += ["> 服务器要一起升级：`git pull && sudo docker compose up -d --build`", ""]
    lines += ["## 下载哪一个", "", "| 文件 | 适用 |", "|---|---|"]
    for _, suffix, label in VARIANTS:
        lines.append(f"| `exam-client-{version}-{suffix}.exe` | {label} |")
    for suffix, label in lan:
        lines.append(f"| `{LAN_PREFIX}{version}-{suffix}.exe` | 机房版 · {label} |")
    lines += ["",
              f"exe 里内置的教师端地址是 `{SERVER}`。要连别的地址：把 exe 改名成 "
              "`考试客户端@IP_端口.exe`（端口前用下划线，如 `考试客户端@192.168.1.8_8080.exe`），"
              "或者学生在登录页填。", "",
              "**姓名登录版**（文件名带 name-login）：先选班级，账号填中文姓名，"
              "初始密码统一 `123456`；同一个班里重名的改填学号。"
              "和普通版连同一个教师端、同一批学生账号，改过的密码两版通用。", ""]
    if lan:
        lines += ["**机房版**（文件名带 `lan`）：不烤教师端地址，学生在登录页填一次机房教师机的地址。"
                  "机房版学生端「检查更新」只认带 `lan` 的这几个。", ""]
    doc = f"docs/更新日志/{version}.md"
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}:{doc}"]).returncode == 0:
        lines.append(f"详细说明（为什么这么改、怎么验证的）：[{doc}]({repo_url}/blob/{tag}/{doc})")
    return "\n".join(lines) + "\n"


def _load_tool():
    """tools/生成更新包.py：找 exe、核对烤进去的版本号，两边共用一份。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen", str(HERE / "tools" / "生成更新包.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _same_version(gen, exe: Path, version: str, skip: bool) -> None:
    """exe 里烤的版本号得和这次发的一致，不然学生端升级完再查，又觉得自己旧了。"""
    if skip:
        return
    got = gen.baked_version(exe)
    if got != version:
        raise SystemExit(f"{exe.name} 里烤的版本是「{got or '认不出'}」，不是 {version}，先重打")


def build(py32: str, py64: str, server: str, version: str) -> None:
    for py in (py32, py64):
        for extra in ([], ["--ucrt"], ["--name-login"], ["--name-login", "--ucrt"]):
            print(f"打包：{Path(py).parent.name} {' '.join(extra)}")
            subprocess.run([sys.executable, "build.py", "--python", py, "--server", server,
                            "--version", version, *extra],
                           cwd=HERE, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="学生端发版：打齐八个 exe，发到 GitHub Releases")
    ap.add_argument("version", help="学生端版本号，如 4.8.0")
    ap.add_argument("--同期", dest="peers", action="append", default=[],
                    help="同一次迭代的服务端版本号，可以给多个")
    ap.add_argument("--提交", dest="commit", default="HEAD", help="标签打在哪个提交上")
    ap.add_argument("--发布目录", dest="out", default=str(HERE / "发布"))
    ap.add_argument("--不打包", dest="skip_build", action="store_true")
    ap.add_argument("--试算", dest="dry", action="store_true")
    ap.add_argument("--不是最新", dest="not_latest", action="store_true",
                    help="补发老版本时用：不把它标成 Latest")
    ap.add_argument("--py32", default=PY32)
    ap.add_argument("--py64", default=PY64)
    ap.add_argument("--server", default=SERVER)
    ap.add_argument("--机房版目录", dest="lan", default="",
                    help=r"机房版打好的 exe 在哪（机房版仓库的 desktop\发布 或 发布）。"
                         "机房版没有自己的公开 Release，它的学生端去联网版这个 Release 里找更新")
    ap.add_argument("--不带机房版", dest="no_lan", action="store_true",
                    help="这一版不发机房版（机房版学生端查到这一版也会提示没有安装包）")
    ap.add_argument("--不核对", dest="no_check", action="store_true",
                    help="不跑 exe 自检核对烤进去的版本号")
    args = ap.parse_args()
    if not args.lan and not args.no_lan:
        raise SystemExit("机房版的 exe 也要发在这个 Release 里（机房版学生端在这儿找更新）："
                         r"加 --机房版目录 <机房版仓库>\发布；这一版确实不发机房版就加 --不带机房版")
    gen = _load_tool()

    tag = f"v{args.version}"
    commit = run("git", "-C", str(ROOT), "rev-parse", args.commit)
    repo_url = run("gh", "repo", "view", "--json", "url", "-q", ".url", cwd=ROOT)

    if not args.dry and not args.skip_build:
        if args.commit != "HEAD":
            raise SystemExit("打包用的是工作区里的源码，只能给 HEAD 打。老版本请在那个提交的 "
                             "worktree 里打好，再用 --发布目录 --不打包 发")
        build(args.py32, args.py64, args.server, args.version)

    out = Path(args.out)
    stage = Path(tempfile.mkdtemp(prefix="release-"))
    assets = []
    for prefix, suffix, label in VARIANTS:
        found = sorted(out.glob(f"{prefix}*.exe"))
        if len(found) != 1:
            raise SystemExit(f"「{out}」里「{prefix}*.exe」应该正好一个，找到 {len(found)} 个")
        _same_version(gen, found[0], args.version, args.no_check)
        target = stage / f"exam-client-{args.version}-{suffix}.exe"
        shutil.copy2(found[0], target)
        assets.append(f"{target}#{label}")
        print(f"   {found[0].name}  →  {target.name}")

    # 机房版：附件名带 exam-client-lan- 前缀，机房版学生端只认这一组（client/update.py）。
    # 机房版只打「内置运行库」那几个，没有的变体跳过
    lan = []
    if args.lan:
        for prefix, suffix, label in VARIANTS:
            exe = gen.find_exe(Path(args.lan), prefix)
            if exe is None:
                continue
            _same_version(gen, exe, args.version, args.no_check)
            target = stage / f"{LAN_PREFIX}{args.version}-{suffix}.exe"
            shutil.copy2(exe, target)
            assets.append(f"{target}#机房版 · {label}")
            lan.append((suffix, label))
            print(f"   机房版 {exe.name}  →  {target.name}")
        if not lan:
            raise SystemExit(f"「{args.lan}」里一个机房版 exe 都没找到")

    body = notes(args.version, args.peers, repo_url, tag, commit, lan)
    print(body)

    if args.dry:
        print("\n试算：没有打包，也没有发布。")
        return 0

    notes_file = stage / "notes.md"
    notes_file.write_text(body, encoding="utf-8")
    title = f"学生端 {args.version}" + "".join(f" · 服务端 {p}" for p in args.peers)
    cmd = ["gh", "release", "create", tag, *assets, "--target", commit,
           "--title", title, "--notes-file", str(notes_file)]
    cmd.append("--latest=false" if args.not_latest else "--latest")
    subprocess.run(cmd, cwd=ROOT, check=True)
    shutil.rmtree(stage, ignore_errors=True)
    print(f"\n已发布 {tag}：{repo_url}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
