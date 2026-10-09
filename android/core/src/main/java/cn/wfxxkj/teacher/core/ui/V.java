package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import cn.wfxxkj.teacher.core.R;

/**
 * 用代码搭界面的小工具。各功能模块的界面都用它搭，长得统一、改一处全 APP 跟着变。
 *
 * <pre>
 * LinearLayout card = V.card(ctx);
 * card.addView(V.text(ctx, "期中考试", V.H3));
 * card.addView(V.text(ctx, "共 42 人交卷", V.BODY2));
 * card.addView(V.button(ctx, "查看成绩", V.BTN_TONAL, v -&gt; open()));
 * </pre>
 */
public final class V {
    private V() {}

    // ---------- 文字样式 ----------

    /** 大数字、大标题 */
    public static final int DISPLAY = 0;
    /** 页面标题 */
    public static final int H1 = 1;
    /** 区块标题 */
    public static final int H2 = 2;
    /** 卡片标题、列表主文字 */
    public static final int H3 = 3;
    /** 正文 */
    public static final int BODY = 4;
    /** 次要正文（灰一点） */
    public static final int BODY2 = 5;
    /** 小字说明（最淡） */
    public static final int CAPTION = 6;
    /** 表单标签、分组小标题 */
    public static final int LABEL = 7;

    public static TextView text(Context c, CharSequence s) {
        return text(c, s, BODY);
    }

    public static TextView text(Context c, CharSequence s, int style) {
        TextView t = new TextView(c);
        t.setText(s);
        style(t, style);
        return t;
    }

    public static void style(TextView t, int style) {
        Palette p = Palette.of(t.getContext());
        float size;
        int color;
        boolean bold = false;
        switch (style) {
            case DISPLAY:
                size = 28;
                color = p.text;
                bold = true;
                break;
            case H1:
                size = 22;
                color = p.text;
                bold = true;
                break;
            case H2:
                size = 18;
                color = p.text;
                bold = true;
                break;
            case H3:
                size = 16;
                color = p.text;
                bold = true;
                break;
            case BODY2:
                size = 14;
                color = p.text2;
                break;
            case CAPTION:
                size = 12;
                color = p.text3;
                break;
            case LABEL:
                size = 13;
                color = p.text2;
                bold = true;
                break;
            default:
                size = 15;
                color = p.text;
        }
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, size);
        t.setTextColor(color);
        t.setTypeface(bold ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        t.setLineSpacing(0, style == BODY || style == BODY2 ? 1.25f : 1.1f);
        t.setIncludeFontPadding(true);
    }

    /** 单行，放不下打省略号 */
    public static TextView oneLine(TextView t) {
        t.setSingleLine(true);
        t.setEllipsize(TextUtils.TruncateAt.END);
        return t;
    }

    public static TextView lines(TextView t, int max) {
        t.setMaxLines(max);
        t.setEllipsize(TextUtils.TruncateAt.END);
        return t;
    }

    public static TextView color(TextView t, int color) {
        t.setTextColor(color);
        return t;
    }

