package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Printer;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
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
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 成绩分析（网页 ExamAnalysis.vue）：看全体 / 某几个班 / 选几个学生对比；
 * 自动结论、十项指标、分数段、知识范围、班级对比（分组柱 + 箱线图）、每题得分率、
 * 大题得分率、难度与区分度、操作题每一步通过率、名次。每张图下面能展开看原始数字。
 * 数据每 20 秒自动刷新一次（可关），顶栏可打印 / 存 PDF。
 */
final class AnalysisScreen extends Screen {

    private static final String M_ALL = "all", M_CLASSES = "classes", M_STUDENTS = "students";
    private static final int MAX_STUDENTS = 8;
    private static final long AUTO_MS = 20_000;

    private final long examId;
    private final String examTitle;
    private JSONObject data;
    private String mode = M_ALL;
    private final List<Object> pickClasses = new ArrayList<>();
    private final List<Object> pickStudents = new ArrayList<>();
    private boolean auto = true;
    private boolean shown;
    private int loadSeq;
    /** 哪几张图展开了数据表 */
    private final Set<String> tables = new HashSet<>();

    private ScrollView scroll;
    private LinearLayout page, content;
    private ChipRow modeRow;
    private TextView scopeText, updated, pickBtn;
    private StateView state;

    AnalysisScreen(long examId, String examTitle) {
        this.examId = examId;
        this.examTitle = examTitle;
    }

    @Override
    public String title() {
        return "成绩分析";
    }

