package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

/** 自动换行的横排：一行放不下就折到下一行。标签、筛选条件、选项按钮用。 */
public class FlowBox extends ViewGroup {
    private final int hGap, vGap;

    public FlowBox(Context c, int hGapDp, int vGapDp) {
        super(c);
        hGap = Ui.dp(c, hGapDp);
        vGap = Ui.dp(c, vGapDp);
    }

    @Override
    protected void onMeasure(int widthSpec, int heightSpec) {
        int max = MeasureSpec.getSize(widthSpec) - getPaddingLeft() - getPaddingRight();
        boolean unbounded = MeasureSpec.getMode(widthSpec) == MeasureSpec.UNSPECIFIED;
        int x = 0, y = 0, rowH = 0, widest = 0;
        for (int i = 0; i < getChildCount(); i++) {
            View ch = getChildAt(i);
            if (ch.getVisibility() == GONE) continue;
            ch.measure(MeasureSpec.makeMeasureSpec(unbounded ? 0 : max,
                            unbounded ? MeasureSpec.UNSPECIFIED : MeasureSpec.AT_MOST),
                    MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED));
            int w = ch.getMeasuredWidth(), h = ch.getMeasuredHeight();
            if (!unbounded && x > 0 && x + w > max) {
                x = 0;
                y += rowH + vGap;
                rowH = 0;
            }
            x += w + hGap;
            widest = Math.max(widest, x - hGap);
            rowH = Math.max(rowH, h);
        }
        int height = y + rowH + getPaddingTop() + getPaddingBottom();
        int width = unbounded ? widest + getPaddingLeft() + getPaddingRight() : MeasureSpec.getSize(widthSpec);
        setMeasuredDimension(width, resolveSize(height, heightSpec));
    }

    @Override
    protected void onLayout(boolean changed, int l, int t, int r, int b) {
        int max = getWidth() - getPaddingLeft() - getPaddingRight();
        int x = 0, y = 0, rowH = 0;
        for (int i = 0; i < getChildCount(); i++) {
            View ch = getChildAt(i);
            if (ch.getVisibility() == GONE) continue;
            int w = ch.getMeasuredWidth(), h = ch.getMeasuredHeight();
            if (x > 0 && x + w > max) {
                x = 0;
                y += rowH + vGap;
                rowH = 0;
            }
            int left = getPaddingLeft() + x, top = getPaddingTop() + y;
            ch.layout(left, top, left + w, top + h);
            x += w + hGap;
            rowH = Math.max(rowH, h);
        }
    }
}
