"""考试：取卷（去答案）与后端判分。

安全上的关键约定：
    给学生的接口一律走 exam_questions(..., with_answer=False)，
    答案只在 grade() 里读，永远不进响应体。

判分分两段（2.4.0 起）：

    客观题  选择题、判断题这些机器判得了的 —— 交卷当场算分；
    主观题  操作题这些要人看的 —— 先记 0 分，老师在成绩页逐题给分后补上。

所以一份答卷的总分 = 客观题得分 + 主观题得分，老师阅卷后 score 会变。
学生交完卷立刻看到的是客观题那一段，界面上会写明"操作题待老师评阅"。

**老卷子（2.4.0 之前组的）没有每题分值**，这里会自动退回原来的算法：
按客观题正确率折成百分制。历史成绩因此一分不变。判断依据是
has_scores()：卷面上有没有任何一道题带分值。
"""

import json
import secrets

from sqlalchemy.orm import Session

from .. import clock
from ..models import Exam, Paper, PaperItem, Question
from ..siteconfig import site
from . import sim, stem as stem_rules
from .paper import right_letter


def _json(raw, fallback):
    """读一段存在库里的 JSON。坏了就当默认值 —— 一道题的仿真数据格式不对，
    不该让整场考试交不上卷。"""
    try:
        got = json.loads(raw or "")
    except (ValueError, TypeError):
        return fallback
    return got if isinstance(got, type(fallback)) else fallback


def new_token() -> str:
    """学生链接里的口令，够随机以防被猜到。"""
    return secrets.token_urlsafe(site.exam.token_length)


def manual_types() -> set[str]:
    """要老师人工评阅的题型，见 config.yaml 的 exam.manual_types。"""
    return set(site.exam.manual_types)


def is_manual(item: dict) -> bool:
    return item.get("type") in manual_types()


def has_scores(items: list[dict]) -> bool:
    """这份卷子有没有设每题分值。没有就是 2.4.0 之前的老卷子。"""
    return any(int(it.get("score") or 0) for it in items)


def sim_kind_of(q: Question) -> str:
    """这道操作题属于哪一类仿真：win / wps / html / ai，或者 drag。

    判法和出卷、判分那条路**完全一致**（先看老师配的仿真任务，没配就按题干推），
    所以组卷时筛出来的题，学生在考场上看到的就是那一类，不会出现"卷子上说是
    网页题、客户端铺出来却是别的"。

    `drag` 不是一种仿真环境，而是"没有仿真环境"——热区拖拽、流程图补全这类
    题目现在就落在这儿。组卷配置里用它来指定"这一组只要拖拽类的题"。
    """
    if q.sim_task is not None:
        return (q.sim_task.kind or "").strip() or "drag"
    got = stem_rules.auto_sim(q.stem or "", q.scope or "")
    return got["kind"] if got else "drag"


