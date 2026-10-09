package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 一个教师账号的详情（网页账号表格的一行 + 它的操作列）：
 * 资料、带的班（分配）、删除权开关，以及重置密码、改姓名、设为管理员/降为教师、停用/启用。
 */
public class UserDetailScreen extends Screen {

    private JSONObject user;
    private LinearLayout page;

    UserDetailScreen(JSONObject user) {
        this.user = user;
    }

    @Override
    public String title() {
        return MeUi.nameOf(user);
    }

    @Override
    public String subtitle() {
        return Json.str(user, "username");
    }

    private boolean isSelf() {
        return user.optLong("id") == session().userId();
    }

    @Override
    protected View onCreateView(Context c) {
        page = V.page(c);
        render();
        ScrollView sv = V.scroll(c, page);
        sv.setBackgroundColor(Palette.of(c).page);
        return sv;
    }

    private void render() {
        Context c = ctx();
        page.removeAllViews();
        boolean active = Json.bool(user, "is_active");
        boolean admin = MeUi.isAdmin(user);

        // 头部
        LinearLayout head = V.card(c);
        LinearLayout row = V.hbox(c);
        TextView av = V.avatar(c, MeUi.nameOf(user), 56);
        if (!active) av.setAlpha(0.4f);
        row.addView(av);
        LinearLayout texts = V.vbox(c);
        V.pad(texts, 14, 0, 0, 0);
        LinearLayout nameRow = V.hbox(c);
        TextView nm = V.oneLine(V.text(c, MeUi.nameOf(user), V.H2));
        nm.setMaxWidth(Ui.dp(c, Ui.wide(c) ? 400 : 150));
        nameRow.addView(nm);
        V.addStart(nameRow, MeUi.roleTag(c, user, false), 8);
        V.addStart(nameRow, V.tag(c, active ? "正常" : "已停用", active ? Tone.SUCCESS : Tone.NEUTRAL), 6);
        texts.addView(nameRow);
        V.addTop(texts, V.text(c, "登录名 " + Json.str(user, "username") + (isSelf() ? "（我自己）" : ""),
                V.CAPTION), 4);
        row.addView(texts, V.fill());
        head.addView(row);
        page.addView(head, V.matchWrap());

        GridBox cols = new GridBox(c, 320, 2, 16);

        // 资料
        LinearLayout info = MeUi.titledCard(c, "资料");
        info.addView(V.kv(c, "姓名", Json.str(user, "name")));
        info.addView(V.kv(c, "用户名", Json.str(user, "username")));
        info.addView(V.kv(c, "联系方式", Json.str(user, "contact").isEmpty() ? "未填" : Json.str(user, "contact")));
        info.addView(V.kv(c, "任教班级", Json.str(user, "grade_class")));
        info.addView(V.kv(c, "创建时间", MeUi.time(Json.str(user, "created_at"))));
        cols.addView(info);

        // 班级与权限
        LinearLayout perm = MeUi.titledCard(c, "班级与权限");
        TextView l1 = V.text(c, "带的班", V.LABEL);
        perm.addView(l1);
        FlowBox fb = new FlowBox(c, 6, 6);
        List<String> classes = Json.strings(Json.arr(user, "class_names"));
        if (classes.isEmpty()) fb.addView(V.text(c, "未分配", V.BODY2));
        for (String n : classes) fb.addView(V.tag(c, n, Tone.INFO));
        V.addTop(perm, fb, 8);
        TextView assign = V.button(c, R.drawable.ic_class, "分配班级", V.BTN_TONAL,
                v -> UserSheets.assignClasses(this, user, this::updated));
        V.addTop(perm, assign, 12);
        V.addTop(perm, V.text(c, "带的班决定这位老师能给谁发考试。", V.CAPTION), 6);
        V.addTop(perm, V.divider(c), 14);
        LinearLayout delRow = V.hbox(c);
        V.pad(delRow, 0, 10, 0, 0);
        LinearLayout dt = V.vbox(c);
        dt.addView(V.text(c, "删除权", V.BODY));
        dt.addView(V.text(c, admin ? "管理员天然拥有全部权限" : "能否删除题库、练习文本、更新日志和打字成绩", V.CAPTION));
        delRow.addView(dt, V.fill());
        if (admin) {
            delRow.addView(V.tag(c, "全部", Tone.DANGER));
        } else {
            Switch sw = new Switch(c);
            sw.setChecked(Json.bool(user, "can_delete"));
            sw.setOnClickListener(v -> {
                sw.setChecked(Json.bool(user, "can_delete")); // 以服务器结果为准
                toggleDelete();
            });
            delRow.addView(sw);
        }
        perm.addView(delRow);
        cols.addView(perm);
        V.addTop(page, cols, 16);

        // 操作
        page.addView(MeUi.groupTitle(c, "操作"));
        LinearLayout ops = MeUi.group(c,
                V.row(c, R.drawable.ic_key, Tone.PRIMARY, "重置密码", "生成新密码，只显示一次", null,
                        v -> UserSheets.resetPassword(this, user)),
                V.row(c, R.drawable.ic_edit, Tone.PRIMARY, "修改姓名", null, null, v -> rename()));
        if (!admin) {
            MeUi.addRow(ops, V.row(c, R.drawable.ic_manage_accounts, Tone.WARNING, "设为管理员",
                    "管理员能看到全校的考试与成绩、管理账号", null, v -> setRole("admin")));
        } else if (!isSelf()) {
            MeUi.addRow(ops, V.row(c, R.drawable.ic_person, Tone.WARNING, "降为教师", null, null,
                    v -> setRole("teacher")));
        }
        if (!isSelf()) {
            MeUi.addRow(ops, active
                    ? V.row(c, R.drawable.ic_block, Tone.DANGER, "停用账号", "停用后无法登录，数据保留，可再启用", null,
                    v -> toggleActive())
                    : V.row(c, R.drawable.ic_check_circle, Tone.SUCCESS, "重新启用", null, null, v -> toggleActive()));
        }
        page.addView(ops, V.matchWrap());
        invalidateChrome();
    }

