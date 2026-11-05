package cn.wfxxkj.teacher.paper;

import android.content.Context;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Charts;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 组卷首页（底部「组卷」标签）：卷头、卷面结构（题量/分值加减器）、抽题条件、
 * 实时的抽题预览（preview-plan）和最近组卷；底部常驻「生成试卷」。
 * 手机上一列往下滚；宽屏左边设置、右边预览和历史。
 */
final class ComposeScreen extends Screen {

    private FrameLayout body;
    private StateView state;
    private Blueprint bp;
    private BlueprintEditor editor;

    // 底部栏
    private TextView barMain, barSub;
    private TextView generateBtn;

    // 预览卡
    private TextView planSummary;
    private Charts.HBars planBars;
    private LinearLayout planShort;
    private int planSeq;
    private final Runnable planTask = this::refreshPlan;

    // 最近组卷
    private LinearLayout recentBox;
    private TextView recentAll;

    @Override
    public String title() {
        return "组卷";
    }

    @Override
    public String subtitle() {
        return bp == null ? null : (bp.bySections ? "按卷面结构 · 六大题" : "按题型自由组卷");
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_history, "组卷历史", () -> push(new HistoryScreen())));
        if (bp != null) {
            a.add(Action.menu(R.drawable.ic_restart_alt, "题量和分值恢复默认", () -> {
                bp.resetBlueprint();
                editor.syncFromModel();
                onBlueprintChanged();
            }));
            a.add(Action.menu(R.drawable.ic_refresh, "全部设置恢复默认", () ->
                    Dialogs.confirm(ctx(), "全部恢复默认？", "卷头、题量、分值、知识范围和选项都回到学校配置的默认值。",
                            "恢复", false, () -> {
                                bp.resetAll();
                                build();
                            })));
        }
        return a;
    }

    @Override
    protected View onCreateView(Context c) {
        LinearLayout root = V.vbox(c);
        root.setBackgroundColor(Palette.of(c).page);
        body = new FrameLayout(c);
        root.addView(body, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));
        state = new StateView(c);
        body.addView(state, new FrameLayout.LayoutParams(V.MATCH, V.WRAP, Gravity.TOP));
        root.addView(bottomBar(c));
        return root;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    @Override
    protected void onShow() {
        if (bp != null) loadRecent();
    }

    @Override
    protected void onDestroy() {
        main().removeCallbacks(planTask);
    }

    private void load() {
        state.loading();
        V.enable(generateBtn, false);
        run(() -> new Blueprint(PaperApi.config(), PaperApi.dicts()), b -> {
            bp = b;
            if (!b.numerals.isEmpty()) PaperScreen.numerals = new ArrayList<>(b.numerals);
            build();
            invalidateChrome();
        }, e -> {
            state.error(e.getMessage(), this::load);
            return true;
        });
    }

    // ---------- 搭界面 ----------

    private void build() {
        Context c = ctx();
        body.removeAllViews();
        editor = new BlueprintEditor(c, bp, this::onBlueprintChanged);

        View head = headCard(c);
        View structure = structureCard(c);
        View options = optionsCard(c);
        View plan = planCard(c);
        View recent = recentCard(c);

        if (wide()) {
            LinearLayout cols = V.hbox(c);
            cols.setGravity(Gravity.TOP);
            LinearLayout left = column(c, 24, 12);
            addCard(left, head);
            addCard(left, structure);
            addCard(left, options);
            LinearLayout right = column(c, 12, 24);
            addCard(right, plan);
            addCard(right, recent);
            cols.addView(V.scroll(c, left), new LinearLayout.LayoutParams(0, V.MATCH, 1.25f));
            cols.addView(V.scroll(c, right), new LinearLayout.LayoutParams(0, V.MATCH, 1f));
            body.addView(cols, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        } else {
            LinearLayout page = V.page(c);
            page.setPadding(page.getPaddingLeft(), page.getPaddingTop(), page.getPaddingRight(), Ui.dp(c, 24));
            addCard(page, head);
            addCard(page, structure);
            addCard(page, plan);
            addCard(page, options);
            addCard(page, recent);
            ScrollView sv = V.scroll(c, page);
            body.addView(sv, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        }
        V.enable(generateBtn, true);
        renderBar();
        schedulePlan(0);
        loadRecent();
    }

    private static LinearLayout column(Context c, int startDp, int endDp) {
        LinearLayout l = V.vbox(c);
        l.setPadding(Ui.dp(c, startDp), Ui.dp(c, 12), Ui.dp(c, endDp), Ui.dp(c, 24));
        return l;
    }

    private static void addCard(LinearLayout parent, View card) {
        LinearLayout.LayoutParams lp = V.matchWrap();
        lp.bottomMargin = Ui.dp(parent.getContext(), 12);
        parent.addView(card, lp);
    }

    /** 卡片标题：图标 + 标题 + 小字说明 */
    static LinearLayout cardTitle(Context c, int icon, Tone tone, String title, String sub) {
        LinearLayout row = V.hbox(c);
        row.addView(V.iconTile(c, icon, tone));
        LinearLayout texts = V.vbox(c);
        texts.addView(V.text(c, title, V.H3));
        if (sub != null) texts.addView(V.text(c, sub, V.CAPTION));
        LinearLayout.LayoutParams lp = V.fill();
        lp.setMarginStart(Ui.dp(c, 12));
        row.addView(texts, lp);
        V.pad(row, 0, 0, 0, 14);
        return row;
    }

    private View headCard(Context c) {
        LinearLayout card = V.card(c);
        card.addView(cardTitle(c, R.drawable.ic_description, Tone.PRIMARY, "卷头", "印在试卷最上方"));
        Form f = new Form(c);
        Form.Text title = f.text("试卷标题", bp.title).required();
        title.onChange(() -> bp.title = title.value());
        Form.Text school = f.text("学校", bp.school, "印在卷头，可留空");
        school.onChange(() -> bp.school = school.value());
        Form.Text dur = f.number("考试时长（分钟）", null, false);
        dur.set(bp.duration);
        dur.hint("例如 40，可留空");
        dur.onChange(() -> bp.duration = dur.value());
        f.row(school, dur);
        trimLastMargin(f);
        card.addView(f.view());
        return card;
    }

    private View structureCard(Context c) {
        LinearLayout card = V.card(c);
        card.addView(cardTitle(c, R.drawable.ic_assignment, Tone.VIOLET, "卷面结构", wide() ? "调题量和分值，右侧实时预览" : "调题量和分值，下方实时预览"));
        if (!bp.sections.isEmpty()) {
            Form f = new Form(c);
            final Form.Choice mode = f.choice(null, Option.pairs(true, "六大题（赋分）", false, "按题型"), bp.bySections);
            mode.onChange(() -> {
                bp.bySections = Boolean.TRUE.equals(mode.value());
                editor.renderMode();
                invalidateChrome();
                onBlueprintChanged();
            });
            card.addView(f.view());
        }
        card.addView(editor.view());
        return card;
    }

    private View optionsCard(Context c) {
        LinearLayout card = V.card(c);
        card.addView(cardTitle(c, R.drawable.ic_tune, Tone.INFO, "抽题条件", null));
        Form f = new Form(c);
        final Form.Multi scopes = f.multi("知识范围", Option.of(bp.scopes.toArray(new String[0])), bp.pickedScopes)
                .placeholder("不选表示全部 " + bp.scopes.size() + " 类");
        if (bp.bySections) scopes.help("只作用于没限定范围的那几组；限定了范围的组仍按各自的范围抽。");
        scopes.onChange(() -> {
            bp.pickedScopes.clear();
            for (Object o : scopes.values()) bp.pickedScopes.add(String.valueOf(o));
            onBlueprintChanged();
        });
        final Form.Text seed = f.text("随机种子", bp.seed, "填了可复现同一套卷子");
        seed.onChange(() -> bp.seed = seed.value());
        f.section("选项").setTextSize(14);
        final Form.Toggle shuffle = f.toggle("选择判断题乱序",
                "每个学生的选择题、判断题顺序各不相同，选项也打乱（答案自动跟随）；只在同一大题里换，操作题不动",
                bp.shuffleOptions);
        shuffle.onChange(() -> bp.shuffleOptions = shuffle.value());
        final Form.Toggle require = f.toggle("跳过原卷未给答案的题目", null, bp.requireAnswer);
        require.onChange(() -> {
            bp.requireAnswer = require.value();
            onBlueprintChanged();
        });
        final Form.Toggle pinned = f.toggle("优先放入题库里的必出题", null, bp.usePinned);
        pinned.onChange(() -> bp.usePinned = pinned.value());
        final Form.Toggle save = f.toggle("把这套卷子存档", "存档后出现在组卷历史里，可以再打开、发布考试", bp.save);
        save.onChange(() -> bp.save = save.value());
        trimLastMargin(f);
        card.addView(f.view());
        return card;
    }

    /** Form 每项下面都留 16dp，最后一项放在卡片里就多了，去掉 */
    private static void trimLastMargin(Form f) {
        LinearLayout l = f.layout();
        if (l.getChildCount() == 0) return;
        View last = l.getChildAt(l.getChildCount() - 1);
        if (last.getLayoutParams() instanceof LinearLayout.LayoutParams) {
            ((LinearLayout.LayoutParams) last.getLayoutParams()).bottomMargin = 0;
        }
    }

    private View planCard(Context c) {
        LinearLayout card = V.card(c);
        card.addView(cardTitle(c, R.drawable.ic_bar_chart, Tone.SUCCESS, "抽题预览", "本次抽题的知识范围分布"));
        planSummary = V.text(c, "正在计算…", V.BODY2);
        card.addView(planSummary);
        planBars = new Charts.HBars(c);
        planBars.setColor(Palette.of(c).primary);
        V.addTop(card, planBars, 10);
        planShort = V.vbox(c);
        card.addView(planShort);
        V.addTop(card, V.text(c, "抽题在各知识范围之间轮流分配名额，某个范围题目不够时名额自动让给其他范围。", V.CAPTION), 10);
        return card;
    }

    private View recentCard(Context c) {
        LinearLayout card = V.card(c);
        V.pad(card, 0, 16, 0, 8);
        LinearLayout head = cardTitle(c, R.drawable.ic_history, Tone.WARNING, "最近组卷", "存档的试卷可以再次打开、导出");
        V.pad(head, 16, 0, 8, 6);
        recentAll = V.button(c, "全部", V.BTN_TEXT, v -> push(new HistoryScreen()));
        head.addView(recentAll);
        card.addView(head);
        recentBox = V.vbox(c);
        card.addView(recentBox);
        return card;
    }

    // ---------- 数据 ----------

    private void onBlueprintChanged() {
        renderBar();
        schedulePlan(350);
    }

    private void schedulePlan(long delay) {
        main().removeCallbacks(planTask);
        main().postDelayed(planTask, delay);
    }

    private void refreshPlan() {
        if (isDestroyed() || bp == null) return;
        final int seq = ++planSeq;
        final JSONObject payload = bp.payload();
        if (planSummary != null) planSummary.setText("正在计算…");
        run(() -> PaperApi.previewPlan(payload), plan -> {
            if (seq == planSeq) renderPlan(plan);
        }, e -> {
            if (seq == planSeq && planSummary != null) planSummary.setText("预览失败：" + e.getMessage());
            return true;
        });
    }

    private void renderPlan(JSONObject plan) {
        Context c = ctx();
        Palette p = Palette.of(c);
        int total = Json.num(plan, "total");
        int full = Json.num(plan, "full_score");
        planSummary.setText(total == 0 ? "把题量调大于 0" : "共 " + total + " 题" + (full > 0 ? "，满分 " + full + " 分" : ""));
        List<Charts.Point> pts = new ArrayList<>();
        JSONObject tally = Json.obj(plan, "tally");
        java.util.Iterator<String> it = tally.keys();
        while (it.hasNext()) {
            String k = it.next();
            int v = tally.optInt(k, 0);
            pts.add(new Charts.Point(k, v, v > 0 ? 0 : p.text3, String.valueOf(v)));
        }
        planBars.setData(pts);
        planShort.removeAllViews();
        for (String w : Json.strings(Json.arr(plan, "shortfall"))) {
            TextView t = V.notice(c, w, Tone.WARNING);
            t.setTextSize(13);
            V.addTop(planShort, t, 8);
        }
        editor.applyPlan(plan);
        // 底部栏也说一声够不够
        int shortN = Json.arr(plan, "shortfall").length();
        barSub.setText(shortN > 0 ? "有 " + shortN + " 处题库不够，会少抽" : "题库题量充足");
        barSub.setTextColor(shortN > 0 ? p.warning : p.success);
    }

    private void loadRecent() {
        run(PaperApi::papers, list -> {
            if (recentBox == null) return;
            Context c = ctx();
            recentBox.removeAllViews();
            recentAll.setText(list.isEmpty() ? "全部" : "全部 " + list.size());
            if (list.isEmpty()) {
                TextView t = V.text(c, "还没有存档的试卷。勾选「把这套卷子存档」后会出现在这里。", V.BODY2);
                V.pad(t, 16, 4, 16, 12);
                recentBox.addView(t);
                return;
            }
            for (int i = 0; i < Math.min(4, list.size()); i++) {
                final JSONObject row = list.get(i);
                String sub = Json.str(row, "code") + " · " + Json.num(row, "question_count") + " 题";
                LinearLayout r = V.row(c, R.drawable.ic_description, Tone.PRIMARY, Json.str(row, "title"), sub,
                        Fmt.shortDateTime(Json.str(row, "created_at")),
                        v -> push(PaperScreen.open(row.optLong("id"), Json.str(row, "title"))));
                recentBox.addView(r);
            }
        }, e -> true);
    }

    // ---------- 底部栏 ----------

    private View bottomBar(Context c) {
        Palette p = Palette.of(c);
        LinearLayout wrap = V.vbox(c);
        wrap.setBackgroundColor(p.surface);
        wrap.addView(V.divider(c));
        LinearLayout bar = V.hbox(c);
        int side = Ui.dp(c, wide() ? 24 : 16);
        bar.setPadding(side, Ui.dp(c, 10), side, Ui.dp(c, 10));
        LinearLayout texts = V.vbox(c);
        barMain = V.oneLine(V.text(c, "", V.H3));
        barSub = V.oneLine(V.text(c, "", V.CAPTION));
        texts.addView(barMain);
        texts.addView(barSub);
        bar.addView(texts, V.fill());
        generateBtn = V.button(c, R.drawable.ic_shuffle, "生成试卷", V.BTN_PRIMARY, v -> generate());
        generateBtn.setMinWidth(Ui.dp(c, 140));
        bar.addView(generateBtn);
        wrap.addView(bar);
        return wrap;
    }

    private void renderBar() {
        if (bp == null) return;
        int n = bp.plannedCount();
        if (bp.bySections) barMain.setText(n + " 题 · " + bp.plannedFull() + " 分");
        else barMain.setText(n + " 题（不赋分）");
        if (TextUtils.isEmpty(barSub.getText())) barSub.setText("正在核对题库…");
    }

    private void generate() {
        if (bp == null) return;
        Ui.hideKeyboard(body);
        if (TextUtils.isEmpty(bp.title == null ? null : bp.title.trim())) {
            toast("请填写试卷标题");
            return;
        }
        if (bp.plannedCount() == 0) {
            toast("题量都是 0，先把题量调大于 0");
            return;
        }
        final JSONObject payload = bp.payload();
        final boolean saved = bp.save;
        runBusy("正在抽题组卷…", () -> PaperApi.generate(payload), paper -> {
            List<String> warn = Json.strings(Json.arr(paper, "warnings"));
            if (warn.isEmpty()) toast("抽到 " + Json.num(paper, "total") + " 道题" + (saved ? "，已存档" : ""));
            push(new PaperScreen(paper, payload));
            if (saved) loadRecent();
        });
    }
}
