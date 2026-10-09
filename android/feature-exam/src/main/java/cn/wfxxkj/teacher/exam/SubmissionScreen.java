package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 一份学生答卷 + 操作题人工阅卷（网页「学生答卷」对话框）。
 * 每道题显示作答和参考答案、对错；操作题按检查点列出每一问的结果，带给分框（给满分 / 给 0 分）。
 * 底部固定一条：操作题合计 + 保存评分；后面还有待阅的答卷时可以「保存并阅下一份」。
 */
final class SubmissionScreen extends Screen {

    private static final String F_ALL = "all", F_MANUAL = "manual", F_WRONG = "wrong";

    private final JSONObject exam;
    private final long examId;
    private long subId;
    private final List<Long> queue;
    private JSONObject detail;

    private LinearLayout root, page, bar;
    private ScrollView scroll;
    private StateView state;
    private TextView barSum;
    private ChipRow filter;
    private LinearLayout questions;
    /** 题目 id → 给分输入框 */
    private final Map<String, EditText> inputs = new LinkedHashMap<>();
    private final List<JSONObject> manualItems = new ArrayList<>();
    private boolean dirty;

    SubmissionScreen(JSONObject exam, long subId, List<Long> queue) {
        this.exam = exam;
        this.examId = exam.optLong("id");
        this.subId = subId;
        this.queue = new ArrayList<>(queue);
    }

    @Override
    public String title() {
        return detail == null ? "学生答卷" : Json.str(detail, "student_name") + " 的答卷";
    }

    @Override
    public String subtitle() {
        return Json.str(exam, "title");
    }

    private boolean canGrade() {
        return detail != null && Json.bool(detail, "can_grade") && !manualItems.isEmpty();
    }

    @Override
    protected View onCreateView(Context c) {
        root = V.vbox(c);
        page = V.page(c);
        scroll = V.scroll(c, page);
        root.addView(scroll, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));
        state = new StateView(c);
        page.addView(state, V.matchWrap());

