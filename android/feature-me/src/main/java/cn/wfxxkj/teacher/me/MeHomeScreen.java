package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.session.Prefs;
import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「我的」首页：顶部是当前老师的名片（头像、姓名、角色、服务器和连接状态），
 * 下面分组进入各子页。对应网页顶栏右侧的用户菜单（我的账号、退出登录）、
 * 菜单里的「反馈」「更新日志」「账号」，以及深浅色切换和页脚版本号。
 */
public class MeHomeScreen extends Screen implements Session.Listener {

    private LinearLayout content;
    private LinearLayout userCard;
    private View adminRows;
    private View changelogRow;
    private LinearLayout feedbackRow;
    private TextView pendingTag;
    private TextView themeText;
    private TextView versionText;
    private TextView statusText;
    private View statusDot;

    @Override
    public String title() {
        return "我的";
    }

    @Override
    protected View onCreateView(Context ctx) {
        content = V.page(ctx);
        build();
        session().addListener(this);
        ScrollView sv = V.scroll(ctx, content);
        sv.setBackgroundColor(Palette.of(ctx).page);
        return sv;
    }

    private void build() {
        Context c = ctx();
        content.removeAllViews();

        userCard = V.card(c, v -> push(new ProfileScreen()));
        content.addView(userCard, V.matchWrap());
        renderUser();

        // 账号
        content.addView(MeUi.groupTitle(c, "账号"));
        LinearLayout account = MeUi.group(c,
                V.row(c, R.drawable.ic_person, Tone.PRIMARY, "我的账号", "个人资料、修改密码", null,
                        v -> push(new ProfileScreen())));
        adminRows = V.row(c, R.drawable.ic_manage_accounts, Tone.VIOLET, "账号管理",
                "新增教师、重置密码、分配班级、权限", null, v -> push(new UsersScreen()));
        MeUi.addRow(account, adminRows);
        content.addView(account, V.matchWrap());

        // 交流
        content.addView(MeUi.groupTitle(c, "交流"));
        feedbackRow = V.row(c, R.drawable.ic_feedback, Tone.SUCCESS, "需求反馈", "提建议、看大家的反馈与回复",
                null, v -> push(new FeedbackScreen()));
        pendingTag = V.tag(c, "", Tone.WARNING);
        pendingTag.setVisibility(View.GONE);
        MeUi.putTrailing(feedbackRow, pendingTag);
        changelogRow = V.row(c, R.drawable.ic_new_releases, Tone.WARNING, "更新日志", "平台每一次改动的记录",
                null, v -> push(new ChangelogScreen()));
        content.addView(MeUi.group(c, feedbackRow, changelogRow), V.matchWrap());

        // 应用
        content.addView(MeUi.groupTitle(c, "应用"));
        LinearLayout settings = V.row(c, R.drawable.ic_settings, Tone.NEUTRAL, "设置", "深浅色、清除缓存", null,
                v -> push(new SettingsScreen()));
        themeText = V.oneLine(V.text(c, "", V.BODY2));
        MeUi.putTrailing(settings, themeText);
        LinearLayout about = V.row(c, R.drawable.ic_info, Tone.INFO, "关于", "版本号、服务器信息", null,
                v -> push(new AboutScreen()));
        versionText = V.oneLine(V.text(c, "", V.BODY2));
        MeUi.putTrailing(about, versionText);
        content.addView(MeUi.group(c, settings, about), V.matchWrap());

        TextView logout = V.button(c, R.drawable.ic_logout, "退出登录", V.BTN_DANGER_TONAL, v -> confirmLogout());
        V.addTop(content, logout, 24);

        applyRole();
        renderTrailing();
    }

