package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 仿真任务详情 + 编辑。对应网页 Sims.vue 的编辑态（不含模拟器本身）：
 * <ul>
 * <li>改名称；AI 题改工具名称、开场白；</li>
 * <li>看初始环境（文字版）；网页编程题直接改代码布置环境、改代码做标准答案并生成检查点；</li>
 * <li>检查点：改描述和分值、删一条、全部清空；</li>
 * <li>试判：拿「什么都不做」（初始环境）或标准答案跑一遍检查点；</li>
 * <li>保存、删除。</li>
 * </ul>
 * Windows / WPS 的环境布置和答案录制要在桌面模拟器里点，手机上给出到电脑网页端的入口。
 */
final class SimDetailScreen extends Screen {
    private final long id;
    private JSONObject sim;
    private String kind = "";
    private String title = "";
    private JSONObject env = new JSONObject();
    private JSONArray checks = new JSONArray();
    /** 本次在手机上做的标准答案（只有网页编程题） */
    private JSONObject answer;
    private JSONObject tried;
    private String tryLabel;
    private String saved;

    private LinearLayout root;
    private LinearLayout page;

    SimDetailScreen(long id) {
        this.id = id;
    }

    @Override
    public String title() {
        return kind.isEmpty() ? "仿真任务" : Bank.kindName(kind) + "仿真题";
    }

    @Override
    public String subtitle() {
        return dirty() ? "有改动未保存" : null;
    }

    @Override
    protected View onCreateView(Context ctx) {
        root = V.vbox(ctx);
        root.setBackgroundColor(Palette.of(ctx).page);
        page = V.page(ctx);
        ScrollView sv = V.scroll(ctx, page);
        root.addView(sv, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));
        page.addView(new StateView(ctx).loading());
        return root;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    private void load() {
        run(() -> BankApi.sim(id), s -> {
            // 列表接口才有引用数，详情接口没有，从列表里补
            sim = s;
            kind = Json.str(s, "kind");
            title = Json.str(s, "title");
            env = Json.copy(Json.obj(s, "env"));
            checks = Json.arr(Json.copy(s), "checks");
            saved = snapshot();
            render();
            invalidateChrome();
            run(() -> BankApi.sims(kind), all -> {
                for (JSONObject o : all) {
                    if (o.optLong("id") == id) {
                        Json.put(sim, "question_count", o.optInt("question_count"));
                        render();
                    }
                }
            }, e -> true);
        }, e -> {
            page.removeAllViews();
            page.addView(new StateView(ctx()).error(e.getMessage(), this::load));
            return true;
        });
    }

    private String snapshot() {
        return Json.of("title", title, "env", env, "checks", checks).toString();
    }

    private boolean dirty() {
        return saved != null && !saved.equals(snapshot());
    }

    private void changed() {
        render();
        invalidateChrome();
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (sim == null) return a;
        if (dirty()) a.add(Action.icon(R.drawable.ic_check, "保存", this::save));
        a.add(Action.menu(R.drawable.ic_edit, "改名称", this::rename));
        a.add(Action.menu(R.drawable.ic_content_copy, "复制电脑端出题地址", this::copyUrl));
        a.add(Action.menu(R.drawable.ic_delete, "删除", this::delete).danger());
        return a;
    }

    @Override
    public boolean onBack() {
        if (dirty()) {
            Dialogs.confirm(ctx(), "放弃修改？", "改动还没保存，退出后就没了。", "放弃", true, () -> {
                saved = null;
                finish();
            });
            return true;
        }
        return false;
    }

    // ---------- 界面 ----------