    @Override
    public String subtitle() {
        return data == null ? examTitle : Json.str(Json.obj(data, "exam"), "title");
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_refresh, "刷新", () -> load(false)));
        a.add(Action.menu(R.drawable.ic_print, "打印 / 存 PDF", () -> Printer.print(activity(), page,
                "成绩分析-" + subtitle())));
        return a;
    }

    @Override
    protected View onCreateView(Context c) {
        page = V.page(c);
        scroll = V.scroll(c, page);

        // 看谁
        modeRow = new ChipRow(c);
        modeRow.setOptions(Option.pairs(M_ALL, "全体参考学生", M_CLASSES, "按班级", M_STUDENTS, "学生对比"), M_ALL);
        modeRow.setOnPicked(o -> {
            mode = String.valueOf(o.value);
            renderPicker();
            load(false);
            if (M_CLASSES.equals(mode) && pickClasses.isEmpty() || M_STUDENTS.equals(mode) && pickStudents.isEmpty()) {
                pick();
            }
        });
        page.addView(modeRow);

        LinearLayout pickLine = V.hbox(c);
        scopeText = V.text(c, "", V.BODY2);
        pickLine.addView(scopeText, V.fill());
        pickBtn = V.button(c, R.drawable.ic_filter_list, "选择", V.BTN_TONAL, v -> pick());
        pickLine.addView(pickBtn);
        V.addTop(page, pickLine, 8);

        LinearLayout autoLine = V.hbox(c);
        updated = V.text(c, "", V.CAPTION);
        autoLine.addView(updated, V.fill());
        autoLine.addView(V.text(c, "自动刷新", V.CAPTION));
        Switch sw = new Switch(c);
        sw.setChecked(auto);
        sw.setOnCheckedChangeListener((b, on) -> {
            auto = on;
            if (on) schedule();
        });
        V.addStart(autoLine, sw, 4);
        V.addTop(page, autoLine, 4);

        content = V.vbox(c);
        state = new StateView(c);
        content.addView(state, V.matchWrap());
        V.addTop(page, content, 8);
        renderPicker();
        return scroll;
    }

    @Override
    protected void onFirstShow() {
        load(false);
    }

    @Override
    protected void onShow() {
        shown = true;
        schedule();
    }

    @Override
    protected void onHide() {
        shown = false;
    }

    /** 每 20 秒静默刷新一次（页面在前台、开着自动刷新时） */
    private void schedule() {
        final int seq = ++loadSeq;
        post(() -> {
            if (seq != loadSeq || !shown || !auto) return;
            load(true);
            schedule();
        }, AUTO_MS);
    }

    private void load(boolean quiet) {
        if (!quiet && data == null) state.loading();
        final List<Object> cls = M_CLASSES.equals(mode) ? new ArrayList<>(pickClasses) : null;
        final List<Object> stu = M_STUDENTS.equals(mode) ? new ArrayList<>(pickStudents) : null;
        run(() -> {
            ExamApi.ensureConfig();
            return ExamApi.analysis(examId, cls, stu);
        }, d -> {
            data = d;
            invalidateChrome();
            render();
        }, e -> {
            if (data == null) {
                state.error("数据没取到：" + e.getMessage(), () -> load(false));
                return true;
            }
            return quiet; // 自动刷新失败不打扰，下一轮再试
        });
    }

    // ---------- 选范围 ----------

    private void renderPicker() {
        boolean need = !M_ALL.equals(mode);
        pickBtn.setVisibility(need ? View.VISIBLE : View.GONE);
        if (M_CLASSES.equals(mode)) pickBtn.setText(pickClasses.isEmpty() ? "选班级" : "已选 " + pickClasses.size() + " 个班");
        if (M_STUDENTS.equals(mode)) pickBtn.setText(pickStudents.isEmpty() ? "选学生" : "已选 " + pickStudents.size() + " 人");
        String scope = "全体参考学生";
        if (data != null) {
            JSONObject sc = Json.obj(data, "scope");
            String kind = Json.str(sc, "kind");
            if ("classes".equals(kind)) scope = "班级：" + android.text.TextUtils.join("、", Json.strings(Json.arr(sc, "classes")));
            if ("students".equals(kind)) {
                List<String> names = new ArrayList<>();
                for (JSONObject s : Json.list(Json.arr(data, "compare"))) names.add(Json.str(s, "name"));
                scope = "学生对比：" + android.text.TextUtils.join("、", names);
            }
        }
        scopeText.setText("现在看的是：" + scope);
    }

    private void pick() {
        if (data == null) {
            toast("数据还没取到，稍等一下");
            return;
        }
        JSONObject opts = Json.obj(data, "options");
        if (M_CLASSES.equals(mode)) {
            List<Option> o = new ArrayList<>();
            for (String n : Json.strings(Json.arr(opts, "classes"))) o.add(new Option(n, n));
            Dialogs.chooseMany(ctx(), "选一个或几个班", o, pickClasses, vals -> {
                pickClasses.clear();
                pickClasses.addAll(vals);
                renderPicker();
                load(false);
            });
        } else if (M_STUDENTS.equals(mode)) {
            List<Option> o = new ArrayList<>();
            for (JSONObject s : Json.list(Json.arr(opts, "students"))) {
                o.add(new Option(s.optLong("sub_id"), Json.str(s, "name"),
                        ExamUi.dot(Json.str(s, "class"), Json.str(s, "no"), Fmt.num(Json.dbl(s, "score")) + " 分")));
            }
            Dialogs.chooseMany(ctx(), "选学生对比（最多 " + MAX_STUDENTS + " 人）", o, pickStudents, vals -> {
                pickStudents.clear();
                for (Object v : vals) if (pickStudents.size() < MAX_STUDENTS) pickStudents.add(v);
                if (vals.size() > MAX_STUDENTS) toast("最多对比 " + MAX_STUDENTS + " 人，只取了前 " + MAX_STUDENTS + " 个");
                renderPicker();
                load(false);
            });
        }
    }

    // ---------- 画 ----------

    private void render() {
        Context c = ctx();
        renderPicker();
        String up = Json.str(data, "updated_at");
        updated.setText(up.length() >= 19 ? "数据更新于 " + up.substring(11, 19) : "");
        content.removeAllViews();
        JSONObject s = Json.obj(data, "summary");
        if (Json.num(s, "count") == 0) {
            StateView empty = new StateView(c);
            empty.empty("这个范围里还没有人交卷", "换个范围看看，或等学生交卷");
            content.addView(empty, V.matchWrap());
            return;
        }
        double pass = Json.dbl(data, "pass_line");

        // 自动结论
        LinearLayout concl = card(c, "自动结论", null);
        List<String> lines = Json.strings(Json.arr(data, "conclusions"));
        for (int i = 0; i < lines.size(); i++) {
            LinearLayout row = V.hbox(c);
            row.setGravity(Gravity.TOP);
            TextView no = V.text(c, (i + 1) + "", V.LABEL);
            no.setTextColor(Palette.of(c).primary);
            no.setMinWidth(Ui.dp(c, 20));
            row.addView(no);
            row.addView(V.text(c, lines.get(i), V.BODY), V.fill());
            V.addTop(concl, row, i == 0 ? 0 : 8);
        }
        content.addView(concl, V.matchWrap());

        // 指标
        GridBox kpis = new GridBox(c, 140, 5, 10);
        kpis.addView(V.stat(c, String.valueOf(Json.num(s, "count")), "参考人数", Tone.PRIMARY));
        kpis.addView(V.stat(c, Fmt.num(Json.dbl(s, "avg")), "平均分 / " + Json.num(s, "full") + "　得分率 " + Fmt.num(Json.dbl(s, "avg_rate")) + "%", Tone.NEUTRAL));
        kpis.addView(V.stat(c, Fmt.num(Json.dbl(s, "median")), "中位数", Tone.NEUTRAL));
        kpis.addView(V.stat(c, Fmt.num(Json.dbl(s, "max")) + " / " + Fmt.num(Json.dbl(s, "min")), "最高 / 最低", Tone.NEUTRAL));
        kpis.addView(V.stat(c, Fmt.num(Json.dbl(s, "std")), "标准差", Tone.NEUTRAL));
        kpis.addView(V.stat(c, Fmt.num(Json.dbl(s, "pass_rate")) + "%", "及格率（及格线 " + Fmt.num(pass) + "%）", Tone.SUCCESS));
        kpis.addView(V.stat(c, Fmt.num(Json.dbl(s, "excellent_rate")) + "%", "优秀率（≥85%）", Tone.INFO));
        kpis.addView(V.stat(c, Fmt.num(Json.dbl(s, "low_rate")) + "%", "低分率（<40%）", Tone.DANGER));
        kpis.addView(V.stat(c, String.valueOf(Json.num(s, "full_marks")), "满分人数", Tone.VIOLET));
        int pending = Json.num(s, "pending");
        kpis.addView(V.stat(c, String.valueOf(pending), "份待老师复核", pending > 0 ? Tone.WARNING : Tone.NEUTRAL));
        V.addTop(content, kpis, 12);

        GridBox grid = new GridBox(c, 380, 2, 12);
        V.addTop(content, grid, 12);

        // 学生对比
        List<JSONObject> compare = Json.list(Json.arr(data, "compare"));
        if (!compare.isEmpty()) {
            grid.addView(compareChart(c, "知识范围得分率对比", compare, "by_scope", pass));
            grid.addView(compareChart(c, "大题得分率对比", compare, "by_section", pass));
            grid.addView(compareList(c, compare));
        }

        // 分数段
        List<JSONObject> bands = Json.list(Json.arr(data, "bands"));
        LinearLayout bc = card(c, "分数段分布", "bands");
        List<Charts.Point> bp = new ArrayList<>();
        for (JSONObject b : bands) {
            int n = Json.num(b, "count");
            bp.add(new Charts.Point(Json.str(b, "label"), n, 0, n > 0 ? String.valueOf(n) : ""));
        }
        bc.addView(new Charts.Bars(c, 200).setData(bp), V.matchWrap());
        if (tables.contains("bands")) {
            DataTable t = new DataTable(c, new String[]{"分数段", "人数"}, new int[]{120, 80});
            for (JSONObject b : bands) t.add(Json.str(b, "label"), String.valueOf(Json.num(b, "count")));
            V.addTop(bc, t, 10);
        }
        grid.addView(bc);

        // 知识范围
        List<JSONObject> scopes = Json.list(Json.arr(data, "scopes"));
        LinearLayout sc = card(c, "知识范围掌握情况", "scopes");
        sc.addView(rateBars(c, scopes, "name"), V.matchWrap());
        if (tables.contains("scopes")) {
            DataTable t = new DataTable(c, new String[]{"知识范围", "题数", "满分 / 平均", "得分率"}, new int[]{130, 56, 100, 76});
            for (JSONObject g : scopes) {
                Double r = Json.dblOrNull(g, "rate");
                t.add(new CharSequence[]{Json.str(g, "name"), String.valueOf(Json.num(g, "questions")),
                        Fmt.num(Json.dbl(g, "full")) + " / " + Fmt.num(Json.dbl(g, "avg")), ExamUi.pct(r)},
                        new int[]{0, 0, 0, ExamUi.rateColor(c, r)});
            }
            V.addTop(sc, t, 10);
        }
        grid.addView(sc);

        // 班级对比
        List<JSONObject> classes = Json.list(Json.arr(data, "classes"));
        if (classes.size() > 1) {
            LinearLayout cc = card(c, "班级对比", "classes");
            List<String> names = new ArrayList<>();
            double[][] v = new double[3][classes.size()];
            for (int i = 0; i < classes.size(); i++) {
                JSONObject k = classes.get(i);
                names.add(Json.str(k, "name"));
                v[0][i] = Json.dbl(k, "avg_rate");
                v[1][i] = Json.dbl(k, "pass_rate");
                v[2][i] = Json.dbl(k, "excellent_rate");
            }
            List<String> legend = new ArrayList<>();
            legend.add("平均得分率");
            legend.add("及格率");
            legend.add("优秀率");
            cc.addView(MiniCharts.legend(c, legend));
            V.addTop(cc, new MiniCharts.Grouped(c, 240).setData(names, v, pass), 8);
            if (tables.contains("classes")) {
                DataTable t = new DataTable(c, new String[]{"班级", "人数", "平均分", "中位数", "最高", "最低", "标准差", "及格率", "优秀率"},
                        new int[]{110, 56, 70, 70, 56, 56, 70, 70, 70});
                for (JSONObject k : classes) {
                    t.add(Json.str(k, "name"), String.valueOf(Json.num(k, "count")), Fmt.num(Json.dbl(k, "avg")),
                            Fmt.num(Json.dbl(k, "median")), Fmt.num(Json.dbl(k, "max")), Fmt.num(Json.dbl(k, "min")),
                            Fmt.num(Json.dbl(k, "std")), Fmt.num(Json.dbl(k, "pass_rate")) + "%",
                            Fmt.num(Json.dbl(k, "excellent_rate")) + "%");
                }
                V.addTop(cc, t, 10);
            }
            grid.addView(cc);

            LinearLayout bx = card(c, "各班分数分布（箱线图）", null);
            List<double[]> boxes = new ArrayList<>();
            for (JSONObject k : classes) {
                List<Double> b = new ArrayList<>();
                org.json.JSONArray arr = Json.arr(k, "box");
                for (int i = 0; i < arr.length(); i++) b.add(arr.optDouble(i));
                // 有的版本前面多一个序号：取最后 5 个
                double[] five = new double[5];
                for (int i = 0; i < 5 && b.size() >= 5; i++) five[i] = b.get(b.size() - 5 + i);
                boxes.add(b.size() >= 5 ? five : null);
            }
            bx.addView(new MiniCharts.Box(c, 240).setData(names, boxes, Json.dbl(s, "full")), V.matchWrap());
            V.addTop(bx, V.text(c, "箱子是中间一半学生的分数，横线是中位数，上下两端是最高、最低分。", V.CAPTION), 6);
            grid.addView(bx);
        }

        // 每题得分率（独占一行）
        List<JSONObject> qs = Json.list(Json.arr(data, "questions"));
        LinearLayout qc = card(c, "每题得分率", "questions");
        List<Charts.Point> qp = new ArrayList<>();
        Palette pal = Palette.of(c);
        for (JSONObject q : qs) {
            Double r = Json.dblOrNull(q, "rate");
            if (r == null) continue;
            qp.add(new Charts.Point(String.valueOf(Json.num(q, "no")), r, r >= pass ? pal.primary : pal.danger, ""));
        }
        qc.addView(V.text(c, "红色是低于及格线（" + Fmt.num(pass) + "%）的题，横轴是题号。题多时可左右滑动。", V.CAPTION));
        V.addTop(qc, wideBars(c, qp), 8);
        if (tables.contains("questions")) {
            DataTable t = new DataTable(c, new String[]{"题号", "题型", "大题", "知识范围", "题干", "均分 / 满分", "得分率", "区分度", "未作答"},
                    new int[]{52, 70, 100, 110, 220, 90, 70, 64, 64});
            for (JSONObject q : qs) {
                Double r = Json.dblOrNull(q, "rate");
                t.add(new CharSequence[]{String.valueOf(Json.num(q, "no")), Json.str(q, "type"), Json.str(q, "section"),
                        Json.str(q, "scope"), Json.str(q, "stem"),
                        Fmt.num(Json.dbl(q, "avg")) + " / " + Json.num(q, "score"), ExamUi.pct(r),
                        Fmt.num(Json.dblOrNull(q, "discrimination")), String.valueOf(Json.num(q, "blank"))},
                        new int[]{0, 0, 0, 0, 0, 0, ExamUi.rateColor(c, r), 0, 0});
            }
            V.addTop(qc, t, 10);
        }
        V.addTop(content, qc, 12);

        GridBox grid2 = new GridBox(c, 380, 2, 12);
        V.addTop(content, grid2, 12);
        // 大题
        LinearLayout sec = card(c, "大题得分率", null);
        sec.addView(rateBars(c, Json.list(Json.arr(data, "sections")), "name"), V.matchWrap());
        grid2.addView(sec);

        // 难度与区分度
        LinearLayout dc = card(c, "难度与区分度", null);
        MiniCharts.Scatter sp = new MiniCharts.Scatter(c, 240);
        for (JSONObject q : qs) {
            Double r = Json.dblOrNull(q, "rate"), d = Json.dblOrNull(q, "discrimination");
            if (r != null && d != null) sp.add(r, d, "第" + Json.num(q, "no") + "题");
        }
        dc.addView(sp, V.matchWrap());
        V.addTop(dc, V.text(c, "越往右越容易；越往上越能区分会的和不会的。落在虚线下面（黄点）的题值得回头看看。", V.CAPTION), 6);
        grid2.addView(dc);

        // 操作题每一步
        List<Charts.Point> ops = new ArrayList<>();
        for (JSONObject o : Json.list(Json.arr(data, "operations"))) {
            for (JSONObject ck : Json.list(Json.arr(o, "checks"))) {
                double r = Json.dbl(ck, "pass_rate");
                ops.add(new Charts.Point("第" + Json.num(o, "no") + "题 · " + Json.str(ck, "desc"), r,
                        r >= pass ? pal.primary : pal.danger, Fmt.num(r) + "%"));
            }
        }
        if (!ops.isEmpty()) {
            LinearLayout oc = card(c, "操作题每一步的通过率", null);
            oc.addView(new Charts.HBars(c).setMax(100).setData(ops), V.matchWrap());
            V.addTop(content, oc, 12);
        }

        // 名次
        V.addTop(content, rankingCard(c), 12);
    }

    /** 带标题的卡片；tableKey 非空时标题右边有「看数据 / 收起数据」 */
    private LinearLayout card(Context c, String title, String tableKey) {
        LinearLayout card = V.card(c);
        LinearLayout head = V.hbox(c);
        head.addView(V.text(c, title, V.H3), V.fill());
        if (tableKey != null) {
            boolean on = tables.contains(tableKey);
            head.addView(V.button(c, on ? "收起数据" : "看数据", V.BTN_TEXT, v -> {
                if (!tables.remove(tableKey)) tables.add(tableKey);
                int y = scroll.getScrollY();
                render();
                scroll.post(() -> scroll.scrollTo(0, y));
            }));
        }
        V.pad(head, 0, 0, 0, 8);
        card.addView(head);
        return card;
    }

    /** 得分率横条（及格的主题色、不及格的红色），null 的跳过 */
    private View rateBars(Context c, List<JSONObject> rows, String labelKey) {
        Palette p = Palette.of(c);
        double pass = Json.dbl(data, "pass_line");
        List<Charts.Point> pts = new ArrayList<>();
        for (JSONObject g : rows) {
            Double r = Json.dblOrNull(g, "rate");
            if (r == null) continue;
            pts.add(new Charts.Point(Json.str(g, labelKey), r, r >= pass ? p.primary : p.danger, Fmt.num(r) + "%"));
        }
        if (pts.isEmpty()) return V.text(c, "没有数据", V.BODY2);
        return new Charts.HBars(c).setMax(100).setData(pts);
    }

    /** 题多的竖柱图：每根至少 14dp，放不下就横向滑 */
    private View wideBars(Context c, List<Charts.Point> pts) {
        int need = pts.size() * 14;
        int avail = Ui.widthDp(c) - (Ui.wide(c) ? 80 : 64);
        Charts.Bars bars = new Charts.Bars(c, 200).setData(pts);
        if (need <= avail) return bars;
        HorizontalScrollView hs = new HorizontalScrollView(c);
        hs.setHorizontalScrollBarEnabled(true);
        LinearLayout inner = new LinearLayout(c);
        inner.addView(bars, new LinearLayout.LayoutParams(Ui.dp(c, need), Ui.dp(c, 200)));
        hs.addView(inner);
        return hs;
    }

    private View compareChart(Context c, String title, List<JSONObject> compare, String key, double pass) {
        LinearLayout card = card(c, title, null);
        List<String> cats = new ArrayList<>();
        for (JSONObject g : Json.list(Json.arr(compare.get(0), key))) cats.add(Json.str(g, "name"));
        double[][] v = new double[compare.size()][cats.size()];
        List<String> names = new ArrayList<>();
        for (int k = 0; k < compare.size(); k++) {
            names.add(Json.str(compare.get(k), "name"));
            List<JSONObject> gs = Json.list(Json.arr(compare.get(k), key));
            for (int i = 0; i < cats.size(); i++) {
                Double r = i < gs.size() ? Json.dblOrNull(gs.get(i), "rate") : null;
                v[k][i] = r == null ? Double.NaN : r;
            }
        }
        card.addView(MiniCharts.legend(c, names));
        // 类别多时每类至少 40dp 宽，放不下横向滑
        MiniCharts.Grouped g = new MiniCharts.Grouped(c, 240).setData(cats, v, pass);
        int need = cats.size() * Math.max(40, compare.size() * 12) + 40;
        int avail = Ui.wide(c) ? 340 : Ui.widthDp(c) - 64;
        if (need <= avail) {
            V.addTop(card, g, 8);
        } else {
            HorizontalScrollView hs = new HorizontalScrollView(c);
            LinearLayout inner = new LinearLayout(c);
            inner.addView(g, new LinearLayout.LayoutParams(Ui.dp(c, need), Ui.dp(c, 240)));
            hs.addView(inner);
            V.addTop(card, hs, 8);
        }
        return card;
    }

    private View compareList(Context c, List<JSONObject> compare) {
        LinearLayout card = card(c, "所选学生", null);
        Palette p = Palette.of(c);
        for (int k = 0; k < compare.size(); k++) {
            JSONObject st = compare.get(k);
            LinearLayout row = V.vbox(c);
            LinearLayout top = V.hbox(c);
            View dot = new View(c);
            dot.setBackground(V.round(c, p.series(k), 4));
            top.addView(dot, new LinearLayout.LayoutParams(Ui.dp(c, 10), Ui.dp(c, 10)));
            TextView name = V.text(c, Json.str(st, "name"), V.H3);
            V.addStart(top, name, 8);
            V.addStart(top, V.text(c, Json.str(st, "class"), V.CAPTION), 8);
            top.addView(V.spring(c));
            top.addView(V.text(c, Fmt.num(Json.dbl(st, "score")) + " 分 · " + Fmt.num(Json.dbl(st, "rate")) + "% · 第 "
                    + Json.num(st, "rank") + " / " + Json.num(st, "of") + " 名", V.BODY2));
            row.addView(top);
            FlowBox chips = ExamUi.tags(c);
            for (JSONObject g : Json.list(Json.arr(st, "by_scope"))) {
                Double r = Json.dblOrNull(g, "rate");
                Tone t = r == null ? Tone.NEUTRAL : r >= Json.dbl(data, "pass_line") ? Tone.SUCCESS : Tone.DANGER;
                chips.addView(ExamUi.tag(c, Json.str(g, "name") + " " + ExamUi.pct(r), t));
            }
            V.addTop(row, chips, 6);
            V.addTop(card, row, k == 0 ? 0 : 14);
        }
        return card;
    }

    private boolean rankingAll;

    private View rankingCard(Context c) {
        LinearLayout card = card(c, "名次", null);
        List<JSONObject> rows = Json.list(Json.arr(data, "ranking"));
        card.addView(V.text(c, "点一行可查看这个学生的答卷", V.CAPTION));
        DataTable t = new DataTable(c, new String[]{"姓名", "名次", "班级", "学号", "总分", "得分率", "客观题", "操作题"},
                new int[]{80, 52, 110, 100, 60, 70, 64, 64});
        int limit = rankingAll ? rows.size() : Math.min(30, rows.size());
        for (int i = 0; i < limit; i++) {
            JSONObject r = rows.get(i);
            Double rate = Json.dblOrNull(r, "rate");
            t.add(new CharSequence[]{Json.str(r, "name"), String.valueOf(Json.num(r, "rank")), Json.str(r, "class"),
                    Json.str(r, "no"), Fmt.num(Json.dbl(r, "score")), ExamUi.pct(rate),
                    Fmt.num(Json.dbl(r, "objective")), Fmt.num(Json.dbl(r, "subjective"))},
                    new int[]{0, 0, 0, 0, 0, ExamUi.rateColor(c, rate), 0, 0});
            final long sub = r.optLong("sub_id");
            t.onRowClick(i, v -> openSubmission(sub));
        }
        V.addTop(card, t, 8);
        if (!rankingAll && rows.size() > limit) {
            V.addTop(card, V.button(c, "显示全部 " + rows.size() + " 人", V.BTN_TONAL, v -> {
                rankingAll = true;
                int y = scroll.getScrollY();
                render();
                scroll.post(() -> scroll.scrollTo(0, y));
            }), 10);
        }
        return card;
    }

    private void openSubmission(long subId) {
        // 从分析页进答卷：只看 + 阅卷（删除、批量在提交记录页做），考试权限从列表取
        runBusy("正在打开…", () -> ExamApi.exam(examId), exam -> push(new SubmissionScreen(exam, subId, new ArrayList<>())));
    }
}
