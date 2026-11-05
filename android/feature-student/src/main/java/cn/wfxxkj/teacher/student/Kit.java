package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.text.TextUtils;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/** 本模块里几个页面共用的小工具 */
final class Kit {
    private Kit() {}

    /** 下拉里「未分班 / 未分配」的值（Option 的 null 会被当成没选，所以用 -1 占位） */
    static final int NONE = -1;

    // ---------- 数据变了，让别的页面回来时刷新 ----------

    private static int version;

    /** 学生或班级有增删改时调一下 */
    static void touch() {
        version++;
    }

    static int version() {
        return version;
    }

    // ---------- 取字段 ----------

    static int id(JSONObject o) {
        return o == null ? 0 : o.optInt("id");
    }

    /** 可能是 null 的整数字段 */
    static Integer intOrNull(JSONObject o, String key) {
        Long v = Json.longOrNull(o, key);
        return v == null ? null : v.intValue();
    }

    static List<Integer> ids(List<JSONObject> rows) {
        List<Integer> out = new ArrayList<>();
        for (JSONObject r : rows) out.add(id(r));
        return out;
    }

    /** 「张三、李四、王五 等 12 人」 */
    static String names(List<JSONObject> rows, String key, int max, String unit) {
        List<String> parts = new ArrayList<>();
        for (int i = 0; i < rows.size() && i < max; i++) parts.add(Json.str(rows.get(i), key));
        String s = TextUtils.join("、", parts);
        if (rows.size() > max) s += " 等 " + rows.size() + " " + unit;
        return s;
    }

    /** 名字：姓名，没有就用户名 */
    static String teacherName(JSONObject t) {
        String n = Json.str(t, "name");
        return n.isEmpty() ? Json.str(t, "username") : n;
    }

    // ---------- 下拉选项 ----------

    /** 班级选项。noneLabel 不为 null 时最前面加一项（值 NONE） */
    static List<Option> classOptions(List<JSONObject> classes, String noneLabel) {
        List<Option> out = new ArrayList<>();
        if (noneLabel != null) out.add(new Option(NONE, noneLabel));
        for (JSONObject c : classes) {
            String owner = Json.str(c, "owner_name");
            out.add(new Option(id(c), Json.str(c, "display"),
                    Json.num(c, "student_count") + " 名学生 · " + (owner.isEmpty() ? "未分配老师" : owner)));
        }
        return out;
    }

    /** 教师选项：停用的账号不能接班，不列出来 */
    static List<Option> teacherOptions(List<JSONObject> users, String noneLabel) {
        List<Option> out = new ArrayList<>();
        if (noneLabel != null) out.add(new Option(NONE, noneLabel));
        for (JSONObject t : users) {
            if (!Json.bool(t, "is_active")) continue;
            boolean admin = "admin".equals(Json.str(t, "role"));
            out.add(new Option(id(t), teacherName(t) + (admin ? "（管理员）" : ""),
                    "账号 " + Json.str(t, "username")));
        }
        return out;
    }

    /** 下拉的值 → 接口要的班级 / 教师 id（NONE → null） */
    static Integer idOf(Object v) {
        if (v == null) return null;
        int i = v instanceof Number ? ((Number) v).intValue() : Integer.parseInt(String.valueOf(v));
        return i == NONE ? null : i;
    }

    // ---------- 导入结果 ----------

