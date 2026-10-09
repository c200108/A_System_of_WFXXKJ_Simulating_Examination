package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Printer;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 打字学情分析（对应网页 TypingAnalysis.vue）。
 *
 * <ul>
 *   <li>看什么：模块（中文 / 英文 / 键盘 / 全部）× 时间（近 7 / 30 / 90 天 / 全部）；</li>
 *   <li>看谁：全体 / 某几个班 / 选几个学生对比（最多 8 人）；</li>
 *   <li>页面开着时每 30 秒自动重取一次（可在菜单里关），学生在练，这边的图和结论自己会变；</li>
 *   <li>结论是服务端按数据写的，这里只负责画；每张图都能展开「看数据」；</li>
 *   <li>打印 / 另存 PDF、分享结论。</li>
 * </ul>
 */
final class AnalysisScreen extends Screen {
    private static final long AUTO_MS = 30_000;
    private static final String[] MODULE_ALL = {"中文", "英文", "键盘", "全部"};

    private String module;
    private int days = 30;
    /** all / classes / students */
    private String mode = "all";
    private List<String> pickClasses = new ArrayList<>();
    private List<String> pickStudents = new ArrayList<>();

    private JSONObject data;
    private boolean auto = true;
    private boolean loading;
    private int seq;
    private final Set<String> tables = new HashSet<>();
    private String rankSort = "rank";

