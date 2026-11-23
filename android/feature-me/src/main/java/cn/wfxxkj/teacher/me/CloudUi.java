package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.graphics.Typeface;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Locale;

import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/** 个人云盘（服务端 2.25.0）几个页面共用的：字节换算、进度条、云盘网址那一行 */
final class CloudUi {
    private CloudUi() {}

    static final double GB = 1024.0 * 1024 * 1024;

    /** 字节 → 「1.5 GB」「320 MB」（和网页 cloud.js 的 fmtBytes 一样） */
    static String bytes(double n) {
        if (n >= Math.pow(1024, 4)) return String.format(Locale.ROOT, "%.2f TB", n / Math.pow(1024, 4));
        if (n >= GB) return String.format(Locale.ROOT, n >= 100 * GB ? "%.0f GB" : "%.1f GB", n / GB);
        double mb = 1024.0 * 1024;
        if (n >= mb) return String.format(Locale.ROOT, n >= 100 * mb ? "%.0f MB" : "%.1f MB", n / mb);
        if (n >= 1024) return Math.round(n / 1024) + " KB";
        return (long) n + " B";
    }

    /** 用了百分之几，0～100 */
    static double pct(double used, double quota) {
        if (quota <= 0) return 0;
        return Math.min(100, Math.round(used / quota * 1000) / 10.0);
    }

    /** 细进度条；danger = 超额 / 快满了标红 */
    static View bar(Context c, double pct, boolean danger) {
        Palette p = Palette.of(c);
        LinearLayout track = V.hbox(c);
        track.setBackground(V.round(c, p.surfaceAlt, 4));
        track.setClipToOutline(true);
        View fill = new View(c);
        fill.setBackground(V.round(c, danger ? p.danger : p.primary, 4));
        float w = (float) Math.max(0, Math.min(100, pct));
        track.addView(fill, new LinearLayout.LayoutParams(0, Ui.dp(c, 8), w));
        track.addView(new View(c), new LinearLayout.LayoutParams(0, Ui.dp(c, 8), 100 - w));
        track.setLayoutParams(new LinearLayout.LayoutParams(V.MATCH, Ui.dp(c, 8)));
        return track;
    }

    /** 云盘网址：用 APP 登录时填的服务器地址 + /cloud/ */
    static String url() {
        return Session.get().server().replaceAll("/+$", "") + "/cloud/";
    }

    /** 「云盘网址 http://…/cloud/  复制」 */
    static View urlRow(cn.wfxxkj.teacher.core.nav.Screen s) {
        Context c = s.ctx();
        Palette p = Palette.of(c);
        LinearLayout row = V.hbox(c);
        row.setBackground(V.round(c, p.surfaceAlt, 8));
        V.pad(row, 12, 6, 4, 6);
        LinearLayout texts = V.vbox(c);
        texts.addView(V.text(c, "云盘网址", V.CAPTION));
        TextView u = V.text(c, url(), V.BODY2);
        u.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        u.setTextColor(p.primary);
        u.setTextIsSelectable(true);
        texts.addView(u);
        row.addView(texts, V.fill());
        row.addView(V.button(c, "复制", V.BTN_TEXT, v -> {
            Sys.copy(c, "云盘网址", url());
            s.toast("云盘网址已复制");
        }));
        return row;
    }
}