    public static TextView bold(TextView t) {
        t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    // ---------- 布局 ----------

    public static LinearLayout vbox(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    /** 横排，竖直居中 */
    public static LinearLayout hbox(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    public static LinearLayout.LayoutParams lp(int w, int h) {
        return new LinearLayout.LayoutParams(w, h);
    }

    public static final int MATCH = ViewGroup.LayoutParams.MATCH_PARENT;
    public static final int WRAP = ViewGroup.LayoutParams.WRAP_CONTENT;

    /** 横排里占满剩余宽度 */
    public static LinearLayout.LayoutParams fill() {
        return new LinearLayout.LayoutParams(0, WRAP, 1f);
    }

    public static LinearLayout.LayoutParams weight(float w) {
        return new LinearLayout.LayoutParams(0, WRAP, w);
    }

    public static LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(MATCH, WRAP);
    }

    /** 加子视图并设外边距（dp）：上、下 */
    public static <T extends View> T add(ViewGroup parent, T child) {
        parent.addView(child);
        return child;
    }

    public static <T extends View> T add(ViewGroup parent, T child, ViewGroup.LayoutParams lp) {
        parent.addView(child, lp);
        return child;
    }

    /** 竖排里加一个子视图，上方留 topDp 间距 */
    public static <T extends View> T addTop(LinearLayout parent, T child, int topDp) {
        LinearLayout.LayoutParams lp = matchWrap();
        lp.topMargin = Ui.dp(parent.getContext(), topDp);
        parent.addView(child, lp);
        return child;
    }

    /** 横排里加一个子视图，左边留 startDp 间距 */
    public static <T extends View> T addStart(LinearLayout parent, T child, int startDp) {
        LinearLayout.LayoutParams lp = lp(WRAP, WRAP);
        lp.setMarginStart(Ui.dp(parent.getContext(), startDp));
        parent.addView(child, lp);
        return child;
    }

    public static <T extends View> T pad(T v, int allDp) {
        int p = Ui.dp(v.getContext(), allDp);
        v.setPadding(p, p, p, p);
        return v;
    }

    public static <T extends View> T pad(T v, int hDp, int vDp) {
        int h = Ui.dp(v.getContext(), hDp), w = Ui.dp(v.getContext(), vDp);
        v.setPadding(h, w, h, w);
        return v;
    }

    public static <T extends View> T pad(T v, int l, int t, int r, int b) {
        Context c = v.getContext();
        v.setPadding(Ui.dp(c, l), Ui.dp(c, t), Ui.dp(c, r), Ui.dp(c, b));
        return v;
    }

    public static <T extends View> T margins(T v, int l, int t, int r, int b) {
        Context c = v.getContext();
        ViewGroup.LayoutParams lp = v.getLayoutParams();
        ViewGroup.MarginLayoutParams m = lp instanceof ViewGroup.MarginLayoutParams
                ? (ViewGroup.MarginLayoutParams) lp : new LinearLayout.LayoutParams(MATCH, WRAP);
        m.setMargins(Ui.dp(c, l), Ui.dp(c, t), Ui.dp(c, r), Ui.dp(c, b));
        v.setLayoutParams(m);
        return v;
    }

    public static View space(Context c, int dp) {
        View v = new View(c);
        v.setLayoutParams(new LinearLayout.LayoutParams(Ui.dp(c, dp), Ui.dp(c, dp)));
        return v;
    }

    /** 横排里把后面的东西推到最右边 */
    public static View spring(Context c) {
        View v = new View(c);
        v.setLayoutParams(new LinearLayout.LayoutParams(0, 1, 1f));
        return v;
    }

    public static View divider(Context c) {
        View v = new View(c);
        v.setBackgroundColor(Palette.of(c).divider);
        v.setLayoutParams(new LinearLayout.LayoutParams(MATCH, Math.max(1, Ui.dp(c, 0.8f))));
        return v;
    }

    /** 可滚动的竖排页面。返回 ScrollView，内容放在 {@code (LinearLayout) scroll.getChildAt(0)} */
    public static ScrollView scroll(Context c, View content) {
        ScrollView s = new ScrollView(c);
        s.setFillViewport(true);
        s.setClipToPadding(false);
        s.addView(content, new FrameLayout.LayoutParams(MATCH, WRAP));
        return s;
    }

    /**
     * 页面内容容器：两边留白、宽屏时限宽居中（表单、详情页在平板上不会拉成一长条）。
     * 返回的 LinearLayout 往里加内容；把 {@link #page} 的结果放进 ScrollView。
     */
    public static LinearLayout page(Context c) {
        LinearLayout l = new MaxWidthLinearLayout(c, Ui.dp(c, 760));
        l.setOrientation(LinearLayout.VERTICAL);
        int h = Ui.dp(c, Ui.wide(c) ? 24 : 16);
        l.setPadding(h, Ui.dp(c, 12), h, Ui.dp(c, 96));
        return l;
    }

    // ---------- 背景 ----------

    public static GradientDrawable round(int color, float radiusPx) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(radiusPx);
        return d;
    }

    public static GradientDrawable round(Context c, int color, int radiusDp) {
        return round(color, Ui.dpf(c, radiusDp));
    }

    public static GradientDrawable stroke(Context c, int fill, int strokeColor, int radiusDp) {
        GradientDrawable d = round(c, fill, radiusDp);
        d.setStroke(Math.max(1, Ui.dp(c, 1)), strokeColor);
        return d;
    }

    /** 带水波纹的背景 */
    public static Drawable ripple(Context c, Drawable content, int radiusDp) {
        GradientDrawable mask = round(c, 0xFFFFFFFF, radiusDp);
        return new RippleDrawable(ColorStateList.valueOf(Palette.of(c).ripple), content, mask);
    }

    /** 让任意视图可点，带水波纹 */
    public static <T extends View> T clickable(T v, int radiusDp, View.OnClickListener l) {
        Context c = v.getContext();
        Drawable bg = v.getBackground();
        v.setBackground(ripple(c, bg, radiusDp));
        v.setClickable(true);
        v.setFocusable(true);
        v.setOnClickListener(l);
        return v;
    }

    // ---------- 卡片 ----------

    /** 白底圆角卡片（竖排，内边距 16dp） */
    public static LinearLayout card(Context c) {
        LinearLayout l = vbox(c);
        Palette p = Palette.of(c);
        l.setBackground(stroke(c, p.surface, p.border, 16));
        pad(l, 16);
        return l;
    }

    /** 可点的卡片 */
    public static LinearLayout card(Context c, View.OnClickListener l) {
        LinearLayout card = card(c);
        clickable(card, 16, l);
        return card;
    }

    /** 区块标题：左边粗体标题，右边可放一个文字按钮 */
    public static LinearLayout section(Context c, String title, String action, View.OnClickListener onAction) {
        LinearLayout row = hbox(c);
        row.addView(text(c, title, H3), fill());
        if (action != null) row.addView(button(c, action, BTN_TEXT, onAction));
        pad(row, 4, 8, 0, 8);
        return row;
    }

    // ---------- 按钮 ----------

    public static final int BTN_PRIMARY = 0;
    /** 浅色底的次要按钮 */
    public static final int BTN_TONAL = 1;
    public static final int BTN_OUTLINE = 2;
    public static final int BTN_TEXT = 3;
    public static final int BTN_DANGER = 4;
    /** 浅红底的危险操作 */
    public static final int BTN_DANGER_TONAL = 5;

    public static TextView button(Context c, CharSequence label, int kind, View.OnClickListener l) {
        TextView b = new TextView(c);
        b.setText(label);
        b.setGravity(Gravity.CENTER);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setSingleLine(true);
        b.setMinHeight(Ui.dp(c, kind == BTN_TEXT ? 36 : 44));
        b.setMinWidth(Ui.dp(c, kind == BTN_TEXT ? 48 : 72));
        pad(b, kind == BTN_TEXT ? 10 : 18, 0, kind == BTN_TEXT ? 10 : 18, 0);
        Palette p = Palette.of(c);
        int fg, bg = 0, stroke = 0;
        switch (kind) {
            case BTN_PRIMARY:
                fg = p.onPrimary;
                bg = p.primary;
                break;
            case BTN_TONAL:
                fg = p.primary;
                bg = p.primarySoft;
                break;
            case BTN_OUTLINE:
                fg = p.text;
                bg = p.surface;
                stroke = p.border;
                break;
            case BTN_DANGER:
                fg = 0xFFFFFFFF;
                bg = p.danger;
                break;
            case BTN_DANGER_TONAL:
                fg = p.danger;
                bg = p.dangerSoft;
                break;
            default:
                fg = p.primary;
        }
        b.setTextColor(fg);
        GradientDrawable d = round(c, bg, 12);
        if (stroke != 0) d.setStroke(Ui.dp(c, 1), stroke);
        b.setBackground(ripple(c, d, 12));
        b.setOnClickListener(l);
        b.setClickable(true);
        b.setFocusable(true);
        return b;
    }

    /** 按钮的禁用/启用（变淡、不可点） */
    public static void enable(View v, boolean on) {
        v.setEnabled(on);
        v.setAlpha(on ? 1f : 0.45f);
    }

    /** 带图标的按钮（图标在文字左边） */
    public static TextView button(Context c, int iconRes, CharSequence label, int kind, View.OnClickListener l) {
        TextView b = button(c, label, kind, l);
        Drawable d = c.getDrawable(iconRes);
        if (d != null) {
            d = d.mutate();
            int s = Ui.dp(c, 18);
            d.setBounds(0, 0, s, s);
            d.setTint(b.getCurrentTextColor());
            b.setCompoundDrawablesRelative(d, null, null, null);
            b.setCompoundDrawablePadding(Ui.dp(c, 6));
        }
        return b;
    }

    /** 圆形图标按钮（48dp 触控区） */
    public static ImageView iconButton(Context c, int iconRes, String desc, View.OnClickListener l) {
        ImageView iv = icon(c, iconRes, Palette.of(c).text2, 24);
        int s = Ui.dp(c, 44);
        iv.setLayoutParams(new LinearLayout.LayoutParams(s, s));
        iv.setScaleType(ImageView.ScaleType.CENTER);
        iv.setContentDescription(desc);
        iv.setBackground(new RippleDrawable(ColorStateList.valueOf(Palette.of(c).ripple), null, null));
        iv.setOnClickListener(l);
        iv.setClickable(true);
        iv.setFocusable(true);
        return iv;
    }

    public static ImageView icon(Context c, int iconRes, int color, int sizeDp) {
        ImageView iv = new ImageView(c);
        iv.setImageResource(iconRes);
        iv.setImageTintList(ColorStateList.valueOf(color));
        int s = Ui.dp(c, sizeDp);
        iv.setLayoutParams(new LinearLayout.LayoutParams(s, s));
        iv.setScaleType(ImageView.ScaleType.FIT_CENTER);
        return iv;
    }

    /** 圆角方块里的图标（列表、设置项前面那种） */
    public static FrameLayout iconTile(Context c, int iconRes, Tone tone) {
        int[] t = Palette.of(c).tone(tone);
        FrameLayout f = new FrameLayout(c);
        f.setBackground(round(c, t[1], 12));
        ImageView iv = icon(c, iconRes, t[0], 22);
        f.addView(iv, new FrameLayout.LayoutParams(Ui.dp(c, 22), Ui.dp(c, 22), Gravity.CENTER));
        int s = Ui.dp(c, 40);
        f.setLayoutParams(new LinearLayout.LayoutParams(s, s));
        return f;
    }

    // ---------- 标签、徽标 ----------

    /** 小标签：「已发布」「单选题」这类 */
    public static TextView tag(Context c, CharSequence s, Tone tone) {
        int[] t = Palette.of(c).tone(tone);
        TextView v = new TextView(c);
        v.setText(s);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        v.setTextColor(t[0]);
        v.setTypeface(Typeface.DEFAULT_BOLD);
        v.setSingleLine(true);
        v.setBackground(round(c, t[1], 6));
        pad(v, 7, 2, 7, 2);
        return v;
    }

    /** 红点数字徽标 */
    public static TextView badge(Context c, int count) {
        TextView v = new TextView(c);
        v.setText(count > 99 ? "99+" : String.valueOf(count));
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        v.setTextColor(0xFFFFFFFF);
        v.setTypeface(Typeface.DEFAULT_BOLD);
        v.setGravity(Gravity.CENTER);
        v.setMinWidth(Ui.dp(c, 18));
        v.setMinHeight(Ui.dp(c, 18));
        v.setBackground(round(c, Palette.of(c).danger, 9));
        pad(v, 5, 0, 5, 0);
        return v;
    }

    /** 可选中的小圆角按钮（筛选条件） */
    public static TextView chip(Context c, CharSequence s, boolean selected, View.OnClickListener l) {
        TextView v = new TextView(c);
        v.setText(s);
        v.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        v.setSingleLine(true);
        v.setGravity(Gravity.CENTER);
        v.setMinHeight(Ui.dp(c, 34));
        pad(v, 14, 0, 14, 0);
        setChip(v, selected);
        v.setOnClickListener(l);
        return v;
    }

    public static void setChip(TextView v, boolean selected) {
        Context c = v.getContext();
        Palette p = Palette.of(c);
        v.setSelected(selected);
        v.setTextColor(selected ? p.primary : p.text2);
        v.setTypeface(selected ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        GradientDrawable d = round(c, selected ? p.primarySoft : p.surface, 17);
        d.setStroke(Ui.dp(c, 1), selected ? p.primarySoft : p.border);
        v.setBackground(ripple(c, d, 17));
    }

    /** 圆形头像（取名字最后一个字） */
    public static TextView avatar(Context c, String name, int sizeDp) {
        TextView v = new TextView(c);
        String n = name == null ? "" : name.trim();
        v.setText(n.isEmpty() ? "?" : n.substring(n.length() - 1));
        v.setGravity(Gravity.CENTER);
        v.setTextColor(0xFFFFFFFF);
        v.setTypeface(Typeface.DEFAULT_BOLD);
        v.setTextSize(TypedValue.COMPLEX_UNIT_PX, Ui.dp(c, sizeDp) * 0.42f);
        GradientDrawable d = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF6D85F7, 0xFF3F5BD8});
        d.setShape(GradientDrawable.OVAL);
        v.setBackground(d);
        int s = Ui.dp(c, sizeDp);
        v.setLayoutParams(new LinearLayout.LayoutParams(s, s));
        return v;
    }