    private LinearLayout page;
    private LinearLayout body;
    private StateView state;
    private ChipRow scopeRow;
    private TextView pickBtn;
    private TextView scopeText;
    private TextView failed;

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            if (auto && !loading) load(true);
            post(this, AUTO_MS);
        }
    };
    private boolean ticking;
    private boolean visible;

    /**
     * @param module   中文 / 英文 / 键盘 / 全部（空 = 中文）
     * @param classes  只看这几个班（可空）
     * @param students 这几个学生对比（「班级|姓名」，可空；优先于班级）
     */
    AnalysisScreen(String module, List<String> classes, List<String> students) {
        this.module = TextUtils.isEmpty(module) ? "中文" : module;
        if (students != null && !students.isEmpty()) {
            mode = "students";
            pickStudents = new ArrayList<>(students);
        } else if (classes != null && !classes.isEmpty()) {
            mode = "classes";
            pickClasses = new ArrayList<>(classes);
        }
    }

    @Override
    public String title() {
        return "打字学情分析";
    }

    @Override
    public String subtitle() {
        String upd = data == null ? "" : Json.str(data, "updated_at");
        if (upd.length() >= 19) return "数据更新于 " + upd.substring(11, 19) + (auto ? " · 自动刷新" : "");
        return loading ? "正在加载…" : null;
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_refresh, "刷新", () -> load(false)));
        a.add(Action.icon(R.drawable.ic_print, "打印 / 存 PDF", this::print));
        a.add(Action.menu(R.drawable.ic_timer, auto ? "关闭自动刷新（现每 30 秒）" : "开启自动刷新（每 30 秒）", () -> {
            auto = !auto;
            toast(auto ? "已开启自动刷新" : "已关闭自动刷新");
            invalidateChrome();
        }));
        a.add(Action.menu(R.drawable.ic_share, "分享结论", this::shareConclusions).enabled(hasData()));
        return a;
    }

    // ---------------------------------------------------------------- 界面

    @Override
    protected View onCreateView(Context c) {
        page = V.page(c);
        if (Ui.wide(c)) {
            // 图多，平板上放宽一点，两列卡片
            page = new cn.wfxxkj.teacher.core.ui.MaxWidthLinearLayout(c, Ui.dp(c, 1100));
            page.setOrientation(LinearLayout.VERTICAL);
            page.setPadding(Ui.dp(c, 24), Ui.dp(c, 12), Ui.dp(c, 24), Ui.dp(c, 48));
        }
        Palette p = Palette.of(c);

        // 模块
        ChipRow mods = new ChipRow(c);
        mods.setOptions(Option.of(MODULE_ALL), module);
        mods.setOnPicked(o -> {
            module = String.valueOf(o.value);
            load(false);
        });
        page.addView(mods);

        // 时间
        ChipRow dayRow = new ChipRow(c);
        dayRow.setOptions(Option.pairs(7, "近 7 天", 30, "近 30 天", 90, "近 90 天", 0, "全部时间"), days);
        dayRow.setOnPicked(o -> {
            days = ((Number) o.value).intValue();
            load(false);
        });
        V.addTop(page, dayRow, 4);

        // 看谁
        LinearLayout who = V.hbox(c);
        scopeRow = new ChipRow(c);
        scopeRow.setOptions(Option.pairs("all", "全体", "classes", "按班级", "students", "学生对比"), mode);
        scopeRow.setOnPicked(o -> {
            mode = String.valueOf(o.value);
            renderScope();
            if ("all".equals(mode)) load(false);
            else if (current().isEmpty()) openPicker();
            else load(false);
        });
        who.addView(scopeRow, V.fill());
        V.addTop(page, who, 4);

        pickBtn = V.button(c, R.drawable.ic_tune, "", V.BTN_TONAL, v -> openPicker());
        pickBtn.setTextSize(14);
        pickBtn.setMinHeight(Ui.dp(c, 40));
        pickBtn.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        pickBtn.setEllipsize(TextUtils.TruncateAt.END);
        V.addTop(page, pickBtn, 8);

        scopeText = V.text(c, "", V.CAPTION);
        V.pad(scopeText, 4, 0, 0, 0);
        V.addTop(page, scopeText, 8);

        failed = V.notice(c, "数据没取到，稍后会自动再试", Tone.DANGER);
        failed.setVisibility(View.GONE);
        V.addTop(page, failed, 10);

        state = new StateView(c);
        V.addTop(page, state, 8);

        body = V.vbox(c);
        V.addTop(page, body, 4);

        renderScope();
        ScrollView sv = V.scroll(c, page);
        sv.setBackgroundColor(p.page);
        return sv;
    }

    private List<String> current() {
        return "classes".equals(mode) ? pickClasses : "students".equals(mode) ? pickStudents : new ArrayList<>();
    }

    private void renderScope() {
        if ("all".equals(mode)) {
            pickBtn.setVisibility(View.GONE);
        } else {
            pickBtn.setVisibility(View.VISIBLE);
            List<String> cur = current();
            String label;
            if ("classes".equals(mode)) {
                label = cur.isEmpty() ? "选一个或几个班" : "班级：" + TextUtils.join("、", cur);
            } else {
                List<String> names = new ArrayList<>();
                for (String k : cur) names.add(k.contains("|") ? k.substring(k.indexOf('|') + 1) : k);
                label = cur.isEmpty() ? "搜姓名，最多选 " + StudentPickSheet.MAX + " 人"
                        : "学生（" + cur.size() + "）：" + TextUtils.join("、", names);
            }
            pickBtn.setText(label);
        }
        scopeText.setText("现在看的是：" + scopeLabel());
    }

    private String scopeLabel() {
        if (data == null) return "all".equals(mode) || current().isEmpty() ? "全体学生" : "…";
        JSONObject sc = Json.obj(data, "scope");
        String kind = Json.str(sc, "kind");
        if ("classes".equals(kind)) return "班级：" + TextUtils.join("、", Json.strings(Json.arr(sc, "classes")));
        if ("students".equals(kind)) {
            List<String> n = new ArrayList<>();
            for (JSONObject o : Json.list(Json.arr(data, "compare"))) n.add(Json.str(o, "name"));
            return "学生对比：" + TextUtils.join("、", n);
        }
        return "全体学生";
    }

    private void openPicker() {
        JSONObject opts = data == null ? new JSONObject() : Json.obj(data, "options");
        if ("classes".equals(mode)) {
            List<Option> o = new ArrayList<>();
            for (String k : Json.strings(Json.arr(opts, "classes"))) o.add(new Option(k, k));
            for (String k : pickClasses) if (!Json.strings(Json.arr(opts, "classes")).contains(k)) o.add(new Option(k, k));
            if (o.isEmpty()) {
                toast("这段时间里还没有班级的练习记录");
                return;
            }
            Dialogs.chooseMany(ctx(), "选班级", o, pickClasses, vals -> {
                pickClasses = new ArrayList<>();
                for (Object v : vals) pickClasses.add(String.valueOf(v));
                renderScope();
                load(false);
            });
        } else if ("students".equals(mode)) {
            StudentPickSheet.show(ctx(), Json.list(Json.arr(opts, "students")), pickStudents, keys -> {
                pickStudents = keys;
                renderScope();
                load(false);
            });
        }
    }

    // ---------------------------------------------------------------- 取数

    @Override
    protected void onFirstShow() {
        load(false);
    }

    @Override
    protected void onShow() {
        visible = true;
        if (!ticking) {
            ticking = true;
            post(tick, AUTO_MS);
        }
    }

    @Override
    protected void onHide() {
        visible = false;
    }

    private void load(final boolean quiet) {
        if (quiet && !visible) return; // 被别的页面盖住时不刷
        final int my = ++seq;
        loading = true;
        if (!quiet && data == null) state.loading();
        if (!quiet) invalidateChrome();
        final String mod = "全部".equals(module) ? "" : module;
        final int d = days;
        final List<String> cls = "classes".equals(mode) ? new ArrayList<>(pickClasses) : null;
        final List<String> stu = "students".equals(mode) ? new ArrayList<>(pickStudents) : null;
        run(() -> TypingApi.analysis(mod, d, cls, stu), r -> {
            if (my != seq) return;
            loading = false;
            data = r;
            failed.setVisibility(View.GONE);
            render();
            renderScope();
            invalidateChrome();
        }, e -> {
            if (my != seq) return true;
            loading = false;
            failed.setVisibility(View.VISIBLE);
            if (data == null) state.error(e.getMessage(), () -> load(false));
            invalidateChrome();
            return quiet; // 自动刷新失败不弹提示，上面那条红字够了
        });
    }

    private boolean hasData() {
        return data != null && Json.num(Json.obj(data, "summary"), "count") > 0;
    }

    private boolean speedy() {
        return Json.bool(data, "speedy");
    }

    private String unit() {
        return "英文".equals(module) ? "字母/分" : "字/分";
    }

    // ---------------------------------------------------------------- 画

    private void render() {
        Context c = ctx();
        body.removeAllViews();
        JSONObject s = Json.obj(data, "summary");
        if (Json.num(s, "count") <= 0) {
            state.empty("这个范围里还没有练习记录", "换个模块、放宽时间，或者等学生练一会儿再看");
            return;
        }
        state.hide();
        boolean speedy = speedy();

        // 自动结论
        LinearLayout con = V.card(c);
        con.setBackground(V.round(c, Palette.of(c).primarySoft, 16));
        LinearLayout ch = V.hbox(c);
        ch.addView(V.icon(c, R.drawable.ic_info, Palette.of(c).primary, 20));
        TextView ct = V.text(c, "自动结论", V.H3);
        V.pad(ct, 8, 0, 0, 0);
        ch.addView(ct);
        con.addView(ch);
        List<String> lines = Json.strings(Json.arr(data, "conclusions"));
        for (int i = 0; i < lines.size(); i++) {
            LinearLayout row = V.hbox(c);
            row.setGravity(Gravity.TOP);
            TextView no = V.text(c, (i + 1) + ".", V.BODY);
            no.setMinWidth(Ui.dp(c, 22));
            no.setTextColor(Palette.of(c).primary);
            V.bold(no);
            row.addView(no);
            TextView t = V.text(c, lines.get(i), V.BODY);
            t.setTextIsSelectable(true);
            row.addView(t, V.fill());
            V.addTop(con, row, 8);
        }
        body.addView(con, V.matchWrap());

        // 指标
        GridBox k = new GridBox(c, 140, 6, 10);
        k.addView(TypingUi.kpi(c, String.valueOf(Json.num(s, "count")), "练习人次", null, Tone.PRIMARY));
        k.addView(TypingUi.kpi(c, String.valueOf(Json.num(s, "students")), "参与人数",
                "人均 " + TypingUi.num(s, "per_student") + " 次", Tone.SUCCESS));
        if (speedy) {
            k.addView(TypingUi.kpi(c, TypingUi.num(s, "avg_speed"), "平均速度", unit(), Tone.VIOLET));
            k.addView(TypingUi.kpi(c, TypingUi.num(s, "median_speed") + " / " + TypingUi.num(s, "max_speed"),
                    "中位数 / 最快", unit(), Tone.INFO));
        }
        k.addView(TypingUi.kpi(c, TypingUi.pct(s, "avg_accuracy"), "平均正确率", null, Tone.WARNING));
        k.addView(TypingUi.kpi(c, TypingUi.pct(s, "reach_rate"), "达标率", "两星及以上", Tone.SUCCESS));
        k.addView(TypingUi.kpi(c, TypingUi.pct(s, "three_star_rate"), "三星", null, Tone.WARNING));
        k.addView(TypingUi.kpi(c, TypingUi.mmss(Json.dblOrNull(s, "avg_duration")), "平均用时", null, Tone.NEUTRAL));
        k.addView(TypingUi.kpi(c, TypingUi.num(s, "minutes"), "累计练习", "分钟", Tone.NEUTRAL));
        int once = Json.num(s, "once_only");
        k.addView(TypingUi.kpi(c, String.valueOf(once), "只练过一次", "人", once > 0 ? Tone.DANGER : Tone.NEUTRAL));
        V.addTop(body, k, 12);

        // 学生对比
        List<JSONObject> compare = Json.list(Json.arr(data, "compare"));
        if (!compare.isEmpty()) {
            GridBox g = grid();
            if (speedy) g.addView(compareCard("每次练习的速度", compare, "speed", false));
            g.addView(compareCard("每次练习的正确率", compare, "accuracy", true));
            V.addTop(body, g, 12);
        }

        // 走势
        List<JSONObject> pts = Json.list(Json.arr(Json.obj(data, "trend"), "points"));
        String[] tl = new String[pts.size()];
        for (int i = 0; i < tl.length; i++) tl[i] = Json.str(pts.get(i), "label");
        GridBox g1 = grid();
        boolean week = "week".equals(Json.str(Json.obj(data, "trend"), "unit"));
        List<String[]> trendRows = new ArrayList<>();
        for (JSONObject o : pts) {
            trendRows.add(speedy
                    ? new String[]{Json.str(o, "label"), String.valueOf(Json.num(o, "count")), String.valueOf(Json.num(o, "students")),
                    TypingUi.num(o, "avg_speed"), TypingUi.pct(o, "avg_accuracy")}
                    : new String[]{Json.str(o, "label"), String.valueOf(Json.num(o, "count")), String.valueOf(Json.num(o, "students")),
                    TypingUi.pct(o, "avg_accuracy")});
        }
        String[] trendHead = speedy ? new String[]{"日期", "人次", "人数", "平均速度", "平均正确率"}
                : new String[]{"日期", "人次", "人数", "平均正确率"};
        g1.addView(chartCard(week ? "每周练习人次" : "每天练习人次", "trend",
                new AnalysisCharts.Columns(c, 180).values(pts.size() <= 14)
                        .set(tl, one("练习人次", nums(pts, "count"), 0), false),
                null, trendHead, trendRows));
        if (speedy) {
            g1.addView(chartCard("平均速度走势（" + unit() + "）", null,
                    new AnalysisCharts.Lines(c, 180).set(tl, one("平均速度", nums(pts, "avg_speed"), 0), false),
                    null, null, null));
        }
        g1.addView(chartCard("平均正确率走势", null,
                new AnalysisCharts.Lines(c, 180).set(tl, one("平均正确率", nums(pts, "avg_accuracy"), 0), true),
                null, null, null));
        V.addTop(body, g1, 12);

        // 分布
        GridBox g2 = grid();
        if (speedy) g2.addView(bandCard("速度分布（" + unit() + "）", "speed", "速度段", Json.list(Json.arr(data, "speed_bands"))));
        g2.addView(bandCard("正确率分布", "acc", "正确率", Json.list(Json.arr(data, "accuracy_bands"))));
        List<JSONObject> st = Json.list(Json.arr(data, "stars"));
        String[] sl = new String[st.size()];
        for (int i = 0; i < sl.length; i++) sl[i] = Json.str(st.get(i), "label");
        AnalysisCharts.Columns starChart = new AnalysisCharts.Columns(c, 180);
        starChart.set(sl, one("次数", nums(st, "count"), 2), false);
        g2.addView(chartCard("星级构成", null, starChart, null, null, null));
        g2.addView(difficultyCard(speedy));
        V.addTop(body, g2, 12);

        // 各班（学生对比时不看班级：两三个人谈不上班与班之间）
        List<JSONObject> cls = Json.list(Json.arr(data, "classes"));
        if (compare.isEmpty() && !cls.isEmpty()) {
            String[] cl = new String[cls.size()];
            for (int i = 0; i < cl.length; i++) cl[i] = Json.str(cls.get(i), "name");
            GridBox g3 = grid();
            if (speedy) {
                g3.addView(chartCard("各班平均速度（" + unit() + "）", "classes",
                        new AnalysisCharts.Columns(c, 180).set(cl, one("平均速度", nums(cls, "avg_speed"), 0), false),
                        null, null, null));
            }
            List<AnalysisCharts.Series> rate = new ArrayList<>();
            rate.add(series("平均正确率", nums(cls, "avg_accuracy"), 0));
            rate.add(series("达标率", nums(cls, "reach_rate"), 1));
            g3.addView(chartCard("各班正确率与达标率", null,
                    new AnalysisCharts.Columns(c, 200).set(cl, rate, true), AnalysisCharts.legend(c, rate), null, null));
            if (speedy && cls.size() > 1) {
                List<double[]> boxes = new ArrayList<>();
                for (JSONObject o : cls) {
                    JSONArray b = Json.arr(o, "box");
                    double[] v = new double[b.length()];
                    for (int i = 0; i < v.length; i++) v[i] = b.optDouble(i, 0);
                    boxes.add(v);
                }
                LinearLayout bc = chartCard("各班速度分布（箱线图）", null,
                        new AnalysisCharts.Box(c, 200).set(cl, boxes), null, null, null);
                bc.addView(note(c, "每个学生先求平均速度；箱子是中间一半学生，横线是中位数，两头是最快和最慢。"));
                g3.addView(bc);
            }
            V.addTop(body, g3, 12);
            if (tables.contains("classes") || !speedy) V.addTop(body, classTable(cls, speedy), 12);
        }

        // 学生名单
        V.addTop(body, rankingCard(), 12);
    }

    private GridBox grid() {
        return new GridBox(ctx(), 340, 2, 12);
    }

    private static Double[] nums(List<JSONObject> rows, String key) {
        Double[] out = new Double[rows.size()];
        for (int i = 0; i < out.length; i++) out[i] = Json.dblOrNull(rows.get(i), key);
        return out;
    }

    private AnalysisCharts.Series series(String name, Double[] v, int colorIdx) {
        AnalysisCharts.Series s = new AnalysisCharts.Series(name, v);
        s.color = Palette.of(ctx()).series(colorIdx);
        return s;
    }

    private List<AnalysisCharts.Series> one(String name, Double[] v, int colorIdx) {
        return new ArrayList<>(Collections.singletonList(series(name, v, colorIdx)));
    }

    /**
     * 一张图的卡片。toggleKey 不为空时右上角有「看数据 / 收起数据」，
     * 点了展开 head/rows 这张表（rows 为空则只切换 tables 里的开关，例如各班大表）。
     */
    private LinearLayout chartCard(String title, final String toggleKey, View chart, View legend,
                                   String[] head, List<String[]> rows) {
        Context c = ctx();
        LinearLayout card = V.card(c);
        boolean open = toggleKey != null && tables.contains(toggleKey);
        card.addView(TypingUi.cardTitle(c, title, toggleKey == null ? null : open ? "收起数据" : "看数据", v -> {
            if (tables.contains(toggleKey)) tables.remove(toggleKey);
            else tables.add(toggleKey);
            render();
        }));
        if (legend != null) card.addView(legend);
        card.addView(chart, V.matchWrap());
        if (open && head != null && rows != null) {
            V.addTop(card, TypingUi.table(c, head, rows), 10);
        }
        return card;
    }

    private LinearLayout bandCard(String title, String key, String col, List<JSONObject> bands) {
        String[] l = new String[bands.size()];
        List<String[]> rows = new ArrayList<>();
        for (int i = 0; i < l.length; i++) {
            l[i] = Json.str(bands.get(i), "label");
            rows.add(new String[]{l[i], String.valueOf(Json.num(bands.get(i), "count"))});
        }
        return chartCard(title, key, new AnalysisCharts.Columns(ctx(), 180).set(l, one("次数", nums(bands, "count"), 0), false),
                null, new String[]{col, "次数"}, rows);
    }

    private LinearLayout difficultyCard(boolean speedy) {
        Context c = ctx();
        LinearLayout card = V.card(c);
        card.addView(TypingUi.cardTitle(c, "难度", null, null));
        List<String[]> rows = new ArrayList<>();
        for (JSONObject o : Json.list(Json.arr(data, "difficulties"))) {
            rows.add(speedy
                    ? new String[]{Json.str(o, "name"), String.valueOf(Json.num(o, "count")), TypingUi.pct(o, "share"),
                    TypingUi.num(o, "avg_speed"), TypingUi.pct(o, "avg_accuracy"), TypingUi.pct(o, "reach_rate")}
                    : new String[]{Json.str(o, "name"), String.valueOf(Json.num(o, "count")), TypingUi.pct(o, "share"),
                    TypingUi.pct(o, "avg_accuracy"), TypingUi.pct(o, "reach_rate")});
        }
        card.addView(TypingUi.table(c, speedy ? new String[]{"难度", "次数", "占比", "平均速度", "正确率", "达标率"}
                : new String[]{"难度", "次数", "占比", "正确率", "达标率"}, rows));
        if ("全部".equals(module)) {
            List<String[]> mr = new ArrayList<>();
            for (JSONObject o : Json.list(Json.arr(data, "by_module"))) {
                mr.add(new String[]{Json.str(o, "name"), String.valueOf(Json.num(o, "count")),
                        String.valueOf(Json.num(o, "students")), TypingUi.num(o, "avg_speed"), TypingUi.pct(o, "avg_accuracy")});
            }
            V.addTop(card, V.text(c, "各模块", V.LABEL), 14);
            V.addTop(card, TypingUi.table(c, new String[]{"模块", "次数", "人数", "平均速度", "正确率"}, mr), 6);
        }
        return card;
    }

    private LinearLayout compareCard(String title, List<JSONObject> compare, String key, boolean pct) {
        int longest = 0;
        for (JSONObject o : compare) longest = Math.max(longest, Json.arr(o, "points").length());
        String[] l = new String[longest];
        for (int i = 0; i < longest; i++) l[i] = "第" + (i + 1) + "次";
        List<AnalysisCharts.Series> ss = new ArrayList<>();
        for (int i = 0; i < compare.size(); i++) {
            JSONArray p = Json.arr(compare.get(i), "points");
            Double[] v = new Double[longest];
            for (int j = 0; j < p.length(); j++) v[j] = Json.dblOrNull(p.optJSONObject(j), key);
            ss.add(series(Json.str(compare.get(i), "name"), v, i));
        }
        return chartCard(title, null, new AnalysisCharts.Lines(ctx(), 220).set(l, ss, pct),
                AnalysisCharts.legend(ctx(), ss), null, null);
    }

    private View classTable(List<JSONObject> cls, boolean speedy) {
        Context c = ctx();
        LinearLayout card = V.card(c);
        card.addView(TypingUi.cardTitle(c, "各班明细", speedy ? "收起" : null, v -> {
            tables.remove("classes");
            render();
        }));
        List<String[]> rows = new ArrayList<>();
        for (JSONObject o : cls) {
            String roster = Json.isNull(o, "roster") ? "—" : String.valueOf(Json.num(o, "roster"));
            String part = Json.isNull(o, "participation") ? "—" : TypingUi.pct(o, "participation");
            List<String> r = new ArrayList<>();
            r.add(Json.str(o, "name"));
            r.add(Json.num(o, "students") + " / " + roster);
            r.add(part);
            r.add(String.valueOf(Json.num(o, "count")));
            r.add(TypingUi.num(o, "per_student"));
            if (speedy) r.add(TypingUi.num(o, "avg_speed"));
            r.add(TypingUi.pct(o, "avg_accuracy"));
            r.add(TypingUi.pct(o, "reach_rate"));
            rows.add(r.toArray(new String[0]));
        }
        List<String> head = new ArrayList<>();
        Collections.addAll(head, "班级", "练过 / 名单", "参与率", "人次", "人均");
        if (speedy) head.add("平均速度");
        Collections.addAll(head, "正确率", "达标率");
        card.addView(TypingUi.table(c, head.toArray(new String[0]), rows));
        return card;
    }

    // ---------------------------------------------------------------- 学生名单

    private View rankingCard() {
        Context c = ctx();
        final List<JSONObject> all = Json.list(Json.arr(data, "ranking"));
        LinearLayout card = V.card(c);
        card.addView(TypingUi.cardTitle(c, "学生名单（" + all.size() + " 人）",
                all.size() > 10 ? "查看全部" : null, v -> openRanking()));
        ChipRow sort = new ChipRow(c);
        sort.setOptions(RankingScreen.sorts(speedy()), rankSort);
        sort.setOnPicked(o -> {
            rankSort = String.valueOf(o.value);
            render();
        });
        card.addView(sort);
        List<JSONObject> sorted = RankingScreen.sort(all, rankSort);
        int n = Math.min(10, sorted.size());
        for (int i = 0; i < n; i++) {
            if (i > 0) card.addView(V.divider(c));
            final JSONObject o = sorted.get(i);
            View row = RankingScreen.row(c, o, speedy(), unit());
            V.clickable(row, 8, v -> openStudent(o));
            card.addView(row);
        }
        if (sorted.size() > n) {
            TextView more = V.button(c, "查看全部 " + sorted.size() + " 人", V.BTN_TONAL, v -> openRanking());
            V.addTop(card, more, 8);
        }
        card.addView(note(c, "进步：这段时间里最后 3 次的平均" + (speedy() ? "速度" : "正确率")
                + "减最初 3 次的，练满 4 次才算。点一个学生看他自己的学情。"));
        return card;
    }

    private void openRanking() {
        push(new RankingScreen(Json.list(Json.arr(data, "ranking")), speedy(), unit(), rankSort,
                "全部".equals(module) ? "全部" : module));
    }

    private void openStudent(JSONObject o) {
        List<String> one = new ArrayList<>(Collections.singletonList(Json.str(o, "key")));
        push(new AnalysisScreen(module, null, one));
    }

    private static TextView note(Context c, String s) {
        TextView t = V.text(c, s, V.CAPTION);
        V.pad(t, 0, 8, 0, 0);
        return t;
    }

    // ---------------------------------------------------------------- 打印、分享

    private void print() {
        if (!hasData()) {
            toast("还没有可打印的内容");
            return;
        }
        Printer.print(activity(), page, "打字学情分析");
    }

    private void shareConclusions() {
        if (!hasData()) return;
        StringBuilder b = new StringBuilder("打字学情分析（").append(module).append("，")
                .append(days == 0 ? "全部时间" : "近 " + days + " 天").append("，").append(scopeLabel()).append("）\n");
        List<String> lines = Json.strings(Json.arr(data, "conclusions"));
        for (int i = 0; i < lines.size(); i++) b.append(i + 1).append(". ").append(lines.get(i)).append('\n');
        b.append("数据更新于 ").append(Fmt.dateTime(Json.str(data, "updated_at").replace(' ', 'T')));
        Sys.share(ctx(), "分享学情结论", b.toString());
    }
}
