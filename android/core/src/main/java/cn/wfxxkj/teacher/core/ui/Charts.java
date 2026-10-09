package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 几种简单的图表，自己用 Canvas 画（不引图表库）：
 * <ul>
 *   <li>{@link Bars} 竖柱状图（分数段分布等），柱子多了自动横向变窄；</li>
 *   <li>{@link HBars} 横条图（每道题得分率、班级对比），手机竖屏上最好读；</li>
 *   <li>{@link Donut} 环形图 + 图例（占比）；</li>
 *   <li>{@link Line} 折线图（趋势）。</li>
 * </ul>
 * 颜色跟着深浅色走。
 */
public final class Charts {
    private Charts() {}

    /** 一个数据点：标签 + 数值 (+ 可选颜色，0 = 自动) */
    public static final class Point {
        public final String label;
        public final double value;
        public final int color;
        /** 柱子上显示的文字，null = 显示数值 */
        public final String text;

        public Point(String label, double value) {
            this(label, value, 0, null);
        }

        public Point(String label, double value, int color, String text) {
            this.label = label;
            this.value = value;
            this.color = color;
            this.text = text;
        }
    }

    static Paint paint(Context c, int color, float textSp) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(color);
        if (textSp > 0) p.setTextSize(Ui.sp(c, textSp));
        return p;
    }

    // ---------- 竖柱 ----------

    public static class Bars extends View {
        private List<Point> points = new ArrayList<>();
        private final Paint bar, label, value, grid;
        private int defaultColor;
        private final int height;

        public Bars(Context c, int heightDp) {
            super(c);
            Palette p = Palette.of(c);
            defaultColor = p.primary;
            bar = paint(c, p.primary, 0);
            label = paint(c, p.text3, 11);
            label.setTextAlign(Paint.Align.CENTER);
            value = paint(c, p.text2, 11);
            value.setTextAlign(Paint.Align.CENTER);
            grid = paint(c, p.divider, 0);
            grid.setStrokeWidth(Ui.dpf(c, 1));
            height = Ui.dp(c, heightDp);
        }

        public Bars setData(List<Point> data) {
            points = data == null ? new ArrayList<>() : data;
            invalidate();
            return this;
        }

        public Bars setColor(int c) {
            defaultColor = c;
            invalidate();
            return this;
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), height);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            if (points.isEmpty()) return;
            Context c = getContext();
            float top = Ui.dpf(c, 18), bottom = getHeight() - Ui.dpf(c, 22);
            float w = getWidth();
            double max = 0;
            for (Point p : points) max = Math.max(max, p.value);
            if (max <= 0) max = 1;
            for (int i = 0; i <= 3; i++) {
                float y = bottom - (bottom - top) * i / 3f;
                canvas.drawLine(0, y, w, y, grid);
            }
            int n = points.size();
            float slot = w / n;
            float bw = Math.min(Ui.dpf(c, 36), slot * 0.62f);
            float r = Math.min(Ui.dpf(c, 6), bw / 2);
            boolean thinLabels = slot < label.measureText("100-100");
            for (int i = 0; i < n; i++) {
                Point p = points.get(i);
                float cx = slot * i + slot / 2;
                float h = (float) ((bottom - top) * (p.value / max));
                bar.setColor(p.color != 0 ? p.color : defaultColor);
                if (h > 0) {
                    RectF rect = new RectF(cx - bw / 2, bottom - h, cx + bw / 2, bottom);
                    Path path = new Path();
                    path.addRoundRect(rect, new float[]{r, r, r, r, 0, 0, 0, 0}, Path.Direction.CW);
                    canvas.drawPath(path, bar);
                }
                String vt = p.text != null ? p.text : Fmt.num(p.value);
                canvas.drawText(vt, cx, bottom - h - Ui.dpf(c, 5), value);
                if (!thinLabels || i % 2 == 0) {
                    String lb = TextUtils.ellipsize(p.label, new android.text.TextPaint(label),
                            thinLabels ? slot * 2 : slot, TextUtils.TruncateAt.END).toString();
                    canvas.drawText(lb, cx, getHeight() - Ui.dpf(c, 6), label);
                }
            }
        }
    }

    // ---------- 横条 ----------

    /** 横条图：每行「标签 ███████ 数值」，行数多就自然变高（放在可滚动页面里） */
    public static class HBars extends View {
        private List<Point> points = new ArrayList<>();
        private final Paint bar, track, label, value;
        private int defaultColor;
        private double max = -1;
        private final float rowH;
        private float labelW;

        public HBars(Context c) {
            super(c);
            Palette p = Palette.of(c);
            defaultColor = p.primary;
            bar = paint(c, p.primary, 0);
            track = paint(c, p.surfaceAlt, 0);
            label = paint(c, p.text2, 13);
            value = paint(c, p.text, 13);
            value.setFakeBoldText(true);
            value.setTextAlign(Paint.Align.RIGHT);
            rowH = Ui.dpf(c, 30);
        }

        public HBars setData(List<Point> data) {
            points = data == null ? new ArrayList<>() : data;
            requestLayout();
            invalidate();
            return this;
        }

        /** 固定满刻度（例如得分率固定 100），不设则取最大值 */
        public HBars setMax(double m) {
            max = m;
            invalidate();
            return this;
        }

        public HBars setColor(int c) {
            defaultColor = c;
            invalidate();
            return this;
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), (int) (rowH * points.size() + Ui.dpf(getContext(), 4)));
        }

        @Override
        protected void onDraw(Canvas canvas) {
            if (points.isEmpty()) return;
            Context c = getContext();
            float w = getWidth();
            labelW = 0;
            for (Point p : points) labelW = Math.max(labelW, label.measureText(p.label));
            labelW = Math.min(labelW, w * 0.36f) + Ui.dpf(c, 10);
            float valueW = value.measureText("100.0%") + Ui.dpf(c, 8);
            double m = max > 0 ? max : 0;
            if (m <= 0) for (Point p : points) m = Math.max(m, p.value);
            if (m <= 0) m = 1;
            float barL = labelW, barR = w - valueW;
            float bh = Ui.dpf(c, 10);
            for (int i = 0; i < points.size(); i++) {
                Point p = points.get(i);
                float cy = rowH * i + rowH / 2;
                String lb = TextUtils.ellipsize(p.label, new android.text.TextPaint(label),
                        labelW - Ui.dpf(c, 10), TextUtils.TruncateAt.END).toString();
                canvas.drawText(lb, 0, cy + label.getTextSize() / 3, label);
                RectF trackR = new RectF(barL, cy - bh / 2, barR, cy + bh / 2);
                canvas.drawRoundRect(trackR, bh / 2, bh / 2, track);
                float len = (float) ((barR - barL) * Math.min(1, Math.max(0, p.value / m)));
                if (len > 0) {
                    bar.setColor(p.color != 0 ? p.color : defaultColor);
                    canvas.drawRoundRect(new RectF(barL, cy - bh / 2, barL + Math.max(len, bh), cy + bh / 2),
                            bh / 2, bh / 2, bar);
                }
                canvas.drawText(p.text != null ? p.text : Fmt.num(p.value), w, cy + value.getTextSize() / 3, value);
            }
        }
    }

    // ---------- 环形 ----------

    /** 环形图 + 右侧（窄屏时下方）图例。中间可以写一行字 */
    public static LinearLayout donut(Context c, List<Point> data, String centerText, String centerSub) {
        LinearLayout box = new LinearLayout(c);
        box.setOrientation(Ui.widthDp(c) >= 400 ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        box.setGravity(android.view.Gravity.CENTER);
        Donut d = new Donut(c, data, centerText, centerSub);
        int s = Ui.dp(c, 150);
        box.addView(d, new LinearLayout.LayoutParams(s, s));
        LinearLayout legend = V.vbox(c);
        double total = 0;
        for (Point p : data) total += p.value;
        Palette pal = Palette.of(c);
        for (int i = 0; i < data.size(); i++) {
            Point p = data.get(i);
            LinearLayout row = V.hbox(c);
            V.pad(row, 0, 4, 0, 4);
            View dot = new View(c);
            dot.setBackground(V.round(c, p.color != 0 ? p.color : pal.series(i), 5));
            row.addView(dot, new LinearLayout.LayoutParams(Ui.dp(c, 10), Ui.dp(c, 10)));
            TextView t = V.text(c, p.label, V.BODY2);
            LinearLayout.LayoutParams tl = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
            tl.setMarginStart(Ui.dp(c, 8));
            row.addView(t, tl);
            TextView v = V.text(c, Fmt.num(p.value) + (total > 0 ? "（" + Fmt.percent(p.value / total) + "）" : ""), V.BODY2);
            V.bold(v);
            LinearLayout.LayoutParams vl = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
            vl.setMarginStart(Ui.dp(c, 8));
            row.addView(v, vl);
            legend.addView(row);
        }
        LinearLayout.LayoutParams llp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        if (box.getOrientation() == LinearLayout.HORIZONTAL) llp.setMarginStart(Ui.dp(c, 24));
        else llp.topMargin = Ui.dp(c, 12);
        box.addView(legend, llp);
        return box;
    }

    public static class Donut extends View {
        private final List<Point> points;
        private final String center, sub;
        private final Paint arc, centerP, subP, track;

        public Donut(Context c, List<Point> data, String center, String sub) {
            super(c);
            points = data;
            this.center = center;
            this.sub = sub;
            Palette p = Palette.of(c);
            arc = paint(c, p.primary, 0);
            arc.setStyle(Paint.Style.STROKE);
            arc.setStrokeWidth(Ui.dpf(c, 18));
            track = paint(c, p.surfaceAlt, 0);
            track.setStyle(Paint.Style.STROKE);
            track.setStrokeWidth(Ui.dpf(c, 18));
            centerP = paint(c, p.text, 20);
            centerP.setFakeBoldText(true);
            centerP.setTextAlign(Paint.Align.CENTER);
            subP = paint(c, p.text3, 12);
            subP.setTextAlign(Paint.Align.CENTER);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            float s = Math.min(getWidth(), getHeight());
            float pad = arc.getStrokeWidth() / 2 + 2;
            RectF r = new RectF(pad, pad, s - pad, s - pad);
            canvas.drawArc(r, 0, 360, false, track);
            double total = 0;
            for (Point p : points) total += p.value;
            if (total > 0) {
                float start = -90;
                Palette pal = Palette.of(getContext());
                for (int i = 0; i < points.size(); i++) {
                    Point p = points.get(i);
                    float sweep = (float) (360 * p.value / total);
                    if (sweep <= 0) continue;
                    arc.setColor(p.color != 0 ? p.color : pal.series(i));
                    canvas.drawArc(r, start, Math.max(0.5f, sweep - (points.size() > 1 ? 1.5f : 0)), false, arc);
                    start += sweep;
                }
            }
            if (center != null) {
                float cy = s / 2 + (sub == null ? centerP.getTextSize() / 3 : 0);
                canvas.drawText(center, s / 2, cy, centerP);
                if (sub != null) canvas.drawText(sub, s / 2, cy + subP.getTextSize() + Ui.dpf(getContext(), 4), subP);
            }
        }
    }

    // ---------- 折线 ----------

    public static class Line extends View {
        private List<Point> points = new ArrayList<>();
        private final Paint line, dot, label, grid, fill;
        private final int height;

        public Line(Context c, int heightDp) {
            super(c);
            Palette p = Palette.of(c);
            line = paint(c, p.primary, 0);
            line.setStyle(Paint.Style.STROKE);
            line.setStrokeWidth(Ui.dpf(c, 2.5f));
            line.setStrokeJoin(Paint.Join.ROUND);
            dot = paint(c, p.primary, 0);
            fill = paint(c, (p.primary & 0x00FFFFFF) | 0x22000000, 0);
            label = paint(c, p.text3, 11);
            label.setTextAlign(Paint.Align.CENTER);
            grid = paint(c, p.divider, 0);
            grid.setStrokeWidth(Ui.dpf(c, 1));
            height = Ui.dp(c, heightDp);
        }

        public Line setData(List<Point> data) {
            points = data == null ? new ArrayList<>() : data;
            invalidate();
            return this;
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), height);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            if (points.isEmpty()) return;
            Context c = getContext();
            float top = Ui.dpf(c, 16), bottom = getHeight() - Ui.dpf(c, 22);
            float left = Ui.dpf(c, 12), right = getWidth() - Ui.dpf(c, 12);
            double max = 0, min = Double.MAX_VALUE;
            for (Point p : points) {
                max = Math.max(max, p.value);
                min = Math.min(min, p.value);
            }
            if (max == min) {
                max += 1;
                min = Math.max(0, min - 1);
            }
            for (int i = 0; i <= 3; i++) {
                float y = bottom - (bottom - top) * i / 3f;
                canvas.drawLine(left, y, right, y, grid);
            }
            int n = points.size();
            Path path = new Path(), area = new Path();
            float step = n > 1 ? (right - left) / (n - 1) : 0;
            int every = Math.max(1, (int) Math.ceil(n / Math.max(1f, (right - left) / Ui.dpf(c, 56))));
            for (int i = 0; i < n; i++) {
                float x = n > 1 ? left + step * i : (left + right) / 2;
                float y = (float) (bottom - (bottom - top) * (points.get(i).value - min) / (max - min));
                if (i == 0) {
                    path.moveTo(x, y);
                    area.moveTo(x, bottom);
                }
                path.lineTo(x, y);
                area.lineTo(x, y);
                if (i == n - 1) area.lineTo(x, bottom);
                canvas.drawCircle(x, y, Ui.dpf(c, 3), dot);
                if (i % every == 0) canvas.drawText(points.get(i).label, x, getHeight() - Ui.dpf(c, 6), label);
            }
            area.close();
            canvas.drawPath(area, fill);
            canvas.drawPath(path, line);
        }
    }
}