    private void render() {
        Context c = ctx();
        page.removeAllViews();
        boolean ai = "ai".equals(kind);

        // 概要
        LinearLayout head = V.card(c);
        FlowBox tags = new FlowBox(c, 6, 6);
        tags.addView(V.tag(c, Bank.kindName(kind), Bank.kindTone(kind)));
        int used = sim.optInt("question_count");
        tags.addView(V.tag(c, used > 0 ? "被 " + used + " 道题引用" : "还没有题目挂它",
                used > 0 ? Tone.SUCCESS : Tone.NEUTRAL));
        head.addView(tags);
        LinearLayout tr = V.hbox(c);
        TextView tt = V.text(c, title.isEmpty() ? "（未命名）" : title, V.H2);
        tr.addView(tt, V.fill());
        tr.addView(V.iconButton(c, R.drawable.ic_edit, "改名称", v -> rename()));
        V.addTop(head, tr, 8);
        String meta = ai ? "按题干自动判分" : checks.length() + " 条检查点 · 满分 " + total() + " 分";
        String created = Fmt.dateTime(Json.str(sim, "created_at"));
        if (!created.isEmpty()) meta += " · 创建于 " + created;
        head.addView(V.text(c, meta, V.CAPTION));
        page.addView(head, V.matchWrap());

        if (SimCreate.needsDesktop(kind)) V.addTop(page, desktopCard(c), 12);

        if (ai) {
            LinearLayout card = V.card(c);
            card.setPadding(0, Ui.dp(c, 8), 0, Ui.dp(c, 8));
            card.addView(V.row(c, R.drawable.ic_computer, Tone.VIOLET, "工具名称",
                    Json.str(env, "tool"), null, v -> editEnvText("tool", "工具名称", "如：通义千问 / 文心一言 / DeepSeek")));
            card.addView(V.row(c, R.drawable.ic_feedback, Tone.VIOLET, "开场白",
                    Json.str(env, "greeting"), null, v -> editEnvText("greeting", "开场白", "学生打开时 AI 说的第一句话")));
            V.addTop(page, card, 12);
            V.addTop(page, V.notice(c, "这类题不用你做标准答案，也不用出检查点。学生要做的是把题干里的要求完整地描述给 AI 工具并发送，"
                    + "判分就看两条：提交过提问、提问内容覆盖题目要求 —— 判分时按题干现算，所以题干把要求写清楚就行。\n"
                    + "对话里的回复由本地模板生成，不联网调用真实大模型（考试环境不往外发请求）。", Tone.SUCCESS), 12);
        } else {
            // 初始环境
            LinearLayout envCard = V.card(c);
            LinearLayout eh = V.hbox(c);
            eh.addView(V.text(c, "① 初始环境", V.H3), V.fill());
            if ("html".equals(kind)) {
                eh.addView(V.button(c, R.drawable.ic_edit, "改代码", V.BTN_TONAL, v -> editEnvCode()));
            }
            envCard.addView(eh, V.matchWrap());
            V.addTop(envCard, V.text(c, "学生打开时看到的样子", V.CAPTION), 2);
            V.addTop(envCard, SimEnvView.build(c, kind, env), 10);
            if ("html".equals(kind)) {
                V.addTop(envCard, V.text(c, "改完环境记得重新做一遍标准答案 —— 检查点是按环境算出来的。", V.CAPTION), 8);
            }
            V.addTop(page, envCard, 12);

            // 标准答案 + 试判
            LinearLayout ac = V.card(c);
            ac.addView(V.text(c, "② 标准答案与试判", V.H3));
            if ("html".equals(kind)) {
                V.addTop(ac, V.text(c, "从初始环境开始按题目要求改一遍代码，系统对比前后差异生成检查点（追加在后面），改改措辞和分值就行。",
                        V.BODY2), 6);
                V.addTop(ac, V.button(c, R.drawable.ic_playlist_add, answer == null ? "做标准答案并生成检查点"
                        : "改标准答案并重新生成检查点", V.BTN_PRIMARY, v -> doAnswer()), 10);
            } else {
                V.addTop(ac, V.text(c, "标准答案要在电脑网页端的模拟器里做一遍才能生成检查点；手机上可以先试判「什么都不做」，应该是 0 分。",
                        V.BODY2), 6);
            }
            LinearLayout tb = V.hbox(c);
            tb.addView(V.button(c, "试判：什么都不做", V.BTN_OUTLINE, v -> tryRun(env, "什么都不做")), V.weight(1));
            if (answer != null) {
                tb.addView(V.space(c, 10));
                tb.addView(V.button(c, "试判：标准答案", V.BTN_TONAL, v -> tryRun(answer, "标准答案")), V.weight(1));
            }
            V.addTop(ac, tb, 10);
            V.addTop(ac, V.text(c, "按答案做完应该是满分；什么都不做应该是 0 分。", V.CAPTION), 6);
            if (tried != null) V.addTop(ac, triedView(c), 12);
            V.addTop(page, ac, 12);

            // 检查点
            V.addTop(page, checksCard(c), 12);
        }

        // 底部按钮
        LinearLayout btns = V.hbox(c);
        TextView save = V.button(c, R.drawable.ic_check, "保存", V.BTN_PRIMARY, v -> save());
        V.enable(save, dirty());
        btns.addView(save, V.weight(1));
        btns.addView(V.space(c, 12));
        btns.addView(V.button(c, R.drawable.ic_delete, "删除", V.BTN_DANGER_TONAL, v -> delete()), V.weight(1));
        V.addTop(page, btns, 16);
    }