        // 底部固定的保存条
        bar = V.hbox(c);
        Palette p = Palette.of(c);
        bar.setBackgroundColor(p.surface);
        V.pad(bar, 16, 10, 16, 10);
        barSum = V.text(c, "", V.BODY2);
        bar.addView(barSum, V.fill());
        bar.setVisibility(View.GONE);
        LinearLayout.LayoutParams dl = new LinearLayout.LayoutParams(V.MATCH, Math.max(1, Ui.dp(c, 0.8f)));
        View line = V.divider(c);
        line.setLayoutParams(dl);
        LinearLayout barWrap = V.vbox(c);
        barWrap.addView(line);
        barWrap.addView(bar, V.matchWrap());
        root.addView(barWrap, V.matchWrap());
        return root;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::load));
        if (Json.bool(exam, "can_edit") && detail != null) {
            a.add(Action.menu(R.drawable.ic_delete, "删除这份答卷", this::remove).danger());
        }
        return a;
    }

    @Override
    public boolean onBack() {
        if (dirty && canGrade()) {
            Dialogs.confirm(ctx(), "还没保存评分", "改过的分数还没保存，直接离开会丢掉。", "不保存，离开", true,
                    () -> {
                        dirty = false;
                        finish();
                    });
            return true;
        }
        return false;
    }

    private void load() {
        if (state.getParent() == null) {
            page.removeAllViews();
            page.addView(state, V.matchWrap());
        }
        state.loading();
        run(() -> ExamApi.submission(examId, subId), d -> {
            detail = d;
            dirty = false;
            invalidateChrome();
            render();
            scroll.scrollTo(0, 0);
        }, e -> {
            if (detail == null) {
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
        inputs.clear();
        manualItems.clear();
        List<JSONObject> items = Json.list(Json.arr(detail, "detail"));
        for (JSONObject d : items) if (Json.bool(d, "manual")) manualItems.add(d);

        page.addView(headerCard(c), V.matchWrap());

        if (!manualItems.isEmpty()) {
            TextView n;
            if (!Json.bool(detail, "can_grade")) {
                String cls = Json.str(detail, "student_class");
                n = V.notice(c, "这份答卷是「" + (cls.isEmpty() ? "未填班级" : cls)
                        + "」的，不是你带的班，只能查看，不能评分；请该班老师批改。", Tone.INFO);
            } else {
                n = V.notice(c, "带给分框的是操作题。按检查点判过的：全部通过的已给满分、全部没过的给了 0 分，不用再管；"
                        + "部分通过的按比例预填了分数，看一眼没问题就保存（觉得不对可以改）。没挂仿真的机器判不了，要你看着作答给分。"
                        + "留空表示还没评，和给 0 分不是一回事。保存后总分自动重算，学生那边跟着更新。", Tone.WARNING);
            }
            V.addTop(page, n, 12);
        }

        filter = new ChipRow(c);
        int wrong = 0;
        for (JSONObject d : items) if (Json.bool(d, "scored") && !Json.bool(d, "ok")) wrong++;
        List<Option> opts = new ArrayList<>();
        opts.add(new Option(F_ALL, "全部 " + items.size() + " 题"));
        if (!manualItems.isEmpty()) opts.add(new Option(F_MANUAL, "操作题 " + manualItems.size()));
        opts.add(new Option(F_WRONG, "答错的 " + wrong));
        // 有题要阅时先只看操作题，省得在几十道选择题里往下翻
        boolean toGrade = canGrade() && Json.num(detail, "pending_manual") > 0;
        filter.setOptions(opts, toGrade ? F_MANUAL : F_ALL);
        filter.setOnPicked(o -> applyFilter());
        V.addTop(page, filter, 12);

        questions = V.vbox(c);
        for (int i = 0; i < items.size(); i++) {
            View card = questionCard(c, i + 1, items.get(i));
            card.setTag(items.get(i));
            V.addTop(questions, card, 10);
        }
        page.addView(questions, V.matchWrap());
        applyFilter();
        renderBar();
    }

    private void applyFilter() {
        Object f = filter.value();
        for (int i = 0; i < questions.getChildCount(); i++) {
            View v = questions.getChildAt(i);
            JSONObject d = (JSONObject) v.getTag();
            boolean show = F_ALL.equals(f)
                    || F_MANUAL.equals(f) && Json.bool(d, "manual")
                    || F_WRONG.equals(f) && Json.bool(d, "scored") && !Json.bool(d, "ok");
            v.setVisibility(show ? View.VISIBLE : View.GONE);
        }
    }

    private View headerCard(Context c) {
        Palette p = Palette.of(c);
        LinearLayout card = V.card(c);
        LinearLayout top = V.hbox(c);
        top.addView(V.avatar(c, Json.str(detail, "student_name"), 48));
        LinearLayout texts = V.vbox(c);
        texts.addView(V.text(c, Json.str(detail, "student_name"), V.H2));
        String no = Json.str(detail, "student_no");
        texts.addView(V.text(c, ExamUi.dot(Json.str(detail, "student_class").isEmpty() ? "未填班级"
                : Json.str(detail, "student_class"), no.isEmpty() ? "无学号" : "学号 " + no), V.CAPTION));
        LinearLayout.LayoutParams tl = V.fill();
        tl.setMarginStart(Ui.dp(c, 12));
        top.addView(texts, tl);
        double sc = Json.dbl(detail, "score"), full = Json.dbl(detail, "full_score");
        TextView score = ExamUi.score(c, sc, full, V.DISPLAY);
        score.setTextColor(ExamUi.passed(sc, full) ? p.success : p.danger);
        top.addView(score);
        card.addView(top);

        FlowBox info = ExamUi.tags(c);
        if (full > 0) {
            info.addView(ExamUi.tag(c, "客观 " + Json.num(detail, "objective_score") + " / "
                    + Json.num(detail, "objective_total"), Tone.PRIMARY));
            if (Json.num(detail, "subjective_total") > 0) {
                info.addView(ExamUi.tag(c, "操作题 " + Json.num(detail, "subjective_score") + " / "
                        + Json.num(detail, "subjective_total"), Tone.VIOLET));
            }
        } else {
            info.addView(ExamUi.tag(c, "答对 " + Json.num(detail, "right_count") + " / "
                    + Json.num(detail, "objective_count"), Tone.PRIMARY));
        }
        int pending = Json.num(detail, "pending_manual");
        if (pending > 0) info.addView(ExamUi.tag(c, "待阅 " + pending + " 题", Tone.WARNING));
        String grader = Json.str(detail, "graded_by_name");
        if (!grader.isEmpty()) info.addView(ExamUi.tag(c, grader + " 已评阅", Tone.SUCCESS));
        V.addTop(card, info, 12);
        TextView when = V.text(c, "交卷时间 " + Fmt.dateTime(Json.str(detail, "submitted_at"))
                + (Json.isNull(detail, "graded_at") ? "" : "　评阅时间 " + Fmt.dateTime(Json.str(detail, "graded_at"))), V.CAPTION);
        V.addTop(card, when, 8);
        return card;
    }

    private View questionCard(Context c, int no, JSONObject d) {
        Palette p = Palette.of(c);
        boolean manual = Json.bool(d, "manual");
        LinearLayout card = V.card(c);
        if (manual) {
            // 要阅的题：浅黄底 + 黄边，一眼看得出哪些等着给分
            card.setBackground(V.stroke(c, p.warningSoft, p.warning, 16));
        }

        FlowBox tags = ExamUi.tags(c);
        tags.addView(ExamUi.tag(c, "第 " + no + " 题", Tone.NEUTRAL));
        tags.addView(ExamUi.tag(c, Json.str(d, "type"), Tone.PRIMARY));
        int score = Json.num(d, "score");
        if (score > 0) tags.addView(ExamUi.tag(c, score + " 分", Tone.NEUTRAL));
        if (Json.bool(d, "auto")) {
            tags.addView(ExamUi.tag(c, "自动判分 " + Json.num(d, "check_passed") + "/" + Json.num(d, "check_total") + " 问", Tone.SUCCESS));
        }
        String id = Json.str(d, "id");
        if (Json.bool(d, "auto_graded")) {
            tags.addView(ExamUi.tag(c, Json.dbl(d, "earned") >= score ? "检查点全过，已自动给满分" : "检查点全没过，已自动给 0 分", Tone.SUCCESS));
        } else if (manual && Json.bool(d, "auto") && !Json.bool(d, "graded")) {
            tags.addView(ExamUi.tag(c, "部分通过，已按比例预填，待复核", Tone.WARNING));
        } else if (manual) {
            boolean has = Json.bool(d, "graded") || Json.bool(d, "auto");
            tags.addView(ExamUi.tag(c, has ? "已给分" : "待评阅", has ? Tone.SUCCESS : Tone.WARNING));
        } else if (!Json.bool(d, "scored")) {
            tags.addView(ExamUi.tag(c, "不计分", Tone.INFO));
        } else if (Json.bool(d, "ok")) {
            double e = Json.dbl(d, "earned");
            tags.addView(ExamUi.tag(c, "✓ 答对" + (e > 0 ? " +" + Fmt.num(e) : ""), Tone.SUCCESS));
        } else {
            tags.addView(ExamUi.tag(c, "✕ 答错", Tone.DANGER));
        }
        card.addView(tags);

        TextView stem = V.text(c, Json.str(d, "stem"), V.BODY);
        stem.setTextIsSelectable(true);
        V.addTop(card, stem, 10);

        // 选择题把选项列出来，学生选的和正确答案标色
        List<JSONObject> options = Json.list(Json.arr(d, "options"));
        String mine = Json.str(d, "mine"), answer = Json.str(d, "answer");
        if (!options.isEmpty() && !manual) {
            LinearLayout ol = V.vbox(c);
            for (JSONObject o : options) {
                String label = Json.str(o, "label");
                boolean right = !label.isEmpty() && answer.contains(label);
                boolean picked = !label.isEmpty() && mine.contains(label);
                TextView t = V.text(c, label + ". " + Json.str(o, "content"), V.BODY2);
                if (right) {
                    t.setTextColor(p.success);
                    V.bold(t);
                } else if (picked) {
                    t.setTextColor(p.danger);
                }
                V.pad(t, 0, 2, 0, 2);
                ol.addView(t);
            }
            V.addTop(card, ol, 6);
        }

        List<JSONObject> checks = Json.list(Json.arr(d, "checks"));
        if (!checks.isEmpty()) {
            // 仿真题：每一问过没过、为什么。原始作答是一大段 JSON，不显示
            LinearLayout cl = V.vbox(c);
            for (JSONObject ck : checks) {
                boolean ok = Json.bool(ck, "ok");
                LinearLayout row = V.hbox(c);
                row.setGravity(Gravity.TOP);
                V.pad(row, 0, 3, 0, 3);
                row.addView(V.icon(c, ok ? R.drawable.ic_check_circle : R.drawable.ic_cancel, ok ? p.success : p.danger, 18));
                TextView t = V.text(c, Json.str(ck, "desc") + (ok ? "" : "（" + Json.str(ck, "why") + "）"), V.BODY2);
                if (!ok) t.setTextColor(p.danger);
                LinearLayout.LayoutParams lp = V.fill();
                lp.setMarginStart(Ui.dp(c, 6));
                row.addView(t, lp);
                cl.addView(row);
            }
            V.addTop(card, cl, 8);
            if (!Json.str(d, "reason").isEmpty()) V.addTop(card, V.text(c, Json.str(d, "reason"), V.CAPTION), 4);
        } else {
            LinearLayout ans = V.vbox(c);
            ans.setBackground(V.round(c, p.surfaceAlt, 10));
            V.pad(ans, 12, 8, 12, 8);
            TextView m = V.text(c, "学生作答：" + (mine.isEmpty() ? "未作答" : mine), V.BODY2);
            if (Json.bool(d, "scored") && !Json.bool(d, "ok")) m.setTextColor(p.danger);
            m.setTextIsSelectable(true);
            ans.addView(m);
            if (!answer.isEmpty()) {
                TextView a = V.text(c, "参考答案：" + answer, V.BODY2);
                a.setTextColor(p.success);
                a.setTextIsSelectable(true);
                V.addTop(ans, a, 4);
            }
            V.addTop(card, ans, 8);
        }

        if (manual) V.addTop(card, gradeRow(c, d, id, score), 12);
        return card;
    }

    /** 给分：输入框 + / 满分 + 给满分 / 给 0 分 */
    private View gradeRow(Context c, JSONObject d, String id, int full) {
        boolean can = Json.bool(detail, "can_grade");
        FlowBox row = new FlowBox(c, 8, 8);
        LinearLayout box = V.hbox(c);
        box.addView(V.text(c, "给分", V.LABEL));
        EditText in = Fields.input(c, "未评");
        in.setInputType(InputType.TYPE_CLASS_NUMBER);
        in.setGravity(Gravity.CENTER);
        in.setSelectAllOnFocus(true);
        // 已给过分的、按检查点判过的回填；没给过的留空（留空和给 0 分是两回事）
        if (Json.bool(d, "graded") || Json.bool(d, "auto")) in.setText(Fmt.num(Json.dbl(d, "earned")));
        in.setEnabled(can);
        LinearLayout.LayoutParams ilp = new LinearLayout.LayoutParams(Ui.dp(c, 84), V.WRAP);
        ilp.setMarginStart(Ui.dp(c, 8));
        ilp.setMarginEnd(Ui.dp(c, 6));
        box.addView(in, ilp);
        box.addView(V.text(c, "/ " + full + " 分", V.BODY2));
        row.addView(box);
        if (can) {
            row.addView(V.button(c, "给满分", V.BTN_TONAL, v -> in.setText(String.valueOf(full))));
            row.addView(V.button(c, "给 0 分", V.BTN_OUTLINE, v -> in.setText("0")));
        }
        in.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int a, int b, int cc) {}

            @Override
            public void onTextChanged(CharSequence s, int a, int b, int cc) {}

            @Override
            public void afterTextChanged(Editable s) {
                dirty = true;
                Integer v = parse(s.toString());
                in.setActivated(v != null && v > full);
                renderBar();
            }
        });
        inputs.put(id, in);
        return row;
    }

    private static Integer parse(String s) {
        try {
            s = s.trim();
            return s.isEmpty() ? null : Integer.valueOf(s);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /** 底部条：操作题合计（实时）+ 保存 */
    private void renderBar() {
        if (manualItems.isEmpty()) {
            bar.setVisibility(View.GONE);
            return;
        }
        Context c = ctx();
        int got = 0, full = 0;
        for (JSONObject d : manualItems) {
            full += Json.num(d, "score");
            EditText in = inputs.get(Json.str(d, "id"));
            Integer v = in == null ? null : parse(in.getText().toString());
            if (v != null) got += v;
        }
        android.text.SpannableStringBuilder sb = new android.text.SpannableStringBuilder("操作题合计 ");
        int st = sb.length();
        sb.append(String.valueOf(got));
        sb.setSpan(new android.text.style.StyleSpan(android.graphics.Typeface.BOLD), st, sb.length(), 0);
        sb.setSpan(new android.text.style.RelativeSizeSpan(1.3f), st, sb.length(), 0);
        sb.append(" / ").append(String.valueOf(full)).append(" 分");
        barSum.setText(sb);
        bar.setVisibility(View.VISIBLE);
        while (bar.getChildCount() > 1) bar.removeViewAt(1);
        if (canGrade()) {
            if (!queue.isEmpty()) {
                V.addStart(bar, V.button(c, "保存并下一份", V.BTN_TONAL, v -> save(true)), 8);
            }
            V.addStart(bar, V.button(c, "保存评分", V.BTN_PRIMARY, v -> save(false)), 8);
        }
    }

    private void save(boolean next) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        for (int i = 0; i < manualItems.size(); i++) {
            JSONObject d = manualItems.get(i);
            String id = Json.str(d, "id");
            EditText in = inputs.get(id);
            String raw = in == null ? "" : in.getText().toString().trim();
            if (raw.isEmpty()) continue;
            Integer v = parse(raw);
            int full = Json.num(d, "score");
            if (v == null || v < 0) {
                toast("给分要填 0 以上的整数");
                focus(in);
                return;
            }
            if (v > full) {
                toast("这道题最多 " + full + " 分，给多了");
                focus(in);
                return;
            }
            scores.put(id, v);
        }
        runBusy("正在保存评分…", () -> ExamApi.gradeManual(examId, subId, scores), r -> {
            int pending = Json.num(r, "pending_manual");
            toast(pending > 0 ? "已保存，还有 " + pending + " 道题没给分" : "已评完，这份卷子 " + Json.num(r, "score") + " 分");
            dirty = false;
            if (next && !queue.isEmpty()) {
                subId = queue.remove(0);
                detail = null;
                load();
            } else {
                finish(true);
            }
        });
    }

    private void focus(EditText in) {
        if (in == null) return;
        in.setActivated(true);
        in.requestFocus();
        in.post(() -> in.requestRectangleOnScreen(new android.graphics.Rect(0, 0, in.getWidth(), in.getHeight()), false));
    }

    private void remove() {
        String no = Json.str(detail, "student_no");
        Dialogs.confirm(ctx(), "删除答卷",
                "删除 " + Json.str(detail, "student_name") + "（" + (no.isEmpty() ? "无学号" : no)
                        + "）的答卷？删掉后这个学生可以重新交卷。",
                "删除", true, () -> runBusy("正在删除…", () -> {
                    ExamApi.deleteSubmission(examId, subId);
                    return true;
                }, ok -> {
                    toast("已删除");
                    dirty = false;
                    finish(true);
                }));
    }
}
