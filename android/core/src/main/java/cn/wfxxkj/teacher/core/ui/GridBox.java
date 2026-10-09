package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;

/**
 * 自动分列的网格：按自己的实际宽度算一行放几个（每个至少 minCellDp 宽），
 * 手机上一行两个统计卡，平板上一行四五个，转屏、分屏自动重排，不用写两套布局。
 *
 * <p>每行高度取这一行里最高的那个，同一行的格子拉成一样高。
 */
public class GridBox extends ViewGroup {
    private final int minCell;
    private final int maxColumns;
    private final int gap;
    private int columns = 1;

    public GridBox(Context c, int minCellDp, int maxColumns, int gapDp) {
        super(c);
        this.minCell = Ui.dp(c, minCellDp);
        this.maxColumns = Math.max(1, maxColumns);
        this.gap = Ui.dp(c, gapDp);
    }

    /** 当前一行几列（测量后才有效） */
    public int columns() {
        return columns;
    }

    @Override
    protected void onMeasure(int widthSpec, int heightSpec) {
        int width = MeasureSpec.getSize(widthSpec);
        int inner = width - getPaddingLeft() - getPaddingRight();
        int n = Math.max(1, Math.min(maxColumns, (inner + gap) / Math.max(1, minCell + gap)));
        columns = n;
        int cellW = (inner - gap * (n - 1)) / n;
        int count = getChildCount();
        int total = getPaddingTop() + getPaddingBottom();
        int visibleIndex = 0;
        int rowMax = 0;
        int[] rowHeights = new int[(count + n - 1) / n + 1];
        int row = 0;
        for (int i = 0; i < count; i++) {
            View ch = getChildAt(i);
            if (ch.getVisibility() == GONE) continue;
            ch.measure(MeasureSpec.makeMeasureSpec(cellW, MeasureSpec.EXACTLY),
                    MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED));
            rowMax = Math.max(rowMax, ch.getMeasuredHeight());
            visibleIndex++;
            if (visibleIndex % n == 0) {
                rowHeights[row++] = rowMax;
                rowMax = 0;
            }
        }
        if (visibleIndex % n != 0) rowHeights[row++] = rowMax;
        // 同一行拉成一样高
        visibleIndex = 0;
        for (int i = 0; i < count; i++) {
            View ch = getChildAt(i);
            if (ch.getVisibility() == GONE) continue;
            int h = rowHeights[visibleIndex / n];
            if (ch.getMeasuredHeight() != h) {
                ch.measure(MeasureSpec.makeMeasureSpec(cellW, MeasureSpec.EXACTLY),
                        MeasureSpec.makeMeasureSpec(h, MeasureSpec.EXACTLY));
            }
            visibleIndex++;
        }
        for (int r = 0; r < row; r++) total += rowHeights[r] + (r > 0 ? gap : 0);
        setMeasuredDimension(width, resolveSize(total, heightSpec));
    }

    @Override
    protected void onLayout(boolean changed, int l, int t, int r, int b) {
        int n = columns;
        int inner = getWidth() - getPaddingLeft() - getPaddingRight();
        int cellW = (inner - gap * (n - 1)) / n;
        boolean rtl = getLayoutDirection() == LAYOUT_DIRECTION_RTL;
        int y = getPaddingTop();
        int idx = 0;
        int rowH = 0;
        for (int i = 0; i < getChildCount(); i++) {
            View ch = getChildAt(i);
            if (ch.getVisibility() == GONE) continue;
            int col = idx % n;
            if (col == 0 && idx > 0) {
                y += rowH + gap;
                rowH = 0;
            }
            int x = getPaddingLeft() + col * (cellW + gap);
            if (rtl) x = getWidth() - getPaddingRight() - (col + 1) * cellW - col * gap;
            ch.layout(x, y, x + cellW, y + ch.getMeasuredHeight());
            rowH = Math.max(rowH, ch.getMeasuredHeight());
            idx++;
        }
    }
}
