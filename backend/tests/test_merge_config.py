"""还原备份时合并 config.yaml：旧的值全留着，新版本多出来的配置项补进去（2.12.1）。

tests/fixtures/config_2_8_backup.yaml 是 2.8.x 那一版的 config.yaml（早期备份里就是它），
校徽改成配过的样子 —— 和报上来的那份备份一致。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tools import merge_config as M

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
OLD = (HERE / "fixtures" / "config_2_8_backup.yaml").read_text(encoding="utf-8")
NEW = (BACKEND.parent / "config.yaml").read_text(encoding="utf-8")


def test_老备份补齐新版本的配置项():
    text, added = M.merge_text(OLD, NEW)
    assert "time" in added and "typing.require_roster" in added and "typing.min_done_ratio" in added
    got = yaml.safe_load(text)
    assert got["time"]["offset_hours"] == 0
    assert got["typing"]["submit_interval_sec"] == 60 and got["typing"]["require_roster"] is True
    assert "系统时间的校正" in text and "防刷" in text, "新配置项上面的说明一起抄过来"
    M.check(text)


def test_旧的值和写法一个不动():
    text, _ = M.merge_text(OLD, NEW)
    got = yaml.safe_load(text)
    assert got["site"]["favicon"] == "/uploads/校徽.png"
    assert got["paper"]["sections"] == yaml.safe_load(OLD)["paper"]["sections"], "卷面结构整个用备份的"
    assert 'label: "Windows 操作"' in text
    # 备份原有的每一行都还在，顺序不变
    old_lines = [ln for ln in OLD.splitlines()]
    it = iter(text.splitlines())
    assert all(any(ln == x for x in it) for ln in old_lines), "备份里的行要按原顺序都在"


def test_新配置项放在新版本里它前一项的后面():
    text = M.merge_text(OLD, NEW)[0]
    lines = text.splitlines()
    assert lines.index("time:") < lines.index("upload:"), "新版本里 time 在 upload 前面"
    assert lines.index("time:") > lines.index("import:")
    i = next(n for n, ln in enumerate(lines) if ln.startswith("  three_star_min_speed:"))
    assert lines[i + 2].startswith("  min_done_ratio:"), "跟在前一项后面（中间是它的说明）"


def test_合一次和合两次一样():
    once = M.merge_text(OLD, NEW)[0]
    twice, added = M.merge_text(once, NEW)
    assert added == [] and twice == once
    assert M.merge_text(NEW, NEW) == (NEW if NEW.endswith("\n") else NEW + "\n", [])


def test_缩进不一样的备份照样对齐():
    old = "exam:\n    pass_score: 70\n"
    new = "exam:\n  pass_score: 60\n  # 口令长度\n  token_length: 9\n"
    text, added = M.merge_text(old, new)
    assert added == ["exam.token_length"]
    assert "    # 口令长度\n    token_length: 9" in text
    assert yaml.safe_load(text) == {"exam": {"pass_score": 70, "token_length": 9}}


def test_备份里多出来的键留着():
    old = "exam:\n  pass_score: 70\n  whatever: 1\n"
    text, _ = M.merge_text(old, "exam:\n  pass_score: 60\n")
    assert yaml.safe_load(text)["exam"]["whatever"] == 1


def test_合出来通不过校验就不输出(tmp_path):
    bad = tmp_path / "old.yaml"
    bad.write_text(OLD.replace("pass_score: 60", 'pass_score: "六十"'), encoding="utf-8")
    out = tmp_path / "out.yaml"
    assert M.main([str(bad), str(BACKEND.parent / "config.yaml"), str(out)]) == 1
    assert not out.exists()


def test_命令行_写到输出文件(tmp_path):
    out = tmp_path / "merged.yaml"
    assert M.main([str(HERE / "fixtures" / "config_2_8_backup.yaml"),
                   str(BACKEND.parent / "config.yaml"), str(out)]) == 0
    assert yaml.safe_load(out.read_text(encoding="utf-8"))["time"] == {"offset_hours": 0}
    assert b"\r\n" not in out.read_bytes()


def test_命令行_旧的从标准输入读():
    got = subprocess.run([sys.executable, "-m", "tools.merge_config", "-", str(BACKEND.parent / "config.yaml")],
                         input=OLD.encode("utf-8"), capture_output=True, cwd=BACKEND,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert got.returncode == 0, got.stderr.decode("utf-8", "replace")
    assert yaml.safe_load(got.stdout.decode("utf-8"))["time"] == {"offset_hours": 0}
    assert "补进新版本的" in got.stderr.decode("utf-8")


@pytest.mark.parametrize("old", ["", "site:\n  title: x\n"])
def test_几乎空的备份也能合(old):
    text, _ = M.merge_text(old, NEW)
    M.check(text)
    assert set(yaml.safe_load(text)) == set(yaml.safe_load(NEW))
