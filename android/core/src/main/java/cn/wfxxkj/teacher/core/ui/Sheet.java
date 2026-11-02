package cn.wfxxkj.teacher.core.ui;

import android.app.Dialog;
import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import cn.wfxxkj.teacher.core.R;

/**
 * 弹层：手机上从底部滑上来（底部弹层），平板上居中显示的对话框。
 * 选择列表、筛选面板、小表单都用它。
 *
 * <pre>
 * Sheet s = new Sheet(ctx, "新建班级");
 * s.content(form.view());
 * s.buttons("取消", null, "保存", () -&gt; { if (save()) s.dismiss(); });
 * s.show();
 * </pre>
 * 「保存」按钮的回调里自己决定要不要关（表单校验没过就不关）。
 */
public class Sheet {
    private final Context ctx;
    private final Dialog dialog;
    private final LinearLayout panel;
    private final LinearLayout body;
    private final ScrollView scroll;
    private LinearLayout footer;
    private final boolean centered;
    private Runnable onDismiss;

    public Sheet(Context c, CharSequence title) {
        ctx = c;
        centered = Ui.wide(c);
        dialog = new Dialog(c, R.style.Wf_Sheet);
        Palette p = Palette.of(c);

        FrameLayout root = new FrameLayout(c);
        root.setOnClickListener(v -> dismiss());

        panel = V.vbox(c);
        panel.setClickable(true); // 点面板不关
        float r = Ui.dpf(c, 24);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(p.surface);
        bg.setCornerRadii(centered ? new float[]{r, r, r, r, r, r, r, r} : new float[]{r, r, r, r, 0, 0, 0, 0});
        panel.setBackground(bg);
        panel.setClipToOutline(true);

        if (!centered) {
            View grip = new View(c);
            grip.setBackground(V.round(c, p.border, 3));
            LinearLayout.LayoutParams glp = new LinearLayout.LayoutParams(Ui.dp(c, 36), Ui.dp(c, 4));
            glp.gravity = Gravity.CENTER_HORIZONTAL;
            glp.topMargin = Ui.dp(c, 10);
            panel.addView(grip, glp);
        }
        if (title != null) {
            TextView t = V.text(c, title, V.H2);
            V.pad(t, 20, centered ? 20 : 12, 20, 8);
            panel.addView(t);
        }
        body = V.vbox(c);
        V.pad(body, 20, 4, 20, 12);
        scroll = new ScrollView(c);
        scroll.addView(body);
        panel.addView(scroll, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));

        int maxW = Ui.dp(c, 560);
        FrameLayout.LayoutParams plp = new FrameLayout.LayoutParams(V.MATCH, V.WRAP,
                centered ? Gravity.CENTER : Gravity.BOTTOM);
        root.addView(panel, plp);
        root.setOnApplyWindowInsetsListener((v, in) -> {
            int[] i = Ui.insets(in);
            int w = v.getWidth();
            int side = centered && w > maxW ? (w - maxW) / 2 : 0;
            FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) panel.getLayoutParams();
            lp.leftMargin = side + i[2];
            lp.rightMargin = side + i[3];
            lp.topMargin = i[0] + Ui.dp(c, centered ? 24 : 48);
            lp.bottomMargin = centered ? i[1] + Ui.dp(c, 24) : 0;
            panel.setLayoutParams(lp);
            panel.setPadding(0, 0, 0, centered ? 0 : i[1]);
            return in;
        });
        root.addOnLayoutChangeListener((v, l, t, rr, b, ol, ot, orr, ob) -> {
            if (rr - l != orr - ol) v.requestApplyInsets();
        });

        dialog.setContentView(root);
        Window w = dialog.getWindow();
        if (w != null) {
            w.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
            // setDecorFitsSystemWindows 是安卓 11（API 30）才有的。APP 最低支持安卓 10，
            // 以前不判断，安卓 10 的手机上一弹底部弹窗就 NoSuchMethodError，APP 直接退回桌面
            if (Build.VERSION.SDK_INT >= 30) {
                w.setDecorFitsSystemWindows(false);
            } else {
                w.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
            }
            w.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        }
        dialog.setOnDismissListener(d -> {
            if (onDismiss != null) onDismiss.run();
        });
        dialog.setOnShowListener(d -> {
            panel.setTranslationY(centered ? Ui.dp(c, 16) : panel.getHeight() + Ui.dp(c, 40));
            panel.setAlpha(centered ? 0f : 1f);
            panel.animate().translationY(0).alpha(1f).setDuration(220)
                    .setInterpolator(new DecelerateInterpolator(1.6f)).start();
        });
    }

    public Context ctx() {
        return ctx;
    }

    /** 放内容（会被包在可滚动区域里） */
    public Sheet content(View v) {
        body.addView(v, new LinearLayout.LayoutParams(V.MATCH, V.WRAP));
        return this;
    }

    /** 内容区本身（往里继续加东西） */
    public LinearLayout body() {
        return body;
    }

    /** 内容区去掉左右内边距（列表铺满） */
    public Sheet flush() {
        body.setPadding(0, body.getPaddingTop(), 0, body.getPaddingBottom());
        return this;
    }

    /**
     * 底部按钮：次要（左）+ 主要（右）。次要按钮回调为 null 时点了直接关；
     * 主要按钮不自动关，回调里自己调 {@link #dismiss()}。任一 label 为 null 则不显示。
     */
    public Sheet buttons(String secondary, Runnable onSecondary, String primary, Runnable onPrimary) {
        return buttons(secondary, onSecondary, primary, onPrimary, false);
    }

    public Sheet buttons(String secondary, Runnable onSecondary, String primary, Runnable onPrimary,
                         boolean dangerPrimary) {
        if (footer == null) {
            footer = V.hbox(ctx);
            V.pad(footer, 20, 8, 20, 16);
            panel.addView(footer);
        }
        footer.removeAllViews();
        if (secondary != null) {
            footer.addView(V.button(ctx, secondary, V.BTN_OUTLINE, v -> {
                if (onSecondary != null) onSecondary.run();
                else dismiss();
            }), V.weight(1));
        }
        if (secondary != null && primary != null) footer.addView(V.space(ctx, 12));
        if (primary != null) {
            footer.addView(V.button(ctx, primary, dangerPrimary ? V.BTN_DANGER : V.BTN_PRIMARY, v -> {
                if (onPrimary != null) onPrimary.run();
            }), V.weight(1));
        }
        return this;
    }

    /** 底部按钮区（想自己摆按钮时用） */
    public LinearLayout footer() {
        if (footer == null) {
            footer = V.hbox(ctx);
            V.pad(footer, 20, 8, 20, 16);
            panel.addView(footer);
        }
        return footer;
    }

    public Sheet onDismiss(Runnable r) {
        onDismiss = r;
        return this;
    }

    /** 点外面、按返回键能不能关（有没保存的输入时可以关掉） */
    public Sheet cancelable(boolean on) {
        dialog.setCancelable(on);
        dialog.setCanceledOnTouchOutside(on);
        return this;
    }

    public Sheet show() {
        dialog.show();
        return this;
    }

    public void dismiss() {
        Ui.hideKeyboard(panel);
        if (dialog.isShowing()) dialog.dismiss();
    }

    public boolean isShowing() {
        return dialog.isShowing();
    }

    public Dialog dialog() {
        return dialog;
    }
}