    /** 名片：头像、姓名 + 角色、登录名、服务器 + 连接状态 */
    private void renderUser() {
        Context c = ctx();
        userCard.removeAllViews();
        JSONObject u = session().user();
        LinearLayout row = V.hbox(c);
        row.addView(V.avatar(c, session().displayName(), 60));
        LinearLayout texts = V.vbox(c);
        V.pad(texts, 14, 0, 0, 0);

        LinearLayout nameRow = V.hbox(c);
        TextView name = V.oneLine(V.text(c, session().displayName(), V.H2));
        // 名字很长时打省略号，不把角色标签挤出去
        name.setMaxWidth(Ui.dp(c, Ui.wide(c) ? 420 : 170));
        nameRow.addView(name);
        V.addStart(nameRow, MeUi.roleTag(c, u, false), 8);
        texts.addView(nameRow);

        String sub = "登录名 " + Json.str(u, "username");
        String gc = Json.str(u, "grade_class");
        if (!gc.isEmpty()) sub += " · " + gc;
        V.addTop(texts, V.oneLine(V.text(c, sub, V.BODY2)), 2);

        LinearLayout server = V.hbox(c);
        statusDot = new View(c);
        int s = Ui.dp(c, 8);
        server.addView(statusDot, new LinearLayout.LayoutParams(s, s));
        statusText = V.oneLine(V.text(c, "", V.CAPTION));
        V.addStart(server, statusText, 6);
        V.addTop(texts, server, 6);
        row.addView(texts, V.fill());
        row.addView(V.icon(c, R.drawable.ic_chevron_right, Palette.of(c).text3, 20));
        userCard.addView(row);
        renderOnline();
    }

    private void renderOnline() {
        if (statusText == null) return;
        Context c = ctx();
        boolean on = session().isOnline();
        Palette p = Palette.of(c);
        statusDot.setBackground(V.round(c, on ? p.success : p.danger, 4));
        String server = session().server().replaceFirst("^https?://", "");
        statusText.setText(server + "  ·  " + (on ? "已连接" : "未连接"));
    }

    private void applyRole() {
        boolean admin = session().isAdmin();
        // 账号管理、更新日志只有管理员能进（和网页菜单一致）
        setRowVisible(adminRows, admin);
        setRowVisible(changelogRow, admin);
    }

    /** 隐藏一行时把它上面的分隔线一起藏掉 */
    private static void setRowVisible(View row, boolean on) {
        row.setVisibility(on ? View.VISIBLE : View.GONE);
        LinearLayout g = (LinearLayout) row.getParent();
        int i = g.indexOfChild(row);
        if (i > 0) g.getChildAt(i - 1).setVisibility(on ? View.VISIBLE : View.GONE);
    }

    private void renderTrailing() {
        int mode = session().prefs().themeMode();
        themeText.setText(mode == Prefs.THEME_DARK ? "深色" : mode == Prefs.THEME_LIGHT ? "浅色" : "跟随系统");
        String app = AboutScreen.appVersion(ctx());
        versionText.setText(TextUtils.isEmpty(app) ? "" : "v" + app);
    }

    @Override
    protected void onFirstShow() {
        // 以服务端为准刷新一次身份：本机存的可能是旧的（比如管理员改了角色）
        run(MeApi::me, u -> session().setUser(u), e -> true);
    }

    @Override
    protected void onShow() {
        renderTrailing();
        renderOnline();
        // 有待审核的反馈时提醒一下（老师都能看到条数，管理员据此去审）
        run(MeApi::feedbackPending, n -> {
            pendingTag.setText(n + " 条待审核");
            pendingTag.setVisibility(n > 0 ? View.VISIBLE : View.GONE);
        }, e -> true);
    }

    private void confirmLogout() {
        Dialogs.confirm(ctx(), "退出登录", "确定要退出登录吗？退出后需要重新输入密码。", "退出登录", true,
                () -> host().logout(null));
    }

    // ---------- 登录状态变化 ----------

    @Override
    public void onOnlineChanged(boolean online, String message) {
        renderOnline();
    }

    @Override
    public void onUserChanged(JSONObject user) {
        if (isDestroyed()) return;
        renderUser();
        applyRole();
    }

    @Override
    protected void onDestroy() {
        session().removeListener(this);
    }
}
