package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.session.Prefs;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 设置（APP 专有）：深浅色（跟随系统 / 浅色 / 深色，对应网页顶栏的深色切换），清除缓存。
 */
public class SettingsScreen extends Screen {

    private TextView cacheText;

    @Override
    public String title() {
        return "设置";
    }

    @Override
    protected View onCreateView(Context c) {
        LinearLayout page = V.page(c);
        int mode = session().prefs().themeMode();

        page.addView(MeUi.groupTitle(c, "外观"));
        page.addView(MeUi.group(c,
                themeRow(c, R.drawable.ic_settings, "跟随系统", "和手机的深色模式保持一致", Prefs.THEME_SYSTEM, mode),
                themeRow(c, R.drawable.ic_light_mode, "浅色", null, Prefs.THEME_LIGHT, mode),
                themeRow(c, R.drawable.ic_dark_mode, "深色", "晚上用更护眼", Prefs.THEME_DARK, mode)), V.matchWrap());

        page.addView(MeUi.groupTitle(c, "存储"));
        LinearLayout cache = V.row(c, R.drawable.ic_delete, Tone.WARNING, "清除缓存",
                "导出、下载留下的临时文件，清掉不影响任何数据", null, v -> clearCache());
        cacheText = V.oneLine(V.text(c, "计算中…", V.BODY2));
        MeUi.putTrailing(cache, cacheText);
        page.addView(MeUi.group(c, cache), V.matchWrap());

        ScrollView sv = V.scroll(c, page);
        sv.setBackgroundColor(Palette.of(c).page);
        return sv;
    }

    private View themeRow(Context c, int icon, String title, String sub, final int value, int current) {
        LinearLayout row = V.row(c, icon, value == current ? Tone.PRIMARY : Tone.NEUTRAL, title, sub, null,
                v -> setTheme(value));
        // 去掉箭头，选中的打勾
        row.removeViewAt(row.getChildCount() - 1);
        if (value == current) {
            row.addView(V.icon(c, R.drawable.ic_check, Palette.of(c).primary, 22));
        }
        return row;
    }

    private void setTheme(int mode) {
        if (mode == session().prefs().themeMode()) return;
        session().prefs().setThemeMode(mode);
        // 颜色都是建视图时取的，整页重建才能换过来
        activity().recreate();
    }

    @Override
    protected void onFirstShow() {
        measure();
    }

    private void measure() {
        final File dir = ctx().getCacheDir();
        run(() -> sizeOf(dir), n -> cacheText.setText(Fmt.size(n)));
    }

    private void clearCache() {
        final File dir = ctx().getCacheDir();
        Dialogs.confirm(ctx(), "清除缓存", "清掉导出、下载留下的临时文件。已经存到「下载」里的文件不受影响。", "清除", false,
                () -> runBusy("正在清除…", () -> {
                    long before = sizeOf(dir);
                    File[] kids = dir.listFiles();
                    if (kids != null) for (File f : kids) delete(f);
                    return before - sizeOf(dir);
                }, freed -> {
                    toast("已清除 " + Fmt.size(Math.max(0, freed)));
                    measure();
                }));
    }

    private static long sizeOf(File f) {
        if (f == null || !f.exists()) return 0;
        if (f.isFile()) return f.length();
        long n = 0;
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) n += sizeOf(k);
        return n;
    }

    private static void delete(File f) {
        File[] kids = f.isDirectory() ? f.listFiles() : null;
        if (kids != null) for (File k : kids) delete(k);
        //noinspection ResultOfMethodCallIgnored
        f.delete();
    }
}
