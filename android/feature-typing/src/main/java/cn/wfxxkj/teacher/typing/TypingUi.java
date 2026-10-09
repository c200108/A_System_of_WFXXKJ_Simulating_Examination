package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.List;
import java.util.Locale;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/** 本模块共用的小部件和格式化 */
final class TypingUi {
    private TypingUi() {}

    /** 秒 → 「02:35」（和网页的 fmt 一样） */
    static String mmss(Double sec) {
        if (sec == null) return "—";
        long s = Math.round(sec);
        return String.format(Locale.ROOT, "%02d:%02d", s / 60, s % 60);
    }

    static String stars(int n) {
        if (n <= 0) return "—";
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < n; i++) b.append('★');
        return b.toString();
    }

    /** 正确率的颜色档：≥80 绿，60–79 正常，&lt;60 红（同网页） */
    static int accuracyColor(Context c, double acc) {
        Palette p = Palette.of(c);
        return acc >= 80 ? p.success : acc >= 60 ? p.text : p.danger;
    }

    static Tone moduleTone(String module) {
        if ("中文".equals(module)) return Tone.PRIMARY;
        if ("英文".equals(module)) return Tone.VIOLET;
        return Tone.INFO;
    }

    static Tone difficultyTone(String d) {
        if ("困难".equals(d)) return Tone.DANGER;
        if ("中等".equals(d)) return Tone.WARNING;
        return Tone.SUCCESS;
    }

    /** 百分数字段：「78.6%」，null 显示「—」 */
    static String pct(JSONObject o, String key) {
        Double d = Json.dblOrNull(o, key);
        return d == null ? "—" : Fmt.num(d) + "%";
    }

    /** 数字字段，null 显示「—」 */
    static String num(JSONObject o, String key) {
        return Fmt.num(Json.dblOrNull(o, key));
    }

    /** 带符号的进步值：+3.5 / -2 / — */
    static String signed(Double v) {
        if (v == null) return "—";
        return (v > 0 ? "+" : "") + Fmt.num(v);
    }

    /** 卡片里的小标题行：粗体标题 + 右边一个文字按钮（可为空） */
    static LinearLayout cardTitle(Context c, String title, String action, View.OnClickListener onAction) {
        LinearLayout row = V.hbox(c);
        row.addView(V.text(c, title, V.H3), V.fill());
        if (action != null) {
            TextView b = V.button(c, action, V.BTN_TEXT, onAction);
            b.setTextSize(13);
            b.setMinHeight(Ui.dp(c, 32));
            row.addView(b);
        }
        V.pad(row, 0, 0, 0, 8);
        return row;
    }

    /** 统计小卡：大数字 + 说明 + 单位 */
    static View kpi(Context c, String number, String label, String unit, Tone tone) {
        LinearLayout box = V.stat(c, number, label, tone);
        if (unit != null && !unit.isEmpty()) {
            TextView u = V.text(c, unit, V.CAPTION);
            box.addView(V.oneLine(u));
        }
        return box;
    }

    /** 紧凑的统计小卡（列表页头部用，手机上一行三个） */
    static View mini(Context c, String number, String label, Tone tone) {
        LinearLayout box = V.vbox(c);
        int[] t = Palette.of(c).tone(tone);
        box.setBackground(V.round(c, t[1], 12));
        V.pad(box, 12, 8, 8, 8);
        TextView n = V.oneLine(V.text(c, number, V.H2));
        n.setTextColor(tone == Tone.NEUTRAL ? Palette.of(c).text : t[0]);
        box.addView(n);
        box.addView(V.oneLine(V.text(c, label, V.CAPTION)));
        return box;
    }

    /**
     * 简单的数据表（「看数据」展开的那种）：首行表头，列宽按内容，超宽可横向滑动。
     * rows 里每行的格子数要和 head 一样。
     */
    static View table(Context c, String[] head, List<String[]> rows) {
        Palette p = Palette.of(c);
        LinearLayout grid = V.vbox(c);
        int cols = head.length;
        // 先量每列最宽
        int[] w = new int[cols];
        TextView probe = V.text(c, "", V.BODY2);
        for (int i = 0; i < cols; i++) w[i] = (int) probe.getPaint().measureText(head[i]);
        for (String[] r : rows) {
            for (int i = 0; i < cols && i < r.length; i++) {
                w[i] = Math.max(w[i], (int) probe.getPaint().measureText(r[i] == null ? "" : r[i]));
            }
        }
        int padH = Ui.dp(c, 10);
        grid.addView(tableRow(c, head, w, padH, true, p.surfaceAlt));
        for (int k = 0; k < rows.size(); k++) {
            grid.addView(V.divider(c));
            grid.addView(tableRow(c, rows.get(k), w, padH, false, 0));
        }
        grid.setBackground(V.stroke(c, p.surface, p.border, 10));
        grid.setClipToOutline(true);
        HorizontalScrollView hs = new HorizontalScrollView(c);
        hs.setHorizontalScrollBarEnabled(false);
        hs.setFillViewport(true);
        hs.addView(grid, new HorizontalScrollView.LayoutParams(V.MATCH, V.WRAP));
        return hs;
    }

    private static LinearLayout tableRow(Context c, String[] cells, int[] w, int padH, boolean head, int bg) {
        LinearLayout row = V.hbox(c);
        if (bg != 0) row.setBackgroundColor(bg);
        for (int i = 0; i < w.length; i++) {
            TextView t = V.text(c, i < cells.length && cells[i] != null ? cells[i] : "", head ? V.LABEL : V.BODY2);
            if (!head && i == 0) t.setTextColor(Palette.of(c).text);
            t.setSingleLine(true);
            t.setGravity(i == 0 ? Gravity.START : Gravity.END);
            t.setPadding(padH, Ui.dp(c, 8), padH, Ui.dp(c, 8));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(w[i] + padH * 2 + Ui.dp(c, 2), V.WRAP);
            if (i == 0) {
                lp = new LinearLayout.LayoutParams(0, V.WRAP, 1f);
                t.setMinWidth(w[i] + padH * 2 + Ui.dp(c, 2));
            }
            if (head) t.setTypeface(Typeface.DEFAULT_BOLD);
            row.addView(t, lp);
        }
        return row;
    }

    /** 筛选条件的小胶囊（显示已选的条件，点 × 去掉） */
    static TextView pill(Context c, String text, View.OnClickListener onClick) {
        TextView t = V.tag(c, text + "  ×", Tone.PRIMARY);
        t.setMinHeight(Ui.dp(c, 28));
        t.setGravity(Gravity.CENTER_VERTICAL);
        V.pad(t, 10, 2, 10, 2);
        t.setOnClickListener(onClick);
        return t;
    }
}
