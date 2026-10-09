package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.Html;
import android.text.TextUtils;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/** 账号管理里的几个弹层：新增账号、重置密码、分配班级、改自己的密码 */
final class UserSheets {
    private UserSheets() {}

    interface Saved {
        void saved(JSONObject user);
    }

    // ---------- 新增账号 ----------

    static void create(Screen s, Runnable after) {
        Context c = s.ctx();
        Sheet sh = new Sheet(c, "新增账号");
        Form f = new Form(c);
        Form.Text username = f.text("用户名", "", "登录用，建议用拼音或工号").required();
        username.edit.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        Form.Text name = f.text("姓名", "", "留空则同用户名").maxLength(64);
        f.row(username, name);
        TextView pl = V.text(c, "初始密码", V.LABEL);
        V.pad(pl, 2, 0, 0, 6);
        LinearLayout pbox = V.vbox(c);
        pbox.addView(pl);
        EditText pwd = Fields.input(c, null);
        pwd.setText(MeUi.randomPassword());
        pbox.addView(MeUi.passwordRow(c, pwd), V.matchWrap());
        f.custom(pbox);
        Form.Choice role = f.choice("角色", Option.pairs("teacher", "教师", "admin", "管理员"), "teacher");
        f.note("用户名只能用字母、数字、下划线、点、减号，至少 3 个字符；密码至少 6 位、不能是纯数字。");
        sh.content(f.view());
        sh.buttons("取消", null, "创建", () -> {
            if (!f.validate()) return;
            final String u = username.value(), n = name.value(), p = pwd.getText().toString(), r = role.string();
            if (p.isEmpty()) {
                s.toast("请填初始密码");
                return;
            }
            // 具体规则（长度、可用字符、不能纯数字）由后端判，报错直接显示
            s.runBusy("正在创建…", () -> MeApi.createUser(u, p, n, r), user -> {
                sh.dismiss();
                after.run();
                MeUi.showCredential(c, "创建成功，请把这两行发给老师", "账号：" + u + "\n密码：" + p);
            });
        });
        sh.show();
    }

    // ---------- 重置密码 ----------

    static void resetPassword(Screen s, JSONObject u) {
        Context c = s.ctx();
        final String who = MeUi.nameOf(u);
        Sheet sh = new Sheet(c, "重置密码");
        TextView line = V.text(c, "给「" + who + "」设置新密码：", V.BODY);
        V.pad(line, 0, 0, 0, 10);
        sh.content(line);
        EditText pwd = Fields.input(c, null);
        pwd.setText(MeUi.randomPassword());
        sh.content(MeUi.passwordRow(c, pwd));
        TextView tip = V.text(c, "确定后新密码只显示一次，请当场记下发给本人。系统里没有邮箱，老师忘记密码只能由管理员重置。",
                V.CAPTION);
        V.pad(tip, 2, 10, 0, 0);
        sh.content(tip);
        sh.buttons("取消", null, "确定重置", () -> {
            final String p = pwd.getText().toString();
            if (p.isEmpty()) {
                s.toast("请填新密码");
                return;
            }
            s.runBusy("正在重置…", () -> MeApi.updateUser(u.optLong("id"), Json.of("password", p)), r -> {
                sh.dismiss();
                MeUi.showCredential(c, "已重置，请把新密码发给本人", who + " 的新密码：" + p);
            });
        });
        sh.show();
    }

    // ---------- 分配班级 ----------

