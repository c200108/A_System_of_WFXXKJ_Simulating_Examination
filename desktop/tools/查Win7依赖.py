# -*- coding: utf-8 -*-
r"""查一个打包好的 exe 在 Win7 上会不会因为缺 DLL 起不来。

    python tools/查Win7依赖.py 发布\考试客户端-32位@1.2.3.4_80.exe

**为什么需要它**：这类毛病在开发机上一点痕迹都没有 —— Win10/11 什么都有，
exe 跑得好好的；拷到 Win7 上双击，弹一个「丢失 api-ms-win-core-xxx.dll」，
或者更难懂的「Error loading Python DLL，LoadLibrary: 找不到指定的程序」。

判据：把包里每个 DLL/PYD 的导入表摊开，凡是 `api-ms-win-*` 就看它**在不在
包里**。在包里的没问题（跟着 exe 一起解包出来，Win7 也能加载）；不在包里的，
Win7 系统里也没有（那套 api-set 是 Win8 才有的机制），就是起不来的原因。

顺带报一下 `ucrtbase.dll` 的版本：**10.0.10240 是 SDK 重分发包那份，兼容 Win7**；
10.0.2xxxx 是从打包机（Win10/11）的 System32 抄来的，在 Win7 上必崩。
"""

from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from pathlib import Path

import pefile
from PyInstaller.archive.readers import CArchiveReader

# Win7 SP1 自带的老 DLL，随便用
CLASSIC = {
    "kernel32.dll", "user32.dll", "gdi32.dll", "advapi32.dll", "shell32.dll",
    "ole32.dll", "oleaut32.dll", "comctl32.dll", "comdlg32.dll", "ws2_32.dll",
    "wsock32.dll", "crypt32.dll", "rpcrt4.dll", "shlwapi.dll", "version.dll",
    "winmm.dll", "imm32.dll", "msvcrt.dll", "netapi32.dll", "userenv.dll",
    "iphlpapi.dll", "psapi.dll", "bcrypt.dll", "ncrypt.dll", "secur32.dll",
    "wldap32.dll", "normaliz.dll", "dbghelp.dll", "uxtheme.dll", "usp10.dll",
    "gdiplus.dll", "mpr.dll", "setupapi.dll", "cfgmgr32.dll", "powrprof.dll",
    "winspool.drv", "dwmapi.dll", "wintrust.dll", "cabinet.dll", "wtsapi32.dll",
}


def unpack(exe: Path, out: Path) -> list[Path]:
    """把 onefile 的 exe 摊开。打成文件夹的（onedir）直接扫那个文件夹。"""
    if exe.is_dir():
        return [p for p in exe.rglob("*") if p.suffix.lower() in (".dll", ".pyd", ".exe")]
    arch = CArchiveReader(str(exe))
    got = []
    for name in arch.toc:
        if not name.lower().endswith((".dll", ".pyd")):
            continue
        data = arch.extract(name)
        raw = data[1] if isinstance(data, tuple) else data
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        got.append(target)
    return got


def version_of(path: Path) -> str:
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        for fi in getattr(pe, "FileInfo", [[]])[0]:
            if fi.Key.decode() == "StringFileInfo":
                for st in fi.StringTable:
                    return st.entries.get(b"FileVersion", b"").decode()
    except Exception:                                       # noqa: BLE001
        pass
    return ""


def imports_of(path: Path) -> set:
    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        return {e.dll.decode().lower() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])}
    except Exception:                                       # noqa: BLE001
        return set()


def audit(exe: Path) -> int:
    work = Path(tempfile.mkdtemp(prefix="win7dep-"))
    files = unpack(exe, work)
    if not files:
        print(f"{exe} 里一个 DLL 都没有？打包是不是没成？")
        return 1
    inside = {p.name.lower() for p in files}

    missing: dict = {}
    for p in files:
        for dep in imports_of(p):
            if dep in inside or dep in CLASSIC:
                continue
            if dep.startswith("api-ms-win-"):
                missing.setdefault(dep, []).append(p.name)

    ucrt = next((p for p in files if p.name.lower() == "ucrtbase.dll"), None)
    if ucrt:
        ver = version_of(ucrt)
        old = ver.startswith("10.0.10240")
        print(f"ucrtbase.dll：{ver}　{'← SDK 重分发包，兼容 Win7' if old else '← 打包机的 System32，**Win7 上会崩**'}")
    else:
        print("包里没有 ucrtbase.dll（用的是系统那份，机器得自己打过 KB2999226）")

    print(f"包里 {len(files)} 个 DLL/PYD")
    if missing:
        print(f"\n**Win7 上会缺 {len(missing)} 个 api-set**：")
        for dep, who in sorted(missing.items()):
            print(f"   {dep:46s} ← {', '.join(sorted(set(who))[:3])}")
        print("\n这些名字的 DLL 是 Win8 才引入的机制，Win7 系统里没有、包里也没带，"
              "双击就会弹「丢失 xxx.dll」。用 build.py --ucrt 重打一次。")
        return 1
    print("\nWin7 依赖检查通过：包里每个 api-set 都自带，没有缺的。")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(audit(Path(sys.argv[1])))
