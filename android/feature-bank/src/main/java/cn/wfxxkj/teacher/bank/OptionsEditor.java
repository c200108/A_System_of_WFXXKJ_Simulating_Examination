package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 选择题的选项编辑：每行「字母 + 输入框 + 删除」，下面「添加选项」。
 * 留空的选项保存时不提交（和网页「留空表示不用这一项」一致）。字母按顺序自动排 A、B、C…
 */
final class OptionsEditor extends LinearLayout {
    private static final int MAX = 8;

    private final LinearLayout rows;
    private final TextView add;
    private final Runnable onChange;
    private final List<EditText> edits = new ArrayList<>();

    OptionsEditor(Context c, List<String[]> initial, Runnable onChange) {
        super(c);
        this.onChange = onChange;
        setOrientation(VERTICAL);
        addView(V.pad(V.text(c, "可选项", V.LABEL), 2, 0, 0, 6));
        rows = V.vbox(c);
        addView(rows, V.matchWrap());
        add = V.button(c, R.drawable.ic_add, "添加选项", V.BTN_TEXT, v -> {
            addRow("");
            changed();
            edits.get(edits.size() - 1).requestFocus();
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        lp.topMargin = Ui.dp(c, 2);
        addView(add, lp);
        TextView hint = V.text(c, "留空表示不用这一项", V.CAPTION);
        V.pad(hint, 2, 0, 0, 0);
        addView(hint);
        for (String[] o : initial) addRow(o[1]);
        relabel();
    }

    private void addRow(String content) {
        Context c = getContext();
        LinearLayout row = V.hbox(c);
        TextView label = V.text(c, "", V.LABEL);
        label.setGravity(Gravity.CENTER);
        label.setTextColor(Palette.of(c).text2);
        label.setBackground(V.round(c, Palette.of(c).surfaceAlt, 14));
        int s = Ui.dp(c, 28);
        row.addView(label, new LinearLayout.LayoutParams(s, s));
        EditText e = Fields.input(c, "选项内容");
        e.setText(content);
        e.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence x, int a, int b, int d) {}

            @Override
            public void onTextChanged(CharSequence x, int a, int b, int d) {}

            @Override
            public void afterTextChanged(Editable x) {
                changed();
            }
        });
        LinearLayout.LayoutParams lp = V.fill();
        lp.setMarginStart(Ui.dp(c, 10));
        row.addView(e, lp);
        final EditText ref = e;
        row.addView(V.iconButton(c, R.drawable.ic_close, "删除这一项", v -> {
            int i = edits.indexOf(ref);
            if (i < 0 || edits.size() <= 2) return;
            edits.remove(i);
            rows.removeViewAt(i);
            relabel();
            changed();
        }));
        LinearLayout.LayoutParams rl = V.matchWrap();
        rl.bottomMargin = Ui.dp(c, 8);
        rows.addView(row, rl);
        edits.add(e);
        relabel();
    }

    private void relabel() {
        for (int i = 0; i < rows.getChildCount(); i++) {
            LinearLayout row = (LinearLayout) rows.getChildAt(i);
            ((TextView) row.getChildAt(0)).setText(String.valueOf((char) ('A' + i)));
            V.enable(row.getChildAt(2), rows.getChildCount() > 2);
        }
        add.setVisibility(edits.size() >= MAX ? GONE : VISIBLE);
    }

    private void changed() {
        if (onChange != null) onChange.run();
    }

    List<String> labels() {
        List<String> out = new ArrayList<>();
        for (int i = 0; i < edits.size(); i++) out.add(String.valueOf((char) ('A' + i)));
        return out;
    }

    /** [字母, 内容] */
    List<String[]> values() {
        List<String[]> out = new ArrayList<>();
        for (int i = 0; i < edits.size(); i++) {
            out.add(new String[]{String.valueOf((char) ('A' + i)), edits.get(i).getText().toString()});
        }
        return out;
    }

    String contentOf(String label) {
        for (String[] o : values()) if (o[0].equalsIgnoreCase(label)) return o[1].trim();
        return "";
    }
}
