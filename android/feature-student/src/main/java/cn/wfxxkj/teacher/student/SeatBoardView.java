package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.text.Layout;
import android.text.StaticLayout;
import android.text.TextPaint;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;

import java.util.HashSet;
import java.util.Set;

import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;

/**
 * 在线座次的「座位板」：把网页端的座次表（{@link SeatSheet}）按原样式画出来。
 *
 * <ul>
 *   <li>双指缩放、单指拖动平移；打开时按宽度铺满</li>
 *   <li>点一下格子 → {@link Listener#onTap}</li>
 *   <li>在学生上长按抓起，拖到别的格子松手 → {@link Listener#onDrop}（换座位）；拖到边上会自动滚</li>
 *   <li>小组底色、班干部、分数角标、设备故障由 {@link Deco} 提供，只画不改表（和网页端一样不写进格子样式）</li>
 * </ul>
 * 格子底色、字色、粗斜体、字号、对齐、边框、合并、列宽行高都照网页存的来。
 */
final class SeatBoardView extends View {

    interface Listener {
        void onTap(int x, int y);

        boolean canDrag(int x, int y);

        void onDrop(int fx, int fy, int tx, int ty);
    }

    /** 格子上额外显示的东西 */
    interface Deco {
        /** 小组底色，0 = 没有 */
        int groupColor(int x, int y);

        /** 左上角小标签：班长 / 组长，没有返回 null */
        String role(int x, int y);

        /** 右上角分数：+3 / -1，没有返回 null */
        String points(int x, int y);

        /** 设备故障说明（标了故障但没写说明返回 ""），没标返回 null */
        String broken(int x, int y);
    }

    private SeatSheet sheet;
    private Listener listener;
    private Deco deco;
    private final Set<String> selected = new HashSet<>();

    private float zoom = 1f;          // 相对「1 个表格 px = 1 dp」
    private float scrollX, scrollY;
    private boolean fitted;
    private final float unit;          // 1 个表格 px 画成多少屏幕像素（zoom = 1 时）
    private int[] colX = new int[1];   // 每列左边的表格 px 位置（多一项 = 总宽）
    private int[] rowY = new int[1];

    private final Paint fill = new Paint();
    private final Paint line = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final TextPaint text = new TextPaint(Paint.ANTI_ALIAS_FLAG);
    private final TextPaint small = new TextPaint(Paint.ANTI_ALIAS_FLAG);
    private final Paint hatch = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final Palette pal;

    private final ScaleGestureDetector scaler;
    private final GestureDetector gestures;

    // 拖动换座
    private int dragFx = -1, dragFy = -1, overX = -1, overY = -1;
    private float dragPx, dragPy;
    private String dragLabel = "";

