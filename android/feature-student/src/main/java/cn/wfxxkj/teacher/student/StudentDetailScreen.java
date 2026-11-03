package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 一个学生的详情：资料一览，下面一组操作（编辑、调班、重置密码、启用/停用、删除）。
 * 网页上这些散在表格的「编辑」按钮和批量操作里，APP 上点卡片进来一处做完。
 */
final class StudentDetailScreen extends Screen {
    private JSONObject s;
    private List<JSONObject> classes;
    private LinearLayout page;

    StudentDetailScreen(JSONObject student, List<JSONObject> classes) {
        this.s = student;
        this.classes = classes == null ? new ArrayList<>() : classes;
    }

    @Override
    public String title() {
        return Json.str(s, "name");
    }

    @Override
    public String subtitle() {
        return "学号 " + Json.str(s, "student_no");
    }

    @Override
    protected View onCreateView(Context ctx) {
        page = V.page(ctx);
        ScrollView sv = V.scroll(ctx, page);
        render();
        return sv;
    }

    @Override
    protected void onFirstShow() {
        // 从班级详情进来时没带班级列表，补一份（编辑、调班要用）
        if (classes.isEmpty()) {
            final boolean admin = session().isAdmin();
            run(() -> StudentApi.pickableClasses(admin), cl -> classes = cl, e -> true);
        }
    }

    @Override
    public List<Action> actions() {
        return Arrays.asList(
                Action.icon(R.drawable.ic_analytics, "学情", () -> push(new StudentInsightScreen(Kit.id(s), Json.str(s, "name")))),
                Action.icon(R.drawable.ic_edit, "编辑", this::edit));
    }

