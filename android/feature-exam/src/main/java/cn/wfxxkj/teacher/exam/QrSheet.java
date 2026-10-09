package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 学生链接的二维码：老师把手机举给学生扫，或者存成图片发到班级群。
 * 网页版没有二维码（电脑上直接复制链接），手机上扫码更顺手，所以 APP 多了这一项。
 */
final class QrSheet {
    private QrSheet() {}

    static void show(Screen s, String title, String link) {
        Context c = s.ctx();
        QrCode qr;
        try {
            qr = QrCode.encode(link);
        } catch (IllegalArgumentException e) {
            s.toast(e.getMessage());
            return;
        }
        Sheet sheet = new Sheet(c, "扫码答题");
        LinearLayout box = V.vbox(c);
        box.setGravity(Gravity.CENTER_HORIZONTAL);
        TextView t = V.text(c, title, V.H3);
        t.setGravity(Gravity.CENTER);
        box.addView(t);

        // 二维码永远白底黑块（深色模式下也一样，否则不好扫）
        FrameLayout frame = new FrameLayout(c);
        frame.setBackground(V.stroke(c, Color.WHITE, Palette.of(c).border, 16));
        V.pad(frame, 22); // 四周留够白边（静区），扫得快
        int side = Math.min(Ui.dp(c, 240), Ui.dp(c, Ui.widthDp(c) * 0.62f));
        frame.addView(new QrView(c, qr), new FrameLayout.LayoutParams(side, side));
        LinearLayout.LayoutParams flp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        flp.topMargin = Ui.dp(c, 14);
        flp.gravity = Gravity.CENTER_HORIZONTAL;
        box.addView(frame, flp);

        TextView l = V.text(c, link, V.CAPTION);
        l.setGravity(Gravity.CENTER);
        l.setTextIsSelectable(true);
        V.addTop(box, l, 12);
        TextView hint = V.text(c, "学生用手机扫码或浏览器打开链接即可答题，不需要账号", V.CAPTION);
        hint.setGravity(Gravity.CENTER);
        V.addTop(box, hint, 4);

        LinearLayout row = V.hbox(c);
        row.setGravity(Gravity.CENTER);
        row.addView(V.button(c, R.drawable.ic_content_copy, "复制链接", V.BTN_TONAL, v -> {
            Sys.copy(c, "考试链接", link);
            s.toast("链接已复制");
        }));
        row.addView(V.space(c, 10));
        row.addView(V.button(c, R.drawable.ic_share, "分享", V.BTN_TONAL,
                v -> Sys.share(c, "把考试链接发给学生", title + "\n" + link)));
        V.addTop(box, row, 16);

        sheet.content(box);
        sheet.buttons("关闭", null, "保存图片", () -> {
            sheet.dismiss();
            saveImage(s, qr, title);
        });
        sheet.show();
    }

    /** 画成带标题的白底图片，存进「下载/教学平台」 */
    private static void saveImage(Screen s, QrCode qr, String title) {
        s.runBusy("正在保存…", () -> {
            int cell = 16, quiet = 4, side = (qr.size + quiet * 2) * cell;
            int textH = 120;
            Bitmap bm = Bitmap.createBitmap(side, side + textH, Bitmap.Config.ARGB_8888);
            Canvas cv = new Canvas(bm);
            cv.drawColor(Color.WHITE);
            Paint p = new Paint();
            p.setColor(Color.BLACK);
            for (int y = 0; y < qr.size; y++) {
                for (int x = 0; x < qr.size; x++) {
                    if (qr.get(x, y)) {
                        cv.drawRect((x + quiet) * cell, (y + quiet) * cell, (x + quiet + 1) * cell,
                                (y + quiet + 1) * cell, p);
                    }
                }
            }
            Paint tp = new Paint(Paint.ANTI_ALIAS_FLAG);
            tp.setColor(0xFF222222);
            tp.setTextSize(40);
            tp.setTextAlign(Paint.Align.CENTER);
            String shown = android.text.TextUtils.ellipsize(title, new android.text.TextPaint(tp), side - 40,
                    android.text.TextUtils.TruncateAt.END).toString();
            cv.drawText(shown, side / 2f, side + 50, tp);
            tp.setTextSize(28);
            tp.setColor(0xFF777777);
            cv.drawText("扫码进入考试", side / 2f, side + 96, tp);
            File dir = new File(s.ctx().getCacheDir(), "dl");
            //noinspection ResultOfMethodCallIgnored
            dir.mkdirs();
            File f = new File(dir, "qr-" + System.currentTimeMillis() + ".png");
            FileOutputStream out = new FileOutputStream(f);
            bm.compress(Bitmap.CompressFormat.PNG, 100, out);
            out.close();
            bm.recycle();
            String name = Files.safeName(title + "_二维码.png");
            Uri uri = Files.save(s.ctx(), f, name, "image/png");
            return new Object[]{uri, Files.displayName(s.ctx(), uri, name)};
        }, r -> {
            Uri uri = (Uri) r[0];
            String name = (String) r[1];
            s.snack("已保存到「下载/教学平台/" + name + "」", "打开", () -> Files.open(s.ctx(), uri, name));
        });
    }

    /** 画二维码的视图 */
    static final class QrView extends View {
        private final QrCode qr;
        private final Paint dark = new Paint();

        QrView(Context c, QrCode qr) {
            super(c);
            this.qr = qr;
            dark.setColor(Color.BLACK);
            setContentDescription("考试链接二维码");
        }

        @Override
        protected void onDraw(Canvas canvas) {
            int n = qr.size;
            float cell = Math.min(getWidth(), getHeight()) / (float) n;
            for (int y = 0; y < n; y++) {
                for (int x = 0; x < n; x++) {
                    if (qr.get(x, y)) {
                        canvas.drawRect(x * cell, y * cell, (x + 1) * cell + 0.5f, (y + 1) * cell + 0.5f, dark);
                    }
                }
            }
        }
    }
}
