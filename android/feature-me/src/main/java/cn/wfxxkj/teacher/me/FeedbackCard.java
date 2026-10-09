package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 一条反馈的卡片。三种样子：
 * 公开区（回复、点赞、管理员的撤下/删除）、待审核（联系方式、通过/拒绝/删除）、已拒绝（原因、改为通过/删除）。
 */
final class FeedbackCard extends LinearLayout {

    static final int PUBLIC = 0;
    static final int PENDING = 1;
    static final int REJECTED = 2;

    /** 卡片上的按钮回调到页面 */
    interface Handler {
        void like(JSONObject f);

        void reply(JSONObject f);

        void withdraw(JSONObject f, JSONObject reply);

        void review(JSONObject f, String status);

        void delete(JSONObject f);

        void more(JSONObject f);

        void preview(String url);

        boolean isAdmin();

        boolean canWithdraw(JSONObject reply);
    }

    private final Handler h;

    FeedbackCard(Context c, Handler h) {
        super(c);
        this.h = h;
        setOrientation(VERTICAL);
    }

    static Tone toneOf(String category) {
        switch (category) {
            case "建议":
                return Tone.PRIMARY;
            case "问题":
                return Tone.WARNING;
            case "表扬":
                return Tone.SUCCESS;
            default:
                return Tone.NEUTRAL;
        }
    }

    void bind(final JSONObject f, int mode) {
        Context c = getContext();
        Palette p = Palette.of(c);
        removeAllViews();
        GradientDrawable bg = V.stroke(c, p.surface, p.border, 16);
        if (mode == REJECTED) bg.setStroke(Ui.dp(c, 1), p.border, Ui.dp(c, 5), Ui.dp(c, 4));
        setBackground(bg);
        V.pad(this, 16, 12, 8, 12);

        // 头：称呼 · 类型 · 时间 …… [⋮]
        LinearLayout meta = V.hbox(c);
        LinearLayout who = V.vbox(c);
        LinearLayout line1 = V.hbox(c);
        TextView author = V.oneLine(V.text(c, Json.str(f, "author"), V.H3));
        author.setTextSize(15);
        author.setMaxWidth(Ui.dp(c, 140));
        line1.addView(author);
        String cat = Json.str(f, "category");
        V.addStart(line1, V.tag(c, cat, mode == REJECTED ? Tone.NEUTRAL : toneOf(cat)), 8);
        if (mode == PENDING) V.addStart(line1, V.tag(c, "待审核", Tone.WARNING), 6);
        who.addView(line1);
        String sub = MeUi.time(Json.str(f, "created_at"));
        if (mode != PUBLIC && !Json.str(f, "contact").isEmpty()) sub += "  ·  联系方式 " + Json.str(f, "contact");
        TextView subT = V.text(c, sub, V.CAPTION);
        V.addTop(who, subT, 2);
        meta.addView(who, V.fill());
        if (mode == PUBLIC && h.isAdmin()) {
            meta.addView(V.iconButton(c, R.drawable.ic_more_vert, "更多", v -> h.more(f)));
        }
        addView(meta);

        if (mode == REJECTED && !Json.str(f, "review_note").isEmpty()) {
            TextView note = V.text(c, "拒绝原因：" + Json.str(f, "review_note"), V.CAPTION);
            note.setTextColor(p.warning);
            V.pad(note, 0, 4, 8, 0);
            addView(note);
        }

        // 正文
        TextView content = V.text(c, Json.str(f, "content"), V.BODY);
        content.setLineSpacing(0, 1.4f);
        content.setTextIsSelectable(false);
        if (mode == REJECTED) content.setTextColor(p.text2);
        V.pad(content, 0, 8, 8, 0);
        addView(content);

        // 配图
        List<String> images = Json.strings(Json.arr(f, "images"));
        if (!images.isEmpty()) {
            FlowBox pics = new FlowBox(c, 8, 8);
            V.pad(pics, 0, 10, 8, 0);
            for (final String url : images) pics.addView(thumb(c, url, 104, 78, v -> h.preview(url)));
            addView(pics);
        }

        if (mode == PUBLIC) {
            bindReplies(c, f);
            bindBar(c, f);
        } else {
            LinearLayout bar = V.hbox(c);
            V.pad(bar, 0, 10, 8, 0);
            if (mode == PENDING) {
                bar.addView(V.button(c, R.drawable.ic_check, "通过", V.BTN_TONAL, v -> h.review(f, "approved")));
                V.addStart(bar, V.button(c, "拒绝", V.BTN_OUTLINE, v -> h.review(f, "rejected")), 8);
            } else {
                bar.addView(V.button(c, R.drawable.ic_restart_alt, "改为通过", V.BTN_TONAL, v -> h.review(f, "approved")));
            }
            bar.addView(V.spring(c));
            bar.addView(V.button(c, "删除", V.BTN_TEXT, v -> h.delete(f)));
            ((TextView) bar.getChildAt(bar.getChildCount() - 1)).setTextColor(p.danger);
            addView(bar);
        }
    }