    private int total() {
        int n = 0;
        for (JSONObject ch : Json.list(checks)) n += Math.max(0, ch.optInt("score", 0));
        return n;
    }

    private View desktopCard(Context c) {
        LinearLayout card = V.card(c);
        card.setBackground(V.round(c, Palette.of(c).warningSoft, 16));
        LinearLayout h = V.hbox(c);
        h.addView(V.icon(c, R.drawable.ic_computer, Palette.of(c).warning, 22));
        TextView t = V.text(c, "环境布置和标准答案录制请到电脑上做", V.H3);
        t.setTextColor(Palette.of(c).warning);
        LinearLayout.LayoutParams lp = V.fill();
        lp.setMarginStart(Ui.dp(c, 10));
        h.addView(t, lp);
        card.addView(h);
        V.addTop(card, V.text(c, "这类题要在网页里的模拟" + ("win".equals(kind) ? " XP 桌面里新建、拖动、右键改名删除文件"
                : " WPS 里用工具栏排版") + "，手机屏幕用不了模拟器。手机上可以看环境、改名称、改检查点描述和分值、试判和删除。\n"
                + "电脑浏览器打开：" + Bank.webSimsUrl(), V.BODY2), 8);
        LinearLayout b = V.hbox(c);
        b.addView(V.button(c, R.drawable.ic_content_copy, "复制地址", V.BTN_OUTLINE, v -> copyUrl()), V.weight(1));
        b.addView(V.space(c, 10));
        b.addView(V.button(c, R.drawable.ic_share, "发到电脑", V.BTN_OUTLINE, v ->
                Sys.share(c, "仿真操作题", "在电脑浏览器打开，编辑仿真题「" + title + "」：" + Bank.webSimsUrl())), V.weight(1));
        V.addTop(card, b, 10);
        return card;
    }

    private View triedView(Context c) {
        Palette p = Palette.of(c);
        int score = tried.optInt("score"), full = tried.optInt("full");
        boolean good = score == full;
        LinearLayout box = V.vbox(c);
        box.setBackground(V.round(c, good ? p.successSoft : p.warningSoft, 12));
        V.pad(box, 12, 10, 12, 10);
        TextView h = V.text(c, "试判（" + tryLabel + "）：" + score + " / " + full + " 分", V.H3);
        h.setTextColor(good ? p.success : p.warning);
        box.addView(h);
        for (JSONObject r : Json.list(Json.arr(tried, "results"))) {
            boolean ok = Json.bool(r, "ok");
            LinearLayout row = V.hbox(c);
            row.setGravity(Gravity.TOP);
            row.addView(V.icon(c, ok ? R.drawable.ic_check_circle : R.drawable.ic_cancel, ok ? p.success : p.danger, 18));
            String why = Json.str(r, "why");
            TextView t = V.text(c, Json.str(r, "desc") + (ok || why.isEmpty() ? "" : "（" + why + "）"), V.BODY2);
            if (!ok) t.setTextColor(p.danger);
            LinearLayout.LayoutParams lp = V.fill();
            lp.setMarginStart(Ui.dp(c, 8));
            row.addView(t, lp);
            row.addView(V.text(c, r.optInt("earned") + "/" + r.optInt("score"), V.CAPTION));
            V.addTop(box, row, 6);
        }
        return box;
    }

