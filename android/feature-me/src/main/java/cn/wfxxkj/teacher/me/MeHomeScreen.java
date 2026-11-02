package cn.wfxxkj.teacher.me;

import android.content.ActivityNotFoundException;
import android.content.Context;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.File;
import java.util.concurrent.atomic.AtomicBoolean;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.session.Prefs;
import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Sheet;
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
    private TextView updateText;
    /** 这次「检查更新」的编号：5 秒到点和查询结果谁先回来谁算，另一个作废 */
    private int checkSeq;
    private boolean checking;
    /** 下载好了、但还没允许「安装未知应用」的那个 apk：老师从设置页回来就直接装 */
    private static File pendingApk;
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
        LinearLayout update = V.row(c, R.drawable.ic_download, Tone.SUCCESS, "检查更新", "从 GitHub 获取教师端新版",
                null, v -> checkUpdate());
        updateText = V.oneLine(V.text(c, "", V.BODY2));
        MeUi.putTrailing(update, updateText);
        LinearLayout about = V.row(c, R.drawable.ic_info, Tone.INFO, "关于", "版本号、服务器信息", null,
                v -> push(new AboutScreen()));
        versionText = V.oneLine(V.text(c, "", V.BODY2));
        MeUi.putTrailing(about, versionText);
        content.addView(MeUi.group(c, settings, update, about), V.matchWrap());
        coolDown();

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
        // 刚去设置里允许了「安装未知应用」回来：下好的那个直接装，不用再点一次（也不受 60 秒限制）
        if (pendingApk != null && pendingApk.isFile() && AppUpdate.canInstall(ctx())) {
            File f = pendingApk;
            pendingApk = null;
            install(f);
        }
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

    // ---------- 检查更新（见 AppUpdate） ----------

    /** 行尾倒数：两次检查至少隔 60 秒 */
    private void coolDown() {
        if (updateText == null || isDestroyed()) return;
        int left = AppUpdate.waitLeft();
        if (checking) return;
        updateText.setText(left > 0 ? left + " 秒后可再查" : "");
        if (left > 0) post(this::coolDown, 1000);
    }

    private void checkUpdate() {
        if (checking) return;
        int left = AppUpdate.waitLeft();
        if (left > 0) {
            toast("刚查过，" + left + " 秒后可以再查");
            return;
        }
        AppUpdate.markChecked();
        checking = true;
        final int token = ++checkSeq;
        updateText.setText("正在检查…");
        // 整次 5 秒封顶：到点还没回来就算查不到，之后再回来的结果作废
        post(() -> {
            if (token != checkSeq || !checking) return;
            checking = false;
            checkSeq++;
            coolDown();
            Dialogs.alert(ctx(), "检查更新", "无法获取更新：5 秒内没有拿到更新信息，请检查网络后再试。");
        }, AppUpdate.QUERY_MS);
        io().execute(() -> {
            AppUpdate.Release r = null;
            String err = null;
            try {
                r = AppUpdate.latest();
            } catch (AppUpdate.UpdateException e) {
                err = e.getMessage();
            }
            final AppUpdate.Release got = r;
            final String why = err;
            main().post(() -> {
                if (isDestroyed() || token != checkSeq || !checking) return;
                checking = false;
                coolDown();
                onChecked(got, why);
            });
        });
    }

    private void onChecked(AppUpdate.Release r, String why) {
        if (why != null) {
            Dialogs.alert(ctx(), "检查更新", why);
            return;
        }
        String cur = AboutScreen.appVersion(ctx());
        if (r == null) {
            Dialogs.alert(ctx(), "检查更新", "还没有发布过教师端 APP 的安装包。");
            return;
        }
        if (AppUpdate.compare(r.version, cur) <= 0) {
            Dialogs.alert(ctx(), "检查更新", "已经是最新版本（v" + cur + "）。");
            return;
        }
        String notes = r.notes.trim();
        if (notes.length() > 800) notes = notes.substring(0, 800) + "…";
        String size = r.size > 0 ? String.format("，约 %.1f MB", r.size / 1048576.0) : "";
        Dialogs.confirm(ctx(), "发现新版本 v" + r.version,
                "当前 v" + cur + size + "\n\n" + notes, "下载并安装", false, () -> download(r));
    }

    private void download(AppUpdate.Release r) {
        File ready = AppUpdate.apkFile(ctx(), r);
        if (AppUpdate.ready(ready, r)) {         // 之前下好过（比如去设置里开权限之前）
            install(ready);
            return;
        }
        AtomicBoolean cancel = new AtomicBoolean();
        TextView progress = V.text(ctx(), "正在连接…", V.BODY2);
        Sheet sheet = new Sheet(ctx(), "正在下载 v" + r.version).content(progress).cancelable(false);
        sheet.buttons("取消", () -> {
            cancel.set(true);
            sheet.dismiss();
        }, null, null);
        sheet.show();
        io().execute(() -> {
            File f = null;
            String err = null;
            try {
                f = AppUpdate.download(ctx(), r, (got, total) -> main().post(() -> progress.setText(
                        total > 0 ? String.format("已下载 %d%%（%.1f / %.1f MB）", got * 100 / total,
                                got / 1048576.0, total / 1048576.0)
                                : String.format("已下载 %.1f MB", got / 1048576.0))), cancel);
            } catch (AppUpdate.UpdateException e) {
                err = e.getMessage();
            }
            final File done = f;
            final String why = err;
            main().post(() -> {
                if (sheet.isShowing()) sheet.dismiss();
                if (isDestroyed() || cancel.get()) return;
                if (why != null) Dialogs.alert(ctx(), "检查更新", why);
                else install(done);
            });
        });
    }

    /** 交给系统安装器；还没允许「安装未知应用」的先带老师去设置页 */
    private void install(File apk) {
        if (!AppUpdate.canInstall(ctx())) {
            pendingApk = apk;
            Dialogs.confirm(ctx(), "需要允许安装",
                    "安卓要先允许本 APP 安装应用：点「去设置」打开「允许来自此来源的应用」，返回后会自动开始安装。",
                    "去设置", false, () -> startSafely(AppUpdate.allowInstallIntent(ctx())));
            return;
        }
        startSafely(AppUpdate.installIntent(ctx(), apk));
    }

    private void startSafely(android.content.Intent i) {
        try {
            activity().startActivity(i);
        } catch (ActivityNotFoundException e) {
            toast("这台手机打不开安装器，请到 GitHub 页面手动下载安装");
        }
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