    // ---------- 常用组合 ----------

    /**
     * 设置项式的一行：[图标] 标题/副标题 ……… 右侧文字 &gt;
     * icon 传 0 不显示；onClick 为 null 时不显示箭头。
     */
    public static LinearLayout row(Context c, int icon, Tone tone, CharSequence title, CharSequence sub,
                                   CharSequence trailing, View.OnClickListener onClick) {
        LinearLayout row = hbox(c);
        pad(row, 16, 12, 12, 12);
        row.setMinimumHeight(Ui.dp(c, 56));
        if (icon != 0) {
            row.addView(iconTile(c, icon, tone));
            row.addView(space(c, 12));
        }
        LinearLayout texts = vbox(c);
        texts.addView(oneLine(text(c, title, BODY)));
        if (!TextUtils.isEmpty(sub)) texts.addView(lines(text(c, sub, CAPTION), 2));
        row.addView(texts, fill());
        if (!TextUtils.isEmpty(trailing)) {
            TextView t = oneLine(text(c, trailing, BODY2));
            t.setMaxWidth(Ui.dp(c, 180));
            addStart(row, t, 8);
        }
        if (onClick != null) {
            row.addView(icon(c, R.drawable.ic_chevron_right, Palette.of(c).text3, 20));
            clickable(row, 0, onClick);
        }
        return row;
    }

