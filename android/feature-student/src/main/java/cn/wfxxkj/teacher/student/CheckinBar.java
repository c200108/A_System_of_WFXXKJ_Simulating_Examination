package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.graphics.Typeface;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 在线座次顶上的「课堂签到」一栏（网页 CheckinBox.vue，服务端 2.24.0）。
 *
 * <p>选时长（1～10 分钟）发起，本班登录着的学生端弹出签到框选座号；签到中显示倒计时和「已签 / 应到 / 缺勤」，
 * 点「详情」看未签到名单、已签的座号、已登录的学生。和网页一样用短轮询：签到进行中每 2 秒问一次进度，
 * 版本号（已签人数 + 最后一条）变了才通知外面重读签到那张表；签到结束、页面被盖住就不问了。
 */
final class CheckinBar {

    interface Listener {
        /** 刚发起：签到建了一张新工作表 */
        void onStarted(JSONObject v);

        /** 有人签到了（版本号变了） */
        void onProgress(JSONObject v);
    }

    private final Screen screen;
    private final int cid;
    private final String clsName;
    private final Listener listener;
    private final LinearLayout root;
    private final TextView status;
    private final LinearLayout buttons;

    private boolean canEdit;
    private JSONObject view;
    private int left;
    private String version = "";
    private boolean visible;
    /** 每次 resume / 发起都换一代，旧的轮询、倒计时自己停 */
    private int gen;
    private boolean polling;
    private Sheet detail;

    CheckinBar(Screen screen, JSONObject cls, Listener l) {
        this.screen = screen;
        this.cid = Kit.id(cls);
        this.clsName = Json.str(cls, "display");
        this.listener = l;
        Context c = screen.ctx();
        root = V.hbox(c);
        V.pad(root, 12, 4, 12, 6);
        root.setGravity(Gravity.CENTER_VERTICAL);
        status = V.text(c, "", V.BODY2);
        root.addView(status, V.fill());
        buttons = V.hbox(c);
        root.addView(buttons);
        root.setVisibility(View.GONE);
    }

    View view() {
        return root;
    }

    void setCanEdit(boolean on) {
        canEdit = on;
        render();
    }

    /** 页面回到前台：问一次，进行中就接着每 2 秒问 */
    void resume() {
        visible = true;
        gen++;
        polling = false;
        poll(gen);
    }

    void pause() {
        visible = false;
        gen++;
        polling = false;
    }

    private boolean active() {
        return view != null && Json.bool(view, "active") && left > 0;
    }

    private void poll(final int g) {
        if (!visible || g != gen || screen.isDestroyed()) return;
        polling = true;
        screen.run(() -> StudentApi.checkinCurrent(cid), v -> {
            if (g != gen) return;
            apply(v);
            schedule(g);
        }, e -> {
            // 老服务器没有签到（404）、网络抖一下：进行中就下一轮再问，不弹错
            if (g == gen) schedule(g);
            return true;
        });
    }

    private void schedule(final int g) {
        polling = false;
        if (view != null && Json.bool(view, "active")) {
            polling = true;
            screen.post(() -> poll(g), left > 0 ? 2000 : 800);
        }
    }

    private void apply(JSONObject v) {
        String before = version;
        view = v;
        if (v == null) {
            render();
            return;
        }
        left = v.optInt("remaining");
        version = v.optInt("id") + ":" + Json.str(v, "version");
        if (!version.equals(before)) listener.onProgress(v);
        render();
        if (detail != null && detail.isShowing()) fillDetail();
        if (Json.bool(v, "active")) tick(gen);
    }

    /** 本地倒计时（每秒），真正的剩余时间以服务器为准，每次轮询校正 */
    private int tickGen = -1;

    private void tick(final int g) {
        if (tickGen == g) return;
        tickGen = g;
        tickLoop(g);
    }

    private void tickLoop(final int g) {
        if (g != gen || !visible) {
            if (tickGen == g) tickGen = -1;
            return;
        }
        screen.post(() -> {
            if (g != gen) return;
            if (left > 0) {
                left--;
                render();
            }
            if (left > 0) tickLoop(g);
            else tickGen = -1;
        }, 1000);
    }

    private static String fmt(int s) {
        return String.format(Locale.ROOT, "%02d:%02d", s / 60, s % 60);
    }

    private void render() {
        Context c = screen.ctx();
        buttons.removeAllViews();
        if (view == null && !canEdit) {
            root.setVisibility(View.GONE);
            return;
        }
        root.setVisibility(View.VISIBLE);
        Palette p = Palette.of(c);
        if (active()) {
            status.setText("签到中 " + fmt(left) + "　已签 " + view.optInt("signed_count") + " / "
                    + view.optInt("total") + "　缺勤 " + view.optInt("absent"));
            status.setTextColor(p.success);
            status.setTypeface(Typeface.DEFAULT_BOLD);
            buttons.addView(V.button(c, "详情", V.BTN_TEXT, v -> showDetail()));
            if (canEdit) buttons.addView(V.button(c, "结束", V.BTN_DANGER_TONAL, v -> stop()));
            return;
        }
        status.setTypeface(Typeface.DEFAULT);
        status.setTextColor(p.text2);
        if (view != null) {
            String tn = Json.str(view, "tab_name");
            status.setText("上次签到（" + (tn.isEmpty() ? "已删表" : tn) + "）：已签 "
                    + view.optInt("signed_count") + " / " + view.optInt("total"));
            V.clickable(status, 6, v -> showDetail());
        } else {
            status.setText("课堂签到：学生端弹框选座号，姓名自动填进新工作表");
            status.setOnClickListener(null);
            status.setClickable(false);
        }
        if (canEdit) buttons.addView(V.button(c, "发起签到", V.BTN_TONAL, v -> askStart()));
    }

