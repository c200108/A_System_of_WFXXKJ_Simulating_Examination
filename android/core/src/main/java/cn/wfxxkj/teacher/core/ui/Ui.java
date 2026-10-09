package cn.wfxxkj.teacher.core.ui;

import android.app.Activity;
import android.content.Context;
import android.content.res.Configuration;
import android.graphics.Color;
import android.os.Build;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.inputmethod.InputMethodManager;

/**
 * 尺寸换算、屏幕大小分档、全面屏和系统栏留白。
 *
 * <p>屏幕分档按 Material 的窗口尺寸类（看当前窗口的宽度，不看是不是平板）：
 * <ul>
 *   <li>{@link #COMPACT} &lt; 600dp：手机竖屏。底部标签栏，单列。</li>
 *   <li>{@link #MEDIUM} 600–839dp：大屏手机横屏、折叠屏展开、小平板。左侧导航栏，列表两列。</li>
 *   <li>{@link #EXPANDED} ≥ 840dp：平板横屏。左侧导航栏，列表三列，表单居中限宽。</li>
 * </ul>
 * 分屏、自由窗口时窗口变窄也会自动按窄的排。
 */
public final class Ui {
    public static final int COMPACT = 0;
    public static final int MEDIUM = 1;
    public static final int EXPANDED = 2;

    private Ui() {}

    public static int dp(Context c, float dp) {
        return Math.round(dp * c.getResources().getDisplayMetrics().density);
    }

    public static float dpf(Context c, float dp) {
        return dp * c.getResources().getDisplayMetrics().density;
    }

    public static float sp(Context c, float sp) {
        return sp * c.getResources().getDisplayMetrics().scaledDensity;
    }

    /** 当前窗口宽度（dp） */
    public static int widthDp(Context c) {
        return c.getResources().getConfiguration().screenWidthDp;
    }

    public static int sizeClass(Context c) {
        int w = widthDp(c);
        if (w >= 840) return EXPANDED;
        if (w >= 600) return MEDIUM;
        return COMPACT;
    }

    /** 宽屏（≥600dp）：用侧边导航、多列布局 */
    public static boolean wide(Context c) {
        return sizeClass(c) != COMPACT;
    }

    /** 按可用宽度（px）算放几列，每列至少 minCellDp 宽 */
    public static int columns(Context c, int availablePx, int minCellDp, int maxColumns) {
        int cell = dp(c, minCellDp);
        int n = cell <= 0 ? 1 : availablePx / cell;
        return Math.max(1, Math.min(maxColumns, n));
    }

    public static boolean isNight(Context c) {
        return (c.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
    }

    // ---------- 全面屏 ----------

    /**
     * 安卓 15 起应用一律全面屏，不处理的话顶部内容会钻到状态栏下面、底部被手势条挡住。
     * 这里在安卓 10~14 上也开成全面屏，然后统一按系统给的留白把内容往里收，各版本长得一样。
     */
    @SuppressWarnings("deprecation")
    public static void edgeToEdge(Activity activity) {
        Window w = activity.getWindow();
        w.setStatusBarColor(Color.TRANSPARENT);
        w.setNavigationBarColor(Color.TRANSPARENT);
        w.setNavigationBarContrastEnforced(false);
        if (Build.VERSION.SDK_INT >= 30) {
            w.setDecorFitsSystemWindows(false);
        } else {
            w.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
        setLightBars(activity, !isNight(activity));
    }

    /** lightBars = 浅色背景，状态栏图标用深色 */
    @SuppressWarnings("deprecation")
    public static void setLightBars(Activity activity, boolean lightBars) {
        Window w = activity.getWindow();
        w.getDecorView(); // 先把窗口装好，否则 setContentView 之前取不到 InsetsController
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = w.getInsetsController();
            if (c != null) {
                int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(lightBars ? mask : 0, mask);
            }
        } else {
            View d = w.getDecorView();
            int flags = d.getSystemUiVisibility();
            int light = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            d.setSystemUiVisibility(lightBars ? (flags | light) : (flags & ~light));
        }
    }

    /** 系统留白：[上, 下, 左, 右]。下 = 导航栏和键盘里高的那个 */
    @SuppressWarnings("deprecation")
    public static int[] insets(WindowInsets in) {
        if (Build.VERSION.SDK_INT >= 30) {
            android.graphics.Insets bars = in.getInsets(WindowInsets.Type.systemBars()
                    | WindowInsets.Type.displayCutout());
            android.graphics.Insets ime = in.getInsets(WindowInsets.Type.ime());
            return new int[]{bars.top, Math.max(bars.bottom, ime.bottom), bars.left, bars.right};
        }
        return new int[]{in.getSystemWindowInsetTop(), in.getSystemWindowInsetBottom(),
                in.getSystemWindowInsetLeft(), in.getSystemWindowInsetRight()};
    }

    /** 键盘是否弹着（只在安卓 11+ 准确） */
    public static boolean imeVisible(WindowInsets in) {
        return Build.VERSION.SDK_INT >= 30 && in.isVisible(WindowInsets.Type.ime());
    }

    public static void hideKeyboard(View v) {
        if (v == null) return;
        InputMethodManager imm = v.getContext().getSystemService(InputMethodManager.class);
        if (imm != null) imm.hideSoftInputFromWindow(v.getWindowToken(), 0);
    }

    public static void showKeyboard(final View v) {
        if (v == null) return;
        v.requestFocus();
        v.postDelayed(() -> {
            InputMethodManager imm = v.getContext().getSystemService(InputMethodManager.class);
            if (imm != null) imm.showSoftInput(v, InputMethodManager.SHOW_IMPLICIT);
        }, 120);
    }
}