    static void assignClasses(Screen s, JSONObject u, Saved onSaved) {
        Context c = s.ctx();
        Sheet sh = new Sheet(c, "分配班级 · " + MeUi.nameOf(u));
        TextView tip = V.text(c, Html.fromHtml("勾中的班归这位老师，<b>他只能给这些班发考试</b>。一个班同时只能有一位老师，"
                + "勾一个已经归别人的班，会从对方那里转过来。", Html.FROM_HTML_MODE_LEGACY), V.BODY2);
        V.pad(tip, 0, 0, 0, 8);
        sh.content(tip);
        StateView state = new StateView(c);
        sh.content(state);
        LinearLayout box = V.vbox(c);
        sh.content(box);
        final Set<Long> picked = new LinkedHashSet<>();
        for (Integer id : Json.ints(Json.arr(u, "class_ids"))) picked.add((long) id);
        final long uid = u.optLong("id");
        sh.buttons("取消", null, "保存", () -> {
            List<Long> ids = new ArrayList<>(picked);
            s.runBusy("正在保存…", () -> MeApi.updateUser(uid, Json.of("class_ids", ids)), r -> {
                sh.dismiss();
                s.toast("班级已更新");
                onSaved.saved(r);
            });
        });
        sh.show();

        s.run(MeApi::classes, classes -> {
            state.hide();
            if (classes.isEmpty()) {
                state.empty("还没有班级", "先去「学生 › 班级」建一批");
                return;
            }
            // 按年级分组，一屏看清
            Map<String, List<JSONObject>> groups = new LinkedHashMap<>();
            for (JSONObject cl : classes) {
                String g = Json.str(cl, "grade");
                if (!groups.containsKey(g)) groups.put(g, new ArrayList<>());
                groups.get(g).add(cl);
            }
            Palette p = Palette.of(c);
            for (Map.Entry<String, List<JSONObject>> e : groups.entrySet()) {
                TextView gname = V.text(c, TextUtils.isEmpty(e.getKey()) ? "未分年级" : e.getKey(), V.LABEL);
                V.pad(gname, 2, 12, 0, 4);
                box.addView(gname);
                cn.wfxxkj.teacher.core.ui.GridBox grid = new cn.wfxxkj.teacher.core.ui.GridBox(c, 150, 4, 4);
                for (JSONObject cl : e.getValue()) {
                    final long cid = cl.optLong("id");
                    LinearLayout row = V.hbox(c);
                    row.setMinimumHeight(Ui.dp(c, 44));
                    CheckBox cb = new CheckBox(c);
                    cb.setClickable(false);
                    cb.setChecked(picked.contains(cid));
                    row.addView(cb);
                    LinearLayout texts = V.vbox(c);
                    String nm = Json.str(cl, "name");
                    if (!Json.bool(cl, "is_active")) nm += "（已停用）";
                    texts.addView(V.oneLine(V.text(c, nm, V.BODY)));
                    // 这个班已经归别人了吗
                    long owner = cl.optLong("owner_id", 0);
                    if (!cl.isNull("owner_id") && owner != 0 && owner != uid) {
                        String on = Json.str(cl, "owner_name");
                        TextView t = V.oneLine(V.text(c, "现属 " + (on.isEmpty() ? "其他老师" : on), V.CAPTION));
                        t.setTextColor(p.warning);
                        texts.addView(t);
                    }
                    row.addView(texts, V.fill());
                    V.clickable(row, 10, v -> {
                        if (picked.contains(cid)) picked.remove(cid);
                        else picked.add(cid);
                        cb.setChecked(picked.contains(cid));
                    });
                    grid.addView(row);
                }
                box.addView(grid, V.matchWrap());
            }
        }, err -> {
            state.error(err.getMessage(), null);
            return true;
        });
    }

    // ---------- 改自己的密码（账号页右上角也能改，和网页一致） ----------

    static void changeMyPassword(Screen s) {
        Context c = s.ctx();
        Sheet sh = new Sheet(c, "修改我的密码");
        Form f = new Form(c);
        Form.Text o = f.password("原密码", null).required();
        Form.Text n = f.password("新密码", "至少 6 位，不能是纯数字").required();
        sh.content(f.view());
        sh.buttons("取消", null, "保存", () -> {
            if (!f.validate()) return;
            final String op = o.raw(), np = n.raw();
            s.runBusy("正在修改…", () -> {
                MeApi.changePassword(op, np);
                return true;
            }, ok -> {
                s.session().passwordChanged(np);
                sh.dismiss();
                s.toast("密码已修改");
            });
        });
        sh.show();
    }
}
