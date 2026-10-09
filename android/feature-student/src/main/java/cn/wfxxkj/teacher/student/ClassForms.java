package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.V;

/** 班级的几个弹层表单：新建 / 修改、按年级批量建班、分配老师（单个或批量）。都只有管理员能用 */
final class ClassForms {
    private ClassForms() {}

    /** 新建（editing = null）或修改班级 */
    static void edit(final Screen host, final JSONObject editing, List<JSONObject> teachers,
                     final Screen.Ok<JSONObject> saved) {
        Context c = host.ctx();
        Sheet s = new Sheet(c, editing == null ? "新建班级" : "修改班级");
        Form f = new Form(c);
        final Form.Text grade = f.text("年级", editing == null ? "" : Json.str(editing, "grade"), "如 七年级")
                .required();
        grade.maxLength(16);
        final Form.Text name = f.text("班级", editing == null ? "" : Json.str(editing, "name"), "如 3班").required();
        name.maxLength(32);
        f.row(grade, name);
        Integer owner = editing == null ? null : Kit.intOrNull(editing, "owner_id");
        final Form.Select ownerSel = f.select("任课老师", Kit.teacherOptions(teachers, "暂不分配"),
                owner == null ? Kit.NONE : owner);
        ownerSel.help("老师只能给自己名下的班发考试");
        if (editing != null) {
            f.note("改了班级名，这个班里学生的班级显示也会跟着改；已经发出去的考试不受影响。");
        }
        s.content(f.view());
        s.buttons("取消", null, "保存", () -> {
            if (!f.validate()) return;
            final Integer ownerId = Kit.idOf(ownerSel.value());
            host.runBusy("正在保存…", () -> editing == null
                    ? StudentApi.createClass(grade.value(), name.value(), ownerId)
                    : StudentApi.updateClass(Kit.id(editing),
                    Json.of("grade", grade.value(), "name", name.value(), "owner_id", ownerId)), row -> {
                s.dismiss();
                Kit.touch();
                host.toast("已保存");
                saved.done(row);
            });
        });
        s.show();
    }

    /** 按年级批量建班：七年级 1~12 班一次建完 */
    static void batch(final Screen host, final Runnable done) {
        Context c = host.ctx();
        Sheet s = new Sheet(c, "按年级批量建班");
        Form f = new Form(c);
        final Form.Text grade = f.text("年级", "", "如 七年级").required();
        grade.maxLength(16);
        final Form.Stepper start = f.stepper("从几班", 1, 1, 99);
        final Form.Stepper end = f.stepper("到几班", 12, 1, 99);
        f.row(start, end);
        final Form.Text suffix = f.text("后缀", "班", null);
        suffix.maxLength(8);
        final TextView preview = f.note("");
        Form.Changed refresh = () -> {
            String g = grade.value().isEmpty() ? "七年级" : grade.value();
            int a = start.value(), b = end.value();
            preview.setText("建出来就是「" + g + a + suffix.value() + "」" + (b > a ? " …「" + g + b + suffix.value() + "」，共 "
                    + (b - a + 1) + " 个班" : "") + "；已存在的会跳过。");
        };
        grade.onChange(refresh);
        start.onChange(refresh);
        end.onChange(refresh);
        suffix.onChange(refresh);
        refresh.changed();
        s.content(f.view());
        s.buttons("取消", null, "建班", () -> {
            if (!f.validate()) return;
            if (start.value() > end.value()) {
                end.setError("不能小于起始班号");
                return;
            }
            host.runBusy("正在建班…", () -> StudentApi.batchClasses(grade.value(), start.value(), end.value(),
                    suffix.value()), r -> {
                s.dismiss();
                Kit.touch();
                int skipped = Json.num(r, "skipped");
                host.toast("新建 " + Json.num(r, "added") + " 个班" + (skipped > 0 ? "，" + skipped + " 个已存在跳过" : ""));
                done.run();
            });
        });
        s.show();
    }