def _item_from_row(item: PaperItem, q: Question) -> dict:
    """把试卷里的一题还原成完整结构（含打乱后的选项与答案）。"""
    snap = json.loads(item.snapshot_json) if item.snapshot_json else {}
    out = {
        "id": q.id,
        "code": q.code,
        "type": q.type,
        "stem": q.stem,
        "answer": snap.get("answer", q.answer) or "",
        "scope": q.scope,
        "source": q.source,
        "image_url": q.image_url,
        "difficulty": q.difficulty,
        "section": item.section or q.type,   # 老卷子没存大题，按题型归
        "score": item.score or 0,
        "options": snap.get("options")
        or [{"label": o.label, "content": o.content} for o in q.options],
    }
    if q.sim_task is not None:
        # sim  —— 学生要拿到的：打开时看到什么
        # sim_checks —— **等同于答案**，只在服务端读，由 strip_answers() 摘掉
        env = _json(q.sim_task.env_json, {})
        checks = _json(q.sim_task.checks_json, [])
        if q.sim_task.kind == "wps":
            # 旧规则自动生成、老师没改过的 WPS 题，按现在的规则当场重算
            # （恢复备份、导入旧数据包后也照样生效，见 stem.refresh_wps）
            fresh = stem_rules.refresh_wps(q.stem or "", env, checks)
            if fresh:
                env, checks = fresh["env"], fresh["checks"]
        out["sim"] = sim.sim_for_student({
            "id": q.sim_task.id, "kind": q.sim_task.kind, "title": q.sim_task.title,
            "env": env,
        })
        out["sim_checks"] = checks
    elif q.type in manual_types():
        # **没配仿真任务的操作题：按题干当场推一份。**
        #
        # 这一支是整条链路的兜底。老师从旧版本导出数据再导进来时，
        # sim_task_id 全是空 —— 只认库里配好的那份的话，所有操作题会一夜之间
        # 变成"不能自动判分"，而且表面上看不出毛病：题目照出，就是没有文件、
        # 没有检查点，学生打开一看是个空壳。
        #
        # 题干跟着题目走，导库不会丢。**所以以题干为准**，环境和检查点一起算，
        # 出包和判分走的是同一个函数，两边不可能对不上。
        auto = stem_rules.auto_sim(q.stem or "", q.scope or "")
        if auto:
            out["sim"] = sim.sim_for_student({
                # 拖拽题不要标题：题干（补全过的）就在正上方，再抄一遍原题干只会
                # 把补全前那句「请点击开始操作进入仿真系统」又端出来
                "id": 0, "kind": auto["kind"],
                "title": "" if auto["kind"] == "drag" else (q.stem or "")[:60],
                "env": auto["env"],
            })
            out["sim_checks"] = auto["checks"]
            # 拖拽题：题干不全的换成补全版（原题干留在库里不动 —— 改了它，下次
            # 导库就认不出这道题了）；原图是旧考试系统的截图，素材区烤在图上、
            # 说明弹窗挡着半张图，现在结构图是重画的，旧图不再显示
            if auto.get("stem"):
                out["stem"] = auto["stem"]
            if auto["kind"] == "drag":
                out["image_url"] = None
    # 题干里的工作目录、文件名换成考场里**实际**的（见 stem.student_stem）
    got_sim = out.get("sim") or {}
    if got_sim.get("kind") in ("win", "wps", "ai"):
        shown = stem_rules.student_stem(out["stem"], got_sim["kind"], got_sim.get("env"))
        if got_sim.get("title") and got_sim["title"] == (q.stem or "")[:60]:
            got_sim["title"] = shown[:60]
        out["stem"] = shown
    return out


def _move_workdir(item: dict, old: str, new: str) -> None:
    """把一道 Windows 题的工作目录从 C:/EXAM/old 挪到 C:/EXAM/new：环境、检查点、题干一起改。"""
    a, b = f"{stem_rules.ROOT}/{old}", f"{stem_rules.ROOT}/{new}"

    def mv(path):
        path = str(path)
        return b + path[len(a):] if path == a or path.startswith(a + "/") else path

    got = item["sim"]
    env = dict(got.get("env") or {})
    env["fs"] = {mv(k): v for k, v in (env.get("fs") or {}).items()}
    item["sim"] = {**got, "env": env}
    checks = []
    for c in item.get("sim_checks") or []:
        a_ = c.get("assert") or {}
        a_ = {**a_, **{k: mv(a_[k]) for k in ("path", "from") if k in a_}}   # from：copied 的原位置
        checks.append({**c, "assert": a_})
    item["sim_checks"] = checks
    item["stem"] = stem_rules.rename_workdir(item["stem"], old, new)
    if item["sim"].get("title"):
        item["sim"]["title"] = item["stem"][:60]


def separate_workdirs(items: list[dict]) -> list[dict]:
    """一张卷子上几道 Windows 操作题的工作目录**同名**时，后面的依次改成「名字2」「名字3」。

    题库里 6 道题都是「请打开本题工作目录下的系统基本操作文件夹」，放进同一张卷子，
    考场里就只有一个「系统基本操作」，六道题的素材挤在一起、互相打架。

    按卷面顺序改，出包、判分、网页答题走的都是 load_items，改出来的名字处处一致。
    """
    prefix = stem_rules.ROOT + "/"

    def tops(it):
        fs = ((it.get("sim") or {}).get("env") or {}).get("fs") or {}
        got = {str(k)[len(prefix):].split("/")[0] for k in fs if str(k).startswith(prefix)}
        got.discard("")
        return got

    wins = [it for it in items if (it.get("sim") or {}).get("kind") == "win"]
    taken = set().union(*(tops(it) for it in wins)) if wins else set()
    used: set = set()
    for it in wins:
        mine = tops(it)
        if len(mine) == 1:
            top = next(iter(mine))
            if top in used:
                n = 2
                while f"{top}{n}" in taken or f"{top}{n}" in used:
                    n += 1
                _move_workdir(it, top, f"{top}{n}")
                top = f"{top}{n}"
            used.add(top)
        else:
            used |= mine
    return items


