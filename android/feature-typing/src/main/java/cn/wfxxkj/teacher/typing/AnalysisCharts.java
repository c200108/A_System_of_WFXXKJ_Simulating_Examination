package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.graphics.Canvas;
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
 * 学情分析页用的图（core 的 Charts 没有的几种）：
 * <ul>
 *   <li>{@link Columns} 竖柱，可分组（两组并排），标签多了自动隔几个显示一个，带纵轴刻度；</li>
 *   <li>{@link Lines} 多条折线，空值断开（那天没人练），带纵轴刻度；</li>
 *   <li>{@link Box} 箱线图（各班学生平均速度的最慢 / 四分位 / 中位数 / 最快）。</li>
 * </ul>
 * 规矩和网页一样：一张图一个纵轴，颜色按系列固定顺序，两个以上系列一定有图例。
 */
final class AnalysisCharts {
    private AnalysisCharts() {}

    /** 一个系列：名字 + 每个横轴位置的值（null = 没数据） */
    static final class Series {
        final String name;
        final Double[] values;
        int color;

        Series(String name, Double[] values) {
            this.name = name;
            this.values = values;
        }
    }

    static Paint paint(Context c, int color, float sp) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setColor(color);
        if (sp > 0) p.setTextSize(Ui.sp(c, sp));
        return p;
    }

    /** 图例：一排「● 名字」 */
    static View legend(Context c, List<Series> series) {
        FlowBox f = new FlowBox(c, 14, 4);
        for (Series s : series) {
            LinearLayout row = V.hbox(c);
            View dot = new View(c);
            dot.setBackground(V.round(c, s.color, 5));
            row.addView(dot, new LinearLayout.LayoutParams(Ui.dp(c, 10), Ui.dp(c, 10)));
            TextView t = V.text(c, s.name, V.CAPTION);
            V.pad(t, 6, 0, 0, 0);
            row.addView(t);
            f.addView(row);
        }
        V.pad(f, 0, 0, 0, 6);
        return f;
    }

    /** 共用的坐标系：左边纵轴刻度、底下横轴标签 */
    abstract static class Axes extends View {
        final Paint grid, axisText, label;
        final int height;
        String[] labels = new String[0];
        /** 纵轴固定 0–100（百分比）；否则 0–自动 */
        boolean percent;
        double max = 1;
        float left, right, top, bottom;

        Axes(Context c, int heightDp) {
            super(c);
            Palette p = Palette.of(c);
            grid = paint(c, p.divider, 0);
            grid.setStrokeWidth(Ui.dpf(c, 1));
            axisText = paint(c, p.text3, 10);
            axisText.setTextAlign(Paint.Align.RIGHT);
            label = paint(c, p.text3, 11);
            label.setTextAlign(Paint.Align.CENTER);
            height = Ui.dp(c, heightDp);
        }

        @Override
        protected void onMeasure(int w, int h) {
            setMeasuredDimension(MeasureSpec.getSize(w), height);
        }

        /** 刻度取整：0、step、2step… 让最大值落在 4 格以内 */
        double niceMax(double m) {
            if (percent) return 100;
            if (m <= 0) return 4;
            double raw = m / 4;
            double mag = Math.pow(10, Math.floor(Math.log10(raw)));
            double[] steps = {1, 2, 2.5, 5, 10};
            double step = mag;
            for (double s : steps) {
                if (s * mag >= raw) {
                    step = s * mag;
                    break;
                }
            }
            if (step < 1) step = 1;
            return step * 4;
        }

        void drawFrame(Canvas canvas) {
            Context c = getContext();
            String widest = percent ? "100%" : Fmt.num(max);
            left = axisText.measureText(widest) + Ui.dpf(c, 8);
            right = getWidth() - Ui.dpf(c, 4);
            top = Ui.dpf(c, 14);
            bottom = getHeight() - Ui.dpf(c, 22);
            for (int i = 0; i <= 4; i++) {
                float y = bottom - (bottom - top) * i / 4f;
                canvas.drawLine(left, y, right, y, grid);
                String t = Fmt.num(max * i / 4) + (percent ? "%" : "");
                canvas.drawText(t, left - Ui.dpf(c, 6), y + axisText.getTextSize() / 3, axisText);
            }
        }

        float y(double v) {
            return (float) (bottom - (bottom - top) * Math.max(0, Math.min(1, v / max)));
        }

        /** 横轴标签：放不下就隔几个画一个 */
        void drawLabels(Canvas canvas, float[] xs) {
            Context c = getContext();
            int n = labels.length;
            if (n == 0) return;
            float slot = (right - left) / n;
            float widest = 0;
            for (String s : labels) widest = Math.max(widest, label.measureText(s));
            int every = Math.max(1, (int) Math.ceil((widest + Ui.dpf(c, 6)) / Math.max(1, slot)));
            if (every > 1 && n <= 8) every = 1; // 少的时候宁可省略号也全显示（班级名）
            TextPaint tp = new TextPaint(label);
            for (int i = 0; i < n; i += every) {
                String s = every == 1 ? TextUtils.ellipsize(labels[i], tp, slot - Ui.dpf(c, 2),
                        TextUtils.TruncateAt.END).toString() : labels[i];
                canvas.drawText(s, xs[i], getHeight() - Ui.dpf(c, 6), label);
            }
        }
    }

    // ---------------------------------------------------------------- 竖柱

    static final class Columns extends Axes {
        private List<Series> series = new ArrayList<>();
        private final Paint bar, value;
        private boolean showValues = true;

        Columns(Context c, int heightDp) {
            super(c, heightDp);
            bar = paint(c, Palette.of(c).primary, 0);
            value = paint(c, Palette.of(c).text2, 10);
            value.setTextAlign(Paint.Align.CENTER);
        }

        Columns set(String[] labels, List<Series> series, boolean percent) {
            this.labels = labels;
            this.series = series;
            this.percent = percent;
            double m = 0;
            for (Series s : series) for (Double v : s.values) if (v != null) m = Math.max(m, v);
            max = niceMax(m);
            invalidate();
            return this;
        }

        Columns values(boolean on) {
            showValues = on;
            return this;
        }

        @Override
        protected void onDraw(Canvas canvas) {
            if (labels.length == 0 || series.isEmpty()) return;
            drawFrame(canvas);
            Context c = getContext();
            int n = labels.length, k = series.size();
            float slot = (right - left) / n;
            float group = Math.min(slot * 0.7f, Ui.dpf(c, 34) * k);
            float bw = group / k;
            float r = Math.min(Ui.dpf(c, 4), bw / 2);
            boolean roomForValues = showValues && bw >= value.measureText("888") && k == 1;
            float[] xs = new float[n];
            for (int i = 0; i < n; i++) {
                float cx = left + slot * i + slot / 2;
                xs[i] = cx;
                for (int j = 0; j < k; j++) {
                    Double v = series.get(j).values[i];
                    if (v == null) continue;
                    float x0 = cx - group / 2 + bw * j + (k > 1 ? Ui.dpf(c, 1) : 0);
                    float x1 = x0 + bw - (k > 1 ? Ui.dpf(c, 2) : 0);
                    float yy = y(v);
                    if (v > 0) {
                        bar.setColor(series.get(j).color);
                        Path path = new Path();
                        path.addRoundRect(new RectF(x0, yy, x1, bottom), new float[]{r, r, r, r, 0, 0, 0, 0},
                                Path.Direction.CW);
                        canvas.drawPath(path, bar);
                    }
                    if (roomForValues && v > 0) {
                        canvas.drawText(Fmt.num(v), (x0 + x1) / 2, yy - Ui.dpf(c, 4), value);
                    }
                }
            }
            drawLabels(canvas, xs);
        }
    }

    // ---------------------------------------------------------------- 折线

    static final class Lines extends Axes {
        private List<Series> series = new ArrayList<>();
        private final Paint line, dot, hole;

        Lines(Context c, int heightDp) {
            super(c, heightDp);
            line = paint(c, Palette.of(c).primary, 0);
            line.setStyle(Paint.Style.STROKE);
            line.setStrokeWidth(Ui.dpf(c, 2.2f));
            line.setStrokeJoin(Paint.Join.ROUND);
            line.setStrokeCap(Paint.Cap.ROUND);
            dot = paint(c, Palette.of(c).primary, 0);
            hole = paint(c, Palette.of(c).surface, 0);
        }

        Lines set(String[] labels, List<Series> series, boolean percent) {
            this.labels = labels;
            this.series = series;
            this.percent = percent;
            double m = 0;
            for (Series s : series) for (Double v : s.values) if (v != null) m = Math.max(m, v);
            max = niceMax(m);
            invalidate();
            return this;
        }

        @Override
        protected void onDraw(Canvas canvas) {
            if (labels.length == 0 || series.isEmpty()) return;
            drawFrame(canvas);
            Context c = getContext();
            int n = labels.length;
            float pad = Ui.dpf(c, 8);
            float[] xs = new float[n];
            for (int i = 0; i < n; i++) {
                xs[i] = n == 1 ? (left + right) / 2 : left + pad + (right - left - pad * 2) * i / (n - 1);
            }
            float dr = n > 20 ? Ui.dpf(c, 2.2f) : Ui.dpf(c, 3.5f);
            for (Series s : series) {
                line.setColor(s.color);
                dot.setColor(s.color);
                Path path = new Path();
                boolean open = false;
                for (int i = 0; i < n && i < s.values.length; i++) {
                    Double v = s.values[i];
                    if (v == null) {
                        open = false; // 没数据就断开，不硬连
                        continue;
                    }
                    if (!open) path.moveTo(xs[i], y(v));
                    else path.lineTo(xs[i], y(v));
                    open = true;
                }
                canvas.drawPath(path, line);
                for (int i = 0; i < n && i < s.values.length; i++) {
                    Double v = s.values[i];
                    if (v == null) continue;
                    canvas.drawCircle(xs[i], y(v), dr + Ui.dpf(c, 1.2f), hole);
                    canvas.drawCircle(xs[i], y(v), dr, dot);
                }
            }
            drawLabels(canvas, xs);
        }
    }

    // ---------------------------------------------------------------- 箱线图

    static final class Box extends Axes {
        private List<double[]> boxes = new ArrayList<>();
        private final Paint stroke, fill, mid;

        Box(Context c, int heightDp) {
            super(c, heightDp);
            Palette p = Palette.of(c);
            stroke = paint(c, p.primary, 0);
            stroke.setStyle(Paint.Style.STROKE);
            stroke.setStrokeWidth(Ui.dpf(c, 2));
            fill = paint(c, p.primarySoft, 0);
            mid = paint(c, p.primary, 0);
            mid.setStrokeWidth(Ui.dpf(c, 3));
        }

        /** 每个 box：最慢、下四分位、中位数、上四分位、最快 */
        Box set(String[] labels, List<double[]> boxes) {
            this.labels = labels;
            this.boxes = boxes;
            double m = 0;
            for (double[] b : boxes) if (b.length == 5) m = Math.max(m, b[4]);
            max = niceMax(m);
            invalidate();
            return this;
        }

        @Override
        protected void onDraw(Canvas canvas) {
            if (labels.length == 0) return;
            drawFrame(canvas);
            Context c = getContext();
            int n = labels.length;
            float slot = (right - left) / n;
            float bw = Math.min(Ui.dpf(c, 36), slot * 0.5f);
            float[] xs = new float[n];
            for (int i = 0; i < n; i++) {
                float cx = left + slot * i + slot / 2;
                xs[i] = cx;
                if (i >= boxes.size() || boxes.get(i).length != 5) continue;
                double[] b = boxes.get(i);
                // 须线
                canvas.drawLine(cx, y(b[0]), cx, y(b[1]), stroke);
                canvas.drawLine(cx, y(b[3]), cx, y(b[4]), stroke);
                canvas.drawLine(cx - bw / 4, y(b[0]), cx + bw / 4, y(b[0]), stroke);
                canvas.drawLine(cx - bw / 4, y(b[4]), cx + bw / 4, y(b[4]), stroke);
                // 箱子
                RectF rect = new RectF(cx - bw / 2, y(b[3]), cx + bw / 2, y(b[1]));
                if (rect.height() < Ui.dpf(c, 2)) rect.bottom = rect.top + Ui.dpf(c, 2);
                canvas.drawRoundRect(rect, Ui.dpf(c, 3), Ui.dpf(c, 3), fill);
                canvas.drawRoundRect(rect, Ui.dpf(c, 3), Ui.dpf(c, 3), stroke);
                canvas.drawLine(cx - bw / 2, y(b[2]), cx + bw / 2, y(b[2]), mid);
            }
            drawLabels(canvas, xs);
        }
    }
}