    private void render() {
        Context c = ctx();
        page.removeAllViews();
        Palette p = Palette.of(c);
        boolean active = Json.bool(s, "is_active");

        // 头部：头像 + 姓名 + 标签
        LinearLayout head = V.card(c);
        LinearLayout row = V.hbox(c);
        TextView av = V.avatar(c, Json.str(s, "name"), 56);
        if (!active) av.setAlpha(0.4f);
        row.addView(av);
        LinearLayout texts = V.vbox(c);
        texts.addView(V.text(c, Json.str(s, "name"), V.H1));
        LinearLayout tags = V.hbox(c);
        String cls = Json.str(s, "student_class");
        tags.addView(V.tag(c, cls.isEmpty() ? "未分班" : cls, cls.isEmpty() ? Tone.WARNING : Tone.PRIMARY));
        String g = Json.str(s, "gender");
        if (!g.isEmpty()) V.addStart(tags, V.tag(c, g, "男".equals(g) ? Tone.INFO : Tone.VIOLET), 6);
        V.addStart(tags, V.tag(c, active ? "正常" : "已停用", active ? Tone.SUCCESS : Tone.DANGER), 6);
        V.addTop(texts, tags, 6);
        LinearLayout.LayoutParams tlp = V.fill();
        tlp.setMarginStart(dp(16));
        row.addView(texts, tlp);
        head.addView(row);
        page.addView(head, V.matchWrap());

        // 资料
        LinearLayout info = V.card(c);
        info.addView(V.kv(c, "学号", Json.str(s, "student_no")));
        info.addView(V.kv(c, "姓名", Json.str(s, "name")));
        info.addView(V.kv(c, "班级", cls.isEmpty() ? "未分班" : cls));
        info.addView(V.kv(c, "性别", g.isEmpty() ? "—" : g));
        info.addView(V.kv(c, "状态", active ? "正常" : "已停用（登不上学生平台）"));
        info.addView(V.kv(c, "创建时间", Fmt.dateTime(Json.str(s, "created_at"))));
        page.addView(V.section(c, "资料", "复制学号", v -> {
            Sys.copy(c, "学号", Json.str(s, "student_no"));
            toast("已复制学号");
        }));
        page.addView(info, V.matchWrap());

        // 学情：考试成绩与排名、打字、第三方教学网页的数据（5.1.2）
        LinearLayout ins = V.vbox(c);
        ins.setBackground(V.stroke(c, p.surface, p.border, 16));
        ins.setClipToOutline(true);
        ins.addView(V.row(c, R.drawable.ic_analytics, Tone.VIOLET, "学情", "考试成绩与排名、打字、教学网页数据",
                null, v -> push(new StudentInsightScreen(Kit.id(s), Json.str(s, "name")))));
        V.addTop(page, ins, 12);

        // 操作
        page.addView(V.section(c, "操作", null, null));
        LinearLayout ops = V.vbox(c);
        ops.setBackground(V.stroke(c, p.surface, p.border, 16));
        ops.setClipToOutline(true);
        ops.addView(V.row(c, R.drawable.ic_edit, Tone.PRIMARY, "编辑资料", "改姓名、班级、性别，或设一个新密码",
                null, v -> edit()));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, R.drawable.ic_class, Tone.INFO, "调班", "当前：" + (cls.isEmpty() ? "未分班" : cls),
                null, v -> move()));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, R.drawable.ic_key, Tone.WARNING, "重置密码", "改回学号，学生登录后自己再改",
                null, v -> resetPassword()));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, active ? R.drawable.ic_block : R.drawable.ic_check_circle,
                active ? Tone.NEUTRAL : Tone.SUCCESS, active ? "停用账号" : "启用账号",
                active ? "停用后登不上，数据都在，随时可以再启用" : "恢复登录学生平台", null, v -> toggleActive()));
        ops.addView(V.divider(c));
        LinearLayout del = V.row(c, R.drawable.ic_delete, Tone.DANGER, "删除账号",
                "交过的卷子和练字记录会保留，删除无法撤销", null, v -> delete());
        ((TextView) ((LinearLayout) del.getChildAt(2)).getChildAt(0)).setTextColor(p.danger);
        ops.addView(del);
        page.addView(ops, V.matchWrap());

        TextView tip = V.text(c, "学生在学生平台（网站首页）用学号和密码登录。", V.CAPTION);
        tip.setGravity(Gravity.CENTER);
        V.addTop(page, tip, 16);
        invalidateChrome();
    }

    private void updated(JSONObject row) {
        s = row;
        Kit.touch();
        render();
    }

    private void edit() {
        StudentForm.open(this, s, classes, null, this::updated);
    }

    private void move() {
        boolean admin = session().isAdmin();
        Dialogs.choose(ctx(), "调到哪个班", Kit.classOptions(classes, admin ? "未分班" : null),
                Kit.intOrNull(s, "class_id") == null ? Kit.NONE : Kit.intOrNull(s, "class_id"), o -> {
                    final Integer target = Kit.idOf(o.value);
                    runBusy("正在调班…", () -> StudentApi.updateStudent(Kit.id(s), Json.of("class_id", target)), r -> {
                        toast("已调到「" + o.label + "」");
                        updated(r);
                    });
                });
    }

    private void resetPassword() {
        Dialogs.confirm(ctx(), "重置密码", "把「" + Json.str(s, "name") + "」的密码重置成学号（"
                + Json.str(s, "student_no") + "）？", "重置", false, () ->
                runBusy("正在重置…", () -> StudentApi.bulk(Arrays.asList(Kit.id(s)), "reset_password"), n ->
                        toast("已重置，新密码就是学号")));
    }

    private void toggleActive() {
        final boolean active = Json.bool(s, "is_active");
        Runnable go = () -> runBusy(active ? "正在停用…" : "正在启用…",
                () -> StudentApi.updateStudent(Kit.id(s), Json.of("is_active", !active)), r -> {
                    toast(active ? "已停用" : "已启用");
                    updated(r);
                });
        if (active) {
            Dialogs.confirm(ctx(), "停用账号", "停用后「" + Json.str(s, "name") + "」登不上学生平台，数据都在，随时可以再启用。",
                    "停用", true, go);
        } else {
            go.run();
        }
    }

    private void delete() {
        Kit.confirmTyped(ctx(), "删除学生账号", "即将永久删除「" + Json.str(s, "name") + "」（" + Json.str(s, "student_no")
                        + "）的账号。\n\n交过的卷子和练过的字都会保留，只是不再挂在账号上。删除无法撤销；"
                        + "只是想让人登不上的话，用「停用账号」。",
                "确认删除", () -> runBusy("正在删除…",
                        () -> StudentApi.bulk(Arrays.asList(Kit.id(s)), "delete"), n -> {
                            Kit.touch();
                            toast("已删除");
                            finish();
                        }));
    }
}
