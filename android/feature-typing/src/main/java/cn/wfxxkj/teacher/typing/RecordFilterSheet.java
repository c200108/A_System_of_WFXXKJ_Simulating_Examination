package cn.wfxxkj.teacher.typing;

import android.content.Context;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;

/**
 * 打字成绩的筛选与排序弹层：班级、难度、日期范围、排序方式。
 * 模块和姓名在列表上方直接点 / 搜，不放这里。
 */
final class RecordFilterSheet {
    interface Applied {
        void applied(TypingApi.Filter f);
    }

    /** 排序：和网页表头可排的列一一对应 */
    static final List<Option> SORTS = Option.pairs(
            "time", "练习时间", "speed", "速度", "accuracy", "正确率", "duration", "用时",
            "stars", "评价（星级）", "name", "姓名", "class", "班级");

    private RecordFilterSheet() {}

    static void show(Context c, TypingApi.Filter current, List<String> classes, Applied onApply) {
        Sheet s = new Sheet(c, "筛选与排序");
        Form f = new Form(c);

        List<Option> clsOpts = new ArrayList<>();
        clsOpts.add(new Option("", "全部班级"));
        for (String k : classes) clsOpts.add(new Option(k, k));
        Form.Select cls = f.select("班级", clsOpts, current.studentClass);

        List<Option> diffOpts = new ArrayList<>();
        diffOpts.add(new Option("", "全部"));
        for (String d : TypingApi.DIFFICULTIES) diffOpts.add(new Option(d, d));
        Form.Choice diff = f.choice("难度", diffOpts, current.difficulty);

        Form.DateTime from = f.date("开始日期", current.dateFrom.isEmpty() ? null : current.dateFrom + "T00:00:00");
        Form.DateTime to = f.date("结束日期", current.dateTo.isEmpty() ? null : current.dateTo + "T00:00:00");
        f.row(from, to);

        Form.Select sort = f.select("排序", SORTS, current.sort);
        Form.Choice order = f.choice("顺序", Option.pairs("desc", "从高到低 / 从新到旧", "asc", "从低到高 / 从旧到新"),
                current.order);

        s.content(f.view());
        s.buttons("重置", () -> {
            TypingApi.Filter out = current.copy();
            out.studentClass = "";
            out.difficulty = "";
            out.dateFrom = "";
            out.dateTo = "";
            out.sort = "time";
            out.order = "desc";
            s.dismiss();
            onApply.applied(out);
        }, "应用", () -> {
            String a = from.date() == null ? "" : from.date();
            String b = to.date() == null ? "" : to.date();
            if (!a.isEmpty() && !b.isEmpty() && a.compareTo(b) > 0) {
                to.setError("结束日期不能早于开始日期");
                return;
            }
            TypingApi.Filter out = current.copy();
            out.studentClass = cls.string();
            out.difficulty = diff.string();
            out.dateFrom = a;
            out.dateTo = b;
            out.sort = sort.string().isEmpty() ? "time" : sort.string();
            out.order = order.string().isEmpty() ? "desc" : order.string();
            s.dismiss();
            onApply.applied(out);
        });
        s.show();
    }

    /** 排序方式的文字，筛选胶囊上显示 */
    static String sortLabel(TypingApi.Filter f) {
        return Option.labelOf(SORTS, f.sort) + ("asc".equals(f.order) ? " ↑" : " ↓");
    }
}
