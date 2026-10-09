package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;

/**
 * 常用的弹窗：确认、提示、输入一句话、单选、多选、操作菜单。全部基于 {@link Sheet}，
 * 手机上从底部弹出，平板上居中。
 */
public final class Dialogs {
    private Dialogs() {}

    public interface TextResult {
        void done(String text);
    }

    public interface Picked {
        void done(Option option);
    }

    public interface MultiPicked {
        void done(List<Object> values);
    }

    /** 确认一下再做。danger = 删除这类不可恢复的操作，按钮标红 */
    public static Sheet confirm(Context c, String title, CharSequence message, String okLabel,
                                boolean danger, Runnable onOk) {
        Sheet s = new Sheet(c, title);
        if (!TextUtils.isEmpty(message)) s.content(V.text(c, message, V.BODY2));
        s.buttons("取消", null, okLabel, () -> {
            s.dismiss();
            onOk.run();
        }, danger);
        return s.show();
    }

    public static Sheet alert(Context c, String title, CharSequence message) {
        Sheet s = new Sheet(c, title);
        TextView t = V.text(c, message, V.BODY2);
        t.setTextIsSelectable(true);
        s.content(t);
        s.buttons(null, null, "知道了", s::dismiss);
        return s.show();
    }

    /** 输入一句话（或一段话：lines &gt; 1） */
    public static Sheet prompt(Context c, String title, String hint, String initial, int lines,
                               String okLabel, TextResult onOk) {
        Sheet s = new Sheet(c, title);
        EditText e = Fields.input(c, hint);
        if (lines > 1) {
            e.setSingleLine(false);
            e.setMinLines(lines);
            e.setGravity(Gravity.TOP | Gravity.START);
            e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        }
        if (initial != null) {
            e.setText(initial);
            e.setSelection(e.length());
        }
        s.content(e);
        s.buttons("取消", null, okLabel == null ? "确定" : okLabel, () -> {
            s.dismiss();
            onOk.done(e.getText().toString());
        });
        s.show();
        Ui.showKeyboard(e);
        return s;
    }

    /** 单选列表，点一项就选中并关闭 */
    public static Sheet choose(Context c, String title, List<Option> options, Object selected, Picked onPick) {
        Sheet s = new Sheet(c, title).flush();
        Palette p = Palette.of(c);
        for (final Option o : options) {
            boolean on = Option.same(o.value, selected);
            LinearLayout row = V.hbox(c);
            V.pad(row, 20, 12, 20, 12);
            row.setMinimumHeight(Ui.dp(c, 52));
            LinearLayout texts = V.vbox(c);
            TextView t = V.text(c, o.label, V.BODY);
            if (on) {
                t.setTextColor(p.primary);
                V.bold(t);
            }
            texts.addView(t);
            if (!TextUtils.isEmpty(o.sub)) texts.addView(V.text(c, o.sub, V.CAPTION));
            row.addView(texts, V.fill());
            if (on) row.addView(V.icon(c, R.drawable.ic_check, p.primary, 22));
            V.clickable(row, 0, v -> {
                s.dismiss();
                onPick.done(o);
            });
            s.content(row);
        }
        return s.show();
    }

    /** 多选列表：勾选后点「确定」 */
    public static Sheet chooseMany(Context c, String title, List<Option> options, List<?> selected,
                                   MultiPicked onDone) {
        Sheet s = new Sheet(c, title).flush();
        final Set<Integer> on = new LinkedHashSet<>();
        final List<CheckBox> boxes = new ArrayList<>();
        for (int i = 0; i < options.size(); i++) {
            Option o = options.get(i);
            boolean sel = false;
            if (selected != null) for (Object x : selected) if (Option.same(x, o.value)) sel = true;
            if (sel) on.add(i);
            LinearLayout row = V.hbox(c);
            V.pad(row, 16, 6, 20, 6);
            row.setMinimumHeight(Ui.dp(c, 48));
            CheckBox cb = new CheckBox(c);
            cb.setChecked(sel);
            cb.setClickable(false);
            boxes.add(cb);
            row.addView(cb);
            LinearLayout texts = V.vbox(c);
            texts.addView(V.text(c, o.label, V.BODY));
            if (!TextUtils.isEmpty(o.sub)) texts.addView(V.text(c, o.sub, V.CAPTION));
            row.addView(texts, V.fill());
            final int idx = i;
            V.clickable(row, 0, v -> {
                if (on.contains(idx)) on.remove(idx);
                else on.add(idx);
                cb.setChecked(on.contains(idx));
            });
            s.content(row);
        }
        LinearLayout tools = V.hbox(c);
        V.pad(tools, 12, 0, 12, 0);
        tools.addView(V.button(c, "全选", V.BTN_TEXT, v -> {
            for (int i = 0; i < boxes.size(); i++) {
                on.add(i);
                boxes.get(i).setChecked(true);
            }
        }));
        tools.addView(V.button(c, "清空", V.BTN_TEXT, v -> {
            on.clear();
            for (CheckBox b : boxes) b.setChecked(false);
        }));
        if (options.size() > 3) s.body().addView(tools, 0);
        s.buttons("取消", null, "确定", () -> {
            s.dismiss();
            List<Object> out = new ArrayList<>();
            for (int i = 0; i < options.size(); i++) if (on.contains(i)) out.add(options.get(i).value);
            onDone.done(out);
        });
        return s.show();
    }

    /** 操作菜单（长按、「更多」）：一列带图标的操作 */
    public static Sheet actions(Context c, String title, List<Action> actions) {
        Sheet s = new Sheet(c, title).flush();
        Palette p = Palette.of(c);
        for (final Action a : actions) {
            LinearLayout row = V.hbox(c);
            V.pad(row, 20, 12, 20, 12);
            row.setMinimumHeight(Ui.dp(c, 52));
            int color = a.danger ? p.danger : p.text;
            if (a.icon != 0) {
                ImageView iv = V.icon(c, a.icon, a.danger ? p.danger : p.text2, 22);
                row.addView(iv);
                row.addView(V.space(c, 16));
            }
            TextView t = V.text(c, a.label, V.BODY);
            t.setTextColor(color);
            row.addView(t, V.fill());
            if (!a.enabled) row.setAlpha(0.4f);
            V.clickable(row, 0, v -> {
                if (!a.enabled) return;
                s.dismiss();
                if (a.run != null) a.run.run();
            });
            s.content(row);
        }
        return s.show();
    }

    /** 用在一组按钮前的说明文字 */
    public static View caption(Context c, String text) {
        TextView t = V.text(c, text, V.CAPTION);
        V.pad(t, 20, 0, 20, 8);
        return t;
    }
}
