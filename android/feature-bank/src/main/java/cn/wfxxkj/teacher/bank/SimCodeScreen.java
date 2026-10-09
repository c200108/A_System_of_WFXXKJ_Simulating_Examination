package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.graphics.Typeface;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 网页编程题的代码编辑页：上面一排文件名，下面整屏等宽输入框。
 * 用来「布置环境」（改学生打开时看到的代码）和「做标准答案」（按题目要求改一遍）。
 * 点「完成」把 {文件名: 内容} 带回去。
 */
final class SimCodeScreen extends Screen {
    private final String title;
    private final String hint;
    private final String doneLabel;
    private final Map<String, String> files = new LinkedHashMap<>();
    private final String initial;
    private ChipRow tabs;
    private EditText edit;
    private String current;

    SimCodeScreen(String title, String hint, String doneLabel, JSONObject filesJson) {
        this.title = title;
        this.hint = hint;
        this.doneLabel = doneLabel;
        Iterator<String> it = filesJson.keys();
        while (it.hasNext()) {
            String k = it.next();
            files.put(k, filesJson.optString(k, ""));
        }
        if (files.isEmpty()) files.put("index.html", "");
        initial = result().toString();
    }

    @Override
    public String title() {
        return title;
    }

    @Override
    public String subtitle() {
        return current;
    }

    @Override
    protected View onCreateView(Context ctx) {
        Palette p = Palette.of(ctx);
        LinearLayout root = V.vbox(ctx);
        root.setBackgroundColor(p.page);
        TextView tip = V.notice(ctx, hint, Tone.INFO);
        V.margins(tip, 16, 10, 16, 0);
        root.addView(tip);
        tabs = new ChipRow(ctx);
        V.pad(tabs, 16, 8, 16, 4);
        tabs.setClipToPadding(false);
        tabs.setOnPicked(o -> show(String.valueOf(o.value)));
        root.addView(tabs, V.matchWrap());

        edit = Fields.input(ctx, "在这里写代码");
        edit.setSingleLine(false);
        edit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE
                | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        edit.setTypeface(Typeface.MONOSPACE);
        edit.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        edit.setGravity(Gravity.TOP | Gravity.START);
        edit.setHorizontallyScrolling(false);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(V.MATCH, 0, 1f);
        root.addView(edit, lp);
        V.margins(edit, 16, 6, 16, 16);

        current = files.keySet().iterator().next();
        renderTabs();
        edit.setText(files.get(current));
        return root;
    }

    private void renderTabs() {
        List<Option> opts = new ArrayList<>();
        for (String k : files.keySet()) opts.add(new Option(k, k));
        tabs.setOptions(opts, current);
    }

    private void show(String name) {
        if (current != null) files.put(current, edit.getText().toString());
        current = name;
        edit.setText(files.get(name));
        invalidateChrome();
    }

    private JSONObject result() {
        if (edit != null && current != null) files.put(current, edit.getText().toString());
        JSONObject o = new JSONObject();
        for (Map.Entry<String, String> e : files.entrySet()) {
            try {
                o.put(e.getKey(), e.getValue());
            } catch (Exception ignored) {
                // 键是字符串，不会出错
            }
        }
        return o;
    }

    @Override
    public List<Action> actions() {
        return Arrays.asList(
                Action.icon(R.drawable.ic_check, doneLabel, () -> finish(result())),
                Action.menu(R.drawable.ic_add, "新建文件", this::addFile),
                Action.menu(R.drawable.ic_delete, "删除当前文件", this::removeFile).danger());
    }

    @Override
    public boolean onBack() {
        if (!initial.equals(result().toString())) {
            Dialogs.confirm(ctx(), "放弃修改？", "代码改动还没带回去，退出后就没了。", "放弃", true, this::finish);
            return true;
        }
        return false;
    }

    private void addFile() {
        Dialogs.prompt(ctx(), "新建文件", "如 about.html、main.css", "", 1, "新建", name -> {
            String n = name.trim();
            if (n.isEmpty()) return;
            if (files.containsKey(n)) {
                toast("已经有这个文件了");
                return;
            }
            files.put(current, edit.getText().toString());
            files.put(n, "");
            current = n;
            renderTabs();
            edit.setText("");
            invalidateChrome();
        });
    }

    private void removeFile() {
        if (files.size() <= 1) {
            toast("至少要留一个文件");
            return;
        }
        Dialogs.confirm(ctx(), "删除「" + current + "」？", null, "删除", true, () -> {
            files.remove(current);
            current = files.keySet().iterator().next();
            renderTabs();
            edit.setText(files.get(current));
            invalidateChrome();
        });
    }
}
