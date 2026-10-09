package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;

/**
 * 最宽不超过 maxWidth 的 LinearLayout，放在全宽容器里时内容自己居中。
 * 平板横屏上的表单、详情页靠它保持舒服的阅读宽度；背景和滚动区域仍是全宽。
 */
public class MaxWidthLinearLayout extends LinearLayout {
    private final int maxWidth;
    private int baseLeft, baseRight;
    private boolean adjusting;

    public MaxWidthLinearLayout(Context c, int maxWidthPx) {
        super(c);
        maxWidth = maxWidthPx;
    }

    @Override
    public void setPadding(int left, int top, int right, int bottom) {
        if (!adjusting) {
            baseLeft = left;
            baseRight = right;
        }
        super.setPadding(left, top, right, bottom);
    }

    @Override
    protected void onMeasure(int widthSpec, int heightSpec) {
        int w = View.MeasureSpec.getSize(widthSpec);
        int side = maxWidth > 0 && w > maxWidth ? (w - maxWidth) / 2 : 0;
        int l = baseLeft + side, r = baseRight + side;
        if (l != getPaddingLeft() || r != getPaddingRight()) {
            adjusting = true;
            super.setPadding(l, getPaddingTop(), r, getPaddingBottom());
            adjusting = false;
        }
        super.onMeasure(widthSpec, heightSpec);
    }
}
