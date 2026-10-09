package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 更新日志里的一个版本：版本号、日期，按变动类型（新增/变更/弃用/移除/修复/安全）分组的条目。
 * 长按某一条弹出「复制 / 删除」。
 */
final class ChangelogCard extends LinearLayout {

    interface OnEntry {
        void longPress(JSONObject entry, String version);
    }

    private final OnEntry onEntry;

    ChangelogCard(Context c, OnEntry onEntry) {
        super(c);
        this.onEntry = onEntry;
        setOrientation(VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 16));
        V.pad(this, 16, 14, 16, 10);
    }

    /** 六种变动类型各给一个色调，扫一眼就知道这条是加东西还是修 bug */
    static Tone toneOf(String type) {
        switch (type) {
            case "Added":
                return Tone.SUCCESS;
            case "Changed":
                return Tone.PRIMARY;
            case "Deprecated":
                return Tone.WARNING;
            case "Fixed":
                return Tone.INFO;
            case "Security":
                return Tone.DANGER;
            default:
                return Tone.NEUTRAL;
        }
    }

    static String symbolOf(String type) {
        switch (type) {
            case "Added":
                return "+";
            case "Changed":
                return "↻";
            case "Deprecated":
                return "!";
            case "Removed":
                return "−";
            case "Fixed":
                return "✓";
            case "Security":
                return "◆";
            default:
                return "·";
        }
    }

    void bind(final JSONObject v, boolean latest) {
        Context c = getContext();
        Palette p = Palette.of(c);
        removeAllViews();
        final String version = Json.str(v, "version");

        LinearLayout head = V.hbox(c);
        TextView ver = V.text(c, version, V.H2);
        ver.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        head.addView(ver);
        if (latest) V.addStart(head, V.tag(c, "最新", Tone.PRIMARY), 8);
        head.addView(V.spring(c));
        head.addView(V.text(c, Json.str(v, "released_on"), V.CAPTION));
        addView(head);

        for (JSONObject g : Json.list(Json.arr(v, "groups"))) {
            String type = Json.str(g, "type");
            int[] t = p.tone(toneOf(type));
            LinearLayout gt = V.hbox(c);
            V.pad(gt, 0, 12, 0, 4);
            TextView icon = V.text(c, symbolOf(type), V.LABEL);
            icon.setGravity(Gravity.CENTER);
            icon.setTextColor(t[0]);
            icon.setBackground(V.round(c, t[1], 6));
            int s = Ui.dp(c, 22);
            gt.addView(icon, new LayoutParams(s, s));
            TextView label = V.text(c, Json.str(g, "label"), V.LABEL);
            label.setTextColor(toneOf(type) == Tone.NEUTRAL ? p.text2 : t[0]);
            V.addStart(gt, label, 8);
            TextView en = V.text(c, type, V.CAPTION);
            en.setTypeface(Typeface.MONOSPACE);
            V.addStart(gt, en, 6);
            addView(gt);

            for (final JSONObject it : Json.list(Json.arr(g, "items"))) {
                LinearLayout row = V.hbox(c);
                row.setGravity(Gravity.TOP);
                V.pad(row, 8, 4, 4, 4);
                TextView dot = V.text(c, "•", V.BODY2);
                dot.setTextColor(p.text3);
                row.addView(dot);
                TextView text = V.text(c, Json.str(it, "content"), V.BODY2);
                text.setLineSpacing(0, 1.4f);
                V.pad(text, 8, 0, 0, 0);
                row.addView(text, V.fill());
                row.setOnLongClickListener(x -> {
                    onEntry.longPress(it, version);
                    return true;
                });
                row.setBackground(V.ripple(c, null, 8));
                addView(row);
            }
        }
    }
}
