package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.TreeSet;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 提交记录（网页「成绩」卡片里的学生成绩表）：按班级、状态筛选，按姓名学号搜，可换排序；
 * 点一份进答卷 / 阅卷；能改这场考试的老师可以长按多选批量删除答卷。
 */
final class SubmissionListScreen extends Screen {

    private static final String S_ALL = "all", S_PENDING = "pending", S_PASS = "pass", S_FAIL = "fail";
    private static final String C_ALL = "";
    private static final String NO_CLASS = "未填班级";

    private final JSONObject exam;
    private final long examId;
    private ItemList<JSONObject> list;
    private ChipRow classRow, statusRow;
    private SearchBox search;
    private TextView summary;
    private final List<JSONObject> all = new ArrayList<>();
    private String sort = "score_desc";
    private int selCount = -1;

    SubmissionListScreen(JSONObject exam) {
        this.exam = exam;
        this.examId = exam.optLong("id");
    }

    @Override
    public String title() {
        return selCount >= 0 ? "已选 " + selCount + " 份" : "提交记录";
    }

    @Override
    public String subtitle() {
        return selCount >= 0 ? null : Json.str(exam, "title");
    }

    private boolean canEdit() {
        return Json.bool(exam, "can_edit");
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new SubCard(ctx);
            }

