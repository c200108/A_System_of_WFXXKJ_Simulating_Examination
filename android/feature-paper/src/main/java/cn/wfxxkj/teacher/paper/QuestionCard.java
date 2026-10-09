package cn.wfxxkj.teacher.paper;

import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.text.Editable;
import android.text.InputType;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.io.Images;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 卷面上的一道题（卡片）。两种用法：
 * <ul>
 *   <li>试卷：纯展示，可以显示/隐藏答案（正确选项标绿）；</li>
 *   <li>在线自测：点选项作答、操作题写步骤，交卷后标出对错和答案。</li>
 * </ul>
 */
final class QuestionCard extends LinearLayout {

    private final JSONObject q;
    private final Quiz quiz;
    private final boolean quizMode;
    private final List<TextView[]> optionViews = new ArrayList<>();
    private final List<LinearLayout> optionRows = new ArrayList<>();

    /** quiz 为 null 表示试卷模式 */
    QuestionCard(Context c, JSONObject q, int no, boolean showAnswer, Quiz quiz) {
        super(c);
        this.q = q;
        this.quiz = quiz;
        this.quizMode = quiz != null;
        setOrientation(VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 16));
        V.pad(this, 14, 14, 14, 12);

        String type = Json.str(q, "type");
        boolean op = Quiz.OP.equals(type);

        // ---- 题号行 ----
        LinearLayout head = V.hbox(c);
        TextView num = V.text(c, String.valueOf(no), V.LABEL);
        num.setTextColor(p.primary);
        num.setGravity(Gravity.CENTER);
        num.setMinWidth(Ui.dp(c, 28));
        num.setBackground(V.round(c, p.primarySoft, 14));
        V.pad(num, 6, 0, 6, 0);
        head.addView(num, new LayoutParams(V.WRAP, Ui.dp(c, 28)));
        V.addStart(head, V.tag(c, type, op ? Tone.VIOLET : Tone.PRIMARY), 8);
        head.addView(V.spring(c));
        if (quizMode && quiz.graded) {
            TextView mark;
            if (!Quiz.scorable(q)) mark = V.tag(c, op ? "自评" : "不计分", Tone.WARNING);
            else if (quiz.isCorrect(q)) mark = V.tag(c, "✓ 正确", Tone.SUCCESS);
            else mark = V.tag(c, "✕ 错误", Tone.DANGER);
            V.addStart(head, mark, 6);
        }
        int score = Json.num(q, "score");
        if (score > 0) V.addStart(head, V.tag(c, score + " 分", Tone.NEUTRAL), 6);
        addView(head);

        // ---- 题干 ----
        TextView stem = V.text(c, Json.str(q, "stem"), V.BODY);
        stem.setTextSize(16);
        stem.setLineSpacing(0, 1.25f);
        stem.setTextIsSelectable(!quizMode);
        V.addTop(this, stem, 10);

        // ---- 配图（点开放大） ----
        final String img = Json.str(q, "image_url");
        if (!img.isEmpty()) {
            ImageView iv = new ImageView(c);
            iv.setAdjustViewBounds(true);
            iv.setMaxHeight(Ui.dp(c, 260));
            iv.setScaleType(ImageView.ScaleType.FIT_START);
            iv.setBackground(V.round(c, p.surfaceAlt, 10));
            iv.setClipToOutline(true);
            Images.load(iv, img, Ui.dp(c, 480));
            iv.setOnClickListener(v -> zoom(c, img));
            V.addTop(this, iv, 10);
        }

        // ---- 选项 / 作答 ----
        List<JSONObject> opts = Json.list(Json.arr(q, "options"));
        if (quizMode && op) {
            final long id = q.optLong("id");
            EditText e = Fields.input(c, "写下你的操作步骤，交卷后对照答案要点自评");
            e.setSingleLine(false);
            e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
            e.setMinLines(3);
            e.setGravity(Gravity.TOP | Gravity.START);
            String mine = quiz.resp.get(id);
            if (mine != null) e.setText(mine);
            e.setEnabled(!quiz.graded);
            e.addTextChangedListener(new TextWatcher() {
                @Override
                public void beforeTextChanged(CharSequence s, int st, int co, int af) {}

                @Override
                public void onTextChanged(CharSequence s, int st, int be, int co) {}

                @Override
                public void afterTextChanged(Editable s) {
                    quiz.resp.put(id, s.toString());
                }
            });
            V.addTop(this, e, 10);
        } else if (!opts.isEmpty()) {
            LinearLayout box = V.vbox(c);
            for (JSONObject o : opts) {
                final String label = Json.str(o, "label");
                LinearLayout row = V.hbox(c);
                row.setGravity(Gravity.TOP);
                V.pad(row, 8, 7, 10, 7);
                TextView l = V.text(c, label, V.LABEL);
                l.setGravity(Gravity.CENTER);
                int s = Ui.dp(c, 24);
                row.addView(l, new LayoutParams(s, s));
                TextView content = V.text(c, Json.str(o, "content"), V.BODY);
                LayoutParams clp = V.fill();
                clp.setMarginStart(Ui.dp(c, 10));
                row.addView(content, clp);
                optionRows.add(row);
                optionViews.add(new TextView[]{l, content});
                if (quizMode && !quiz.graded) {
                    V.clickable(row, 10, v -> {
                        quiz.resp.put(q.optLong("id"), label);
                        styleOptions(false);
                    });
                }
                LayoutParams rlp = V.matchWrap();
                rlp.topMargin = Ui.dp(c, 4);
                box.addView(row, rlp);
            }
            V.addTop(this, box, 8);
            styleOptions(showAnswer);
        }

