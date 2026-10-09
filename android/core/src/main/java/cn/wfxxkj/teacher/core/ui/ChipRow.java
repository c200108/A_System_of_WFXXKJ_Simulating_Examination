package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/**
 * 一排可横向滑动的单选筛选条件：「全部 | 单选题 | 多选题 | 判断题 …」。
 * 点一个就选中它并回调。
 */
public class ChipRow extends HorizontalScrollView {

    public interface Picked {
        void picked(Option option);
    }

    private final LinearLayout row;
    private final List<Option> options = new ArrayList<>();
    private final List<TextView> chips = new ArrayList<>();
    private Object value;
    private Picked listener;

    public ChipRow(Context c) {
        super(c);
        setHorizontalScrollBarEnabled(false);
        row = V.hbox(c);
        V.pad(row, 0, 4, 0, 4);
        addView(row);
        setClipToPadding(false);
    }

    public ChipRow setOptions(List<Option> opts, Object selected) {
        row.removeAllViews();
        options.clear();
        chips.clear();
        value = selected;
        for (final Option o : opts) {
            TextView chip = V.chip(getContext(), o.label, Option.same(o.value, selected), v -> {
                set(o.value);
                if (listener != null) listener.picked(o);
            });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
            if (!chips.isEmpty()) lp.setMarginStart(Ui.dp(getContext(), 8));
            row.addView(chip, lp);
            options.add(o);
            chips.add(chip);
        }
        return this;
    }

    public void setOnPicked(Picked p) {
        listener = p;
    }

    public Object value() {
        return value;
    }

    public void set(Object v) {
        value = v;
        for (int i = 0; i < options.size(); i++) V.setChip(chips.get(i), Option.same(options.get(i).value, v));
    }

    /** 改某个选项的文字（例如带上数量「单选题 120」） */
    public void setLabel(Object optionValue, String label) {
        for (int i = 0; i < options.size(); i++) {
            if (Option.same(options.get(i).value, optionValue)) chips.get(i).setText(label);
        }
    }
}