            @Override
            public void bind(View v, JSONObject s, int pos) {
                ((SubCard) v).bind(s);
            }
        });
        list.setCell(360, 3);

        LinearLayout header = V.vbox(c);
        search = new SearchBox(c, "搜姓名或学号");
        V.addTop(header, search, 4);
        statusRow = new ChipRow(c);
        statusRow.setOptions(Option.pairs(S_ALL, "全部", S_PENDING, "待阅卷", S_PASS, "及格", S_FAIL, "不及格"), S_ALL);
        V.addTop(header, statusRow, 6);
        classRow = new ChipRow(c);
        classRow.setVisibility(View.GONE);
        header.addView(classRow);
        summary = V.text(c, "", V.CAPTION);
        V.pad(summary, 4, 4, 0, 4);
        header.addView(summary);
        list.addHeader(header);

        search.setOnSearch(k -> render());
        statusRow.setOnPicked(o -> render());
        classRow.setOnPicked(o -> render());
        list.setOnRefresh(this::load);
        list.setOnItemClick((s, pos) -> open(s));
        if (canEdit()) {
            list.enableSelection(s -> s.optLong("id"), n -> {
                selCount = n;
                invalidateChrome();
            });
        }
        list.setEmpty("还没有人交卷", "把学生链接发给学生，交卷后这里会自动出现");
        return list;
    }

    @Override
    protected void onFirstShow() {
        list.loading();
        load();
    }

    @Override
    protected void onShow() {
        if (!all.isEmpty()) load();
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (selCount >= 0) {
            a.add(Action.icon(R.drawable.ic_select_all, "全选", () -> list.selectAll()));
            a.add(Action.icon(R.drawable.ic_delete, "删除选中的答卷", this::removeSelected));
            a.add(Action.icon(R.drawable.ic_close, "退出多选", () -> list.stopSelection()));
            return a;
        }
        a.add(Action.icon(R.drawable.ic_sort, "排序", this::pickSort));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", () -> {
            list.loading();
            load();
        }));
        a.add(Action.menu(R.drawable.ic_download, "导出成绩 Excel", () -> Files.export(this, "正在导出成绩…",
                () -> ExamApi.exportScores(examId), Json.str(exam, "title") + "_成绩.xlsx")));
        a.add(Action.menu(R.drawable.ic_analytics, "成绩分析",
                () -> push(new AnalysisScreen(examId, Json.str(exam, "title")))));
        if (canEdit()) a.add(Action.menu(R.drawable.ic_done_all, "多选删除", () -> list.startSelection()));
        return a;
    }

    @Override
    public boolean onBack() {
        if (list.isSelecting()) {
            list.stopSelection();
            return true;
        }
        return false;
    }

    private void load() {
        run(() -> ExamApi.submissions(examId), rows -> {
            all.clear();
            all.addAll(rows);
            buildClassRow();
            render();
        }, e -> {
            list.error(e.getMessage(), () -> {
                list.loading();
                load();
            });
            return all.isEmpty();
        });
    }

    private static String classOf(JSONObject s) {
        String c = Json.str(s, "student_class");
        return c.isEmpty() ? NO_CLASS : c;
    }

    /** 班级筛选条：只有一个班时不显示 */
    private void buildClassRow() {
        TreeSet<String> names = new TreeSet<>();
        for (JSONObject s : all) names.add(classOf(s));
        if (names.size() <= 1) {
            classRow.setVisibility(View.GONE);
            classRow.set(C_ALL);
            return;
        }
        Object cur = classRow.value();
        List<Option> opts = new ArrayList<>();
        opts.add(new Option(C_ALL, "全部班级"));
        for (String n : names) opts.add(new Option(n, n));
        classRow.setOptions(opts, cur != null && names.contains(String.valueOf(cur)) ? cur : C_ALL);
        classRow.setVisibility(View.VISIBLE);
    }

    private void render() {
        String k = search.keyword().toLowerCase(Locale.ROOT);
        Object st = statusRow.value();
        Object cls = classRow.getVisibility() == View.VISIBLE ? classRow.value() : C_ALL;
        List<JSONObject> shown = new ArrayList<>();
        int nPending = 0, nPass = 0, nFail = 0;
        for (JSONObject s : all) {
            boolean pend = Json.num(s, "pending_manual") > 0;
            boolean pass = ExamUi.passed(Json.dbl(s, "score"), Json.dbl(s, "full_score"));
            if (pend) nPending++;
            if (pass) nPass++;
            else nFail++;
            if (cls != null && !C_ALL.equals(cls) && !classOf(s).equals(cls)) continue;
            if (S_PENDING.equals(st) && !pend || S_PASS.equals(st) && !pass || S_FAIL.equals(st) && pass) continue;
            if (!k.isEmpty() && !Json.str(s, "student_name").toLowerCase(Locale.ROOT).contains(k)
                    && !Json.str(s, "student_no").toLowerCase(Locale.ROOT).contains(k)) continue;
            shown.add(s);
        }
        statusRow.setLabel(S_ALL, "全部 " + all.size());
        statusRow.setLabel(S_PENDING, "待阅卷 " + nPending);
        statusRow.setLabel(S_PASS, "及格 " + nPass);
        statusRow.setLabel(S_FAIL, "不及格 " + nFail);
        sortList(shown);
        String sortName = Option.labelOf(sortOptions(), sort);
        summary.setText((shown.size() == all.size() ? "共 " + all.size() + " 人" : "筛出 " + shown.size() + " / " + all.size() + " 人")
                + " · " + sortName + (canEdit() ? " · 长按可多选删除" : ""));
        if (!all.isEmpty() && shown.isEmpty()) list.setEmpty("没有符合条件的答卷", "换个筛选条件或关键词试试");
        else list.setEmpty("还没有人交卷", "把学生链接发给学生，交卷后这里会自动出现");
        list.setItems(shown);
    }

    private static List<Option> sortOptions() {
        return Option.pairs("score_desc", "总分从高到低", "score_asc", "总分从低到高",
                "time_desc", "最近交卷在前", "time_asc", "最早交卷在前", "pending", "待阅卷在前", "class", "按班级、学号");
    }

    private void pickSort() {
        Dialogs.choose(ctx(), "排序", sortOptions(), sort, o -> {
            sort = String.valueOf(o.value);
            render();
            list.scrollToTop();
        });
    }

    private void sortList(List<JSONObject> rows) {
        Collections.sort(rows, (a, b) -> {
            switch (sort) {
                case "score_asc":
                    return Double.compare(Json.dbl(a, "score"), Json.dbl(b, "score"));
                case "time_desc":
                    return Json.str(b, "submitted_at").compareTo(Json.str(a, "submitted_at"));
                case "time_asc":
                    return Json.str(a, "submitted_at").compareTo(Json.str(b, "submitted_at"));
                case "pending": {
                    int d = Integer.compare(Json.num(b, "pending_manual"), Json.num(a, "pending_manual"));
                    return d != 0 ? d : Double.compare(Json.dbl(b, "score"), Json.dbl(a, "score"));
                }
                case "class": {
                    int d = classOf(a).compareTo(classOf(b));
                    return d != 0 ? d : Json.str(a, "student_no").compareTo(Json.str(b, "student_no"));
                }
                default:
                    return Double.compare(Json.dbl(b, "score"), Json.dbl(a, "score"));
            }
        });
    }

    private void open(JSONObject s) {
        // 把当前列表顺序里排在后面、还要阅的答卷带过去，阅完一份可以直接下一份
        List<Long> queue = new ArrayList<>();
        boolean after = false;
        for (JSONObject x : list.items()) {
            if (after && Json.num(x, "pending_manual") > 0 && Json.bool(x, "can_grade")) queue.add(x.optLong("id"));
            if (x == s) after = true;
        }
        push(new SubmissionScreen(exam, s.optLong("id"), queue));
    }

    private void removeSelected() {
        List<JSONObject> rows = list.selection();
        if (rows.isEmpty()) {
            toast("先点选要删除的答卷");
            return;
        }
        List<Object> ids = new ArrayList<>();
        for (JSONObject r : rows) ids.add(r.optLong("id"));
        Dialogs.confirm(ctx(), "批量删除答卷",
                "删除选中的 " + rows.size() + " 份答卷？删掉后这些学生可以重新交卷，删了找不回来。",
                "删除 " + rows.size() + " 份", true,
                () -> runBusy("正在删除…", () -> ExamApi.deleteSubmissions(examId, ids), n -> {
                    toast("已删除 " + n + " 份");
                    list.stopSelection();
                    load();
                }));
    }

    /** 一份答卷的卡片 */
    private static final class SubCard extends LinearLayout {
        private final TextView avatar, name, meta, score, detail, time, action;
        private final FlowBox flags;

        SubCard(Context c) {
            super(c);
            setOrientation(VERTICAL);
            Palette p = Palette.of(c);
            setBackground(V.stroke(c, p.surface, p.border, 16));
            V.pad(this, 14, 12, 14, 12);

            LinearLayout top = V.hbox(c);
            avatar = V.avatar(c, "", 40);
            top.addView(avatar);
            LinearLayout texts = V.vbox(c);
            name = V.oneLine(V.text(c, "", V.H3));
            texts.addView(name);
            meta = V.oneLine(V.text(c, "", V.CAPTION));
            texts.addView(meta);
            LinearLayout.LayoutParams tl = V.fill();
            tl.setMarginStart(ExamUi.dp(c, 12));
            top.addView(texts, tl);
            score = V.text(c, "", V.H1);
            score.setGravity(Gravity.END);
            V.addStart(top, score, 8);
            addView(top);

            detail = V.text(c, "", V.BODY2);
            V.addTop(this, detail, 10);
            flags = ExamUi.tags(c);
            V.addTop(this, flags, 8);

            LinearLayout bottom = V.hbox(c);
            time = V.oneLine(V.text(c, "", V.CAPTION));
            bottom.addView(time, V.fill());
            action = V.text(c, "", V.LABEL);
            bottom.addView(action);
            V.addTop(this, bottom, 8);
        }

        void bind(JSONObject s) {
            Context c = getContext();
            Palette p = Palette.of(c);
            String nm = Json.str(s, "student_name");
            avatar.setText(nm.isEmpty() ? "?" : nm.substring(nm.length() - 1));
            name.setText(nm.isEmpty() ? "（未填姓名）" : nm);
            meta.setText(ExamUi.dot(classOf(s), Json.str(s, "student_no").isEmpty() ? "无学号" : Json.str(s, "student_no")));
            double sc = Json.dbl(s, "score"), full = Json.dbl(s, "full_score");
            score.setText(ExamUi.score(c, sc, full, V.H1).getText());
            score.setTextColor(ExamUi.passed(sc, full) ? p.success : p.danger);

            int pending = Json.num(s, "pending_manual");
            if (full > 0) {
                String d = "客观 " + Json.num(s, "objective_score") + "/" + Json.num(s, "objective_total");
                if (Json.num(s, "subjective_total") > 0) {
                    d += "　操作 " + Json.num(s, "subjective_score") + "/" + Json.num(s, "subjective_total");
                } else {
                    d += "　无操作题";
                }
                detail.setText(d);
            } else {
                detail.setText("答对 " + Json.num(s, "right_count") + " / " + Json.num(s, "objective_count") + " 题");
            }
            flags.removeAllViews();
            boolean canGrade = Json.bool(s, "can_grade");
            if (pending > 0) flags.addView(ExamUi.tag(c, "待阅 " + pending + " 题", Tone.WARNING));
            else if (Json.num(s, "subjective_total") > 0) flags.addView(ExamUi.tag(c, "已阅完", Tone.SUCCESS));
            if (!Json.str(s, "graded_by_name").isEmpty()) {
                flags.addView(ExamUi.tag(c, Json.str(s, "graded_by_name") + " 评阅", Tone.NEUTRAL));
            }
            if (!canGrade) flags.addView(ExamUi.tag(c, "非本班 · 只能查看", Tone.INFO));
            flags.setVisibility(flags.getChildCount() == 0 ? GONE : VISIBLE);

            time.setText("交卷 " + Fmt.shortDateTime(Json.str(s, "submitted_at")));
            // 和网页按钮文字一致：查看 / 阅卷 N / 答卷
            String act = !canGrade ? "查看 ›" : pending > 0 ? "阅卷 " + pending + " ›" : "答卷 ›";
            action.setText(act);
            action.setTextColor(canGrade && pending > 0 ? p.warning : p.primary);
        }
    }
}
