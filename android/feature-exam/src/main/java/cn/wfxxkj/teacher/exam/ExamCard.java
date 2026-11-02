package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 考试列表里的一张卡片：标题、状态标签、交卷/均分/待阅三个数、发给哪些班，
 * 底下一排快捷操作（复制链接、二维码、成绩分析）。
 */
final class ExamCard extends LinearLayout {

    /** 卡片上的快捷按钮 */
    interface Quick {
        void copyLink(JSONObject exam);

        void showQr(JSONObject exam);

        void analysis(JSONObject exam);
    }

    private final TextView title, sub, nSubs, nAvg, nPending, targets;
    private final FlowBox tags;
    private JSONObject exam;

    ExamCard(Context c, Quick quick) {
        super(c);
        setOrientation(VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 16));
        V.pad(this, 16, 14, 16, 6);

        LinearLayout head = V.hbox(c);
        head.setGravity(Gravity.TOP);
        head.addView(V.iconTile(c, R.drawable.ic_assignment, Tone.PRIMARY));
        LinearLayout texts = V.vbox(c);
        title = V.lines(V.text(c, "", V.H3), 2);
        texts.addView(title);
        sub = V.oneLine(V.text(c, "", V.CAPTION));
        V.addTop(texts, sub, 2);
        LinearLayout.LayoutParams tl = V.fill();
        tl.setMarginStart(ExamUi.dp(c, 12));
        tl.setMarginEnd(ExamUi.dp(c, 24)); // 右上角留给多选的勾
        head.addView(texts, tl);
        addView(head);

        tags = ExamUi.tags(c);
        V.addTop(this, tags, 10);

        // 三个数
        LinearLayout nums = V.hbox(c);
        nSubs = num(c, nums, "交卷");
        nAvg = num(c, nums, "均分");
        nPending = num(c, nums, "待阅");
        V.addTop(this, nums, 12);

        targets = V.lines(V.text(c, "", V.CAPTION), 2);
        V.addTop(this, targets, 8);

        LinearLayout.LayoutParams dl = new LinearLayout.LayoutParams(V.MATCH, Math.max(1, ExamUi.dp(c, 0.8f)));
        dl.topMargin = ExamUi.dp(c, 10);
        addView(V.divider(c), dl);

        LinearLayout acts = V.hbox(c);
        acts.addView(V.button(c, R.drawable.ic_content_copy, "复制链接", V.BTN_TEXT, v -> quick.copyLink(exam)));
        acts.addView(V.button(c, R.drawable.ic_table_view, "二维码", V.BTN_TEXT, v -> quick.showQr(exam)));
        acts.addView(V.spring(c));
        acts.addView(V.button(c, R.drawable.ic_analytics, "分析", V.BTN_TEXT, v -> quick.analysis(exam)));
        V.addTop(this, acts, 2);
    }

    private static TextView num(Context c, LinearLayout row, String label) {
        LinearLayout box = V.vbox(c);
        TextView n = V.oneLine(V.text(c, "—", V.H2));
        box.addView(n);
        box.addView(V.text(c, label, V.CAPTION));
        row.addView(box, V.weight(1));
        return n;
    }

    void bind(JSONObject e) {
        exam = e;
        Context c = getContext();
        Palette p = Palette.of(c);
        title.setText(Json.str(e, "title"));
        sub.setText(ExamUi.dot(Json.str(e, "owner_name"), Fmt.shortDateTime(Json.str(e, "created_at"))));

        tags.removeAllViews();
        boolean open = Json.bool(e, "is_open");
        tags.addView(ExamUi.tag(c, open ? "开放中" : "已关闭", open ? Tone.SUCCESS : Tone.NEUTRAL));
        if (!Json.bool(e, "can_edit")) tags.addView(ExamUi.tag(c, "只读", Tone.INFO));
        if (Json.bool(e, "show_score")) tags.addView(ExamUi.tag(c, "交卷看分", Tone.PRIMARY));
        if (Json.bool(e, "show_answer")) tags.addView(ExamUi.tag(c, "交卷看答案", Tone.WARNING));
        if (Json.bool(e, "early_submit")) tags.addView(ExamUi.tag(c, "可提前交卷", Tone.SUCCESS));
        if (Json.bool(e, "allow_retake")) tags.addView(ExamUi.tag(c, "可重考", Tone.VIOLET));

        nSubs.setText(String.valueOf(Json.num(e, "submission_count")));
        Double avg = Json.dblOrNull(e, "avg_score");
        int full = Json.num(e, "full_score");
        if (avg == null) {
            nAvg.setText("—");
            nAvg.setTextColor(p.text);
        } else {
            nAvg.setText(ExamUi.score(c, avg, full, V.H2).getText());
            nAvg.setTextColor(ExamUi.passed(avg, full) ? p.success : p.danger);
        }
        int pending = Json.num(e, "ungraded_count");
        nPending.setText(pending > 0 ? String.valueOf(pending) : "—");
        nPending.setTextColor(pending > 0 ? p.warning : p.text3);
        targets.setText("发给：" + ExamUi.targetsText(e));
    }
}
