package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import cn.wfxxkj.teacher.core.R;

/** 加载中 / 空列表 / 出错（带重试）三种状态的占位 */
public class StateView extends LinearLayout {
    private final ProgressBar progress;
    private View iconView;
    private final TextView title;
    private final TextView sub;
    private final TextView button;
    private Runnable action;

    public StateView(Context c) {
        super(c);
        setOrientation(VERTICAL);
        setGravity(Gravity.CENTER);
        V.pad(this, 32, 48, 32, 48);
        progress = new ProgressBar(c);
        progress.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(Palette.of(c).primary));
        addView(progress, new LayoutParams(Ui.dp(c, 36), Ui.dp(c, 36)));
        iconView = V.iconTile(c, R.drawable.ic_inbox, Tone.NEUTRAL);
        LayoutParams ilp = new LayoutParams(Ui.dp(c, 40), Ui.dp(c, 40));
        iconView.setScaleX(1.3f);
        iconView.setScaleY(1.3f);
        addView(iconView, ilp);
        title = V.text(c, "", V.H3);
        title.setGravity(Gravity.CENTER);
        addView(title, wrapTop(16));
        sub = V.text(c, "", V.BODY2);
        sub.setGravity(Gravity.CENTER);
        addView(sub, wrapTop(6));
        button = V.button(c, "重试", V.BTN_TONAL, v -> {
            if (action != null) action.run();
        });
        addView(button, wrapTop(16));
        loading();
    }

    private LayoutParams wrapTop(int dp) {
        LayoutParams lp = new LayoutParams(V.WRAP, V.WRAP);
        lp.topMargin = Ui.dp(getContext(), dp);
        lp.gravity = Gravity.CENTER_HORIZONTAL;
        return lp;
    }

    public StateView loading() {
        setVisibility(VISIBLE);
        progress.setVisibility(VISIBLE);
        iconView.setVisibility(GONE);
        title.setText("正在加载…");
        title.setVisibility(GONE);
        sub.setVisibility(GONE);
        button.setVisibility(GONE);
        return this;
    }

    public StateView empty(String text, String hint) {
        return show(R.drawable.ic_inbox, Tone.NEUTRAL, text, hint, null, null);
    }

    /** 空状态带一个按钮（例如「新建第一场考试」） */
    public StateView empty(String text, String hint, String actionLabel, Runnable onAction) {
        return show(R.drawable.ic_inbox, Tone.PRIMARY, text, hint, actionLabel, onAction);
    }

    public StateView error(String message, Runnable retry) {
        return show(R.drawable.ic_cloud_off, Tone.DANGER, "加载失败", message, retry == null ? null : "重试", retry);
    }

    public StateView show(int icon, Tone tone, String text, String hint, String actionLabel, Runnable onAction) {
        setVisibility(VISIBLE);
        progress.setVisibility(GONE);
        int at = indexOfChild(iconView);
        removeView(iconView);
        iconView = V.iconTile(getContext(), icon, tone);
        iconView.setScaleX(1.3f);
        iconView.setScaleY(1.3f);
        addView(iconView, at, new LayoutParams(Ui.dp(getContext(), 40), Ui.dp(getContext(), 40)));
        title.setText(text);
        title.setVisibility(VISIBLE);
        sub.setText(hint == null ? "" : hint);
        sub.setVisibility(hint == null ? GONE : VISIBLE);
        action = onAction;
        button.setText(actionLabel == null ? "" : actionLabel);
        button.setVisibility(actionLabel == null ? GONE : VISIBLE);
        return this;
    }

    public void hide() {
        setVisibility(GONE);
    }
}
