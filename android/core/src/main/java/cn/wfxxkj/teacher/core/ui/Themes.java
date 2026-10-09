package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.content.res.Configuration;

import cn.wfxxkj.teacher.core.session.Prefs;
import cn.wfxxkj.teacher.core.session.Session;

/**
 * 深浅色：跟随系统 / 固定浅色 / 固定深色（「我的」里切换）。
 * 在 Activity.attachBaseContext 里调 {@link #wrap}，把用户选的模式套到界面上。
 */
public final class Themes {
    private Themes() {}

    public static Context wrap(Context base) {
        Session.init(base);
        int mode = Session.get().prefs().themeMode();
        if (mode == Prefs.THEME_SYSTEM) return base;
        Configuration cfg = new Configuration(base.getResources().getConfiguration());
        cfg.uiMode = (cfg.uiMode & ~Configuration.UI_MODE_NIGHT_MASK)
                | (mode == Prefs.THEME_DARK ? Configuration.UI_MODE_NIGHT_YES : Configuration.UI_MODE_NIGHT_NO);
        return base.createConfigurationContext(cfg);
    }
}
