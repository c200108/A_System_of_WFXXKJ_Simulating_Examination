package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.Html;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 我的账号（网页 Profile.vue）：看账号信息、改个人资料、改密码。
 *
 * <p>能改的只有姓名、任教年级班级、联系方式三项 —— 用户名、角色、启停都得管理员来，
 * 接口那边也是这么限的。
 */
public class ProfileScreen extends Screen {

    private LinearLayout idCard;
    private Form.Text name, gradeClass, contact;
    private Form.Text oldPwd, newPwd, confirmPwd;

    @Override
    public String title() {
        return "我的账号";
    }

    @Override
    protected View onCreateView(Context c) {
        LinearLayout page = V.page(c);

        idCard = V.card(c);
        page.addView(idCard, V.matchWrap());
        renderId(session().user());

        // 两张卡：手机上下排，宽屏左右并排
        GridBox cols = new GridBox(c, 320, 2, 16);
        cols.addView(profileCard(c));
        cols.addView(passwordCard(c));
        V.addTop(page, cols, 16);

        ScrollView sv = V.scroll(c, page);
        sv.setBackgroundColor(Palette.of(c).page);
        return sv;
    }

    private void renderId(JSONObject u) {
        Context c = ctx();
        idCard.removeAllViews();
        LinearLayout row = V.hbox(c);
        row.addView(V.avatar(c, MeUi.nameOf(u), 56));
        LinearLayout texts = V.vbox(c);
        V.pad(texts, 14, 0, 0, 0);
        LinearLayout nameRow = V.hbox(c);
        TextView nm = V.oneLine(V.text(c, MeUi.nameOf(u), V.H2));
        nm.setMaxWidth(Ui.dp(c, Ui.wide(c) ? 420 : 160));
        nameRow.addView(nm);
        V.addStart(nameRow, MeUi.roleTag(c, u, true), 8);
        texts.addView(nameRow);
        String joined = Json.str(u, "created_at");
        joined = joined.length() >= 10 ? joined.substring(0, 10) : "—";
        V.addTop(texts, V.text(c, "登录名 " + Json.str(u, "username") + "  ·  启用于 " + joined, V.CAPTION), 4);
        row.addView(texts, V.fill());
        idCard.addView(row);

        // 名下的班（管理员分配）
        java.util.List<String> classes = Json.strings(Json.arr(u, "class_names"));
        if (!classes.isEmpty()) {
            FlowBox fb = new FlowBox(c, 6, 6);
            for (String n : classes) fb.addView(V.tag(c, n, Tone.NEUTRAL));
            LinearLayout line = V.vbox(c);
            line.addView(V.text(c, "带的班", V.LABEL));
            V.addTop(line, fb, 6);
            V.addTop(idCard, line, 14);
        }

        TextView tip;
        if (MeUi.isAdmin(u)) {
            tip = V.notice(c, Html.fromHtml("你是系统管理员：看得到<b>全校所有老师</b>的考试与成绩，"
                    + "也只有你能下架和删除反馈评论。", Html.FROM_HTML_MODE_LEGACY), Tone.WARNING);
        } else {
            tip = V.notice(c, Html.fromHtml("你只看得到<b>自己发布的考试</b>和上面的成绩，别的老师同样看不到你的。"
                    + "需要跨账号查看请找系统管理员。", Html.FROM_HTML_MODE_LEGACY), Tone.INFO);
        }
        V.addTop(idCard, tip, 14);
    }

    private View profileCard(Context c) {
        LinearLayout card = MeUi.titledCard(c, "个人资料");
        Form f = new Form(c);
        JSONObject u = session().user();
        name = f.text("姓名", Json.str(u, "name"), "显示在顶栏和反馈回复的署名上").maxLength(64);
        gradeClass = f.text("任教年级班级", Json.str(u, "grade_class"), "如 七年级 1-4 班、八(2)(3)班").maxLength(128);
        contact = f.text("联系方式", Json.str(u, "contact"), "手机号或办公室电话，选填").maxLength(64);
        card.addView(f.view());
        card.addView(V.button(c, "保存资料", V.BTN_PRIMARY, v -> saveProfile()), V.matchWrap());
        TextView note = V.text(c, "登录名和角色不能自己改。忘了密码也只能由管理员重置 —— 系统里没存邮箱，找不回来。",
                V.CAPTION);
        V.addTop(card, note, 10);
        return card;
    }

    private View passwordCard(Context c) {
        LinearLayout card = MeUi.titledCard(c, "修改密码");
        Form f = new Form(c);
        oldPwd = f.password("原密码", null).required();
        newPwd = f.password("新密码", "至少 6 位，不能是纯数字").required();
        confirmPwd = f.password("确认新密码", null).required();
        confirmPwd.rule(v -> confirmPwd.raw().equals(newPwd.raw()) ? null : "两次输入的新密码不一致");
        card.addView(f.view());
        card.addView(V.button(c, "修改密码", V.BTN_PRIMARY, v -> {
            if (!f.validate()) return;
            savePassword();
        }), V.matchWrap());
        V.addTop(card, V.text(c, "改完当前登录不会掉线，但下次登录要用新密码。", V.CAPTION), 10);
        return card;
    }

    @Override
    protected void onFirstShow() {
        // 以服务端为准，本机存的可能是旧的
        run(MeApi::me, u -> {
            session().setUser(u);
            renderId(u);
            name.set(Json.str(u, "name"));
            gradeClass.set(Json.str(u, "grade_class"));
            contact.set(Json.str(u, "contact"));
        });
    }

    private void saveProfile() {
        final String n = name.value(), g = gradeClass.value(), ct = contact.value();
        runBusy("正在保存…", () -> MeApi.updateMe(n, g, ct), u -> {
            session().setUser(u); // 名片、顶栏的名字立刻跟着变
            renderId(u);
            toast("资料已保存");
        });
    }

    private void savePassword() {
        // 长度、纯数字之类交给后端判，它的报错更具体
        final String o = oldPwd.raw(), n = newPwd.raw();
        runBusy("正在修改…", () -> {
            MeApi.changePassword(o, n);
            return true;
        }, ok -> {
            // 本机存着的密码跟着换，不然下次自动重登会失败
            session().passwordChanged(n);
            oldPwd.set("");
            newPwd.set("");
            confirmPwd.set("");
            oldPwd.setError(null);
            newPwd.setError(null);
            confirmPwd.setError(null);
            toast("密码已修改，下次登录请用新密码");
        });
    }
}
