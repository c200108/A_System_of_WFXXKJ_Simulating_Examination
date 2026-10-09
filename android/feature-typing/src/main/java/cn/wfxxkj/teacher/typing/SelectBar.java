package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 长按多选时浮在列表底部的操作条：「已选 N 条」+ 一排批量操作按钮。
 * 没在多选时隐藏，不占地方。用法：把 {@link #wrap} 返回的容器当页面根视图。
 */
final class SelectBar extends LinearLayout {
    private final TextView count;
    private final LinearLayout buttons;

    SelectBar(Context c) {
        super(c);
        setOrientation(VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 18));
        setElevation(Ui.dpf(c, 8));
        V.pad(this, 14, 8, 8, 8);
        count = V.text(c, "", V.LABEL);
        V.pad(count, 2, 2, 0, 2);
        addView(count);
        buttons = V.hbox(c);
        HorizontalScrollView hs = new HorizontalScrollView(c);
        hs.setHorizontalScrollBarEnabled(false);
        hs.addView(buttons);
        addView(hs, V.matchWrap());
        setVisibility(GONE);
        setClickable(true);
    }

    /** 加一个按钮（按顺序从左往右排） */
    TextView add(String label, int kind, View.OnClickListener l) {
        TextView b = V.button(getContext(), label, kind, l);
        b.setTextSize(14);
        b.setMinHeight(Ui.dp(getContext(), 40));
        V.pad(b, 14, 0, 14, 0);
        LayoutParams lp = new LayoutParams(V.WRAP, V.WRAP);
        if (buttons.getChildCount() > 0) lp.setMarginStart(Ui.dp(getContext(), 8));
        buttons.addView(b, lp);
        return b;
    }

    /** n &lt; 0 = 退出多选（隐藏） */
    void show(int n, String unit) {
        if (n < 0) {
            setVisibility(GONE);
            return;
        }
        count.setText("已选 " + n + " " + unit + (n == 0 ? "（点卡片勾选）" : ""));
        for (int i = 0; i < buttons.getChildCount(); i++) {
            View b = buttons.getChildAt(i);
            if (b.getTag() != null && "need".equals(b.getTag())) V.enable(b, n > 0);
        }
        setVisibility(VISIBLE);
    }

    /** 把内容和操作条叠在一起：操作条贴底，宽屏时限宽居中 */
    FrameLayout wrap(View content) {
        Context c = getContext();
        FrameLayout root = new FrameLayout(c);
        root.addView(content, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        int side = Ui.dp(c, Ui.wide(c) ? 24 : 12);
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                Ui.wide(c) ? Ui.dp(c, 560) : V.MATCH, V.WRAP, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp.setMargins(side, 0, side, Ui.dp(c, 12));
        root.addView(this, lp);
        return root;
    }

    /** 需要先勾选才能点的按钮（勾 0 条时变灰） */
    static TextView needSelection(TextView b) {
        b.setTag("need");
        return b;
    }
}
