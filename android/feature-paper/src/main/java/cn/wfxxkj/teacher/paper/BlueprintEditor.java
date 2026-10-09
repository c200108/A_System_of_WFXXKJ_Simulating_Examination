package cn.wfxxkj.teacher.paper;

import android.content.Context;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 卷面结构编辑区：
 * <ul>
 *   <li>六大题：每个大题一张小卡，右上改分值，下面每组一行改题量，凑不齐时标黄；</li>
 *   <li>按题型：每个题型一行改题量（不设分值）。</li>
 * </ul>
 * 改了任何数字都回调 {@code onChange}，由页面去刷新抽题预览。
 */
final class BlueprintEditor {

    private final Context ctx;
    private final Blueprint bp;
    private final Runnable onChange;
    private final LinearLayout root;
    private final LinearLayout sectionsBox;
    private final LinearLayout typesBox;
    private final TextView totalText, totalWarn;
    private final List<NumberStepper> scoreSteppers = new ArrayList<>();
    private final List<NumberStepper> countSteppers = new ArrayList<>();
    private final List<String> countKeys = new ArrayList<>();
    private final Map<String, TextView> shortLines = new HashMap<>();
    private final Map<String, LinearLayout> sectionCards = new HashMap<>();

    BlueprintEditor(Context c, Blueprint bp, Runnable onChange) {
        this.ctx = c;
        this.bp = bp;
        this.onChange = onChange;
        root = V.vbox(c);

        // ---- 六大题 ----
        sectionsBox = V.vbox(c);
        for (int si = 0; si < bp.sections.size(); si++) {
            LinearLayout card = sectionCard(bp.sections.get(si), si);
            LinearLayout.LayoutParams lp = V.matchWrap();
            if (si > 0) lp.topMargin = Ui.dp(c, 10);
            sectionsBox.addView(card, lp);
        }
        LinearLayout total = V.hbox(c);
        V.pad(total, 4, 12, 0, 0);
        LinearLayout texts = V.vbox(c);
        totalText = V.text(c, "", V.BODY);
        texts.addView(totalText);
        totalWarn = V.text(c, "不是 100 分，确认一下", V.CAPTION);
        totalWarn.setTextColor(Palette.of(c).warning);
        texts.addView(totalWarn);
        total.addView(texts, V.fill());
        total.addView(V.button(c, cn.wfxxkj.teacher.core.R.drawable.ic_restart_alt, "恢复默认", V.BTN_TEXT, v -> {
            bp.resetBlueprint();
            syncFromModel();
            changed();
        }));
        sectionsBox.addView(total);
        TextView note = V.text(c, "每个大题的分按题目难度摊到题上，同一大题里操作题的分最高；"
                + "操作题要老师在成绩页逐题给分，学生交卷先拿到客观题得分。", V.CAPTION);
        V.addTop(sectionsBox, note, 6);
        root.addView(sectionsBox);

        // ---- 按题型 ----
        typesBox = V.vbox(c);
        for (final String t : bp.types) {
            LinearLayout row = V.hbox(c);
            V.pad(row, 14, 6, 6, 6);
            row.setMinimumHeight(Ui.dp(c, 52));
            row.setBackground(V.round(c, Palette.of(c).surfaceAlt, 12));
            row.addView(V.text(c, t, V.BODY), V.fill());
            Integer v0 = bp.counts.get(t);
            final NumberStepper st = new NumberStepper(c, v0 == null ? 0 : v0, 0, 300);
            st.setOnChanged(v -> {
                bp.counts.put(t, v);
                changed();
            });
            countSteppers.add(st);
            countKeys.add("type:" + t);
            row.addView(st);
            V.addStart(row, V.text(c, "题", V.CAPTION), 6);
            V.addTop(typesBox, row, typesBox.getChildCount() == 0 ? 0 : 8);
        }
        V.addTop(typesBox, V.text(c, "这种方式不给题目赋分，判分仍按客观题正确率折成百分制。", V.CAPTION), 10);
        root.addView(typesBox);

        renderMode();
        renderTotal();
    }

    View view() {
        return root;
    }