def load_items(db: Session, paper: Paper) -> list[dict]:
    """按卷面顺序取出全部题目（含答案，仅供服务端使用）。"""
    out = []
    for it in paper.items:
        q = db.get(Question, it.question_id)
        if q:
            out.append(_item_from_row(it, q))
    return separate_workdirs(out)


def wants_shuffle(paper: Paper | None) -> bool:
    """这份卷子开没开「选择判断题乱序」。老卷子（2.19.0 以前组的）没这一项，算不开 ——
    它们的选项当初是在组卷那一步打乱后存的，再乱一次也没坏处，但题序会和老师印出去的
    那份对不上。"""
    if paper is None:
        return False
    return bool(_json(paper.config_json, {}).get("shuffle"))


def group_items(items: list[dict]) -> list[dict]:
    """按大题分组。大题不等于题型 —— 「物联网实践与探索」里两种题型都有。"""
    groups: list[dict] = []
    for it in items:
        name = it.get("section") or it["type"]
        g = next((g for g in groups if g["name"] == name), None)
        if not g:
            g = {"name": name, "type": name, "score": 0, "items": []}
            groups.append(g)
        g["items"].append(it)
        g["score"] += int(it.get("score") or 0)
    return groups


def strip_answers(groups: list[dict]) -> list[dict]:
    """去掉答案再发给学生。多留一道关卡，避免以后改代码时不小心漏出去。

    每题的分值是留着的 —— 卷面上本来就印着"本题 2 分"，那不是答案线索。
    """
    return [
        {
            "name": g.get("name") or g["type"],
            "type": g["type"],
            "score": g.get("score", 0),
            "items": [
                # sim_checks 是仿真题的答案，和 answer 一样绝不能发给学生
            {
                k: v for k, v in it.items()
                if k not in ("answer", "source", "difficulty", "sim_checks")
            }
                for it in g["items"]
            ],
        }
        for g in groups
    ]


def scorable(item: dict) -> bool:
    """能不能机器判分。操作题靠人看；原卷没给答案的题不计分，
    否则不作答会被判成答对。"""
    return not is_manual(item) and bool((item.get("answer") or "").strip())