    private void askStart() {
        List<Option> opts = new ArrayList<>();
        for (int m = 1; m <= 10; m++) opts.add(new Option(m, m + " 分钟", m == 3 ? "常用" : null));
        Dialogs.choose(screen.ctx(), "发起签到：签到时长", opts, 3, o -> start((Integer) o.value));
    }

    private void start(final int minutes) {
        screen.runBusy("正在发起签到…", () -> StudentApi.checkinStart(cid, minutes), v -> {
            gen++;
            apply(v);
            listener.onStarted(v);
            schedule(gen);
            screen.toast("已发起签到（" + minutes + " 分钟），本班登录着的学生端会弹出签到框");
        });
    }

    private void stop() {
        if (view == null) return;
        final int kid = view.optInt("id");
        Dialogs.confirm(screen.ctx(), "结束签到", "现在就结束签到？还没签的学生就签不了了。", "结束签到", true,
                () -> screen.runBusy("正在结束…", () -> StudentApi.checkinStop(cid, kid), v -> {
                    gen++;
                    apply(v);
                }));
    }

    // ---------------------------------------------------------------- 签到详情

    private LinearLayout detailBody;

    private void showDetail() {
        if (view == null) return;
        Context c = screen.ctx();
        detail = new Sheet(c, "签到详情 · " + clsName);
        detailBody = V.vbox(c);
        detail.content(detailBody);
        fillDetail();
        detail.buttons(null, null, "关闭", detail::dismiss);
        detail.show();
    }

    private void fillDetail() {
        Context c = screen.ctx();
        JSONObject v = view;
        detailBody.removeAllViews();
        String at = Json.str(v, "started_at").replace('T', ' ');
        if (at.length() > 16) at = at.substring(0, 16);
        String sum = Json.str(v, "started_by") + " 发起于 " + at + "，"
                + (active() ? "还剩 " + fmt(left) : "已结束") + "。应到 " + v.optInt("total") + " 人，已签 "
                + v.optInt("signed_count") + " 人，缺勤 " + v.optInt("absent") + " 人。";
        String tn = Json.str(v, "tab_name");
        if (!tn.isEmpty()) sum += "签到结果填在工作表「" + tn + "」里。";
        detailBody.addView(V.text(c, sum, V.BODY2));

        List<JSONObject> unsigned = Json.list(Json.arr(v, "unsigned"));
        V.addTop(detailBody, V.text(c, "未签到（" + unsigned.size() + "）", V.H3), 14);
        if (unsigned.isEmpty()) {
            V.addTop(detailBody, V.text(c, "全部签到了", V.CAPTION), 6);
        } else {
            FlowBox fb = new FlowBox(c, 6, 6);
            for (JSONObject u : unsigned) {
                boolean on = Json.bool(u, "online");
                fb.addView(V.tag(c, Json.str(u, "name") + (on ? "（已登录）" : ""), on ? Tone.SUCCESS : Tone.NEUTRAL));
            }
            V.addTop(detailBody, fb, 6);
        }

        List<JSONObject> signed = Json.list(Json.arr(v, "signed"));
        V.addTop(detailBody, V.text(c, "已签到（" + signed.size() + "）", V.H3), 14);
        for (JSONObject s : signed) {
            String t = Json.str(s, "at").replace('T', ' ');
            t = t.length() >= 19 ? t.substring(11, 19) : t;
            LinearLayout row = V.hbox(c);
            V.pad(row, 0, 4, 0, 4);
            TextView seat = V.text(c, Json.str(s, "seat"), V.BODY2);
            seat.setMinWidth(screen.dp(56));
            V.bold(seat);
            row.addView(seat);
            row.addView(V.text(c, Json.str(s, "name"), V.BODY), V.fill());
            row.addView(V.text(c, t, V.CAPTION));
            detailBody.addView(row, V.matchWrap());
        }

        List<JSONObject> online = Json.list(Json.arr(v, "online"));
        V.addTop(detailBody, V.text(c, "已登录的学生（" + online.size() + "）", V.H3), 14);
        V.addTop(detailBody, V.text(c, "学生端登录着（最近 20 秒内有响应）的同学和他选的座号；没选的还没签到。", V.CAPTION), 4);
        if (!online.isEmpty()) {
            FlowBox fb = new FlowBox(c, 6, 6);
            for (JSONObject o : online) {
                String seat = Json.str(o, "seat");
                fb.addView(V.tag(c, Json.str(o, "name") + (TextUtils.isEmpty(seat) ? " · 未签" : " · " + seat), Tone.SUCCESS));
            }
            V.addTop(detailBody, fb, 6);
        }
    }
}
