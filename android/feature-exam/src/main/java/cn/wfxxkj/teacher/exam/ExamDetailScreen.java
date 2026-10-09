package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.RefreshLayout;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 一场考试的详情：概况数字、学生链接（复制 / 分享 / 二维码）、四个开关、
 * 进入提交记录（阅卷）、成绩分析、样卷、导出成绩、导出考试包，以及「错得最多的题」。
 * 对应网页 Exams.vue 列表里一行的全部按钮 + 下方「成绩」卡片的顶部按钮和右栏。
 */
final class ExamDetailScreen extends Screen {

    private final long id;
    private JSONObject exam;
    private JSONObject stats;

    private RefreshLayout refresh;
    private LinearLayout page;
    private StateView state;
    private boolean busyToggle;

    ExamDetailScreen(JSONObject exam) {
        this.exam = exam;
        this.id = exam.optLong("id");
    }

    @Override
    public String title() {
        return "考试详情";
    }

    @Override
    public String subtitle() {
        return Json.str(exam, "title");
    }

    private boolean canEdit() {
        return Json.bool(exam, "can_edit");
    }

    @Override
    protected View onCreateView(Context c) {
        page = V.page(c);
        ScrollView sv = V.scroll(c, page);
        refresh = new RefreshLayout(c);
        refresh.setContent(sv);
        refresh.setOnRefresh(this::load);
        state = new StateView(c);
        page.addView(state, V.matchWrap());
        return refresh;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    @Override
    protected void onShow() {
        // 从提交记录、阅卷回来：待阅、均分会变
        if (stats != null) load();
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (canEdit()) a.add(Action.icon(R.drawable.ic_edit, "修改设置", this::edit));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::load));
        a.add(Action.menu(R.drawable.ic_content_copy, "复制学生链接", this::copyLink));
        if (canEdit()) a.add(Action.menu(R.drawable.ic_delete, "删除考试", this::remove).danger());
        return a;
    }

    private void load() {
        run(() -> new Object[]{ExamApi.exam(id), ExamApi.stats(id)}, r -> {
            exam = (JSONObject) r[0];
            stats = (JSONObject) r[1];
            refresh.setRefreshing(false);
            invalidateChrome();
            render();
        }, e -> {
            refresh.setRefreshing(false);
            if (stats == null) {
                state.error(e.getMessage(), this::load);
                return true;
            }
            return false;
        });
    }

    // ---------- 界面 ----------

    private void render() {
        Context c = ctx();
        page.removeAllViews();
        page.addView(heroCard(c), V.matchWrap());

        // 概况数字
        GridBox nums = new GridBox(c, 104, 5, 8);
        int full = Json.num(exam, "full_score");
        nums.addView(ExamUi.stat(c, String.valueOf(Json.num(stats, "submission_count")), "已交卷", Tone.PRIMARY));
        nums.addView(ExamUi.stat(c, Fmt.num(Json.dblOrNull(stats, "avg_score")), full > 0 ? "均分（满分 " + full + "）" : "均分", Tone.NEUTRAL));
        nums.addView(ExamUi.stat(c, Fmt.num(Json.dblOrNull(stats, "max_score")), "最高分", Tone.SUCCESS));
        nums.addView(ExamUi.stat(c, Fmt.num(Json.dblOrNull(stats, "min_score")), "最低分", Tone.DANGER));
        int pending = Json.num(exam, "ungraded_count");
        nums.addView(ExamUi.stat(c, String.valueOf(pending), "份待阅卷", pending > 0 ? Tone.WARNING : Tone.NEUTRAL));
        V.addTop(page, nums, 12);

        // 宽屏左右两栏：左边链接 + 开关，右边操作 + 难题
        GridBox cols = new GridBox(c, 340, 2, 12);
        LinearLayout left = V.vbox(c), right = V.vbox(c);
        left.addView(linkCard(c), V.matchWrap());
        V.addTop(left, settingsCard(c), 12);
        right.addView(actionsCard(c), V.matchWrap());
        V.addTop(right, hardestCard(c), 12);
        cols.addView(left);
        cols.addView(right);
        V.addTop(page, cols, 12);
    }

    private View heroCard(Context c) {
        LinearLayout card = V.card(c);
        TextView t = V.text(c, Json.str(exam, "title"), V.H2);
        t.setTextIsSelectable(true);
        card.addView(t);
        LinearLayout tags = V.hbox(c);
        boolean open = Json.bool(exam, "is_open");
        tags.addView(ExamUi.tag(c, open ? "开放中" : "已关闭", open ? Tone.SUCCESS : Tone.NEUTRAL));
        if (!canEdit()) V.addStart(tags, ExamUi.tag(c, "只读", Tone.INFO), 6);
        int pending = Json.num(exam, "ungraded_count");
        if (pending > 0) V.addStart(tags, ExamUi.tag(c, pending + " 份待阅", Tone.WARNING), 6);
        V.addTop(card, tags, 8);
        LinearLayout kvs = V.vbox(c);
        kvs.addView(V.kv(c, "发布人", Json.str(exam, "owner_name")));
        kvs.addView(V.kv(c, "发给", ExamUi.targetsText(exam)));
        kvs.addView(V.kv(c, "发布时间", Fmt.dateTime(Json.str(exam, "created_at"))));
        int full = Json.num(exam, "full_score");
        kvs.addView(V.kv(c, "卷面满分", full > 0 ? full + " 分" : "百分制（老卷子按正确率折算）"));
        V.addTop(card, kvs, 8);
        if (!canEdit()) {
            V.addTop(card, V.notice(c, "这是管理员发布的考试：你可以查看成绩、阅自己班的卷、导出，但不能修改设置或删除。",
                    Tone.INFO), 8);
        }
        return card;
    }

    private View linkCard(Context c) {
        LinearLayout card = V.card(c);
        card.addView(ExamUi.cardTitle(c, "学生链接"));
        String link = ExamApi.linkOf(exam);
        TextView l = V.text(c, link, V.BODY);
        l.setTextIsSelectable(true);
        l.setTypeface(android.graphics.Typeface.MONOSPACE);
        l.setBackground(V.round(c, Palette.of(c).surfaceAlt, 10));
        V.pad(l, 12, 10, 12, 10);
        card.addView(l, V.matchWrap());
        card.addView(V.text(c, "学生打开链接直接答题，不需要账号；题目发给学生时不带答案，判分在服务器上做。", V.CAPTION));
        ((LinearLayout.LayoutParams) card.getChildAt(card.getChildCount() - 1).getLayoutParams()).topMargin = Ui.dp(c, 8);
        LinearLayout row = V.hbox(c);
        row.addView(V.button(c, R.drawable.ic_content_copy, "复制", V.BTN_TONAL, v -> copyLink()), V.weight(1));
        row.addView(V.space(c, 8));
        row.addView(V.button(c, R.drawable.ic_share, "分享", V.BTN_TONAL,
                v -> Sys.share(c, "把考试链接发给学生", Json.str(exam, "title") + "\n" + link)), V.weight(1));
        row.addView(V.space(c, 8));
        row.addView(V.button(c, R.drawable.ic_table_view, "二维码", V.BTN_TONAL,
                v -> QrSheet.show(this, Json.str(exam, "title"), link)), V.weight(1));
        V.addTop(card, row, 12);
        return card;
    }

    private View settingsCard(Context c) {
        LinearLayout card = V.card(c);
        V.pad(card, 16, 14, 8, 6);
        card.addView(ExamUi.cardTitle(c, "考试设置"));
        card.addView(toggleRow(c, "开放答题", "关掉后学生打不开链接", "is_open"));
        card.addView(toggleRow(c, "交卷看分数", "关掉则只提示交卷成功，成绩由老师公布", "show_score"));
        card.addView(toggleRow(c, "交卷看答案", "正式考试建议关，否则先考的学生能把答案带出去", "show_answer"));
        card.addView(toggleRow(c, "允许重考", "默认同一学号只能交一次", "allow_retake"));
        return card;
    }

    /** 一个开关：改了立刻存到服务器，失败就拨回去 */
    private View toggleRow(Context c, String label, String desc, String field) {
        LinearLayout row = V.hbox(c);
        row.setMinimumHeight(Ui.dp(c, 56));
        LinearLayout texts = V.vbox(c);
        texts.addView(V.text(c, label, V.BODY));
        texts.addView(V.text(c, desc, V.CAPTION));
        row.addView(texts, V.fill());
        Switch sw = new Switch(c);
        sw.setChecked(Json.bool(exam, field));
        sw.setEnabled(canEdit());
        row.addView(sw);
        sw.setOnCheckedChangeListener((b, on) -> {
            if (busyToggle) return;
            run(() -> ExamApi.updateExam(id, Json.of(field, on)), saved -> {
                Json.put(exam, field, on);
                toast(label + (on ? "：已打开" : "：已关闭"));
                if ("is_open".equals(field)) render();
            }, e -> {
                busyToggle = true;
                sw.setChecked(!on);
                busyToggle = false;
                return false;
            });
        });
        if (canEdit()) V.clickable(row, 8, v -> sw.toggle());
        else row.setAlpha(0.6f);
        return row;
    }

    private View actionsCard(Context c) {
        LinearLayout card = V.card(c);
        V.pad(card, 0, 8, 0, 8);
        int n = Json.num(exam, "submission_count");
        int pending = Json.num(exam, "ungraded_count");
        card.addView(V.row(c, R.drawable.ic_fact_check, Tone.PRIMARY, "提交记录与阅卷",
                "每个学生的成绩、答卷，操作题人工给分",
                n + " 份" + (pending > 0 ? " · " + pending + " 待阅" : ""), v -> openSubs()));
        card.addView(V.row(c, R.drawable.ic_analytics, Tone.SUCCESS, "成绩分析",
                "分数段、知识范围、班级对比、每题得分率", null,
                v -> push(new AnalysisScreen(id, Json.str(exam, "title")))));
        card.addView(V.row(c, R.drawable.ic_description, Tone.VIOLET, "样卷",
                "带答案的完整试卷，讲评用", null, v -> push(new SamplePaperScreen(id))));
        card.addView(V.row(c, R.drawable.ic_table_view, Tone.INFO, "导出成绩 Excel",
                "成绩汇总、题目分析、主观题作答三张表", null, v -> exportScores()));
        card.addView(V.row(c, R.drawable.ic_computer, Tone.WARNING, "导出考试包（.ekb）",
                "机房断网时的后路：拷到学生机上，和考试客户端放一起离线开考", null, v -> exportDeskPack()));
        return card;
    }

    /** 错得最多的 5 道题（网页成绩卡片右栏） */
    private View hardestCard(Context c) {
        LinearLayout card = V.card(c);
        card.addView(ExamUi.cardTitle(c, "错得最多的题"));
        List<JSONObject> qs = new ArrayList<>();
        for (JSONObject q : Json.list(Json.arr(stats, "questions"))) if (Json.bool(q, "scorable")) qs.add(q);
        Collections.sort(qs, (a, b) -> Double.compare(Json.dbl(a, "accuracy"), Json.dbl(b, "accuracy")));
        if (Json.num(stats, "submission_count") == 0 || qs.isEmpty()) {
            card.addView(V.text(c, "等有人交卷后这里会列出来", V.BODY2));
            return card;
        }
        Palette p = Palette.of(c);
        for (int i = 0; i < Math.min(5, qs.size()); i++) {
            JSONObject q = qs.get(i);
            LinearLayout row = V.hbox(c);
            row.setGravity(Gravity.TOP);
            V.pad(row, 0, 8, 0, 8);
            LinearLayout texts = V.vbox(c);
            texts.addView(V.lines(V.text(c, Json.str(q, "stem"), V.BODY), 2));
            texts.addView(V.text(c, ExamUi.dot(Json.str(q, "type"), Json.str(q, "scope"),
                    Json.str(q, "answer").isEmpty() ? null : "答案 " + Json.str(q, "answer")), V.CAPTION));
            row.addView(texts, V.fill());
            double acc = Json.dbl(q, "accuracy");
            TextView a = V.text(c, Fmt.num(acc) + "%", V.H3);
            a.setTextColor(acc >= 60 ? p.success : p.danger);
            V.addStart(row, a, 12);
            if (i > 0) card.addView(divider(c));
            card.addView(row);
        }
        TextView note = V.text(c, "完整的每题分析在「成绩分析」和导出的 Excel 第二张表里。", V.CAPTION);
        V.addTop(card, note, 6);
        return card;
    }

    private View divider(Context c) {
        View d = V.divider(c);
        d.setLayoutParams(new LinearLayout.LayoutParams(V.MATCH, Math.max(1, Ui.dp(c, 0.8f))));
        return d;
    }

    // ---------- 操作 ----------

    private void openSubs() {
        push(new SubmissionListScreen(exam));
    }

    private void copyLink() {
        String link = ExamApi.linkOf(exam);
        Sys.copy(ctx(), "考试链接", link);
        toast("链接已复制：" + link);
    }

    private void edit() {
        PublishSheet.edit(this, exam, saved -> load());
    }

    private void remove() {
        Dialogs.confirm(ctx(), "删除这场考试？",
                "确定删除《" + Json.str(exam, "title") + "》？已经收到的 " + Json.num(exam, "submission_count")
                        + " 份答卷会一起删掉，删了找不回来。",
                "删除", true, () -> runBusy("正在删除…", () -> {
                    ExamApi.deleteExam(id);
                    return true;
                }, ok -> {
                    toast("已删除");
                    finish(true);
                }));
    }

    private void exportScores() {
        Files.export(this, "正在导出成绩…", () -> ExamApi.exportScores(id), Json.str(exam, "title") + "_成绩.xlsx");
    }

    private void exportDeskPack() {
        Dialogs.confirm(ctx(), "导出考试包",
                "平时不用导出：学生端考试软件联网登录后会自己把卷子取下来。\n\n"
                        + "这个是给「机房网断了」准备的：导出的 .ekb 文件拷到学生机上，和考试客户端 exe 放一个文件夹，"
                        + "照样能考，考完收回 .ans 答卷文件。",
                "导出", false, () -> Files.export(this, "正在打包…", () -> ExamApi.exportDeskPack(id),
                        Json.str(exam, "title") + ".ekb"));
    }
}
