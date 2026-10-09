package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.Calendar;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 关于：APP 版本、服务器版本、平台最新版本（网页页脚的「v版本号」，管理员点进更新日志）、
 * 服务器地址、学校与平台名称、页脚文字。
 */
public class AboutScreen extends Screen {

    private TextView brandText, schoolText, footerText, latestText;
    private LinearLayout latestRow;

    /** APP 自己的版本号（BuildConfig 在 app 模块里，这里从系统取） */
    static String appVersion(Context c) {
        try {
            PackageInfo pi = c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
            return pi.versionName == null ? "" : pi.versionName;
        } catch (Exception e) {
            return "";
        }
    }

    static long appVersionCode(Context c) {
        try {
            return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).getLongVersionCode();
        } catch (Exception e) {
            return 0;
        }
    }

    @Override
    public String title() {
        return "关于";
    }

    @Override
    protected View onCreateView(Context c) {
        LinearLayout page = V.page(c);
        Palette p = Palette.of(c);

        // 头部：图标 + 平台名
        LinearLayout hero = V.vbox(c);
        hero.setGravity(Gravity.CENTER_HORIZONTAL);
        V.pad(hero, 0, 20, 0, 12);
        FrameLayout logo = new FrameLayout(c);
        logo.setBackground(V.round(c, p.primary, 22));
        logo.addView(V.icon(c, R.drawable.ic_school, p.onPrimary, 40),
                new FrameLayout.LayoutParams(Ui.dp(c, 40), Ui.dp(c, 40), Gravity.CENTER));
        hero.addView(logo, new LinearLayout.LayoutParams(Ui.dp(c, 76), Ui.dp(c, 76)));
        String brand = session().prefs().brand();
        brandText = V.text(c, TextUtils.isEmpty(brand) ? "信息科技教学平台" : brand, V.H1);
        brandText.setGravity(Gravity.CENTER);
        hero.addView(brandText, wrapCenter(14));
        TextView sub = V.text(c, "教师端 APP  v" + appVersion(c), V.BODY2);
        sub.setGravity(Gravity.CENTER);
        hero.addView(sub, wrapCenter(4));
        schoolText = V.text(c, "", V.CAPTION);
        schoolText.setGravity(Gravity.CENTER);
        schoolText.setVisibility(View.GONE);
        hero.addView(schoolText, wrapCenter(4));
        page.addView(hero, V.matchWrap());

        // 版本
        page.addView(MeUi.groupTitle(c, "版本"));
        String app = appVersion(c);
        long code = appVersionCode(c);
        LinearLayout appRow = V.row(c, R.drawable.ic_info, Tone.PRIMARY, "APP 版本", null,
                app + (code > 0 ? "（" + code + "）" : ""), null);
        String sv = session().prefs().serverVersion();
        LinearLayout serverRow = V.row(c, R.drawable.ic_dns, Tone.INFO, "服务器版本", "登录时服务器报告的版本",
                TextUtils.isEmpty(sv) ? "未知" : sv, null);
        boolean admin = session().isAdmin();
        // 版本号谁都看得到，但只有管理员点得进更新日志（和网页页脚一致）
        latestRow = V.row(c, R.drawable.ic_new_releases, Tone.WARNING, "平台最新版本",
                admin ? "点开看更新日志" : "更新日志里记录的最新版本", null,
                admin ? v -> push(new ChangelogScreen()) : null);
        latestText = V.oneLine(V.text(c, "…", V.BODY2));
        MeUi.putTrailing(latestRow, latestText);
        page.addView(MeUi.group(c, appRow, serverRow, latestRow), V.matchWrap());

        // 服务器
        page.addView(MeUi.groupTitle(c, "服务器"));
        final String server = session().server();
        LinearLayout addr = V.row(c, R.drawable.ic_link, Tone.NEUTRAL, "服务器地址", server, null, v -> {
            Sys.copy(ctx(), "服务器地址", server);
            toast("已复制服务器地址");
        });
        LinearLayout web = V.row(c, R.drawable.ic_open_in_new, Tone.NEUTRAL, "在浏览器打开网页版", "电脑上用的教师端，功能一致",
                null, v -> {
                    if (!Sys.openUrl(ctx(), server + "/js")) toast("没有能打开网页的应用");
                });
        page.addView(MeUi.group(c, addr, web), V.matchWrap());

        footerText = V.text(c, "", V.CAPTION);
        footerText.setGravity(Gravity.CENTER);
        V.addTop(page, footerText, 24);
        renderFooter(null);

        ScrollView scroll = V.scroll(c, page);
        scroll.setBackgroundColor(p.page);
        return scroll;
    }

    private LinearLayout.LayoutParams wrapCenter(int topDp) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        lp.gravity = Gravity.CENTER_HORIZONTAL;
        lp.topMargin = dp(topDp);
        return lp;
    }

    private void renderFooter(JSONObject cfg) {
        JSONObject site = Json.obj(cfg, "site");
        String title = Json.str(site, "title");
        if (title.isEmpty()) title = brandText.getText().toString();
        String s = "© " + Calendar.getInstance().get(Calendar.YEAR) + " " + title;
        String foot = Json.str(site, "footer");
        if (!foot.isEmpty()) s += "\n" + foot;
        footerText.setText(s);
    }

    @Override
    protected void onFirstShow() {
        run(MeApi::changelogLatest, r -> {
            String v = Json.str(r, "version");
            latestText.setText(v.isEmpty() ? "—" : "v" + v + "  " + Json.str(r, "released_on"));
        }, e -> {
            latestText.setText("—");
            return true;
        });
        run(MeApi::siteConfig, cfg -> {
            JSONObject site = Json.obj(cfg, "site");
            String brand = Json.str(site, "brand");
            if (!brand.isEmpty()) brandText.setText(brand);
            String school = Json.str(cfg, "school");
            if (!school.isEmpty()) {
                schoolText.setText(school);
                schoolText.setVisibility(View.VISIBLE);
            }
            renderFooter(cfg);
        }, e -> true);
    }
}
