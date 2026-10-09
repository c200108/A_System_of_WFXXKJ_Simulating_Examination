package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 图下面「看数据」展开的原始数字小表。列宽固定（dp），放不下时整张表横向滑动；
 * 宽屏放得下时第一列（名称）吃掉剩余宽度。
 */
final class DataTable extends HorizontalScrollView {

    private final LinearLayout body;
    private final int[] widths;
    private int rows;

    DataTable(Context c, String[] headers, int[] widthsDp) {
        super(c);
        setFillViewport(true);
        setHorizontalScrollBarEnabled(false);
        widths = widthsDp;
        body = V.vbox(c);
        Palette p = Palette.of(c);
        body.setBackground(V.stroke(c, p.surface, p.border, 10));
        addView(body, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT));
        LinearLayout head = row(c, headers, true);
        head.setBackground(V.round(c, p.surfaceAlt, 10));
        body.addView(head);
    }

    /** 加一行。colors[i] 非 0 时给那一格上色 */
    DataTable add(CharSequence[] cells, int[] colors) {
        Context c = getContext();
        body.addView(V.divider(c), new LinearLayout.LayoutParams(LayoutParams.MATCH_PARENT, Math.max(1, Ui.dp(c, 0.8f))));
        LinearLayout r = row(c, cells, false);
        if (colors != null) {
            for (int i = 0; i < colors.length && i < r.getChildCount(); i++) {
                if (colors[i] != 0) ((TextView) r.getChildAt(i)).setTextColor(colors[i]);
            }
        }
        body.addView(r);
        rows++;
        return this;
    }

    DataTable add(CharSequence... cells) {
        return add(cells, null);
    }

    /** 某一行可点（名次表点进答卷） */
    void onRowClick(int index, View.OnClickListener l) {
        // 表头占 1 个，之后每行前面一根分隔线
        View r = body.getChildAt(2 + index * 2);
        if (r != null) V.clickable(r, 0, l);
    }

    int size() {
        return rows;
    }

    private LinearLayout row(Context c, CharSequence[] cells, boolean header) {
        LinearLayout r = V.hbox(c);
        r.setMinimumHeight(Ui.dp(c, 38));
        for (int i = 0; i < cells.length; i++) {
            TextView t = V.text(c, cells[i] == null ? "—" : cells[i], header ? V.LABEL : V.BODY2);
            if (!header) t.setTextColor(Palette.of(c).text);
            t.setMaxLines(3);
            t.setEllipsize(android.text.TextUtils.TruncateAt.END);
            V.pad(t, 10, 8, 10, 8);
            t.setGravity(i == 0 ? Gravity.START | Gravity.CENTER_VERTICAL : Gravity.END | Gravity.CENTER_VERTICAL);
            int w = Ui.dp(c, i < widths.length ? widths[i] : 80);
            LinearLayout.LayoutParams lp = i == 0
                    ? new LinearLayout.LayoutParams(w, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                    : new LinearLayout.LayoutParams(w, LinearLayout.LayoutParams.WRAP_CONTENT);
            r.addView(t, lp);
        }
        return r;
    }
}