def grade(items: list[dict], answers: dict) -> dict:
    """后端判分。answers 的键是题目 id（字符串或数字都认）。

    返回里 score 是**当前**总分：主观题还没批，所以等于客观题得分。
    老师批完走 apply_manual() 重算。
    """
    scored = has_scores(items)
    detail = []
    auto_manual: dict[str, int] = {}     # 仿真题自动判出来的分，预填给老师
    auto_sub = 0
    right = 0
    objective = 0
    obj_score = 0
    obj_total = 0
    sub_total = 0

    for it in items:
        mine = answers.get(str(it["id"]), answers.get(it["id"], ""))
        mine = "" if mine is None else str(mine).strip()
        pts = int(it.get("score") or 0)

        if not scorable(it):
            manual = is_manual(it)
            if manual:
                sub_total += pts
            entry = {
                "id": it["id"],
                "type": it["type"],
                "scored": False,
                "manual": manual,
                "score": pts,
                "earned": 0,
                "mine": mine,
                "answer": it.get("answer") or "",
                "reason": "待老师评阅" if manual else "原卷未给答案，不计分",
            }
            # 挂了仿真任务的操作题：按检查点当场判分。判出来的分只是**预填**，
            # 老师在成绩页照样能改（apply_manual 覆盖它）。
            kind = (it.get("sim") or {}).get("kind")
            # AI 工具题老师不出检查点，按题干现算（sim.checks_for）
            sim_checks = sim.checks_for(kind, it.get("sim_checks"), it.get("stem", ""), pts)
            state = sim.load_state(mine) if manual and kind and sim_checks else None
            # 拖拽题交上来一个**空终态** {"state": {}}：那是旧版桌面端（4.7 及以前）——
            # 它画不出拖拽题，只会交个空的，学生根本没机会做。这时别自动判 0 分还标
            # "自动判分"，老样子留给老师评阅。
            # 新版桌面端哪怕一张没放也会交 {"placed": {}}；网页端没碰过的题交的是
            # 空串 —— 这两种照常判分，和别的操作题一样，没做就是 0 分
            if kind == "drag" and mine and state is not None and not state:
                entry["reason"] = "没有拖拽作答数据（旧版桌面端做不了这类题），请老师评阅"
                detail.append(entry)
                continue
            if state is not None:
                ran = sim.run_checks(kind, sim_checks, state)
                earned = scale_sim(ran, pts)
                auto_manual[str(it["id"])] = earned
                auto_sub += earned
                entry.update(
                    earned=earned,
                    auto=True,
                    reason="仿真题自动判分，老师可复核",
                    checks=ran["results"],
                    check_passed=sum(1 for r in ran["results"] if r["ok"]),
                    check_total=len(ran["results"]),
                )
                settle_auto(entry)
            detail.append(entry)
            continue

        objective += 1
        obj_total += pts
        correct = right_letter(it)
        ok = mine == correct
        if ok:
            right += 1
            obj_score += pts
        detail.append(
            {
                "id": it["id"],
                "type": it["type"],
                "scored": True,
                "manual": False,
                "score": pts,
                "earned": pts if ok else 0,
                "ok": ok,
                "mine": mine,
                "answer": correct,
            }
        )

    if not scored:
        # 老卷子：没设分值，照旧按客观题正确率折百分制
        obj_score = round(right / objective * 100) if objective else 0
        obj_total = 100 if objective else 0
        sub_total = 0
        auto_manual, auto_sub = {}, 0

    return {
        "right_count": right,
        "objective_count": objective,
        "objective_score": obj_score,
        "objective_total": obj_total,
        "subjective_score": auto_sub,
        "subjective_total": sub_total,
        # 仿真题已经判了，总分把那部分算进去；剩下的等老师批完再补
        "score": obj_score + auto_sub,
        "full_score": obj_total + sub_total,
        # 待老师评阅的：机器判不了的，加上检查点部分通过、等老师复核的
        "pending_manual": sum(1 for d in detail if d.get("manual") and not d.get("graded")),
        "auto_manual": auto_manual,
        "detail": detail,
    }


def settle_auto(d: dict) -> bool:
    """按检查点给操作题定分：全过给满分、全没过给 0 分，这两种算**已评完**，老师不用再点。

    部分通过的按比例预填（scale_sim 算好的 earned），留给老师复核 —— 那种情况机器
    说不准学生差在哪、该扣多少，得人看一眼。

    老师已经评过的（graded 且不是这里自动定的）一律不动：老师的判断优先。
    返回这一题有没有被改动。
    """
    if not d.get("manual") or not d.get("auto") or d.get("graded"):
        return False
    total = int(d.get("check_total") or 0)
    passed = int(d.get("check_passed") or 0)
    if total <= 0:
        return False
    full = int(d.get("score") or 0)
    if passed == total:
        d.update(earned=full, graded=True, auto_graded=True,
                 reason="检查点全部通过，自动给满分")
        return True
    if passed == 0:
        d.update(earned=0, graded=True, auto_graded=True,
                 reason="检查点全部没通过，自动给 0 分")
        return True
    d["reason"] = f"部分检查点通过（{passed}/{total}），已按比例预填 {d.get('earned', 0)} 分，请老师复核"
    return False


def settle_submission(sub) -> bool:
    """老答卷补一遍 settle_auto（这条规则 2.10.0 才有）。改了返回 True，调用方负责 commit。

    全过 / 全没过的题，分数本来就是满分 / 0（scale_sim 算出来的），这里只把它们
    标成已评完；一份卷子的题全评完了，graded_at 落上，老师列表里的「待阅」就消失。
    """
    detail = json.loads(sub.detail_json or "[]")
    changed = False
    for d in detail:
        before = d.get("earned", 0)
        if settle_auto(d):
            changed = True
            if d["earned"] != before:          # 理论上不会：全过/全没过本来就是满分/0
                sub.subjective_score += d["earned"] - before
                sub.score += d["earned"] - before
    if not changed:
        return False
    sub.detail_json = json.dumps(detail, ensure_ascii=False)
    manual = json.loads(sub.manual_json or "{}")
    for d in detail:
        if d.get("auto_graded"):
            manual[str(d["id"])] = d["earned"]
    sub.manual_json = json.dumps(manual, ensure_ascii=False)
    pending = sum(1 for d in detail if d.get("manual") and not d.get("graded"))
    if pending == 0 and sub.subjective_total > 0 and sub.graded_at is None:
        sub.graded_at = clock.now()
    return True