    private void bindReplies(Context c, JSONObject f) {
        JSONArray replies = Json.arr(f, "replies");
        if (replies.length() == 0) return;
        Palette p = Palette.of(c);
        LinearLayout box = V.vbox(c);
        V.pad(box, 0, 10, 8, 0);
        for (final JSONObject r : Json.list(replies)) {
            LinearLayout one = V.vbox(c);
            GradientDrawable bg = V.round(c, p.surfaceAlt, 10);
            one.setBackground(bg);
            V.pad(one, 12, 8, 4, 8);
            LinearLayout top = V.hbox(c);
            boolean admin = Json.bool(r, "is_admin");
            TextView who = V.oneLine(V.text(c, Json.str(r, "author") + (admin ? "（管理员）" : ""), V.LABEL));
            if (admin) who.setTextColor(p.primary);
            top.addView(who);
            TextView time = V.oneLine(V.text(c, MeUi.time(Json.str(r, "created_at")), V.CAPTION));
            V.addStart(top, time, 8);
            top.addView(V.spring(c));
            if (h.canWithdraw(r)) {
                TextView w = V.button(c, "撤回", V.BTN_TEXT, v -> h.withdraw(f, r));
                w.setTextColor(p.text3);
                w.setTextSize(13);
                w.setMinHeight(Ui.dp(c, 28));
                top.addView(w);
            }
            one.addView(top);
            TextView text = V.text(c, Json.str(r, "content"), V.BODY2);
            V.pad(text, 0, 2, 8, 0);
            one.addView(text);
            LinearLayout.LayoutParams lp = V.matchWrap();
            if (box.getChildCount() > 0) lp.topMargin = Ui.dp(c, 6);
            box.addView(one, lp);
        }
        addView(box);
    }

    /** 点赞 + 回复 */
    private void bindBar(Context c, final JSONObject f) {
        Palette p = Palette.of(c);
        LinearLayout bar = V.hbox(c);
        V.pad(bar, 0, 10, 8, 0);
        boolean liked = Json.bool(f, "liked_by_me");
        int n = Json.num(f, "like_count");
        TextView like = V.chip(c, (n > 0 ? String.valueOf(n) : "赞同"), liked, v -> h.like(f));
        android.graphics.drawable.Drawable d = c.getDrawable(R.drawable.ic_thumb_up);
        if (d != null) {
            d = d.mutate();
            int s = Ui.dp(c, 16);
            d.setBounds(0, 0, s, s);
            d.setTint(liked ? p.primary : p.text2);
            like.setCompoundDrawablesRelative(d, null, null, null);
            like.setCompoundDrawablePadding(Ui.dp(c, 6));
        }
        like.setContentDescription(liked ? "取消点赞" : "点赞");
        bar.addView(like);
        TextView reply = V.button(c, R.drawable.ic_reply, "回复", V.BTN_TEXT, v -> h.reply(f));
        V.addStart(bar, reply, 8);
        if (Json.arr(f, "replies").length() > 0) {
            bar.addView(V.spring(c));
            TextView cnt = V.text(c, Json.arr(f, "replies").length() + " 条回复", V.CAPTION);
            V.pad(cnt, 0, 0, 8, 0);
            bar.addView(cnt);
        }
        addView(bar);
    }

    /** 圆角缩略图 */
    static View thumb(Context c, String url, int wDp, int hDp, OnClickListener l) {
        ImageView iv = new MeImages.Box(c, Ui.dp(c, wDp), Ui.dp(c, hDp));
        iv.setScaleType(ImageView.ScaleType.CENTER_CROP);
        Palette p = Palette.of(c);
        iv.setBackground(V.stroke(c, p.surfaceAlt, p.border, 10));
        iv.setClipToOutline(true);
        iv.setLayoutParams(new LayoutParams(Ui.dp(c, wDp), Ui.dp(c, hDp)));
        iv.setContentDescription("配图");
        MeImages.load(iv, url, Ui.dp(c, wDp * 2));
        if (l != null) iv.setOnClickListener(l);
        return iv;
    }
}
