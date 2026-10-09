package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.content.res.ColorStateList;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.widget.FrameLayout;
import android.widget.ProgressBar;

/**
 * 下拉刷新。包住一个能滚动的子视图（列表、ScrollView），滚到顶后继续往下拉就刷新。
 * 系统没有自带这个控件（SwipeRefreshLayout 在 AndroidX 里），自己写一个小的。
 */
public class RefreshLayout extends FrameLayout {

    public interface OnRefresh {
        void refresh();
    }

    private View target;
    private final FrameLayout indicator;
    private final ProgressBar spinner;
    private final int touchSlop;
    private final int trigger;
    private final int maxPull;
    private float downY;
    private boolean dragging;
    private boolean refreshing;
    private OnRefresh listener;

    public RefreshLayout(Context c) {
        super(c);
        touchSlop = ViewConfiguration.get(c).getScaledTouchSlop();
        trigger = Ui.dp(c, 72);
        maxPull = Ui.dp(c, 120);
        Palette p = Palette.of(c);
        indicator = new FrameLayout(c);
        indicator.setBackground(V.stroke(c, p.surface, p.border, 20));
        indicator.setElevation(Ui.dpf(c, 3));
        spinner = new ProgressBar(c);
        spinner.setIndeterminateTintList(ColorStateList.valueOf(p.primary));
        int s = Ui.dp(c, 24);
        indicator.addView(spinner, new LayoutParams(s, s, Gravity.CENTER));
        int box = Ui.dp(c, 40);
        LayoutParams lp = new LayoutParams(box, box, Gravity.CENTER_HORIZONTAL | Gravity.TOP);
        addView(indicator, lp);
        indicator.setTranslationY(-box);
        indicator.setAlpha(0f);
    }

    public void setContent(View v) {
        if (target != null) removeView(target);
        target = v;
        addView(v, 0, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT));
    }

    public void setOnRefresh(OnRefresh l) {
        listener = l;
    }

    public boolean isRefreshing() {
        return refreshing;
    }

    /** 刷新结束（或开始）时调 */
    public void setRefreshing(boolean on) {
        refreshing = on;
        if (on) {
            indicator.animate().translationY(Ui.dp(getContext(), 16)).alpha(1f).setDuration(150).start();
        } else {
            indicator.animate().translationY(-indicator.getHeight() - Ui.dp(getContext(), 8))
                    .alpha(0f).setDuration(180).start();
        }
    }

    private boolean canChildScrollUp() {
        return target != null && target.canScrollVertically(-1);
    }

    @Override
    public boolean onInterceptTouchEvent(MotionEvent ev) {
        if (!isEnabled() || refreshing || listener == null || canChildScrollUp()) return false;
        switch (ev.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downY = ev.getY();
                dragging = false;
                break;
            case MotionEvent.ACTION_MOVE:
                if (ev.getY() - downY > touchSlop) {
                    dragging = true;
                    downY = ev.getY();
                }
                break;
            default:
                dragging = false;
        }
        return dragging;
    }

    @Override
    public boolean onTouchEvent(MotionEvent ev) {
        if (!dragging) return super.onTouchEvent(ev);
        switch (ev.getActionMasked()) {
            case MotionEvent.ACTION_MOVE: {
                float dy = Math.max(0, ev.getY() - downY);
                float pull = Math.min(maxPull, dy * 0.5f);
                indicator.setTranslationY(pull - indicator.getHeight() + Ui.dp(getContext(), 8));
                indicator.setAlpha(Math.min(1f, pull / trigger));
                indicator.setRotation(pull * 2);
                return true;
            }
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL: {
                dragging = false;
                float dy = Math.max(0, ev.getY() - downY) * 0.5f;
                indicator.setRotation(0);
                if (dy >= trigger && ev.getActionMasked() == MotionEvent.ACTION_UP) {
                    setRefreshing(true);
                    if (listener != null) listener.refresh();
                } else {
                    setRefreshing(false);
                }
                return true;
            }
            default:
                return true;
        }
    }
}
