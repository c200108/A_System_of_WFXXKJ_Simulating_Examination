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
import java.util.Locale;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 个人云盘管理（管理员，网页「账号」页顶上的 CloudAdmin.vue + 表格里「个人云盘」一列，服务端 2.25.0）。
 *
 * <p>服务器磁盘还剩多少、云盘总容量（全校分出去的加起来不能超过它）、已经分出去多少；
 * 下面每位老师一行，点一下分配 / 调整 / 收回（填 0）空间。总容量设成大于 0 云盘才算启用。
 */
final class CloudAdminScreen extends Screen {
    private LinearLayout page;
    private StateView state;
    private JSONObject data;
    private List<JSONObject> users = Collections.emptyList();

    @Override
    public String title() {
        return "个人云盘管理";
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
        if (data == null) state.loading();
        run(() -> new Object[]{MeApi.cloudAdmin(), MeApi.users()}, r -> {
            data = (JSONObject) r[0];
            //noinspection unchecked
            users = (List<JSONObject>) r[1];
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

    private JSONObject acc(JSONObject user) {
        JSONObject a = Json.obj(data, "accounts");
        return a == null ? null : a.optJSONObject(String.valueOf(user.optLong("id")));
    }

    private void render() {
        Context c = ctx();
        page.removeAllViews();
        boolean ok = Json.bool(data, "service_ok");
        double total = Json.dbl(data, "total_bytes"), alloc = Json.dbl(data, "allocated_bytes"),
                used = Json.dbl(data, "used_bytes");

        if (!Json.bool(data, "enabled")) {
            page.addView(V.notice(c, "个人云盘还没启用：在下面设一个大于 0 的「云盘总容量」，再给老师分配空间。", Tone.INFO),
                    V.matchWrap());
        } else if (!ok) {
            page.addView(V.notice(c, Json.str(data, "service_error") + "。服务器上运行 sudo docker compose up -d，"
                    + "再用 sudo docker compose logs openlist 看看原因。", Tone.DANGER), V.matchWrap());
        } else {
            page.addView(V.notice(c, "✓ 云盘服务正常", Tone.SUCCESS), V.matchWrap());
        }

        // 磁盘
        LinearLayout disk = MeUi.titledCard(c, "服务器磁盘");
        JSONObject d = data.optJSONObject("disk");
        V.addTop(disk, V.text(c, Json.str(data, "root_dir_host") + " 所在的盘", V.CAPTION), 0);
        if (d != null) {
            double dt = Json.dbl(d, "total"), du = Json.dbl(d, "used"), df = Json.dbl(d, "free");
            double pct = CloudUi.pct(du, dt);
            V.addTop(disk, CloudUi.bar(c, pct, pct > 90), 8);
            V.addTop(disk, V.text(c, Html.fromHtml("共 " + CloudUi.bytes(dt) + "，已用 " + CloudUi.bytes(du)
                    + "，剩 <b>" + CloudUi.bytes(df) + "</b>", Html.FROM_HTML_MODE_LEGACY), V.BODY2), 6);
        } else {
            V.addTop(disk, V.text(c, "看不到云盘目录（容器里没有挂上）", V.BODY2), 6);
        }
        V.addTop(page, disk, 16);

        // 总容量 + 已分配
        LinearLayout cap = MeUi.titledCard(c, "云盘总容量");
        cap.addView(V.text(c, "全校老师分的空间加起来不能超过它；别设满，给系统和数据库留点地方。", V.CAPTION));
        TextView totalT = V.text(c, CloudUi.bytes(total), V.H2);
        V.addTop(cap, totalT, 8);
        V.addTop(cap, V.button(c, R.drawable.ic_edit, "设置总容量", V.BTN_TONAL, v -> editTotal(d)), 8);
        V.addTop(cap, V.text(c, "已分配给老师", V.LABEL), 16);
        V.addTop(cap, CloudUi.bar(c, CloudUi.pct(alloc, total), false), 8);
        V.addTop(cap, V.text(c, CloudUi.bytes(alloc) + " / " + CloudUi.bytes(total) + " · 实际已用 "
                + CloudUi.bytes(used) + "（" + CloudUi.pct(used, total) + "%）", V.BODY2), 6);
        V.addTop(page, cap, 16);

        // 网址 + 说明
        LinearLayout how = MeUi.titledCard(c, "老师怎么用");
        how.addView(CloudUi.urlRow(this));
        V.addTop(how, V.text(c, "点下面的老师分配空间（填 0 是收回，文件留在服务器上不删）。分到空间的老师在 APP「我的 → 个人云盘」"
                + "或网页顶栏「☁ 个人云盘」直接进，不用再登录；也可以打开上面的网址，用教学平台的用户名和密码登录。"
                + "上传时超出分配的空间会被拒绝，用量每 5 分钟统计一次。", V.BODY2), 10);
        JSONObject ol = data.optJSONObject("openlist_admin");
        if (ol != null) {
            TextView cred = V.text(c, "云盘后台管理员：用户名 " + Json.str(ol, "username") + "　密码 " + Json.str(ol, "password")
                    + "（只给排查问题用；老师的账号、空间都在这里管，不要在云盘后台里改）", V.CAPTION);
            cred.setTextIsSelectable(true);
            V.addTop(how, cred, 10);
        }
        V.addTop(page, how, 16);

        // 每位老师
        page.addView(MeUi.groupTitle(c, "各位老师的空间"));
        LinearLayout list = MeUi.group(c);
        for (final JSONObject u : users) {
            JSONObject a = acc(u);
            boolean on = a != null && Json.bool(a, "allocated");
            String sub;
            if (on) {
                sub = CloudUi.bytes(Json.dbl(a, "used_bytes")) + " / " + CloudUi.bytes(Json.dbl(a, "quota_bytes"))
                        + (Json.bool(a, "over_quota") ? " · 超额" : "");
            } else {
                sub = "未分配";
            }
            LinearLayout row = V.row(c, R.drawable.ic_cloud, on ? (Json.bool(a, "over_quota") ? Tone.DANGER : Tone.PRIMARY)
                    : Tone.NEUTRAL, MeUi.nameOf(u) + "（" + Json.str(u, "username") + "）", sub, null, v -> editQuota(u));
            MeUi.putTrailing(row, V.tag(c, on ? "调整" : "分配", on ? Tone.PRIMARY : Tone.NEUTRAL));
            MeUi.addRow(list, row);
        }
        page.addView(list, V.matchWrap());
    }

    private static String gb(double bytes) {
        double g = Math.round(bytes / CloudUi.GB * 10) / 10.0;
        return g == Math.floor(g) ? String.valueOf((long) g) : String.format(Locale.ROOT, "%.1f", g);
    }

    private void editTotal(JSONObject disk) {
        Context c = ctx();
        Sheet s = new Sheet(c, "云盘总容量");
        Form f = new Form(c);
        double max = disk == null ? 0 : Math.floor(Json.dbl(disk, "total") / CloudUi.GB);
        f.note("单位 GB，可以带一位小数。" + (max > 0 ? "最多设到磁盘总大小 " + (long) max + " GB。" : "")
                + "不能比已经分给老师的 " + CloudUi.bytes(Json.dbl(data, "allocated_bytes")) + " 还小。设成 0 = 不启用云盘。");
        final Form.Text t = f.number("总容量（GB）", Double.valueOf(gb(Json.dbl(data, "total_bytes"))), true).required();
        s.content(f.view());
        s.buttons("取消", null, "保存", () -> {
            if (!f.validate()) return;
            Double v = t.number();
            if (v == null || v < 0) {
                t.setError("填一个不小于 0 的数");
                return;
            }
            s.dismiss();
            final double gbv = v;
            runBusy("正在保存…", () -> {
                MeApi.cloudSetTotal(gbv);
                return true;
            }, r -> {
                toast("云盘总容量已保存");
                load();
            });
        });
        s.show();
    }

    private void editQuota(final JSONObject u) {
        Context c = ctx();
        JSONObject a = acc(u);
        boolean on = a != null && Json.bool(a, "allocated");
        double mine = on ? Json.dbl(a, "quota_bytes") : 0;
        double left = Math.max(0, Json.dbl(data, "total_bytes") - Json.dbl(data, "allocated_bytes") + mine);
        Sheet s = new Sheet(c, "分配个人云盘空间");
        Form f = new Form(c);
        f.note(MeUi.nameOf(u) + "（" + Json.str(u, "username") + "）。最多还能给 " + gb(left) + " GB（云盘总容量 "
                + CloudUi.bytes(Json.dbl(data, "total_bytes")) + "，已分出 " + CloudUi.bytes(Json.dbl(data, "allocated_bytes"))
                + "）。\n填 0 是收回空间：这位老师就打不开云盘了，但文件留在服务器上，以后再分配还在。\n"
                + "云盘登录名和教学平台一样，密码默认也一样（老师可以在「我的 → 个人云盘」里单独设一个）。");
        final Form.Text t = f.number("空间（GB）", Double.valueOf(on ? gb(mine) : "5"), true).required();
        s.content(f.view());
        s.buttons("取消", null, "保存", () -> {
            if (!f.validate()) return;
            Double v = t.number();
            if (v == null || v < 0) {
                t.setError("填一个不小于 0 的数");
                return;
            }
            s.dismiss();
            final double gbv = v;
            final long id = u.optLong("id");
            runBusy("正在保存…", () -> MeApi.cloudSetQuota(id, gbv), r -> {
                toast(gbv > 0 ? "空间已分配" : "已收回空间（文件还在服务器上）");
                load();
            });
        });
        s.show();
    }
}