    private View checksCard(Context c) {
        Palette p = Palette.of(c);
        LinearLayout card = V.card(c);
        LinearLayout h = V.hbox(c);
        h.addView(V.text(c, "检查点（共 " + checks.length() + " 条，满分 " + total() + " 分）", V.H3), V.fill());
        if (checks.length() > 0) {
            h.addView(V.button(c, "全部清空", V.BTN_TEXT, v -> Dialogs.confirm(c, "清空全部检查点？",
                    "清空后要重新做一遍标准答案生成。保存之前都可以放弃修改。", "清空", true, () -> {
                        checks = new JSONArray();
                        changed();
                    })));
        }
        card.addView(h, V.matchWrap());
        if (checks.length() == 0) {
            V.addTop(card, V.text(c, "html".equals(kind) ? "还没有检查点。点上面「做标准答案并生成检查点」。"
                    : "还没有检查点。到电脑网页端切到「② 做标准答案」，做一遍再点「生成检查点」。", V.BODY2), 8);
            return card;
        }
        for (int i = 0; i < checks.length(); i++) {
            final int idx = i;
            JSONObject ch = checks.optJSONObject(i);
            if (ch == null) continue;
            LinearLayout row = V.hbox(c);
            row.setGravity(Gravity.TOP);
            V.pad(row, 4, 10, 4, 10);
            TextView no = V.text(c, String.valueOf(i + 1), V.CAPTION);
            no.setGravity(Gravity.CENTER);
            no.setBackground(V.round(c, p.surfaceAlt, 11));
            int s = Ui.dp(c, 22);
            row.addView(no, new LinearLayout.LayoutParams(s, s));
            LinearLayout texts = V.vbox(c);
            String desc = Json.str(ch, "desc");
            texts.addView(V.text(c, desc.isEmpty() ? "第 " + (i + 1) + " 问" : desc, V.BODY));
            TextView rule = V.lines(SimEnvView.code(c, Json.obj(ch, "assert").toString()), 3);
            rule.setTextIsSelectable(false);
            V.addTop(texts, rule, 4);
            LinearLayout.LayoutParams lp = V.fill();
            lp.setMarginStart(Ui.dp(c, 10));
            row.addView(texts, lp);
            V.addStart(row, V.tag(c, ch.optInt("score") + " 分", Tone.PRIMARY), 8);
            V.clickable(row, 10, v -> editCheck(idx));
            if (i > 0) V.addTop(card, V.divider(c), 4);
            V.addTop(card, row, 4);
        }
        V.addTop(card, V.text(c, "点一条改描述和分值。灰字是这一问实际判分的规则，一般不用动；真要调规则请到电脑网页端照着说明改。",
                V.CAPTION), 8);
        return card;
    }

    // ---------- 编辑 ----------

    private void rename() {
        Dialogs.prompt(ctx(), "名称", "如：新建文件夹并改名（win02）", title, 1, "确定", t -> {
            String v = t.trim();
            if (v.isEmpty()) {
                toast("给这道题起个名字");
                return;
            }
            title = v.length() > 128 ? v.substring(0, 128) : v;
            changed();
        });
    }

    private void editEnvText(String key, String label, String hint) {
        Dialogs.prompt(ctx(), label, hint, Json.str(env, key), 1, "确定", t -> {
            Json.put(env, key, t.trim());
            changed();
        });
    }