    /**
     * 导入（表格 / 粘贴）完成后的说明文字，和网页版措辞一致：
     * 每一行错误只写「哪一行、错在哪」，「怎么改」由后端的 hint 统一给一句。
     */
    static String importReport(JSONObject res, boolean fromFile) {
        int added = Json.num(res, "added");
        int skipped = Json.num(res, "skipped");
        int errorCount = Json.num(res, "error_count");
        List<String> head = new ArrayList<>();
        head.add("新建 " + added + " 个账号");
        if (skipped > 0) head.add(skipped + " 个学号已存在，跳过");
        if (errorCount > 0) head.add(errorCount + (fromFile ? " 行没导进来" : " 行格式不对，没有导入"));
        String first = TextUtils.join("，", head);
        List<String> used = Json.strings(Json.arr(res, "classes"));
        String fallback = Json.str(res, "student_class");
        if (fromFile && !used.isEmpty()) first += "，分别进了：" + TextUtils.join("、", used) + "。";
        else if (fromFile && !fallback.isEmpty()) first += "，都归到「" + fallback + "」。";
        else first += "。";

        List<String> parts = new ArrayList<>();
        parts.add(first);
        parts.add("初始密码 123456，请提醒学生登录后到「首页」改密码。");
        List<String> errors = Json.strings(Json.arr(res, "errors"));
        if (!errors.isEmpty()) {
            parts.add("这些行没能导入：\n" + TextUtils.join("\n", errors));
            if (errorCount > errors.size()) {
                parts.add("（还有 " + (errorCount - errors.size()) + " 行同类问题没列出来）");
            }
        }
        List<String> skippedSheets = Json.strings(Json.arr(res, "sheets_skipped"));
        if (!skippedSheets.isEmpty()) parts.add("跳过了这些工作表：" + TextUtils.join("、", skippedSheets));
        String hint = Json.str(res, "hint");
        if (!hint.isEmpty()) parts.add(hint);
        return TextUtils.join("\n\n", parts);
    }

    // ---------- 危险操作：要手打「删除」两个字 ----------

    /**
     * 和网页版一样，删除前要求输入「删除」两个字才放行（批量删学生、删有人的班）。
     */
    static void confirmTyped(Context c, String title, CharSequence message, String okLabel, Runnable onOk) {
        Sheet s = new Sheet(c, title);
        TextView msg = V.text(c, message, V.BODY2);
        s.content(msg);
        TextView ask = V.text(c, "确认请输入「删除」两个字：", V.LABEL);
        LinearLayout box = V.vbox(c);
        V.addTop(box, ask, 14);
        EditText input = Fields.input(c, "在这里输入：删除");
        V.addTop(box, input, 8);
        TextView err = V.text(c, "", V.CAPTION);
        err.setTextColor(Palette.of(c).danger);
        err.setVisibility(android.view.View.GONE);
        V.addTop(box, err, 4);
        s.content(box);
        s.buttons("取消", null, okLabel, () -> {
            if ("删除".equals(input.getText().toString().trim())) {
                s.dismiss();
                onOk.run();
            } else {
                err.setText("请准确输入「删除」两个字");
                err.setVisibility(android.view.View.VISIBLE);
                input.setActivated(true);
            }
        }, true);
        s.show();
    }

    /** 可点的筛选按钮：「全部班级 ▾」 */
    static TextView dropChip(Context c, String label, android.view.View.OnClickListener l) {
        TextView t = V.chip(c, label, false, l);
        android.graphics.drawable.Drawable d = c.getDrawable(cn.wfxxkj.teacher.core.R.drawable.ic_expand_more);
        if (d != null) {
            d = d.mutate();
            int s = Ui.dp(c, 18);
            d.setBounds(0, 0, s, s);
            d.setTint(Palette.of(c).text2);
            t.setCompoundDrawablesRelative(null, null, d, null);
            t.setCompoundDrawablePadding(Ui.dp(c, 2));
        }
        t.setMinHeight(Ui.dp(c, 44));
        t.setMaxWidth(Ui.dp(c, 160));
        t.setEllipsize(TextUtils.TruncateAt.END);
        V.pad(t, 14, 0, 8, 0);
        return t;
    }

    static void setDropChip(TextView t, String label, boolean active) {
        android.graphics.drawable.Drawable[] ds = t.getCompoundDrawablesRelative();
        t.setText(label);
        V.setChip(t, active);
        t.setCompoundDrawablesRelative(ds[0], ds[1], ds[2], ds[3]);
        if (ds[2] != null) ds[2].setTint(active ? Palette.of(t.getContext()).primary : Palette.of(t.getContext()).text2);
    }
}
