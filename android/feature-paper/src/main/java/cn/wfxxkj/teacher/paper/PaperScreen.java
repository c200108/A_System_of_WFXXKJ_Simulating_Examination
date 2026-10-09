package cn.wfxxkj.teacher.paper;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Charts;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 试卷预览：卷头大卡 + 常用操作（换一批、导出 Excel、学生答题网页、打印/PDF、存档）+
 * 三种看法（试卷 / 答案卷 / 在线自测）。试卷模式可以一键显隐答案。
 * 生成后从组卷首页压进来，也可以从组卷历史打开。宽屏左边卷头和操作，右边卷面。
 */
final class PaperScreen extends Screen {

    private static final int MODE_PAPER = 0, MODE_KEY = 1, MODE_QUIZ = 2;

    /** 大题序号，组卷首页读到配置后会换成学校配置的那套 */
    static List<String> numerals = new ArrayList<>(Arrays.asList("一", "二", "三", "四", "五", "六", "七", "八", "九", "十"));

    private JSONObject paper;
    /** 生成这份卷子用的设置（从历史打开的为 null，不能「换一批」） */
    private final JSONObject payload;
    private final long loadId;
    private final String loadTitle;

    private int mode = MODE_PAPER;
    private boolean showAnswers;
    private final Quiz quiz = new Quiz();

    private FrameLayout body;
    private StateView state;
    private LinearLayout content;
    private LinearLayout scoreBar;
    private TextView answerChip;
    private ScrollView mainScroll;
    private View modeRow;

    /** 刚生成的卷子 */
    PaperScreen(JSONObject paper, JSONObject payload) {
        this.paper = paper;
        this.payload = payload;
        this.loadId = 0;
        this.loadTitle = Json.str(paper, "title");
    }

    private PaperScreen(long id, String title) {
        this.payload = null;
        this.loadId = id;
        this.loadTitle = title;
    }

    /** 打开一份存档的试卷 */
    static PaperScreen open(long id, String title) {
        return new PaperScreen(id, title);
    }

    @Override
    public String title() {
        return "试卷预览";
    }

    @Override
    public String subtitle() {
        if (paper == null) return loadTitle;
        return Json.str(paper, "code") + " · " + Json.num(paper, "total") + " 题";
    }

    private long paperId() {
        return paper == null ? 0 : paper.optLong("paper_id", 0);
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (paper == null) return a;
        if (mode == MODE_PAPER) {
            a.add(Action.icon(showAnswers ? R.drawable.ic_visibility_off : R.drawable.ic_visibility,
                    showAnswers ? "隐藏答案" : "显示答案", this::toggleAnswers));
        }
        a.add(Action.icon(R.drawable.ic_share, "导出与分享", this::exportMenu));
        if (payload != null) a.add(Action.menu(R.drawable.ic_shuffle, "换一批", this::regenerate));
        if (paperId() == 0 && payload != null) a.add(Action.menu(R.drawable.ic_inbox, "存档这套卷子", this::archive));
        a.add(Action.menu(R.drawable.ic_content_copy, "复制卷号", () -> {
            Sys.copy(ctx(), "卷号", Json.str(paper, "code"));
            toast("已复制卷号 " + Json.str(paper, "code"));
        }));
        if (paperId() > 0) a.add(Action.menu(R.drawable.ic_delete, "删除这份试卷", this::delete).danger());
        return a;
    }

    @Override
    public boolean onBack() {
        // 自测做了一半，返回前确认一下
        if (mode == MODE_QUIZ && !quiz.graded && !quiz.resp.isEmpty()) {
            Dialogs.confirm(ctx(), "退出自测？", "已经作答的内容不会保存。", "退出", true, this::finish);
            return true;
        }
        return false;
    }

    @Override
    protected View onCreateView(Context c) {
        body = new FrameLayout(c);
        body.setBackgroundColor(Palette.of(c).page);
        state = new StateView(c);
        body.addView(state, new FrameLayout.LayoutParams(V.MATCH, V.WRAP, Gravity.TOP));
        if (paper != null) build();
        return body;
    }

