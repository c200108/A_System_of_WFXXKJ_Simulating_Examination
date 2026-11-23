package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.Html;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 我的个人云盘（网页「我的账号」里的 CloudCard.vue + 顶栏「☁ 个人云盘」，服务端 2.25.0）。
 *
 * <p>分到多少、用了多少、云盘网址和登录名；「打开个人云盘」免登录直接进（APP 里用 {@link CloudWebScreen}
 * 打开云盘自己的网页 —— 云盘是 OpenList，文件管理界面是它自己的）；也能单独设一个云盘密码，或改回和教学平台一致。
 */
final class CloudScreen extends Screen {
    private LinearLayout page;
    private StateView state;
    private JSONObject info;

    @Override
    public String title() {
        return "个人云盘";
    }

    @Override
    protected View onCreateView(Context c) {
        android.widget.FrameLayout root = new android.widget.FrameLayout(c);
        page = V.page(c);
        ScrollView sv = V.scroll(c, page);
        sv.setBackgroundColor(Palette.of(c).page);
        root.addView(sv);
        state = new StateView(c);
        root.addView(state);
        return root;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    @Override
    public List<Action> actions() {
        return Collections.singletonList(Action.icon(R.drawable.ic_refresh, "刷新", this::load));
    }

    private void load() {
        state.loading();
        run(MeApi::cloudMe, got -> {
            info = got;
            state.hide();
            render();
        }, e -> {
            if (e instanceof ApiException && ((ApiException) e).code == 404) {
                state.empty("这台服务器没有个人云盘", "服务端 2.25.0 起才有，机房局域网版没有这一块");
                return true;
            }
            state.error(e.getMessage(), this::load);
            return true;
        });
    }

    private void render() {
        Context c = ctx();
        page.removeAllViews();
        if (!Json.bool(info, "enabled")) {
            page.addView(V.notice(c, "这台服务器还没启用个人云盘（系统管理员在「账号管理 → 个人云盘」里设了总容量才会启用）。", Tone.INFO),
                    V.matchWrap());
            return;
        }
        if (!Json.bool(info, "allocated")) {
            page.addView(V.notice(c, "你还没有分配个人云盘空间，暂时无法使用。需要的话请联系系统管理员分配。", Tone.INFO),
                    V.matchWrap());
            return;
        }

        // 用量
        LinearLayout usage = MeUi.titledCard(c, "☁ 我的空间");
        double used = Json.dbl(info, "used_bytes"), quota = Json.dbl(info, "quota_bytes");
        boolean over = Json.bool(info, "over_quota");
        double pct = CloudUi.pct(used, quota);
        usage.addView(CloudUi.bar(c, pct, over || pct > 90));
        TextView num = V.text(c, Html.fromHtml("已用 <b>" + CloudUi.bytes(used) + "</b> / 共 " + CloudUi.bytes(quota)
                + "（" + pct + "%）", Html.FROM_HTML_MODE_LEGACY), V.BODY2);
        V.addTop(usage, num, 8);
        V.addTop(usage, V.text(c, "用量每 5 分钟统计一次", V.CAPTION), 2);
        if (over) {
            V.addTop(usage, V.notice(c, "空间超出了分配的额度，暂时不能上传、复制、解压，删掉一些文件后几分钟内自动恢复。",
                    Tone.DANGER), 10);
        }
        V.addTop(usage, V.button(c, R.drawable.ic_cloud, "打开个人云盘", V.BTN_PRIMARY, v -> push(new CloudWebScreen())), 14);
        V.addTop(usage, V.button(c, R.drawable.ic_open_in_new, "用浏览器打开", V.BTN_TONAL, v -> {
            if (!Sys.openUrl(ctx(), CloudUi.url())) toast("这台手机没有浏览器");
        }), 8);
        page.addView(usage, V.matchWrap());

        // 网址、登录名
        LinearLayout acc = MeUi.titledCard(c, "在别的电脑、手机上用");
        acc.addView(CloudUi.urlRow(this));
        boolean custom = Json.bool(info, "password_custom");
        TextView note = V.text(c, Html.fromHtml("在 APP 里点「打开个人云盘」直接进，不用再登录。用浏览器打开上面的网址也行："
                + "用户名 <b>" + Html.escapeHtml(Json.str(info, "login")) + "</b>，密码"
                + (custom ? "<b>是下面单独设置的云盘密码</b>" : "<b>和教学平台的登录密码一样</b>") + "。",
                Html.FROM_HTML_MODE_LEGACY), V.BODY2);
        V.addTop(acc, note, 10);
        V.addTop(page, acc, 16);

        // 云盘密码
        LinearLayout pwd = MeUi.titledCard(c, "云盘密码");
        if (custom) {
            pwd.addView(V.text(c, "云盘密码现在是单独设置的。改回和教学平台一致：", V.BODY2));
            Form f = new Form(c);
            final Form.Text cur = f.password("教学平台的登录密码", null).required();
            V.addTop(pwd, f.view(), 6);
            pwd.addView(V.button(c, "改回一致", V.BTN_TONAL, v -> {
                if (!f.validate()) return;
                final String pw = cur.raw();
                runBusy("正在保存…", () -> MeApi.cloudSyncPassword(pw), r -> {
                    merge(r);
                    toast("云盘密码已改回和教学平台一致");
                });
            }), V.matchWrap());
            V.addTop(pwd, V.text(c, "或者重新设一个：", V.BODY2), 16);
        } else {
            pwd.addView(V.text(c, "单独设置一个云盘密码（设了以后，改教学平台密码不再影响云盘）", V.BODY2));
        }
        Form f2 = new Form(c);
        final Form.Text np = f2.password("新的云盘密码", "至少 6 位").required();
        final Form.Text np2 = f2.password("再输一次", null).required();
        np2.rule(v -> np2.raw().equals(np.raw()) ? null : "两次输入的密码不一致");
        V.addTop(pwd, f2.view(), 6);
        pwd.addView(V.button(c, "设置云盘密码", V.BTN_TONAL, v -> {
            if (!f2.validate()) return;
            final String pw = np.raw();
            runBusy("正在保存…", () -> MeApi.cloudSetPassword(pw), r -> {
                merge(r);
                toast("云盘密码已单独设置。直接打开云盘登录时用这个密码");
            });
        }), V.matchWrap());
        V.addTop(page, pwd, 16);
    }

    private void merge(JSONObject r) {
        if (r != null) {
            for (java.util.Iterator<String> it = r.keys(); it.hasNext(); ) {
                String k = it.next();
                Json.put(info, k, r.opt(k));
            }
        }
        render();
    }
}