def scale_sim(ran: dict, pts: int) -> int:
    """把检查点的得分折算成这道题在卷面上的分值。

    检查点的总分是出题时定的（比如四小问各 2 分），而卷面分值是组卷时按难度
    分摊出来的（这道题可能只占 7 分）—— 两者对不上是常态，必须按比例折算，
    否则会出现"一道 7 分的题判出 8 分"。
    """
    full = int(ran.get("full") or 0)
    if not full or pts <= 0:
        return 0
    got = int(round(pts * int(ran.get("score") or 0) / full))
    return max(0, min(pts, got))


def submission_scores(result: dict) -> dict:
    """交卷时要落库的分数字段。两个交卷入口（学生端、凭链接）共用这一份，
    省得一处加了字段另一处忘了加。"""
    fields = {
        "right_count": result["right_count"],
        "objective_count": result["objective_count"],
        "score": result["score"],
        "objective_score": result["objective_score"],
        "objective_total": result["objective_total"],
        "subjective_score": result["subjective_score"],
        "subjective_total": result["subjective_total"],
        # 仿真题判出来的分预填进去，老师在成绩页能改
        "manual_json": json.dumps(result.get("auto_manual") or {}, ensure_ascii=False),
    }
    # 主观题全是仿真题、已经当场判完的，就别再出现在老师的"待批"里了。
    # graded_by 留空表示不是人批的，成绩页上会标「自动判分」。
    if result["subjective_total"] > 0 and result["pending_manual"] == 0:
        fields["graded_at"] = clock.now()
    return fields


def apply_manual(detail: list[dict], manual_scores: dict) -> dict:
    """把老师给的主观题分数填进明细，重算主观分。

    manual_scores 的键是题目 id，值是得分；超出该题满分的按满分算，
    负数按 0 算 —— 老师手滑打多一位不该让总分冒出卷面。
    返回 {detail, subjective_score, graded_count, pending}。
    """
    got = 0
    graded = 0
    pending = 0

    for d in detail:
        if not d.get("manual"):
            continue
        full = int(d.get("score") or 0)
        raw = manual_scores.get(str(d["id"]), manual_scores.get(d["id"]))
        if (raw is None or raw == "") and d.get("auto_graded") and d.get("graded"):
            # 检查点全过 / 全没过、系统已经定了分的：老师这次没动它，保持原样
            got += int(d.get("earned") or 0)
            graded += 1
            continue
        if raw is None or raw == "":
            d["earned"] = 0
            d["graded"] = False
            pending += 1
            continue
        try:
            value = int(round(float(raw)))
        except (TypeError, ValueError):
            value = 0
        value = max(0, min(full, value))
        d["earned"] = value
        d["graded"] = True
        d["auto_graded"] = False             # 老师给的分，以后 settle_auto 不再碰它
        got += value
        graded += 1

    return {
        "detail": detail,
        "subjective_score": got,
        "graded_count": graded,
        "pending": pending,
    }


def question_stats(exam: Exam, items: list[dict]) -> list[dict]:
    """每题的作答情况，老师用来看哪道题错得多。"""
    by_id = {it["id"]: it for it in items}
    counters: dict[int, dict] = {
        it["id"]: {"right": 0, "wrong": 0, "blank": 0} for it in items
    }

    for sub in exam.submissions:
        for d in json.loads(sub.detail_json or "[]"):
            c = counters.get(d["id"])
            if c is None or not d.get("scored"):
                continue
            if not d.get("mine"):
                c["blank"] += 1
            elif d.get("ok"):
                c["right"] += 1
            else:
                c["wrong"] += 1

    out = []
    for qid, c in counters.items():
        it = by_id[qid]
        answered = c["right"] + c["wrong"] + c["blank"]
        out.append(
            {
                "id": qid,
                "type": it["type"],
                "scope": it["scope"],
                "section": it.get("section") or it["type"],
                "score": int(it.get("score") or 0),
                "difficulty": it.get("difficulty") or 3,
                "stem": it["stem"][:60],
                "answer": it.get("answer") or "",
                "right": c["right"],
                "wrong": c["wrong"],
                "blank": c["blank"],
                "accuracy": round(c["right"] / answered * 100) if answered else 0,
                "scorable": scorable(it),
            }
        )
    return out