    /** 「键：值」一行，详情页用 */
    public static LinearLayout kv(Context c, CharSequence key, CharSequence value) {
        LinearLayout row = hbox(c);
        row.setGravity(Gravity.TOP);
        pad(row, 0, 6, 0, 6);
        TextView k = text(c, key, BODY2);
        k.setMinWidth(Ui.dp(c, 84));
        row.addView(k);
        TextView v = text(c, TextUtils.isEmpty(value) ? "—" : value, BODY);
        v.setTextIsSelectable(true);
        row.addView(v, fill());
        return row;
    }

    /** 统计小卡：大数字 + 说明 */
    public static LinearLayout stat(Context c, CharSequence number, CharSequence label, Tone tone) {
        LinearLayout box = vbox(c);
        int[] t = Palette.of(c).tone(tone);
        box.setBackground(round(c, t[1], 14));
        pad(box, 14, 12, 14, 12);
        TextView n = text(c, number, H1);
        n.setTextColor(tone == Tone.NEUTRAL ? Palette.of(c).text : t[0]);
        box.addView(oneLine(n));
        box.addView(oneLine(text(c, label, CAPTION)));
        return box;
    }

    /** 浅色提示条（说明、警告） */
    public static TextView notice(Context c, CharSequence s, Tone tone) {
        int[] t = Palette.of(c).tone(tone);
        TextView v = text(c, s, BODY2);
        v.setTextColor(tone == Tone.NEUTRAL ? Palette.of(c).text2 : t[0]);
        v.setBackground(round(c, t[1], 12));
        pad(v, 14, 10, 14, 10);
        return v;
    }
}