    private void editCheck(final int idx) {
        final JSONObject ch = checks.optJSONObject(idx);
        if (ch == null) return;
        Sheet s = new Sheet(ctx(), "第 " + (idx + 1) + " 条检查点");
        Form f = new Form(ctx());
        Form.Text desc = f.area("描述", Json.str(ch, "desc"), 2).hint("这一问要求学生做什么");
        Form.Stepper score = f.stepper("分值", ch.optInt("score", 0), 0, 50);
        f.note("判分规则：" + Json.obj(ch, "assert").toString());
        s.content(f.view());
        View del = V.button(ctx(), R.drawable.ic_delete, "删除这条", V.BTN_DANGER_TONAL, v -> {
            s.dismiss();
            JSONArray out = new JSONArray();
            for (int i = 0; i < checks.length(); i++) if (i != idx) out.put(checks.opt(i));
            checks = out;
            changed();
        });
        s.body().addView(del, V.matchWrap());
        s.buttons("取消", null, "确定", () -> {
            if (!f.validate()) return;
            s.dismiss();
            Json.put(ch, "desc", desc.value());
            Json.put(ch, "score", score.value());
            changed();
        });
        s.show();
    }

    private void editEnvCode() {
        push(new SimCodeScreen("布置环境", "学生打开时看到的代码。改完点右上角 ✓ 带回去，再点「保存」才会存进题库。", "完成",
                Json.obj(env, "files")), r -> {
            if (r instanceof JSONObject) {
                Json.put(env, "files", r);
                answer = null;
                tried = null;
                changed();
            }
        });
    }

    private void doAnswer() {
        JSONObject start = answer != null ? Json.obj(answer, "files") : Json.obj(env, "files");
        push(new SimCodeScreen("做标准答案", "按题目要求把代码改一遍。点右上角 ✓ 后系统对比初始环境，自动生成检查点。",
                "生成检查点", Json.copy(start)), r -> {
            if (!(r instanceof JSONObject)) return;
            final JSONObject state = Json.of("files", r);
            runBusy("正在生成检查点…", () -> BankApi.simPropose(kind, env, state), res -> {
                answer = state;
                int n = res.optInt("count");
                if (n == 0) {
                    toast("没看出你做了什么改动，检查点生成不出来");
                    changed();
                    return;
                }
                // 追加而不是覆盖：老师可能分几次做
                for (JSONObject ch : Json.list(Json.arr(res, "checks"))) checks.put(ch);
                tried = null;
                changed();
                toast("生成了 " + n + " 条检查点，改改措辞和分值");
            });
        });
    }

    private void tryRun(final JSONObject state, final String label) {
        if (checks.length() == 0) {
            toast("还没有检查点");
            return;
        }
        final JSONArray cs = checks;
        runBusy("正在试判…", () -> BankApi.simTry(id, state, cs), r -> {
            tried = r;
            tryLabel = label;
            changed();
        });
    }

    private void copyUrl() {
        Sys.copy(ctx(), "教师端地址", Bank.webSimsUrl());
        toast("地址已复制，在电脑浏览器打开");
    }

    // ---------- 保存 / 删除 ----------

    private void save() {
        if (title.trim().isEmpty()) {
            toast("给这道题起个名字");
            return;
        }
        if (!"ai".equals(kind) && checks.length() == 0) {
            Dialogs.confirm(ctx(), "还没有检查点", "没有检查点的话，学生做什么都是 0 分。仍然保存？", "仍然保存", false,
                    this::doSave);
            return;
        }
        doSave();
    }

    private void doSave() {
        final JSONObject body = Json.of("title", title.trim(), "env", env, "checks", checks);
        runBusy("正在保存…", () -> BankApi.simUpdate(id, body), s -> {
            int used = sim.optInt("question_count");
            sim = s;
            Json.put(sim, "question_count", used);
            saved = snapshot();
            changed();
            toast("已保存");
        });
    }

    private void delete() {
        int used = sim.optInt("question_count");
        String msg = used > 0
                ? "有 " + used + " 道题挂着「" + title + "」。删掉之后那些题不会消失，只是退回「老师人工评阅」。已经考完的成绩不受影响。"
                : "确定删除「" + title + "」吗？";
        Dialogs.confirm(ctx(), "删除仿真任务", msg, "删除", true, () -> runBusy("正在删除…", () -> BankApi.simDelete(id), r -> {
            toast("已删除");
            saved = null;
            finish(Boolean.TRUE);
        }));
    }
}
