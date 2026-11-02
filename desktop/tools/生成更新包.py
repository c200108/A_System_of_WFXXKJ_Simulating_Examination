# -*- coding: utf-8 -*-
r"""把「发布」里打好的 exe 做成「检查更新」用的更新包：改好名的 exe + update.json。

    python tools\生成更新包.py 4.12.0                      按本仓库认渠道（联网版 online / 机房版 lan）
    python tools\生成更新包.py 4.12.0 --渠道 lan
    python tools\生成更新包.py 4.12.0 --搬到 http://update.新域名.cn/api/client/update.json

产物在 `desktop\更新包\<渠道>\`，整个目录原样传到服务器的
`<部署目录>/data/client-updates/<渠道>/` 就生效（不用重启后端）：

    scp desktop\更新包\online\*.exe 用户@服务器:/opt/exam-system/data/client-updates/online/
    scp desktop\更新包\online\update.json 用户@服务器:/opt/exam-system/data/client-updates/online/

## update.json 长什么样

    {"version": "4.12.0", "notes": "……", "published_at": "2026-11-02 10:00",
     "assets": {"win32-runtime": {"url": "exam-client-4.12.0-win32-runtime.exe",
                                  "size": 8866572, "sha256": "…"}, …}}

url 写裸文件名，后端返回时改成下载接口的地址（routers/client_update.py）。

## 为什么要核对 exe 里的版本号

清单说 4.12.0、exe 里烤的却是 4.11.1 的话，学生端升级完再查一次，又觉得自己旧了，
**永远升级不完**。所以每个 exe 都跑一遍 `--selftest`，读它报告里的版本号对一遍，
对不上就不生成。（`--不核对` 跳过，只在你确定的时候用。）

`--搬到`：换服务器时用。清单里多写一个 moved_to，学生端读到就转去新地址查，
流程见 desktop/README.md「换服务器」。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # desktop/
sys.path.insert(0, str(HERE))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_exe(out: Path, prefix: str) -> Path | None:
    """「发布」里这个变体的 exe。发版.py 的前缀带 `@`（联网版文件名后面跟地址），
    机房版不烤地址、文件名里没有 `@`，两种都认。"""
    base = prefix.rstrip("@")
    hits = [p for p in out.glob("*.exe")
            if p.stem == base or p.stem.startswith(base + "@")]
    if len(hits) > 1:
        raise SystemExit(f"「{out}」里「{base}」开头的 exe 有 {len(hits)} 个，留一个再来："
                         + "、".join(p.name for p in hits))
    return hits[0] if hits else None


def baked_version(exe: Path) -> str:
    """跑一遍 exe 的自检，从报告里读「版本：x.y.z」。"""
    report = Path(tempfile.gettempdir()) / f"更新包核对-{exe.stem}.txt"
    if report.exists():
        report.unlink()
    subprocess.run([str(exe), "--selftest", str(report)], timeout=180,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    text = report.read_text(encoding="gbk", errors="replace") if report.exists() else ""
    hit = re.search(r"版本：(\d+(?:\.\d+)*)", text)
    return hit.group(1) if hit else ""


def notes_of(version: str) -> str:
    """更新日志里这一版的条目，拼成提示框里那段话。"""
    fabu = _load("fabu", HERE / "发版.py")
    try:
        _, items = fabu.entries(version)
    except SystemExit:
        return ""
    lines = []
    for kind, word in fabu.KINDS.items():
        lines += [f"【{word}】{text}" for k, text in items if k == kind]
    return "\n".join(lines)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    build = _load("build", HERE / "build.py")
    ap = argparse.ArgumentParser(description="生成「检查更新」用的更新包")
    ap.add_argument("version", help="学生端版本号，如 4.12.0；要和 exe 里烤的一致")
    ap.add_argument("--渠道", dest="channel", choices=("online", "lan"),
                    default=build.update_channel(), help="默认按本仓库认")
    ap.add_argument("--发布目录", dest="src", default=str(HERE / "发布"))
    ap.add_argument("--输出", dest="out", default="", help=r"默认 desktop\更新包\<渠道>")
    ap.add_argument("--说明", dest="notes", default="",
                    help="提示框里显示的更新说明；不给就取 changelog_seed.py 里这一版的条目")
    ap.add_argument("--搬到", dest="moved_to", default="",
                    help="换服务器：新清单的完整地址，写进 moved_to")
    ap.add_argument("--不核对", dest="no_check", action="store_true",
                    help="不跑 exe 自检核对版本号")
    args = ap.parse_args()

    version = args.version.strip().lstrip("vV")
    src = Path(args.src)
    out = Path(args.out) if args.out else HERE / "更新包" / args.channel
    fabu = _load("fabu", HERE / "发版.py")

    picked = []
    for prefix, suffix, label in fabu.VARIANTS:
        exe = find_exe(src, prefix)
        if exe is None:
            print(f"   没有 {suffix}（{label}），跳过")
            continue
        if not args.no_check:
            got = baked_version(exe)
            if got != version:
                raise SystemExit(f"{exe.name} 里烤的版本是「{got or '认不出'}」，不是 {version}。"
                                 f"\n先用 build.py --version {version} 重打，或者换个版本号。")
        picked.append((exe, suffix))
    if not picked:
        raise SystemExit(f"「{src}」里一个能用的 exe 都没有")

    notes = args.notes or notes_of(version)
    if not notes:
        print(f"   ※ changelog_seed.py 里没有 {version} 的条目，提示框里不会有更新说明（可用 --说明 补）")

    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("exam-client-*.exe"):        # 只留这一版，服务器上不攒旧包
        old.unlink()
    assets = {}
    for exe, suffix in picked:
        name = f"exam-client-{version}-{suffix}.exe"
        shutil.copy2(exe, out / name)
        assets[suffix] = {"url": name, "size": (out / name).stat().st_size,
                          "sha256": sha256(out / name)}
        print(f"   {exe.name}  →  {name}")
    data = {"version": version, "notes": notes,
            "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"), "assets": assets}
    if args.moved_to:
        data["moved_to"] = args.moved_to.strip()
    (out / "update.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print(f"\n更新包：{out}（{len(assets)} 个 exe + update.json，渠道 {args.channel}）")
    dest = f"用户@服务器:<部署目录>/data/client-updates/{args.channel}/"
    print("传到服务器（先传 exe，最后传清单）：")
    print(f'    scp "{out}\\*.exe" {dest}')
    print(f'    scp "{out}\\update.json" {dest}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