    /**
     * 把一批班分给同一位老师；选「取消分配」就是都变回未分配。
     * 只有一个班时走单个修改接口（和网页「直接在列表里换班主任」一样）。
     */
    static void owner(final Screen host, final List<JSONObject> picked, List<JSONObject> teachers,
                      final Runnable done) {
        Context c = host.ctx();
        Sheet s = new Sheet(c, picked.size() == 1 ? "分配老师" : "批量分配老师");
        Form f = new Form(c);
        f.note(picked.size() == 1
                ? "「" + Json.str(picked.get(0), "display") + "」交给谁带："
                : "把选中的 " + picked.size() + " 个班一起分给同一位老师：\n" + Kit.names(picked, "display", 30, "个班"));
        Integer cur = picked.size() == 1 ? Kit.intOrNull(picked.get(0), "owner_id") : null;
        final Form.Select sel = f.select("任课老师", Kit.teacherOptions(teachers, "取消分配（变回未分配）"),
                cur == null ? Kit.NONE : cur);
        if (picked.size() > 1) f.note("这些班原来的归属会被覆盖。");
        s.content(f.view());
        s.buttons("取消", null, "确定", () -> {
            final Integer ownerId = Kit.idOf(sel.value());
            final List<Integer> ids = Kit.ids(picked);
            host.runBusy("正在保存…", () -> {
                if (ids.size() == 1) {
                    StudentApi.updateClass(ids.get(0), Json.of("owner_id", ownerId));
                    return 1;
                }
                return StudentApi.bulkOwner(ids, ownerId);
            }, n -> {
                s.dismiss();
                Kit.touch();
                host.toast(ownerId != null
                        ? (ids.size() == 1 ? "已分配" : "已把 " + n + " 个班分配出去")
                        : (ids.size() == 1 ? "已取消分配" : "已取消 " + n + " 个班的分配"));
                done.run();
            });
        });
        s.show();
    }

    /** 删除一个班。班里有人时要手打「删除」，学生会变成未分班 */
    static void delete(final Screen host, final JSONObject cls, final Runnable done) {
        final int n = Json.num(cls, "student_count");
        String name = Json.str(cls, "display");
        Runnable go = () -> host.runBusy("正在删除…", () -> StudentApi.deleteClass(Kit.id(cls), n > 0), detached -> {
            Kit.touch();
            host.toast(detached > 0 ? "已删除，" + detached + " 名学生变成未分班" : "已删除");
            done.run();
        });
        if (n > 0) {
            Kit.confirmTyped(host.ctx(), "删除班级", "「" + name + "」里还有 " + n
                    + " 名学生。\n删除后他们会变成「未分班」，需要重新分配。", "确认删除", go);
        } else {
            Kit.confirmTyped(host.ctx(), "删除班级", "确定删除「" + name + "」吗？这个班里没有学生。", "确认删除", go);
        }
    }

    /** 批量删班：把「有人的班」单独摆出来，批量操作最怕顺手把有学生的班一起删了 */
    static void deleteMany(final Screen host, final List<JSONObject> list, final Runnable done) {
        StringBuilder sb = new StringBuilder();
        sb.append("即将删除 ").append(list.size()).append(" 个班级：\n").append(Kit.names(list, "display", 40, "个班"));
        int withStudents = 0, total = 0;
        StringBuilder occ = new StringBuilder();
        for (JSONObject c : list) {
            int n = Json.num(c, "student_count");
            if (n > 0) {
                withStudents++;
                total += n;
                occ.append("\n　").append(Json.str(c, "display")).append("（").append(n).append(" 人）");
            }
        }
        if (withStudents > 0) {
            sb.append("\n\n其中 ").append(withStudents).append(" 个班里还有学生，共 ").append(total).append(" 人：")
                    .append(occ).append("\n删除后这些学生会变成「未分班」，需要重新分配。");
        } else {
            sb.append("\n\n这些班里都没有学生。");
        }
        final boolean force = withStudents > 0;
        final List<Integer> ids = Kit.ids(list);
        Kit.confirmTyped(host.ctx(), "批量删除班级", sb, "删除 " + list.size() + " 个班", () ->
                host.runBusy("正在删除…", () -> StudentApi.bulkDeleteClasses(ids, force), r -> {
                    Kit.touch();
                    int detached = Json.num(r, "detached");
                    host.toast("已删除 " + Json.num(r, "deleted") + " 个班"
                            + (detached > 0 ? "，" + detached + " 名学生变成未分班" : ""));
                    done.run();
                }));
    }
}
