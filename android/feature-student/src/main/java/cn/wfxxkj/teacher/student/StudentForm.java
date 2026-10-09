package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.graphics.Typeface;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 添加 / 编辑一个学生（底部弹层，平板上居中）。
 * 学号是身份，编辑时不能改；密码留空 = 新建用学号当初始密码 / 编辑不改密码。
 */
final class StudentForm {
    private StudentForm() {}

    /**
     * @param editing   null = 新建
     * @param classes   能选的班（管理员全校，老师自己带的班）
     * @param preset    新建时默认放进哪个班（可为 null）
     */
    static void open(final Screen host, final JSONObject editing, List<JSONObject> classes, Integer preset,
                     final Screen.Ok<JSONObject> saved) {
        Context c = host.ctx();
        final boolean admin = host.session().isAdmin();
        Sheet s = new Sheet(c, editing == null ? "添加学生" : "编辑学生");
        Form f = new Form(c);

        final Form.Text no = f.text("学号", editing == null ? "" : Json.str(editing, "student_no"),
                "登录用，建议用学籍号").required();
        no.maxLength(32);
        if (editing != null) {
            no.edit.setEnabled(false);
            no.edit.setAlpha(0.6f);
            no.help("学号是身份，要换只能删了重建");
        } else {
            no.rule(v -> v.matches("[A-Za-z0-9_.-]+") ? null : "学号只能用字母、数字和 _ . -，不能有空格或中文");
        }
        final Form.Text name = f.text("姓名", editing == null ? "" : Json.str(editing, "name"), "学生姓名")
                .required();
        name.maxLength(64);
        f.row(no, name);

        Integer cur = editing == null ? preset : Kit.intOrNull(editing, "class_id");
        List<Option> opts = Kit.classOptions(classes, admin ? "未分班" : null);
        final Form.Select cls = f.select("班级", opts, cur == null ? (admin ? Kit.NONE : null) : cur)
                .placeholder(admin ? "选择班级" : "选择你带的班（必选）");
        if (!admin) cls.required();
        if (!admin && classes.isEmpty()) cls.help("你名下还没有班级，请管理员在「班级」页把班分给你");

        final Form.Choice gender = f.choice("性别", Option.pairs("男", "男", "女", "女", "", "不填"),
                editing == null ? "" : Json.str(editing, "gender"));

        final Form.Text pwd = f.text(editing == null ? "初始密码" : "重置密码", "",
                editing == null ? "留空则用学号当密码" : "留空则不改密码");
        pwd.rule(v -> v.length() < 6 ? "密码至少 6 位" : null);
        pwd.edit.setTypeface(Typeface.MONOSPACE);
        f.row(gender, pwd);

        s.content(f.view());
        if (editing == null) {
            s.content(V.text(c, "学生用学号登录学生平台；系统里没有邮箱，忘了密码只能由老师重置。", V.CAPTION));
        }
        s.buttons("取消", null, "保存", () -> {
            if (!f.validate()) return;
            final JSONObject body;
            Integer classId = Kit.idOf(cls.value());
            if (editing == null) {
                body = Json.of("student_no", no.value(), "name", name.value(), "class_id", classId,
                        "gender", gender.string(), "password", pwd.raw());
            } else {
                body = Json.of("name", name.value(), "class_id", classId, "gender", gender.string());
                if (!pwd.raw().isEmpty()) Json.put(body, "password", pwd.raw());
            }
            host.runBusy("正在保存…", () -> editing == null
                    ? StudentApi.createStudent(body)
                    : StudentApi.updateStudent(Kit.id(editing), body), row -> {
                s.dismiss();
                Kit.touch();
                host.toast("已保存");
                saved.done(row);
            });
        });
        s.show();
    }
}
