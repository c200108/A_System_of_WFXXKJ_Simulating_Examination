package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.DashPathEffect;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.text.TextPaint;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * core 的 Charts 没有的三种图，成绩分析页要用：
 * <ul>
 *   <li>{@link Grouped} 分组柱（班级对比：每班三根柱；学生对比：每个知识范围每人一根）；</li>
 *   <li>{@link Box} 箱线图（各班分数的最高、四分位、中位数、最低）；</li>
 *   <li>{@link Scatter} 散点图（每道题的得分率 × 区分度）。</li>
 * </ul>
 * 颜色跟 core 一样从 Palette.series 按固定顺序取，深浅色自动跟着变。
 */
final class MiniCharts {
    private MiniCharts() {}

    static Paint paint(Context c, int color, float sp) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(color);
        if (sp > 0) p.setTextSize(Ui.sp(c, sp));
        return p;
    }

    /** 图例：彩色小方块 + 名字，自动换行 */
    static View legend(Context c, List<String> names) {
        FlowBox f = new FlowBox(c, 14, 6);
        Palette p = Palette.of(c);
        for (int i = 0; i < names.size(); i++) {
            LinearLayout row = V.hbox(c);
            View dot = new View(c);
            dot.setBackground(V.round(c, p.series(i), 3));
            row.addView(dot, new LinearLayout.LayoutParams(Ui.dp(c, 10), Ui.dp(c, 10)));
            TextView t = V.text(c, names.get(i), V.CAPTION);
            V.addStart(row, t, 6);
            f.addView(row);
        }
        return f;
    }

    /** 画一条水平虚线 + 右端小字（及格线） */
    static void dashed(Canvas cv, Context c, float x0, float x1, float y, String label) {
        Palette p = Palette.of(c);
        Paint d = paint(c, p.text3, 0);
        d.setStyle(Paint.Style.STROKE);
        d.setStrokeWidth(Ui.dpf(c, 1));
        d.setPathEffect(new DashPathEffect(new float[]{Ui.dpf(c, 4), Ui.dpf(c, 3)}, 0));
        Path path = new Path();
        path.moveTo(x0, y);
        path.lineTo(x1, y);
        cv.drawPath(path, d);
        if (label != null) {
            Paint t = paint(c, p.text3, 10);
            t.setTextAlign(Paint.Align.RIGHT);
            cv.drawText(label, x1, y - Ui.dpf(c, 3), t);
        }
    }

    // ---------- 分组柱 ----------

    /** 分组柱：横轴是类别，每类里每个系列一根柱，纵轴 0–100%，带及格线 */
    static final class Grouped extends View {
        private List<String> cats = new ArrayList<>();
        private double[][] values = new double[0][0]; // [系列][类别]，NaN = 没数据
        private final int height;
        private double passLine = -1;

        Grouped(Context c, int heightDp) {
            super(c);
            height = Ui.dp(c, heightDp);
        }

        Grouped setData(List<String> categories, double[][] seriesValues, double passLine) {
            cats = categories;
            values = seriesValues;
            this.passLine = passLine;
            requestLayout();
            invalidate();
            return this;
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), height);
        }

        @Override
        protected void onDraw(Canvas cv) {
            if (cats.isEmpty() || values.length == 0) return;
            Context c = getContext();
            Palette p = Palette.of(c);
            Paint axis = paint(c, p.text3, 10);
            axis.setTextAlign(Paint.Align.RIGHT);
            Paint grid = paint(c, p.divider, 0);
            grid.setStrokeWidth(Ui.dpf(c, 1));
            Paint lab = paint(c, p.text2, 11);
            lab.setTextAlign(Paint.Align.CENTER);
            Paint bar = paint(c, p.primary, 0);
            float left = axis.measureText("100%") + Ui.dpf(c, 6), right = getWidth();
            float top = Ui.dpf(c, 10), bottom = getHeight() - Ui.dpf(c, 22);
            for (int i = 0; i <= 4; i++) {
                float y = bottom - (bottom - top) * i / 4f;
                cv.drawLine(left, y, right, y, grid);
                cv.drawText(i * 25 + "%", left - Ui.dpf(c, 4), y + Ui.dpf(c, 3), axis);
            }
            int n = cats.size(), s = values.length;
            float slot = (right - left) / n;
            float groupW = Math.min(slot * 0.8f, Ui.dpf(c, 26) * s);
            float bw = groupW / s;
            float r = Math.min(Ui.dpf(c, 4), bw / 2);
            for (int i = 0; i < n; i++) {
                float gx = left + slot * i + (slot - groupW) / 2;
                for (int k = 0; k < s; k++) {
                    double v = i < values[k].length ? values[k][i] : Double.NaN;
                    if (Double.isNaN(v) || v <= 0) continue;
                    float h = (float) ((bottom - top) * Math.min(100, v) / 100);
                    bar.setColor(p.series(k));
                    Path path = new Path();
                    path.addRoundRect(new RectF(gx + bw * k + 1, bottom - h, gx + bw * (k + 1) - 1, bottom),
                            new float[]{r, r, r, r, 0, 0, 0, 0}, Path.Direction.CW);
                    cv.drawPath(path, bar);
                }
                String l = TextUtils.ellipsize(cats.get(i), new TextPaint(lab), slot - Ui.dpf(c, 4),
                        TextUtils.TruncateAt.END).toString();
                cv.drawText(l, left + slot * i + slot / 2, getHeight() - Ui.dpf(c, 6), lab);
            }
            if (passLine >= 0) {
                float y = (float) (bottom - (bottom - top) * passLine / 100);
                dashed(cv, c, left, right, y, "及格线 " + Fmt.num(passLine) + "%");
            }
        }
    }

    // ---------- 箱线图 ----------

    static final class Box extends View {
        private List<String> names = new ArrayList<>();
        private List<double[]> boxes = new ArrayList<>(); // [最低, 下四分位, 中位数, 上四分位, 最高]
        private double max = 100;
        private final int height;

        Box(Context c, int heightDp) {
            super(c);
            height = Ui.dp(c, heightDp);
        }

        Box setData(List<String> names, List<double[]> boxes, double max) {
            this.names = names;
            this.boxes = boxes;
            this.max = max > 0 ? max : 100;
            invalidate();
            return this;
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), height);
        }

        @Override
        protected void onDraw(Canvas cv) {
            if (names.isEmpty()) return;
            Context c = getContext();
            Palette p = Palette.of(c);
            Paint axis = paint(c, p.text3, 10);
            axis.setTextAlign(Paint.Align.RIGHT);
            Paint grid = paint(c, p.divider, 0);
            grid.setStrokeWidth(Ui.dpf(c, 1));
            Paint lab = paint(c, p.text2, 11);
            lab.setTextAlign(Paint.Align.CENTER);
            Paint line = paint(c, p.primary, 0);
            line.setStyle(Paint.Style.STROKE);
            line.setStrokeWidth(Ui.dpf(c, 2));
            Paint fill = paint(c, p.primarySoft, 0);
            float left = axis.measureText(Fmt.num(max)) + Ui.dpf(c, 8), right = getWidth();
            float top = Ui.dpf(c, 10), bottom = getHeight() - Ui.dpf(c, 22);
            for (int i = 0; i <= 4; i++) {
                float y = bottom - (bottom - top) * i / 4f;
                cv.drawLine(left, y, right, y, grid);
                cv.drawText(Fmt.num(max * i / 4), left - Ui.dpf(c, 4), y + Ui.dpf(c, 3), axis);
            }
            int n = names.size();
            float slot = (right - left) / n;
            float bw = Math.min(Ui.dpf(c, 36), slot * 0.5f);
            for (int i = 0; i < n; i++) {
                double[] b = boxes.get(i);
                if (b == null || b.length < 5) continue;
                float cx = left + slot * i + slot / 2;
                float yLo = y(b[0], top, bottom), yQ1 = y(b[1], top, bottom), yMed = y(b[2], top, bottom);
                float yQ3 = y(b[3], top, bottom), yHi = y(b[4], top, bottom);
                cv.drawLine(cx, yHi, cx, yQ3, line);
                cv.drawLine(cx, yQ1, cx, yLo, line);
                cv.drawLine(cx - bw / 4, yHi, cx + bw / 4, yHi, line);
                cv.drawLine(cx - bw / 4, yLo, cx + bw / 4, yLo, line);
                RectF rect = new RectF(cx - bw / 2, yQ3, cx + bw / 2, Math.max(yQ1, yQ3 + 2));
                cv.drawRect(rect, fill);
                cv.drawRect(rect, line);
                cv.drawLine(cx - bw / 2, yMed, cx + bw / 2, yMed, line);
                String l = TextUtils.ellipsize(names.get(i), new TextPaint(lab), slot - Ui.dpf(c, 4),
                        TextUtils.TruncateAt.END).toString();
                cv.drawText(l, cx, getHeight() - Ui.dpf(c, 6), lab);
            }
        }

        private float y(double v, float top, float bottom) {
            return (float) (bottom - (bottom - top) * Math.max(0, Math.min(max, v)) / max);
        }
    }

    // ---------- 散点 ----------

    /** 横轴得分率 0–100%，纵轴区分度 -1–1；区分度 &lt; 0.2 的点标题号，0.2 画虚线 */
    static final class Scatter extends View {
        private final List<double[]> pts = new ArrayList<>(); // [得分率, 区分度]
        private final List<String> labels = new ArrayList<>();
        private final int height;

        Scatter(Context c, int heightDp) {
            super(c);
            height = Ui.dp(c, heightDp);
        }

        void add(double rate, double disc, String label) {
            pts.add(new double[]{rate, disc});
            labels.add(label);
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), height);
        }

        @Override
        protected void onDraw(Canvas cv) {
            Context c = getContext();
            Palette p = Palette.of(c);
            Paint axis = paint(c, p.text3, 10);
            axis.setTextAlign(Paint.Align.RIGHT);
            Paint grid = paint(c, p.divider, 0);
            grid.setStrokeWidth(Ui.dpf(c, 1));
            float left = axis.measureText("-0.5") + Ui.dpf(c, 8), right = getWidth() - Ui.dpf(c, 8);
            float top = Ui.dpf(c, 10), bottom = getHeight() - Ui.dpf(c, 34);
            for (int i = 0; i <= 4; i++) {
                double v = -1 + i * 0.5;
                float y = (float) (bottom - (bottom - top) * (v + 1) / 2);
                cv.drawLine(left, y, right, y, grid);
                cv.drawText(Fmt.num(v), left - Ui.dpf(c, 4), y + Ui.dpf(c, 3), axis);
            }
            Paint xl = paint(c, p.text3, 10);
            xl.setTextAlign(Paint.Align.CENTER);
            for (int i = 0; i <= 4; i++) {
                float x = left + (right - left) * i / 4f;
                cv.drawLine(x, top, x, bottom, grid);
                cv.drawText(i * 25 + "%", x, bottom + Ui.dpf(c, 13), xl);
            }
            cv.drawText("得分率 →（越往右越容易）", (left + right) / 2, getHeight() - Ui.dpf(c, 3), xl);
            dashed(cv, c, left, right, (float) (bottom - (bottom - top) * 1.2 / 2), "0.2 以下偏低");
            Paint dot = paint(c, p.primary, 0);
            Paint ring = paint(c, p.surface, 0);
            Paint lab = paint(c, p.text2, 10);
            float rad = Ui.dpf(c, 4.5f);
            for (int i = 0; i < pts.size(); i++) {
                double[] q = pts.get(i);
                float x = (float) (left + (right - left) * Math.max(0, Math.min(100, q[0])) / 100);
                float y = (float) (bottom - (bottom - top) * (Math.max(-1, Math.min(1, q[1])) + 1) / 2);
                cv.drawCircle(x, y, rad + Ui.dpf(c, 1.5f), ring);
                dot.setColor(q[1] < 0.2 ? p.warning : p.primary);
                cv.drawCircle(x, y, rad, dot);
            }
            // 只给区分度偏低的点标题号，全标会糊成一团；同一位置只标一次
            List<float[]> placed = new ArrayList<>();
            for (int i = 0; i < pts.size(); i++) {
                double[] q = pts.get(i);
                if (q[1] >= 0.2) continue;
                float x = (float) (left + (right - left) * Math.max(0, Math.min(100, q[0])) / 100);
                float y = (float) (bottom - (bottom - top) * (Math.max(-1, Math.min(1, q[1])) + 1) / 2);
                boolean clash = false;
                for (float[] pl : placed) if (Math.abs(pl[0] - x) < Ui.dpf(c, 30) && Math.abs(pl[1] - y) < Ui.dpf(c, 12)) clash = true;
                if (clash) continue;
                placed.add(new float[]{x, y});
                lab.setTextAlign(x > right - Ui.dpf(c, 50) ? Paint.Align.RIGHT : Paint.Align.LEFT);
                cv.drawText(labels.get(i), x + (lab.getTextAlign() == Paint.Align.LEFT ? rad + 4 : -rad - 4),
                        y + Ui.dpf(c, 3), lab);
            }
        }
    }
}