        // ---- 答案 ----
        boolean revealAnswer = quizMode ? quiz.graded : showAnswer;
        if (revealAnswer) {
            String ans = Json.str(q, "answer").trim();
            TextView a;
            if (ans.isEmpty()) {
                a = V.notice(c, quizMode ? "这道题原卷未给答案，不计分。" : "原卷未给答案", Tone.WARNING);
            } else {
                a = V.notice(c, (op ? "答案要点：\n" : "答案：") + ans, Tone.SUCCESS);
                a.setTypeface(op ? Typeface.DEFAULT : Typeface.DEFAULT_BOLD);
                a.setTextIsSelectable(true);
            }
            V.addTop(this, a, 10);
        }

        // ---- 来源标签 ----
        FlowBox meta = new FlowBox(c, 6, 6);
        meta.addView(V.tag(c, Json.str(q, "scope"), Tone.INFO));
        int diff = Json.num(q, "difficulty");
        if (diff > 0) meta.addView(V.tag(c, "难度 " + diff, Tone.NEUTRAL));
        if (!Json.str(q, "source").isEmpty()) meta.addView(V.tag(c, Json.str(q, "source"), Tone.NEUTRAL));
        if (!Json.str(q, "code").isEmpty()) meta.addView(V.tag(c, Json.str(q, "code"), Tone.NEUTRAL));
        V.addTop(this, meta, 12);
    }

    /** 选项的样子：选中、对、错、（试卷模式）显示答案 */
    private void styleOptions(boolean showAnswer) {
        Context c = getContext();
        Palette p = Palette.of(c);
        List<JSONObject> opts = Json.list(Json.arr(q, "options"));
        String mine = quizMode ? quiz.resp.get(q.optLong("id")) : null;
        for (int i = 0; i < optionRows.size(); i++) {
            String label = Json.str(opts.get(i), "label");
            boolean right = Quiz.isRightOption(q, label);
            boolean picked = label.equals(mine);
            int fill = 0, stroke = 0, badgeFg = p.text2, badgeBg = p.surfaceAlt;
            if (quizMode && quiz.graded && Quiz.scorable(q)) {
                if (right) {
                    fill = p.successSoft;
                    stroke = p.success;
                    badgeFg = 0xFFFFFFFF;
                    badgeBg = p.success;
                } else if (picked) {
                    fill = p.dangerSoft;
                    stroke = p.danger;
                    badgeFg = 0xFFFFFFFF;
                    badgeBg = p.danger;
                }
            } else if (quizMode && picked) {
                fill = p.primarySoft;
                stroke = p.primary;
                badgeFg = p.onPrimary;
                badgeBg = p.primary;
            } else if (!quizMode && showAnswer && right) {
                fill = p.successSoft;
                badgeFg = 0xFFFFFFFF;
                badgeBg = p.success;
            }
            GradientDrawable bg = V.round(c, fill, 10);
            if (stroke != 0) bg.setStroke(Ui.dp(c, 1.2f), stroke);
            else if (quizMode) bg.setStroke(Ui.dp(c, 1), p.border);
            LinearLayout row = optionRows.get(i);
            if (quizMode && !quiz.graded) row.setBackground(V.ripple(c, bg, 10));
            else row.setBackground(bg);
            TextView badge = optionViews.get(i)[0];
            badge.setTextColor(badgeFg);
            badge.setBackground(V.round(c, badgeBg, 12));
        }
    }

    /** 点图放大看 */
    static void zoom(Context c, String url) {
        Sheet s = new Sheet(c, "题目配图");
        ImageView big = new ImageView(c);
        big.setAdjustViewBounds(true);
        big.setScaleType(ImageView.ScaleType.FIT_CENTER);
        Images.load(big, url, Ui.dp(c, 1000));
        s.content(big);
        s.buttons(null, null, "关闭", s::dismiss);
        s.show();
    }

    /** 大题标题：「一、选择题」+「共 30 题，共 30 分」+ 一行作答说明 */
    static View sectionHeader(Context c, String numeral, JSONObject g, String hint) {
        Palette p = Palette.of(c);
        LinearLayout row = V.hbox(c);
        row.setGravity(Gravity.TOP);
        View bar = new View(c);
        bar.setBackground(V.round(c, p.primary, 2));
        row.addView(bar, new LayoutParams(Ui.dp(c, 4), Ui.dp(c, 20)));
        LinearLayout texts = V.vbox(c);
        String name = Json.str(g, "name");
        if (name.isEmpty()) name = Json.str(g, "type");
        texts.addView(V.text(c, numeral + "、" + name, V.H3));
        int n = Json.arr(g, "items").length();
        int sc = Json.num(g, "score");
        String sub = "共 " + n + " 题" + (sc > 0 ? "，共 " + sc + " 分" : "");
        if (!TextUtils.isEmpty(hint)) sub += " · " + hint;
        texts.addView(V.text(c, sub, V.CAPTION));
        LayoutParams lp = V.fill();
        lp.setMarginStart(Ui.dp(c, 10));
        row.addView(texts, lp);
        V.pad(row, 2, 18, 0, 10);
        return row;
    }
}
