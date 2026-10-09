package cn.wfxxkj.teacher.core.nav;

import android.view.View;

/**
 * 顶栏上的一个操作（图标按钮，或收进「更多」菜单里的一项）、浮动按钮、底部操作菜单的一项。
 *
 * <pre>
 * Action.icon(R.drawable.ic_search, "搜索", this::openSearch)
 * Action.menu("导出 Excel", this::export)            // 收进右上角「⋮」
 * Action.menu("删除", this::delete).danger()
 * </pre>
 */
public final class Action {
    public final int icon;
    public final String label;
    public final Runnable run;
    /** true = 收进「更多」菜单，不单独占一个图标位 */
    public boolean overflow;
    public boolean danger;
    public boolean enabled = true;
    /** 图标右上角的数字（0 不显示） */
    public int badge;

    private Action(int icon, String label, Runnable run, boolean overflow) {
        this.icon = icon;
        this.label = label;
        this.run = run;
        this.overflow = overflow;
    }

    public static Action icon(int icon, String label, Runnable run) {
        return new Action(icon, label, run, false);
    }

    public static Action menu(String label, Runnable run) {
        return new Action(0, label, run, true);
    }

    public static Action menu(int icon, String label, Runnable run) {
        return new Action(icon, label, run, true);
    }

    public Action danger() {
        danger = true;
        return this;
    }

    public Action enabled(boolean on) {
        enabled = on;
        return this;
    }

    public Action badge(int n) {
        badge = n;
        return this;
    }

    /** 方便当 View.OnClickListener 用 */
    public View.OnClickListener listener() {
        return v -> {
            if (enabled && run != null) run.run();
        };
    }
}