    SeatBoardView(Context c) {
        super(c);
        pal = Palette.of(c);
        unit = c.getResources().getDisplayMetrics().density;
        line.setStyle(Paint.Style.STROKE);
        hatch.setStyle(Paint.Style.STROKE);
        hatch.setStrokeWidth(Ui.dpf(c, 1.5f));
        small.setTextSize(Ui.sp(c, 10));
        small.setTypeface(Typeface.DEFAULT_BOLD);
        scaler = new ScaleGestureDetector(c, new ScaleGestureDetector.SimpleOnScaleGestureListener() {
            @Override
            public boolean onScale(ScaleGestureDetector d) {
                zoomBy(d.getScaleFactor(), d.getFocusX(), d.getFocusY());
                return true;
            }
        });
        gestures = new GestureDetector(c, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public boolean onDown(MotionEvent e) {
                return true;
            }

            @Override
            public boolean onScroll(MotionEvent e1, MotionEvent e2, float dx, float dy) {
                if (dragging() || scaler.isInProgress()) return false;
                scrollBy(dx, dy);
                return true;
            }

            @Override
            public boolean onSingleTapUp(MotionEvent e) {
                int[] cell = cellAt(e.getX(), e.getY());
                if (cell != null && listener != null) listener.onTap(cell[0], cell[1]);
                return true;
            }

            @Override
            public void onLongPress(MotionEvent e) {
                if (scaler.isInProgress()) return;
                int[] cell = cellAt(e.getX(), e.getY());
                if (cell == null || listener == null || !listener.canDrag(cell[0], cell[1])) return;
                dragFx = cell[0];
                dragFy = cell[1];
                overX = cell[0];
                overY = cell[1];
                dragPx = e.getX();
                dragPy = e.getY();
                String t = sheet.get(cell[0], cell[1]).trim();
                int sp = t.lastIndexOf(' ');
                dragLabel = sp >= 0 ? t.substring(sp + 1) : t;
                performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS);
                getParent().requestDisallowInterceptTouchEvent(true);
                invalidate();
            }
        });
        gestures.setIsLongpressEnabled(true);
    }

    void setSheet(SeatSheet s) {
        boolean first = sheet == null;
        sheet = s;
        measureGrid();
        if (first) {
            // 第一次拿到表：铺满屏幕宽。界面早就量好了尺寸（数据是后来才回来的），onSizeChanged 不会再来，这里直接适应；
            // 还没量好的话留给 onSizeChanged
            fitted = false;
            if (getWidth() > 0) {
                fitted = true;
                fit();
            }
        }
        clamp();
        invalidate();
    }

    void setListener(Listener l) {
        listener = l;
    }

    void setDeco(Deco d) {
        deco = d;
        invalidate();
    }

    Set<String> selection() {
        return selected;
    }

    /** 缩放：factor 相对现在；按屏幕中心缩 */
    void zoomBy(float factor) {
        zoomBy(factor, getWidth() / 2f, getHeight() / 2f);
    }

    /** 按宽度铺满 */
    void fit() {
        if (getWidth() == 0 || colX[colX.length - 1] == 0) return;
        zoom = Math.max(0.3f, Math.min(3f, (getWidth() - Ui.dp(getContext(), 8)) / (colX[colX.length - 1] * unit)));
        scrollX = scrollY = 0;
        clamp();
        invalidate();
    }

    int zoomPercent() {
        return Math.round(zoom * 100);
    }

    private boolean dragging() {
        return dragFx >= 0;
    }

    private void measureGrid() {
        if (sheet == null) return;
        colX = new int[sheet.cols + 1];
        for (int x = 0; x < sheet.cols; x++) colX[x + 1] = colX[x] + sheet.colWidths[x];
        rowY = new int[sheet.rows() + 1];
        for (int y = 0; y < sheet.rows(); y++) rowY[y + 1] = rowY[y] + sheet.rowHeight(y);
    }

    private float k() {
        return unit * zoom;
    }

    private void zoomBy(float factor, float fx, float fy) {
        float old = zoom;
        zoom = Math.max(0.3f, Math.min(4f, zoom * factor));
        float r = zoom / old;
        scrollX = (scrollX + fx) * r - fx;
        scrollY = (scrollY + fy) * r - fy;
        clamp();
        invalidate();
    }

    private void scrollBy(float dx, float dy) {
        scrollX += dx;
        scrollY += dy;
        clamp();
        invalidate();
    }

    private void clamp() {
        float w = colX[colX.length - 1] * k(), h = rowY[rowY.length - 1] * k();
        scrollX = Math.max(0, Math.min(scrollX, Math.max(0, w - getWidth())));
        scrollY = Math.max(0, Math.min(scrollY, Math.max(0, h - getHeight())));
    }

    @Override
    protected void onSizeChanged(int w, int h, int ow, int oh) {
        super.onSizeChanged(w, h, ow, oh);
        if (!fitted && w > 0) {
            fitted = true;
            fit();
        }
        clamp();
    }

    /** 屏幕坐标 → 格子（合并区域里返回左上角那格） */
    int[] cellAt(float sx, float sy) {
        if (sheet == null) return null;
        float px = (sx + scrollX) / k(), py = (sy + scrollY) / k();
        int x = find(colX, px), y = find(rowY, py);
        if (x < 0 || y < 0) return null;
        // 落在合并区域被盖住的格子上：找左上角
        for (java.util.Map.Entry<String, int[]> e : sheet.merges.entrySet()) {
            int[] p = SeatSheet.parse(e.getKey());
            int[] span = e.getValue();
            if (p != null && x >= p[0] && x < p[0] + span[0] && y >= p[1] && y < p[1] + span[1]) return p;
        }
        return new int[]{x, y};
    }

    private static int find(int[] edges, float v) {
        if (v < 0 || v >= edges[edges.length - 1]) return -1;
        for (int i = 0; i + 1 < edges.length; i++) if (v < edges[i + 1]) return i;
        return -1;
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        if (sheet == null) return false;
        if (dragging()) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_MOVE:
                    dragPx = e.getX();
                    dragPy = e.getY();
                    // 拖到边上自动滚
                    float edge = Ui.dpf(getContext(), 36), step = Ui.dpf(getContext(), 14);
                    float dx = dragPx < edge ? -step : dragPx > getWidth() - edge ? step : 0;
                    float dy = dragPy < edge ? -step : dragPy > getHeight() - edge ? step : 0;
                    if (dx != 0 || dy != 0) scrollBy(dx, dy);
                    int[] c = cellAt(dragPx, dragPy);
                    overX = c == null ? -1 : c[0];
                    overY = c == null ? -1 : c[1];
                    invalidate();
                    return true;
                case MotionEvent.ACTION_UP:
                    int fx = dragFx, fy = dragFy, tx = overX, ty = overY;
                    endDrag();
                    if (tx >= 0 && (tx != fx || ty != fy) && listener != null) listener.onDrop(fx, fy, tx, ty);
                    return true;
                case MotionEvent.ACTION_CANCEL:
                    endDrag();
                    return true;
                default:
                    return true;
            }
        }
        scaler.onTouchEvent(e);
        gestures.onTouchEvent(e);
        if (e.getPointerCount() > 1 || e.getActionMasked() == MotionEvent.ACTION_MOVE) {
            getParent().requestDisallowInterceptTouchEvent(true);
        }
        return true;
    }

    private void endDrag() {
        dragFx = dragFy = overX = overY = -1;
        getParent().requestDisallowInterceptTouchEvent(false);
        invalidate();
    }

    // ---------------------------------------------------------------- 画

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        canvas.drawColor(pal.page);
        if (sheet == null || sheet.isEmpty()) return;
        float k = k();
        canvas.save();
        canvas.translate(-scrollX, -scrollY);
        // 白纸底
        fill.setColor(Color.WHITE);
        canvas.drawRect(0, 0, colX[colX.length - 1] * k, rowY[rowY.length - 1] * k, fill);

        int x0 = Math.max(0, find(colX, scrollX / k)), x1 = find(colX, (scrollX + getWidth()) / k);
        int y0 = Math.max(0, find(rowY, scrollY / k)), y1 = find(rowY, (scrollY + getHeight()) / k);
        if (x1 < 0) x1 = sheet.cols - 1;
        if (y1 < 0) y1 = sheet.rows() - 1;
        // 合并区域的左上角可能在可见区外：往左上多看一些
        int mx0 = x0, my0 = y0;
        for (java.util.Map.Entry<String, int[]> e : sheet.merges.entrySet()) {
            int[] p = SeatSheet.parse(e.getKey());
            int[] span = e.getValue();
            if (p == null) continue;
            if (p[0] < x0 && p[0] + span[0] > x0) mx0 = Math.min(mx0, p[0]);
            if (p[1] < y0 && p[1] + span[1] > y0) my0 = Math.min(my0, p[1]);
        }

        // 先画网格细线（Excel 那种浅灰）
        line.setColor(0xFFE2E5EA);
        line.setStrokeWidth(1);
        for (int y = y0; y <= y1; y++) for (int x = x0; x <= x1; x++) {
            if (sheet.covered.contains(SeatSheet.name(x, y))) continue;
            cellRect(x, y);
            canvas.drawRect(rect, line);
        }
        for (int y = my0; y <= y1; y++) for (int x = mx0; x <= x1; x++) drawCell(canvas, x, y);
        canvas.restore();

        if (dragging()) drawDragGhost(canvas);
    }

    /** 格子（含合并）在「已缩放、未平移」坐标里的矩形，写进 rect */
    private void cellRect(int x, int y) {
        float k = k();
        int[] span = sheet.merges.get(SeatSheet.name(x, y));
        int sw = span == null ? 1 : span[0], sh = span == null ? 1 : span[1];
        int xe = Math.min(sheet.cols, x + sw), ye = Math.min(sheet.rows(), y + sh);
        rect.set(colX[x] * k, rowY[y] * k, colX[xe] * k, rowY[ye] * k);
    }

    private void drawCell(Canvas c, int x, int y) {
        String name = SeatSheet.name(x, y);
        if (sheet.covered.contains(name)) return;
        cellRect(x, y);
        SeatSheet.Style st = sheet.styles.get(name);
        float k = k();
        int gc = deco == null ? 0 : deco.groupColor(x, y);
        int bg = gc != 0 ? gc : st == null ? 0 : st.bg;
        if (bg != 0) {
            fill.setColor(bg);
            c.drawRect(rect, fill);
        }
        String bk = deco == null ? null : deco.broken(x, y);
        if (bk != null) {
            // 设备故障：红色斜纹 + 说明
            fill.setColor(0x22E53935);
            c.drawRect(rect, fill);
            hatch.setColor(0x66E53935);
            c.save();
            c.clipRect(rect);
            float gap = Ui.dpf(getContext(), 8);
            Path p = new Path();
            for (float d = -rect.height(); d < rect.width(); d += gap) {
                p.moveTo(rect.left + d, rect.bottom);
                p.lineTo(rect.left + d + rect.height(), rect.top);
            }
            c.drawPath(p, hatch);
            c.restore();
        }
        boolean sel = selected.contains(name);
        if (sel) {
            fill.setColor(0x332F6FEB);
            c.drawRect(rect, fill);
        }
        if (dragging() && x == overX && y == overY && (x != dragFx || y != dragFy)) {
            fill.setColor(0x4434A853);
            c.drawRect(rect, fill);
        }

        // 字
        String s = bk != null ? "🔧 " + (bk.isEmpty() ? "设备故障" : bk) : sheet.get(x, y);
        if (dragging() && x == dragFx && y == dragFy) s = "";
        if (!s.isEmpty()) {
            float fpx = st != null && st.fontPx > 0 ? st.fontPx : 13;
            text.setTextSize(fpx * k);
            text.setColor(bk != null ? 0xFFC62828 : st != null && st.color != 0 ? st.color : Color.BLACK);
            int flags = (st != null && st.bold) || gc != 0 ? Typeface.BOLD : Typeface.NORMAL;
            if (st != null && st.italic) flags |= Typeface.ITALIC;
            text.setTypeface(Typeface.create(Typeface.DEFAULT, flags));
            text.setUnderlineText(st != null && st.underline);
            int ha = st == null ? -1 : st.hAlign;
            if (ha < 0) ha = s.matches("-?\\d+(\\.\\d+)?") ? 2 : 0;
            if (bk != null) ha = 1;
            Layout.Alignment al = ha == 1 ? Layout.Alignment.ALIGN_CENTER
                    : ha == 2 ? Layout.Alignment.ALIGN_OPPOSITE : Layout.Alignment.ALIGN_NORMAL;
            float pad = 3 * k;
            int w = (int) Math.max(1, rect.width() - pad * 2);
            StaticLayout lay = StaticLayout.Builder.obtain(s, 0, s.length(), text, w)
                    .setAlignment(al).setIncludePad(false).build();
            float th = lay.getHeight();
            int va = st == null ? 1 : st.vAlign;
            float top = va == 0 ? rect.top + pad : va == 2 ? rect.bottom - pad - th : rect.centerY() - th / 2;
            c.save();
            c.clipRect(rect);
            c.translate(rect.left + pad, Math.max(rect.top, top));
            lay.draw(c);
            c.restore();
        }

        // 班干部、分数角标
        if (deco != null && bk == null) {
            float bs = Math.max(8, Math.min(11, 10 * zoom)) * getResources().getDisplayMetrics().scaledDensity;
            small.setTextSize(bs);
            String role = deco.role(x, y);
            if (role != null && !role.isEmpty()) {
                small.setColor(Color.WHITE);
                float tw = small.measureText(role) + bs * 0.6f;
                fill.setColor("班长".equals(role) ? 0xFFE53935 : 0xFF1E88E5);
                c.drawRect(rect.left, rect.top, rect.left + tw, rect.top + bs * 1.3f, fill);
                c.drawText(role, rect.left + bs * 0.3f, rect.top + bs * 1.02f, small);
            }
            String pts = deco.points(x, y);
            if (pts != null && !pts.isEmpty()) {
                small.setColor(pts.startsWith("-") ? 0xFFC62828 : 0xFF2E7D32);
                float tw = small.measureText(pts);
                c.drawText(pts, rect.right - tw - bs * 0.3f, rect.top + bs * 1.02f, small);
            }
        }

        // 边框（照网页存的样式）
        if (st != null) {
            float[] ln = {rect.left, rect.top, rect.right, rect.top, rect.right, rect.top, rect.right, rect.bottom,
                    rect.left, rect.bottom, rect.right, rect.bottom, rect.left, rect.top, rect.left, rect.bottom};
            for (int side = 0; side < 4; side++) {
                if (st.borderW[side] <= 0) continue;
                line.setColor(st.borderC[side]);
                line.setStrokeWidth(Math.max(1, st.borderW[side] * k));
                c.drawLine(ln[side * 4], ln[side * 4 + 1], ln[side * 4 + 2], ln[side * 4 + 3], line);
            }
        }
        if (sel) {
            line.setColor(0xFF2F6FEB);
            line.setStrokeWidth(Ui.dpf(getContext(), 2));
            c.drawRect(rect, line);
        }
    }

    private void drawDragGhost(Canvas c) {
        float r = Ui.dpf(getContext(), 8);
        text.setTextSize(Ui.sp(getContext(), 15));
        text.setTypeface(Typeface.DEFAULT_BOLD);
        text.setUnderlineText(false);
        float tw = text.measureText(dragLabel);
        float pw = tw + r * 3, ph = Ui.dpf(getContext(), 34);
        float left = dragPx - pw / 2, top = dragPy - ph - Ui.dpf(getContext(), 24);
        fill.setColor(pal.primary);
        rect.set(left, top, left + pw, top + ph);
        c.drawRoundRect(rect, r, r, fill);
        text.setColor(Color.WHITE);
        c.drawText(dragLabel, left + (pw - tw) / 2, top + ph / 2 - (text.ascent() + text.descent()) / 2, text);
    }
}
