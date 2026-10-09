package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Images;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 题库列表的一张卡片：
 * <pre>
 * [选择题] [Windows系统操作]                 ③
 * 切换活动窗口的快捷键是（ ）。                [图]
 * A.Alt+Tab  B.Ctrl+C …
 * C0012 · 答案 A                         ☆ 必出
 * </pre>
 * 右下角的星标就是网页表格里的「必出」开关，点一下直接切换。
 */
final class QuestionCard extends LinearLayout {

    interface PinToggle {
        void toggle(JSONObject q);
    }

    private final LinearLayout tags;
    private final TextView level;
    private final TextView stem;
    private final TextView options;
    private final ImageView thumb;
    private final TextView meta;
    private final TextView pin;
    private JSONObject item;

    QuestionCard(Context c, PinToggle onPin) {
        super(c);
        setOrientation(VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 16));
        V.pad(this, 16, 14, 12, 8);

        LinearLayout top = V.hbox(c);
        tags = V.hbox(c);
        top.addView(tags, V.fill());
        level = Bank.levelDot(c, 3);
        top.addView(level);
        // 给多选时右上角的勾留位置
        top.addView(V.space(c, 4));
        addView(top, V.matchWrap());

        LinearLayout body = V.hbox(c);
        body.setGravity(Gravity.TOP);
        LinearLayout texts = V.vbox(c);
        stem = V.lines(V.text(c, "", V.BODY), 3);
        texts.addView(stem);
        options = V.lines(V.text(c, "", V.CAPTION), 2);
        V.pad(options, 0, 4, 0, 0);
        texts.addView(options);
        body.addView(texts, V.fill());
        thumb = new ImageView(c);
        thumb.setScaleType(ImageView.ScaleType.CENTER_CROP);
        thumb.setBackground(V.round(c, p.surfaceAlt, 10));
        thumb.setClipToOutline(true);
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(Ui.dp(c, 56), Ui.dp(c, 56));
        tlp.setMarginStart(Ui.dp(c, 10));
        tlp.topMargin = Ui.dp(c, 2);
        body.addView(thumb, tlp);
        LinearLayout.LayoutParams blp = V.matchWrap();
        blp.topMargin = Ui.dp(c, 8);
        addView(body, blp);

        LinearLayout bottom = V.hbox(c);
        meta = V.oneLine(V.text(c, "", V.CAPTION));
        bottom.addView(meta, V.fill());
        pin = V.text(c, "必出", V.CAPTION);
        pin.setGravity(Gravity.CENTER_VERTICAL);
        pin.setCompoundDrawablePadding(Ui.dp(c, 4));
        V.pad(pin, 10, 8, 6, 8);
        V.clickable(pin, 10, v -> {
            if (item != null && onPin != null) onPin.toggle(item);
        });
        bottom.addView(pin);
        LinearLayout.LayoutParams bl = V.matchWrap();
        bl.topMargin = Ui.dp(c, 4);
        addView(bottom, bl);
    }

    void bind(JSONObject q) {
        item = q;
        Context c = getContext();
        Palette p = Palette.of(c);
        tags.removeAllViews();
        String type = Json.str(q, "type");
        tags.addView(V.tag(c, type, Bank.typeTone(type)));
        String scope = Json.str(q, "scope");
        if (!scope.isEmpty()) {
            TextView t = V.tag(c, scope, Tone.NEUTRAL);
            V.addStart(tags, t, 6);
            t.setEllipsize(TextUtils.TruncateAt.END);
        }
        JSONObject sim = q.optJSONObject("sim_task");
        if (sim != null) V.addStart(tags, V.tag(c, "自动判分", Tone.SUCCESS), 6);

        int lv = q.optInt("difficulty", 3);
        int[] tone = p.tone(Bank.levelTone(lv));
        level.setText(String.valueOf(lv));
        level.setTextColor(Bank.levelTone(lv) == Tone.NEUTRAL ? p.text2 : tone[0]);
        level.setBackground(V.round(c, tone[1], 11));

        stem.setText(Json.str(q, "stem"));
        List<String> opts = new ArrayList<>();
        for (JSONObject o : Json.list(Json.arr(q, "options"))) {
            opts.add(Json.str(o, "label") + "." + Json.str(o, "content"));
        }
        if ("判断题".equals(type)) opts.clear();
        if (sim != null) opts.add("仿真：" + Bank.kindName(Json.str(sim, "kind")) + " · " + Json.str(sim, "title"));
        options.setText(TextUtils.join("　", opts));
        options.setVisibility(opts.isEmpty() ? GONE : VISIBLE);

        String img = Json.str(q, "image_url");
        thumb.setVisibility(img.isEmpty() ? GONE : VISIBLE);
        if (!img.isEmpty()) Images.load(thumb, img, Ui.dp(c, 112));

        String code = Json.str(q, "code");
        String ans = Json.str(q, "answer").replace('\n', ' ');
        StringBuilder m = new StringBuilder(code.isEmpty() ? "#" + q.optLong("id") : code);
        m.append(" · ").append(Json.str(q, "source"));
        if (!ans.isEmpty()) m.append(" · 答案 ").append(ans);
        meta.setText(m);

        boolean pinned = Json.bool(q, "is_pinned");
        android.graphics.drawable.Drawable d = c.getDrawable(R.drawable.ic_star);
        if (d != null) {
            d = d.mutate();
            int s = Ui.dp(c, 18);
            d.setBounds(0, 0, s, s);
            d.setTint(pinned ? p.warning : p.border);
        }
        pin.setCompoundDrawablesRelative(d, null, null, null);
        pin.setTextColor(pinned ? p.warning : p.text3);
        pin.setText(pinned ? "必出" : "设必出");
        pin.setContentDescription(pinned ? "取消必出" : "设为必出");
    }

    /** 列表里的视图（ItemList.Binder 用） */
    static View create(Context c, PinToggle onPin) {
        return new QuestionCard(c, onPin);
    }
}