    private void updated(JSONObject u) {
        user = u;
        render();
        // 改的是自己就同步本机身份，否则「我的」页和实际权限对不上
        if (isSelf()) run(MeApi::me, me -> session().setUser(me), e -> true);
    }

    private void patch(String busy, JSONObject data, String done) {
        final long id = user.optLong("id");
        runBusy(busy, () -> MeApi.updateUser(id, data), u -> {
            toast(done);
            updated(u);
        });
    }

    private void rename() {
        MeUi.prompt(ctx(), "修改姓名", null, "姓名", Json.str(user, "name"), "保存", false, text -> {
            String v = text.trim();
            if (v.isEmpty()) return "不能为空";
            patch("正在保存…", Json.of("name", v), "已修改");
            return null;
        });
    }

    private void setRole(String role) {
        boolean toAdmin = "admin".equals(role);
        Dialogs.confirm(ctx(), toAdmin ? "设为管理员" : "降为教师",
                toAdmin ? "「" + MeUi.nameOf(user) + "」将能看到全校所有老师的考试与成绩，并能管理账号。"
                        : "「" + MeUi.nameOf(user) + "」将只能看到自己的考试与成绩。",
                "确定", false,
                () -> patch("正在修改…", Json.of("role", role), toAdmin ? "已设为管理员" : "已改为普通教师"));
    }

    private void toggleActive() {
        final long id = user.optLong("id");
        if (Json.bool(user, "is_active")) {
            Dialogs.confirm(ctx(), "停用账号", "停用后「" + MeUi.nameOf(user) + "」将无法登录，确定吗？", "停用", true,
                    () -> runBusy("正在停用…", () -> {
                        MeApi.disableUser(id);
                        return true;
                    }, ok -> {
                        toast("已停用");
                        Json.put(user, "is_active", false);
                        render();
                    }));
        } else {
            patch("正在启用…", Json.of("is_active", true), "已重新启用");
        }
    }

    private void toggleDelete() {
        final boolean to = !Json.bool(user, "can_delete");
        Runnable go = () -> patch("正在保存…", Json.of("can_delete", to), to ? "已开通删除权" : "已收回删除权");
        if (to) {
            Dialogs.confirm(ctx(), "开通删除权", "开通后「" + MeUi.nameOf(user) + "」就能删除题库里的题目、练习文本、"
                    + "更新日志和打字成绩了。\n这些是全校共用的内容，删掉所有人都受影响。\n\n确定开通吗？",
                    "确定开通", true, go);
        } else {
            go.run();
        }
    }
}
