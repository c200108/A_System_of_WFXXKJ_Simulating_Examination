package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/**
 * 页面顶部的分段标签（「题库管理 | 批量导入 | 仿真操作题」）。标签多了可以横向滑。
 * 选中的标签下面有一条主题色短线。
 */
public class Tabs extends HorizontalScrollView {

    public interface Selected {
        void selected(int index);
    }

    private final LinearLayout row;
    private final List<TextView> labels = new ArrayList<>();
    private final List<View> bars = new ArrayList<>();
    private int current = -1;
    private Selected listener;

    public Tabs(Context c) {
        super(c);
        setHorizontalScrollBarEnabled(false);
        setFillViewport(true);
        row = new LinearLayout(c);
        row.setOrientation(LinearLayout.HORIZONTAL);
        V.pad(row, 8, 0, 8, 0);
        addView(row);
        setBackgroundColor(Palette.of(c).surface);
    }

    public Tabs add(String title) {
        final int idx = labels.size();
        Context c = getContext();
        LinearLayout tab = V.vbox(c);
        tab.setGravity(Gravity.CENTER_HORIZONTAL);
        TextView t = new TextView(c);
        t.setText(title);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        t.setSingleLine(true);
        t.setGravity(Gravity.CENTER);
        V.pad(t, 14, 12, 14, 10);
        tab.addView(t, new LinearLayout.LayoutParams(V.WRAP, V.WRAP));
        View bar = new View(c);
        bar.setBackground(V.round(c, Palette.of(c).primary, 2));
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(Ui.dp(c, 24), Ui.dp(c, 3));
        tab.addView(bar, blp);
        V.clickable(tab, 8, v -> select(idx));
        row.addView(tab, Ui.wide(c) ? new LinearLayout.LayoutParams(V.WRAP, V.WRAP)
                : new LinearLayout.LayoutParams(0, V.WRAP, 1f));
        labels.add(t);
        bars.add(bar);
        render();
        return this;
    }

    public void setOnSelected(Selected s) {
        listener = s;
    }

    public int current() {
        return current;
    }

    public void setTitle(int index, String title) {
        labels.get(index).setText(title);
    }

    /** 选中第 index 个并通知 */
    public void select(int index) {
        if (index == current) return;
        current = index;
        render();
        if (listener != null) listener.selected(index);
        final View tab = row.getChildAt(index);
        post(() -> smoothScrollTo(Math.max(0, tab.getLeft() - getWidth() / 3), 0));
    }

    private void render() {
        Palette p = Palette.of(getContext());
        for (int i = 0; i < labels.size(); i++) {
            boolean on = i == current;
            labels.get(i).setTextColor(on ? p.primary : p.text2);
            labels.get(i).setTypeface(on ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
            bars.get(i).setVisibility(on ? VISIBLE : INVISIBLE);
        }
    }
}
