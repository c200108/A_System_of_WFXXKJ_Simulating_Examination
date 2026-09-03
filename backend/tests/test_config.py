"""config.yaml 相关：坏配置要报错，好配置要真的改变行为。

这个文件保护的是「改 YAML 就生效」这条链路。以后重构导入规则或组卷默认值时，
如果不小心又把值写回代码里，这里会挂。
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


def child_env(cfg_path: str) -> dict:
    """子进程环境：指定 UTF-8，否则 Windows 下中文报错信息会按 GBK 输出，父进程读不了。"""
    env = dict(os.environ)
    env["CONFIG_FILE"] = cfg_path
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def load_with(tmp_path: Path, yaml_text: str):
    """用一份临时配置起一个子进程，返回 (退出码, 输出)。

    必须开子进程：siteconfig 在模块导入时就把配置读死了，同一进程里改不了。
    """
    cfg = tmp_path / "c.yaml"
    cfg.write_text(textwrap.dedent(yaml_text), encoding="utf-8")
    code = (
        "from app.siteconfig import site;"
        "from app.services.importer import norm_type, norm_answer, parse_options;"
        "import json;"
        "print(json.dumps({"
        "'title': site.paper.default_title,"
        "'counts': site.paper.default_counts,"
        "'pass': site.exam.pass_score,"
        "'prefix': site.paper.code_prefix,"
        "'norm_type_单选': norm_type('单选'),"
        "'norm_type_辨析': norm_type('辨析'),"
        "'judge_是': norm_answer('是', '判断题'),"
        "'judge_yes': norm_answer('yes', '判断题'),"
        "'opts': parse_options('A|甲\\nB|乙', '选择题'),"
        "'maxopts': site.import_.max_options,"
        "}, ensure_ascii=False))"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env(str(cfg)),
    )
    return res.returncode, (res.stdout or "") + (res.stderr or "")


# ---------- 坏配置必须报错，而不是静默用默认值 ----------
@pytest.mark.parametrize(
    "bad, hint",
    [
        ("paper:\n  defalut_counts: {选择题: 5}\n", "Extra inputs are not permitted"),
        ("exam:\n  pass_score: 及格\n", "valid integer"),
        ("exam:\n  pass_score: 200\n", "less than or equal to 100"),
        ("exam:\n  token_length: 2\n", "greater than or equal to 6"),
        ("bank:\n  scopes: 不是列表\n", "valid list"),
        ("没这个键: 1\n", "Extra inputs are not permitted"),
    ],
)
def test_bad_config_refuses_to_start(tmp_path, bad, hint):
    rc, out = load_with(tmp_path, bad)
    assert rc == 1, f"这份坏配置本该拒绝启动：\n{bad}"
    assert "配置文件有问题" in out
    assert hint in out, out


def test_broken_yaml_syntax_is_explained(tmp_path):
    rc, out = load_with(tmp_path, "paper:\n  a: 1\n   b: 2\n")
    assert rc == 1
    assert "YAML 格式错误" in out


# ---------- 好配置必须真的改变行为 ----------
def test_config_actually_changes_behaviour(tmp_path):
    rc, out = load_with(
        tmp_path,
        """
        paper:
          default_title: "换了个标题"
          default_counts: {选择题: 7, 判断题: 2}
          code_prefix: "卷号-"
        exam:
          pass_score: 80
        import:
          type_keywords:
            选择题: ["选择", "单选"]
            判断题: ["判断", "辨析"]
          judge_answers:
            正确: ["是", "yes"]
            错误: ["否", "no"]
          option_separators: "|"
          max_options: 2
        """,
    )
    assert rc == 0, out
    got = json.loads(out.strip().splitlines()[-1])

    # 组卷默认值
    assert got["title"] == "换了个标题"
    assert got["counts"] == {"选择题": 7, "判断题": 2}
    assert got["prefix"] == "卷号-"
    assert got["pass"] == 80

    # 题型识别关键词是配置来的：加了「单选」「辨析」就能认
    assert got["norm_type_单选"] == "选择题"
    assert got["norm_type_辨析"] == "判断题"

    # 判断题答案的各种写法也是配置来的
    assert got["judge_是"] == "正确"
    assert got["judge_yes"] == "正确"

    # 选项分隔符换成 | 之后照样能拆
    assert got["opts"] == [["A", "甲"], ["B", "乙"]]
    assert got["maxopts"] == 2


def test_missing_file_falls_back_to_defaults(tmp_path):
    """配置文件不存在时用内置默认值启动，保证新克隆的仓库能跑。"""
    res = subprocess.run(
        [sys.executable, "-c",
         "from app.siteconfig import site; print('OK', site.exam.pass_score)"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env(str(tmp_path / "根本不存在.yaml")),
    )
    assert res.returncode == 0, res.stderr
    assert "OK 60" in res.stdout


# ---------- 接口把配置发给前端 ----------
def test_config_endpoint_is_public_and_has_no_secrets(client):
    res = client.get("/api/config")  # 不带登录令牌
    assert res.status_code == 200

    body = res.json()
    assert "pass_score" in body["exam"]
    assert "default_counts" in body["paper"]

    raw = res.text.lower()
    for leak in ("secret", "password", "token", "database", "jwt"):
        assert leak not in raw, f"/api/config 里不该出现 {leak}"