    @Override
    protected void onFirstShow() {
        if (paper == null) load();
    }

    private void load() {
        state.loading();
        run(() -> PaperApi.paper(loadId), p -> {
            paper = p;
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
        content = V.vbox(c);
        scoreBar = V.vbox(c);
        modeRow = modeRow(c);

        if (wide()) {
            LinearLayout cols = V.hbox(c);
            cols.setGravity(Gravity.TOP);
            LinearLayout side = V.vbox(c);
            side.setPadding(Ui.dp(c, 24), Ui.dp(c, 12), Ui.dp(c, 12), Ui.dp(c, 24));
            side.addView(hero(c));
            V.addTop(side, tools(c), 12);
            addWarnings(c, side);
            V.addTop(side, tallyCard(c), 12);
            cols.addView(V.scroll(c, side), new LinearLayout.LayoutParams(Ui.dp(c, Ui.sizeClass(c) == Ui.EXPANDED ? 400 : 320), V.MATCH));
            LinearLayout main = V.page(c);
            main.setPadding(Ui.dp(c, 12), Ui.dp(c, 12), Ui.dp(c, 24), Ui.dp(c, 48));
            main.addView(modeRow);
            main.addView(scoreBar);
            main.addView(content);
            mainScroll = V.scroll(c, main);
            cols.addView(mainScroll, new LinearLayout.LayoutParams(0, V.MATCH, 1f));
            body.addView(cols, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        } else {
            LinearLayout page = V.page(c);
            page.setPadding(page.getPaddingLeft(), page.getPaddingTop(), page.getPaddingRight(), Ui.dp(c, 48));
            page.addView(hero(c));
            V.addTop(page, tools(c), 12);
            addWarnings(c, page);
            V.addTop(page, modeRow, 12);
            page.addView(scoreBar);
            page.addView(content);
            mainScroll = V.scroll(c, page);
            body.addView(mainScroll, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        }
        renderContent();
    }

    /** 卷头大卡：标题、学校/时长/卷号、三个数字 */
    private View hero(Context c) {
        Palette p = Palette.of(c);
        LinearLayout card = V.vbox(c);
        GradientDrawable bg = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{p.primary, p.primaryPressed});
        bg.setCornerRadius(Ui.dpf(c, 20));
        card.setBackground(bg);
        V.pad(card, 20, 18, 20, 18);

        LinearLayout top = V.hbox(c);
        TextView tag = V.text(c, paperId() > 0 ? "已存档" : "未存档", V.CAPTION);
        tag.setTextColor(0xFFFFFFFF);
        tag.setBackground(V.round(c, 0x33FFFFFF, 10));
        V.pad(tag, 8, 2, 8, 2);
        top.addView(tag);
        top.addView(V.spring(c));
        TextView code = V.text(c, Json.str(paper, "code"), V.CAPTION);
        code.setTextColor(0xDDFFFFFF);
        top.addView(code);
        card.addView(top);

        TextView title = V.text(c, Json.str(paper, "title"), V.H2);
        title.setTextColor(0xFFFFFFFF);
        V.addTop(card, title, 10);
        List<String> meta = new ArrayList<>();
        if (!Json.str(paper, "school").isEmpty()) meta.add(Json.str(paper, "school"));
        if (!Json.str(paper, "duration").isEmpty()) meta.add("考试时长 " + Json.str(paper, "duration") + " 分钟");
        if (!meta.isEmpty()) {
            TextView m = V.text(c, TextUtils.join("  ·  ", meta), V.BODY2);
            m.setTextColor(0xDDFFFFFF);
            V.addTop(card, m, 4);
        }

        LinearLayout stats = V.hbox(c);
        int full = Json.num(paper, "full_score");
        stats.addView(heroStat(c, String.valueOf(Json.num(paper, "total")), "题"), V.weight(1));
        stats.addView(heroStat(c, full > 0 ? String.valueOf(full) : "—", full > 0 ? "满分" : "不赋分"), V.weight(1));
        stats.addView(heroStat(c, String.valueOf(Json.arr(paper, "groups").length()), "大题"), V.weight(1));
        V.addTop(card, stats, 16);
        return card;
    }

    private static View heroStat(Context c, String n, String label) {
        LinearLayout b = V.vbox(c);
        TextView t = V.text(c, n, V.DISPLAY);
        t.setTextColor(0xFFFFFFFF);
        b.addView(t);
        TextView l = V.text(c, label, V.CAPTION);
        l.setTextColor(0xCCFFFFFF);
        b.addView(l);
        return b;
    }

    /** 常用操作：一排图标按钮 */
    private View tools(Context c) {
        GridBox g = new GridBox(c, 64, 5, 8);
        LinearLayout card = V.card(c);
        V.pad(card, 8, 12, 8, 10);
        if (payload != null) g.addView(tool(c, R.drawable.ic_shuffle, "换一批", Tone.PRIMARY, this::regenerate));
        g.addView(tool(c, R.drawable.ic_table_view, "导出 Excel", Tone.SUCCESS, () -> Exporter.xlsx(this, paper)));
        g.addView(tool(c, R.drawable.ic_quiz, "学生网页", Tone.VIOLET, () -> Exporter.studentHtml(this, paper)));
        g.addView(tool(c, R.drawable.ic_print, "打印 / PDF", Tone.INFO, this::printMenu));
        if (paperId() == 0 && payload != null) g.addView(tool(c, R.drawable.ic_inbox, "存档", Tone.WARNING, this::archive));
        card.addView(g);
        return card;
    }

    private static View tool(Context c, int icon, String label, Tone tone, Runnable r) {
        LinearLayout b = V.vbox(c);
        b.setGravity(Gravity.CENTER_HORIZONTAL);
        V.pad(b, 2, 8, 2, 6);
        b.addView(V.iconTile(c, icon, tone));
        TextView t = V.text(c, label, V.CAPTION);
        t.setTextColor(Palette.of(c).text2);
        t.setGravity(Gravity.CENTER);
        t.setMaxLines(2);
        V.addTop(b, t, 6);
        ((LinearLayout.LayoutParams) t.getLayoutParams()).width = V.WRAP;
        V.clickable(b, 12, v -> r.run());
        return b;
    }

    private void addWarnings(Context c, LinearLayout parent) {
        List<String> w = Json.strings(Json.arr(paper, "warnings"));
        if (w.isEmpty()) return;
        V.addTop(parent, V.notice(c, "题库不够，少抽了一些：\n· " + TextUtils.join("\n· ", w), Tone.WARNING), 12);
    }

    private View tallyCard(Context c) {
        LinearLayout card = V.card(c);
        card.addView(ComposeScreen.cardTitle(c, R.drawable.ic_bar_chart, Tone.SUCCESS, "知识范围分布", null));
        List<Charts.Point> pts = new ArrayList<>();
        JSONObject tally = Json.obj(paper, "tally");
        java.util.Iterator<String> it = tally.keys();
        while (it.hasNext()) {
            String k = it.next();
            int v = tally.optInt(k, 0);
            pts.add(new Charts.Point(k, v, v > 0 ? 0 : Palette.of(c).text3, String.valueOf(v)));
        }
        card.addView(new Charts.HBars(c).setData(pts));
        return card;
    }

    /** 试卷 / 答案卷 / 在线自测 + 「答案」开关 */
    private View modeRow(Context c) {
        LinearLayout row = V.hbox(c);
        ChipRow chips = new ChipRow(c);
        chips.setOptions(Option.pairs(MODE_PAPER, "试卷", MODE_KEY, "答案卷", MODE_QUIZ, "在线自测"), mode);
        chips.setOnPicked(o -> switchMode((Integer) o.value));
        row.addView(chips, V.fill());
        answerChip = V.chip(c, "显示答案", showAnswers, v -> toggleAnswers());
        V.addStart(row, answerChip, 8);
        V.pad(row, 0, 0, 0, 4);
        return row;
    }

    private void switchMode(int m) {
        if (m == mode) return;
        if (mode == MODE_QUIZ && !quiz.graded && !quiz.resp.isEmpty()) {
            final int target = m;
            Dialogs.confirm(ctx(), "离开在线自测？", "已经作答的内容会清空。", "离开", true, () -> {
                quiz.reset();
                mode = target;
                renderContent();
                invalidateChrome();
            });
            // 先把选中状态拨回去，确认了再切
            ((ChipRow) ((LinearLayout) modeRow).getChildAt(0)).set(mode);
            return;
        }
        mode = m;
        if (m == MODE_QUIZ) quiz.reset();
        renderContent();
        invalidateChrome();
    }

    private void toggleAnswers() {
        if (mode != MODE_PAPER) return;
        showAnswers = !showAnswers;
        renderContent();
        invalidateChrome();
    }

    // ---------- 卷面 ----------

    private void renderContent() {
        Context c = ctx();
        ((ChipRow) ((LinearLayout) modeRow).getChildAt(0)).set(mode);
        answerChip.setVisibility(mode == MODE_PAPER ? View.VISIBLE : View.GONE);
        V.setChip(answerChip, showAnswers);
        renderScoreBar(c);
        content.removeAllViews();
        if (mode == MODE_KEY) {
            renderKey(c);
            return;
        }
        int n = 0, gi = 0;
        for (JSONObject g : Json.list(Json.arr(paper, "groups"))) {
            List<JSONObject> items = Json.list(Json.arr(g, "items"));
            content.addView(QuestionCard.sectionHeader(c, numeral(gi++), g, sectionHint(items, mode == MODE_QUIZ)));
            for (JSONObject q : items) {
                QuestionCard card = new QuestionCard(c, q, ++n, showAnswers, mode == MODE_QUIZ ? quiz : null);
                LinearLayout.LayoutParams lp = V.matchWrap();
                lp.bottomMargin = Ui.dp(c, 10);
                content.addView(card, lp);
            }
        }
        if (mode == MODE_QUIZ && !quiz.graded) {
            TextView submit = V.button(c, R.drawable.ic_done_all, "交卷判分", V.BTN_PRIMARY, v -> submitQuiz());
            V.addTop(content, submit, 8);
        }
    }

    private String numeral(int i) {
        return i < numerals.size() ? numerals.get(i) : String.valueOf(i + 1);
    }

    /** 大题下面那行小字。一个大题里可能两种题型都有，按实际内容说 */
    static String sectionHint(List<JSONObject> items, boolean quizMode) {
        boolean hasOp = false, hasPick = false;
        for (JSONObject q : items) {
            if (Quiz.OP.equals(Json.str(q, "type"))) hasOp = true;
            else hasPick = true;
        }
        if (quizMode) {
            if (hasOp && hasPick) return "选择题自动判分；操作题写下步骤，交卷后对照答案要点自评。";
            return hasOp ? "写下操作步骤，交卷后对照答案要点自评。" : "直接在下面选择，交卷后自动判分。";
        }
        if (hasOp && hasPick) return "选择题把答案写在题号前的括号里；操作题在计算机上完成。";
        return hasOp ? "按题目要求在计算机上完成操作。" : "把答案写在题号前的括号里。";
    }

    /** 答案卷：选择判断排成小格子，操作题列出答案要点 */
    private void renderKey(Context c) {
        Palette p = Palette.of(c);
        int n = 0, gi = 0;
        for (JSONObject g : Json.list(Json.arr(paper, "groups"))) {
            List<JSONObject> items = Json.list(Json.arr(g, "items"));
            content.addView(QuestionCard.sectionHeader(c, numeral(gi++), g, null));
            boolean allOp = true;
            for (JSONObject q : items) if (!Quiz.OP.equals(Json.str(q, "type"))) allOp = false;
            LinearLayout card = V.card(c);
            V.pad(card, 14, 14, 14, 14);
            if (allOp) {
                for (JSONObject q : items) {
                    LinearLayout ai = V.vbox(c);
                    TextView h = V.text(c, "第 " + (++n) + " 题　" + Json.str(q, "scope"), V.LABEL);
                    ai.addView(h);
                    String a = Json.str(q, "answer");
                    TextView body = V.text(c, a.isEmpty() ? "原卷未给答案" : a, V.BODY);
                    if (a.isEmpty()) body.setTextColor(p.warning);
                    body.setTextIsSelectable(true);
                    V.addTop(ai, body, 4);
                    ai.setBackground(V.round(c, p.surfaceAlt, 10));
                    V.pad(ai, 12, 10, 12, 10);
                    LinearLayout.LayoutParams lp = V.matchWrap();
                    if (card.getChildCount() > 0) lp.topMargin = Ui.dp(c, 8);
                    card.addView(ai, lp);
                }
            } else {
                FlowBox flow = new FlowBox(c, 8, 8);
                for (JSONObject q : items) {
                    LinearLayout cell = V.hbox(c);
                    cell.setGravity(Gravity.CENTER);
                    cell.setMinimumWidth(Ui.dp(c, 68));
                    cell.setBackground(V.stroke(c, p.surfaceAlt, p.border, 8));
                    V.pad(cell, 10, 5, 10, 5);
                    cell.addView(V.text(c, String.valueOf(++n), V.CAPTION));
                    String a = Json.str(q, "answer");
                    TextView av;
                    if (Quiz.OP.equals(Json.str(q, "type"))) {
                        av = V.text(c, "人工阅", V.LABEL);
                        av.setTextColor(p.warning);
                    } else {
                        av = V.text(c, a.isEmpty() ? "—" : a, V.H3);
                        av.setTextColor(a.isEmpty() ? p.text3 : p.success);
                    }
                    V.addStart(cell, av, 8);
                    flow.addView(cell);
                }
                card.addView(flow);
            }
            LinearLayout.LayoutParams lp = V.matchWrap();
            lp.bottomMargin = Ui.dp(c, 4);
            content.addView(card, lp);
        }
    }

    // ---------- 在线自测 ----------

    private void renderScoreBar(Context c) {
        scoreBar.removeAllViews();
        if (mode != MODE_QUIZ) return;
        Palette p = Palette.of(c);
        LinearLayout card = V.hbox(c);
        card.setBackground(V.stroke(c, p.primarySoft, p.primarySoft, 16));
        V.pad(card, 16, 14, 12, 14);
        LinearLayout texts = V.vbox(c);
        TextView t, sub;
        if (!quiz.graded) {
            t = V.text(c, "在线自测", V.H3);
            sub = V.text(c, "选择题、判断题自动判分；操作题交卷后对照答案要点自评。", V.CAPTION);
        } else if (quiz.full > 0) {
            t = V.text(c, android.text.Html.fromHtml("客观题得分 <font color='" + hex(p.primary) + "'><big><b>"
                    + quiz.got + " / " + quiz.full + "</b></big></font> 分", android.text.Html.FROM_HTML_MODE_COMPACT), V.H3);
            sub = V.text(c, "答对 " + quiz.right + " / " + quiz.obj + " 题  ·  "
                    + (quiz.manual > 0 ? "还有 " + quiz.manual + " 分的操作题，请对照答案要点自评" : "这份卷子没有操作题"), V.CAPTION);
        } else {
            int pct = quiz.obj > 0 ? Math.round(quiz.right * 100f / quiz.obj) : 0;
            t = V.text(c, android.text.Html.fromHtml("客观题答对 <font color='" + hex(p.primary) + "'><big><b>"
                    + quiz.right + " / " + quiz.obj + "</b></big></font>", android.text.Html.FROM_HTML_MODE_COMPACT), V.H3);
            sub = V.text(c, "正确率 " + pct + "%  ·  操作题请对照答案要点自评", V.CAPTION);
        }
        texts.addView(t);
        V.addTop(texts, sub, 2);
        card.addView(texts, V.fill());
        TextView btn = quiz.graded
                ? V.button(c, R.drawable.ic_restart_alt, "重新作答", V.BTN_OUTLINE, v -> {
                    quiz.reset();
                    renderContent();
                })
                : V.button(c, "交卷", V.BTN_PRIMARY, v -> submitQuiz());
        V.addStart(card, btn, 8);
        LinearLayout.LayoutParams lp = V.matchWrap();
        lp.topMargin = Ui.dp(c, 8);
        scoreBar.addView(card, lp);
    }

    private static String hex(int color) {
        return String.format("#%06X", color & 0xFFFFFF);
    }

    private void submitQuiz() {
        int answered = 0, need = 0;
        for (JSONObject g : Json.list(Json.arr(paper, "groups"))) {
            for (JSONObject q : Json.list(Json.arr(g, "items"))) {
                if (Quiz.OP.equals(Json.str(q, "type"))) continue;
                need++;
                if (quiz.resp.containsKey(q.optLong("id"))) answered++;
            }
        }
        Runnable go = () -> {
            quiz.submit(paper);
            renderContent();
            mainScroll.post(() -> mainScroll.smoothScrollTo(0, Math.max(0, modeRow.getTop() - Ui.dp(ctx(), 8))));
        };
        if (answered < need) {
            Dialogs.confirm(ctx(), "还有 " + (need - answered) + " 道没作答", "没作答的题按答错算。确定交卷？", "交卷", false, go);
        } else {
            go.run();
        }
    }

    // ---------- 操作 ----------

    private void exportMenu() {
        List<Action> a = new ArrayList<>();
        a.add(Action.menu(R.drawable.ic_table_view, "导出本卷 Excel", () -> Exporter.xlsx(this, paper)));
        a.add(Action.menu(R.drawable.ic_quiz, "导出学生答题网页（可直接发给学生）", () -> Exporter.studentHtml(this, paper)));
        a.add(Action.menu(R.drawable.ic_print, "打印试卷 / 存 PDF", () -> PrintDoc.print(activity(), paper, false, numerals)));
        a.add(Action.menu(R.drawable.ic_print, "打印答案卷 / 存 PDF", () -> PrintDoc.print(activity(), paper, true, numerals)));
        Dialogs.actions(ctx(), "导出与分享", a);
    }

    private void printMenu() {
        List<Action> a = new ArrayList<>();
        a.add(Action.menu(R.drawable.ic_description, "试卷（带班级、姓名栏）", () -> PrintDoc.print(activity(), paper, false, numerals)));
        a.add(Action.menu(R.drawable.ic_key, "答案卷", () -> PrintDoc.print(activity(), paper, true, numerals)));
        Dialogs.actions(ctx(), "打印 / 存 PDF（在打印页选「另存为 PDF」）", a);
    }

    /** 换一批：同样的设置、新的随机种子 */
    private void regenerate() {
        if (payload == null) return;
        final JSONObject req = Json.copy(payload);
        Json.put(req, "seed", null);
        runBusy("正在换一批…", () -> PaperApi.generate(req), p -> {
            paper = p;
            quiz.reset();
            List<String> warn = Json.strings(Json.arr(p, "warnings"));
            toast(warn.isEmpty() ? "换好了，抽到 " + Json.num(p, "total") + " 道题" : "换好了，但题库不够，少抽了一些");
            build();
            invalidateChrome();
        });
    }

    /** 存档：用同一个随机种子再组一次并保存，抽到的题和顺序完全一样 */
    private void archive() {
        if (payload == null || paperId() > 0) return;
        final JSONObject req = Json.copy(payload);
        Json.put(req, "seed", Json.str(paper, "seed"));
        Json.put(req, "save", true);
        Json.put(req, "title", Json.str(paper, "title"));
        runBusy("正在存档…", () -> PaperApi.generate(req), p -> {
            if (!Json.str(p, "code").isEmpty()) paper = p;
            toast("已存档，可在组卷历史里找到");
            build();
            invalidateChrome();
        });
    }

    private void delete() {
        final long id = paperId();
        Dialogs.confirm(ctx(), "删除这份试卷？", "确定删除《" + Json.str(paper, "title") + "》？删除后不能恢复。",
                "删除", true, () -> runBusy("正在删除…", () -> {
                    PaperApi.delete(id);
                    return true;
                }, ok -> {
                    toast("已删除");
                    finish("deleted");
                }));
    }
}
