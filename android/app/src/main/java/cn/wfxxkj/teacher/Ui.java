package cn.wfxxkj.teacher;

import android.app.Activity;
import android.graphics.Color;
import android.os.Build;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;

/**
 * 全面屏（内容铺到状态栏和导航栏底下）和系统栏留白。
 *
 * 安卓 15 起应用一律全面屏，不处理的话顶部内容会钻到状态栏下面、底部标签栏被手势条挡住。
 * 这里在安卓 10~14 上也开成全面屏，然后统一按系统给的留白把内容往里收，
 * 各版本长得一样，只用维护一套。键盘弹出来时底部留白取键盘高度，输入框不会被盖住。
 */
final class Ui {
    private Ui() {}

    @SuppressWarnings("deprecation")
    static void edgeToEdge(Activity activity, boolean lightBars) {
        Window w = activity.getWindow();
        w.setStatusBarColor(Color.TRANSPARENT);
        w.setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= 29) w.setNavigationBarContrastEnforced(false);
        if (Build.VERSION.SDK_INT >= 30) {
            w.setDecorFitsSystemWindows(false);
        } else {
            w.getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
        setLightBars(activity, lightBars);
    }

    /** lightBars = 浅色背景，状态栏图标用深色 */
    @SuppressWarnings("deprecation")
    static void setLightBars(Activity activity, boolean lightBars) {
        Window w = activity.getWindow();
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

    /** 系统留白：[上, 下, 左, 右]，下 = 导航栏和键盘里高的那个 */
    @SuppressWarnings("deprecation")
    static int[] insets(WindowInsets in) {
        if (Build.VERSION.SDK_INT >= 30) {
            android.graphics.Insets bars = in.getInsets(WindowInsets.Type.systemBars()
                    | WindowInsets.Type.displayCutout());
            android.graphics.Insets ime = in.getInsets(WindowInsets.Type.ime());
            return new int[]{bars.top, Math.max(bars.bottom, ime.bottom), bars.left, bars.right};
        }
        return new int[]{in.getSystemWindowInsetTop(), in.getSystemWindowInsetBottom(),
                in.getSystemWindowInsetLeft(), in.getSystemWindowInsetRight()};
    }

    static int dp(Activity a, float dp) {
        return Math.round(dp * a.getResources().getDisplayMetrics().density);
    }
}