    /** 一个大题的卡片 */
    private LinearLayout sectionCard(final Blueprint.Section sec, int si) {
        Context c = ctx;
        Palette p = Palette.of(c);
        LinearLayout card = V.vbox(c);
        card.setBackground(V.round(c, p.surfaceAlt, 14));
        V.pad(card, 12, 10, 10, 12);

        LinearLayout head = V.hbox(c);
        TextView no = V.text(c, bp.numeral(si), V.LABEL);
        no.setTextColor(p.primary);
        no.setGravity(Gravity.CENTER);
        no.setBackground(V.round(c, p.primarySoft, 7));
        int s = Ui.dp(c, 26);
        head.addView(no, new LinearLayout.LayoutParams(s, s));
        TextView name = V.text(c, sec.name, V.H3);
        name.setTextSize(15);
        LinearLayout.LayoutParams nlp = V.fill();
        nlp.setMarginStart(Ui.dp(c, 10));
        nlp.setMarginEnd(Ui.dp(c, 8));
        head.addView(name, nlp);
        Integer sc = bp.sectionScores.get(sec.name);
        final NumberStepper score = new NumberStepper(c, sc == null ? sec.score : sc, 0, 200);
        score.setOnChanged(v -> {
            bp.sectionScores.put(sec.name, v);
            changed();
        });
        scoreSteppers.add(score);
        head.addView(score);
        V.addStart(head, V.text(c, "分", V.CAPTION), 6);
        card.addView(head);

        for (int li = 0; li < sec.slots.size(); li++) {
            final Blueprint.Slot slot = sec.slots.get(li);
            final String key = Blueprint.slotKey(sec, li);
            LinearLayout row = V.hbox(c);
            V.pad(row, 36, 0, 0, 0);
            FlowBox tags = new FlowBox(c, 6, 6);
            tags.addView(V.tag(c, slot.type, Tone.PRIMARY));
            if (!slot.scopes.isEmpty()) tags.addView(V.tag(c, android.text.TextUtils.join(" / ", slot.scopes), Tone.INFO));
            if ("long_or_image".equals(slot.prefer)) tags.addView(V.tag(c, "长题干或带图", Tone.WARNING));
            for (String k : slot.simKinds) tags.addView(V.tag(c, Blueprint.kindLabel(k), Tone.SUCCESS));
            LinearLayout.LayoutParams tlp = V.fill();
            tlp.setMarginEnd(Ui.dp(c, 8));
            row.addView(tags, tlp);
            Integer cnt = bp.sectionCounts.get(key);
            final NumberStepper st = new NumberStepper(c, cnt == null ? slot.count : cnt, 0, 300);
            st.setOnChanged(v -> {
                bp.sectionCounts.put(key, v);
                changed();
            });
            countSteppers.add(st);
            countKeys.add(key);
            row.addView(st);
            V.addStart(row, V.text(c, "题", V.CAPTION), 6);
            V.addTop(card, row, 10);
        }
        TextView shortLine = V.text(c, "", V.CAPTION);
        shortLine.setTextColor(p.warning);
        shortLine.setTypeface(Typeface.DEFAULT_BOLD);
        V.pad(shortLine, 36, 8, 0, 0);
        shortLine.setVisibility(View.GONE);
        card.addView(shortLine);
        shortLines.put(sec.name, shortLine);
        sectionCards.put(sec.name, card);
        return card;
    }

    private void changed() {
        renderTotal();
        onChange.run();
    }

    /** 组卷方式切换后显示对应的那一块 */
    void renderMode() {
        sectionsBox.setVisibility(bp.bySections ? View.VISIBLE : View.GONE);
        typesBox.setVisibility(bp.bySections ? View.GONE : View.VISIBLE);
    }

    /** 模型被整体改过（恢复默认）后把数字同步回界面 */
    void syncFromModel() {
        for (int i = 0; i < bp.sections.size(); i++) {
            Integer v = bp.sectionScores.get(bp.sections.get(i).name);
            scoreSteppers.get(i).set(v == null ? 0 : v, false);
        }
        for (int i = 0; i < countKeys.size(); i++) {
            String k = countKeys.get(i);
            Integer v = k.startsWith("type:") ? bp.counts.get(k.substring(5)) : bp.sectionCounts.get(k);
            countSteppers.get(i).set(v == null ? 0 : v, false);
        }
        renderMode();
        renderTotal();
    }

    private void renderTotal() {
        int full = bp.plannedFull();
        totalText.setText(android.text.Html.fromHtml("全卷 <b>" + bp.plannedCount() + "</b> 题 · <b>" + full + "</b> 分",
                android.text.Html.FROM_HTML_MODE_COMPACT));
        totalText.setTextColor(full != 100 ? Palette.of(ctx).warning : Palette.of(ctx).text);
        totalWarn.setVisibility(full != 100 ? View.VISIBLE : View.GONE);
    }

    /** 预览结果回来了：大题凑不齐的标黄 */
    void applyPlan(JSONObject plan) {
        Palette p = Palette.of(ctx);
        Map<String, JSONObject> by = new HashMap<>();
        for (JSONObject s : Json.list(Json.arr(plan, "sections"))) by.put(Json.str(s, "name"), s);
        for (Blueprint.Section sec : bp.sections) {
            JSONObject s = by.get(sec.name);
            TextView line = shortLines.get(sec.name);
            LinearLayout card = sectionCards.get(sec.name);
            boolean shortOf = s != null && Json.num(s, "have") < Json.num(s, "want");
            line.setVisibility(shortOf ? View.VISIBLE : View.GONE);
            if (shortOf) line.setText("题库只凑得出 " + Json.num(s, "have") + " 道（要 " + Json.num(s, "want") + " 道）");
            android.graphics.drawable.GradientDrawable bg = V.round(ctx, shortOf ? p.warningSoft : p.surfaceAlt, 14);
            card.setBackground(bg);
        }
    }
}
