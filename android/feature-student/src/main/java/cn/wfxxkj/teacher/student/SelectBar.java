package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 长按多选后从底部浮出的批量操作条：上面一行写选了谁，下面一排图标按钮。
 * 手机竖屏上顶栏只放得下两个图标，批量操作多，放在底部拇指够得着。
 */
final class SelectBar extends LinearLayout {
    private final TextView summary;
    private final LinearLayout buttons;

    SelectBar(Context c) {
        super(c);
        setOrientation(VERTICAL);
        Palette p = Palette.of(c);
        GradientDrawable bg = V.stroke(c, p.surface, p.border, 20);
        setBackground(bg);
        setElevation(Ui.dpf(c, 8));
        V.pad(this, 12, 10, 12, 6);
        summary = V.oneLine(V.text(c, "", V.BODY2));
        V.pad(summary, 6, 0, 6, 4);
        addView(summary, V.matchWrap());
        buttons = V.hbox(c);
        addView(buttons, V.matchWrap());
        setClickable(true); // 别让点击漏到下面的列表
        setVisibility(GONE);
    }

    /** 加一个按钮（图标在上、字在下） */
    SelectBar add(int icon, String label, boolean danger, Runnable run) {
        Context c = getContext();
        Palette p = Palette.of(c);
        int color = danger ? p.danger : p.text;
        LinearLayout b = V.vbox(c);
        b.setGravity(Gravity.CENTER);
        V.pad(b, 2, 6, 2, 6);
        b.addView(V.icon(c, icon, danger ? p.danger : p.primary, 22));
        TextView t = V.oneLine(V.text(c, label, V.CAPTION));
        t.setTextColor(color);
        V.addTop(b, t, 3).setGravity(Gravity.CENTER);
        b.setBackground(null);
        V.clickable(b, 12, v -> run.run());
        buttons.addView(b, new LinearLayout.LayoutParams(0, V.WRAP, 1f));
        return this;
    }

    void setSummary(CharSequence s) {
        summary.setText(s);
    }

    /** 放在 FrameLayout 底部用的布局参数 */
    static FrameLayout.LayoutParams bottom(Context c) {
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(V.MATCH, V.WRAP, Gravity.BOTTOM);
        int m = Ui.dp(c, Ui.wide(c) ? 24 : 12);
        lp.setMargins(m, 0, m, Ui.dp(c, 12));
        if (Ui.wide(c)) {
            lp.width = Ui.dp(c, 560);
            lp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        }
        return lp;
    }
}
