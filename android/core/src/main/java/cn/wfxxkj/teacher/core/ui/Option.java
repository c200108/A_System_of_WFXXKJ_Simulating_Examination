package cn.wfxxkj.teacher.core.ui;

import java.util.ArrayList;
import java.util.List;

/** 下拉、单选、多选里的一个选项：值 + 显示文字（+ 可选的说明） */
public final class Option {
    public final Object value;
    public final String label;
    public final String sub;

    public Option(Object value, String label) {
        this(value, label, null);
    }

    public Option(Object value, String label, String sub) {
        this.value = value;
        this.label = label;
        this.sub = sub;
    }

    /** 值和文字一样的一组选项：Option.of("单选题", "多选题") */
    public static List<Option> of(String... labels) {
        List<Option> out = new ArrayList<>();
        for (String s : labels) out.add(new Option(s, s));
        return out;
    }

    /** 成对给：Option.pairs("single", "单选题", "multi", "多选题") */
    public static List<Option> pairs(Object... kv) {
        List<Option> out = new ArrayList<>();
        for (int i = 0; i + 1 < kv.length; i += 2) out.add(new Option(kv[i], String.valueOf(kv[i + 1])));
        return out;
    }

    public static String labelOf(List<Option> options, Object value) {
        for (Option o : options) if (same(o.value, value)) return o.label;
        return value == null ? "" : String.valueOf(value);
    }

    /** 值比较：数字按数值比（JSON 里 3 和 3.0 算同一个） */
    public static boolean same(Object a, Object b) {
        if (a == null || b == null) return a == b;
        if (a instanceof Number && b instanceof Number) {
            return ((Number) a).doubleValue() == ((Number) b).doubleValue();
        }
        return a.equals(b) || String.valueOf(a).equals(String.valueOf(b));
    }
}
