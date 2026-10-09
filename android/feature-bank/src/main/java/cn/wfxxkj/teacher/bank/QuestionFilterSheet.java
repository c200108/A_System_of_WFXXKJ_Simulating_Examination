package cn.wfxxkj.teacher.bank;

import android.content.Context;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;

/**
 * 筛选弹层：知识范围、来源、难度、只看必出（题型在列表上方的标签条里选，关键字在搜索框里）。
 * 对应网页工具栏上那几个下拉框和「只看必出」勾选框。
 */
final class QuestionFilterSheet {

    interface Applied {
        void applied(BankApi.Filter f);
    }

    private QuestionFilterSheet() {}

    static void show(Context c, BankApi.Filter current, List<String> scopes, List<String> sources, Applied onApply) {
        Sheet s = new Sheet(c, "筛选题目");
        Form f = new Form(c);

        List<Option> scopeOpts = new ArrayList<>();
        scopeOpts.add(new Option("", "全部知识范围"));
        for (String x : scopes) scopeOpts.add(new Option(x, x));
        Form.Select scope = f.select("知识范围", scopeOpts, current.scope);

        List<Option> srcOpts = new ArrayList<>();
        srcOpts.add(new Option("", "全部来源"));
        for (String x : sources) srcOpts.add(new Option(x, x));
        if (!current.source.isEmpty() && !sources.contains(current.source)) {
            srcOpts.add(new Option(current.source, current.source));
        }
        Form.Select source = f.select("来源", srcOpts, current.source);

        List<Option> lvOpts = new ArrayList<>();
        lvOpts.add(new Option(0, "不限"));
        for (int i = 1; i <= 5; i++) lvOpts.add(new Option(i, i + " " + Bank.LEVEL_TEXT[i]));
        Form.Choice level = f.choice("难度", lvOpts, current.difficulty);

        Form.Toggle pinned = f.toggle("只看必出题", "组卷时一定会抽到的题", current.onlyPinned);
        f.row(scope, source);

        s.content(f.view());
        s.buttons("重置", () -> {
            s.dismiss();
            BankApi.Filter out = current.copy();
            out.scope = "";
            out.source = "";
            out.difficulty = 0;
            out.onlyPinned = false;
            onApply.applied(out);
        }, "查看结果", () -> {
            s.dismiss();
            BankApi.Filter out = current.copy();
            out.scope = scope.string();
            out.source = source.string();
            Object lv = level.value();
            out.difficulty = lv instanceof Number ? ((Number) lv).intValue() : 0;
            out.onlyPinned = pinned.value();
            onApply.applied(out);
        });
        s.show();
    }
}
