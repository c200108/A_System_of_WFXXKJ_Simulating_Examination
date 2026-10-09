package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 选择题答案：一排字母按钮，点亮哪个答案就是哪个。
 * 一般单选；题库里也有导入的多选答案（如 AB），所以允许点亮多个，保存时按字母顺序拼起来。
 */
final class AnswerChips extends LinearLayout {
    private final FlowBox flow;
    private final Set<String> on = new TreeSet<>();
    private final List<TextView> chips = new ArrayList<>();
    private List<String> labels = new ArrayList<>();

    AnswerChips(Context c, String answer) {
        super(c);
        setOrientation(VERTICAL);
        addView(V.pad(V.text(c, "答案 *", V.LABEL), 2, 0, 0, 6));
        flow = new FlowBox(c, 8, 8);
        addView(flow, V.matchWrap());
        TextView hint = V.text(c, "点选正确选项；多选题可以点亮多个", V.CAPTION);
        V.pad(hint, 2, 4, 0, 0);
        addView(hint);
        if (answer != null) {
            for (char ch : answer.toUpperCase().toCharArray()) {
                if (ch >= 'A' && ch <= 'Z') on.add(String.valueOf(ch));
            }
        }
    }

    void setLabels(List<String> ls) {
        labels = new ArrayList<>(ls);
        on.retainAll(labels);
        flow.removeAllViews();
        chips.clear();
        for (final String l : labels) {
            TextView chip = V.chip(getContext(), "  " + l + "  ", on.contains(l), v -> {
                if (on.contains(l)) on.remove(l);
                else on.add(l);
                render();
            });
            chips.add(chip);
            flow.addView(chip);
        }
    }

    private void render() {
        for (int i = 0; i < labels.size(); i++) V.setChip(chips.get(i), on.contains(labels.get(i)));
    }

    String value() {
        StringBuilder sb = new StringBuilder();
        for (String s : on) sb.append(s);
        return sb.toString();
    }
}
