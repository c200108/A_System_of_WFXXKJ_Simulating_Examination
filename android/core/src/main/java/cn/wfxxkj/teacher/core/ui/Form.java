package cn.wfxxkj.teacher.core.ui;

import android.app.DatePickerDialog;
import android.app.TimePickerDialog;
import android.content.Context;
import android.text.Editable;
import android.text.InputFilter;
import android.text.InputType;
import android.text.TextUtils;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.Locale;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 表单：一列带标签的输入项，统一的校验和报错显示。
 *
 * <pre>
 * Form f = new Form(ctx);
 * Form.Text name = f.text("姓名", user.name).required();
 * Form.Select role = f.select("角色", Option.pairs("teacher", "教师", "admin", "管理员"), "teacher");
 * Form.Toggle active = f.toggle("启用", true);
 * root.addView(f.view());
 * ...
 * if (!f.validate()) return;          // 没过会在对应项下面标红说明
 * save(name.value(), role.value(), active.value());
 * </pre>
 * 宽屏上用 {@link #row(Field, Field)} 把两个短输入项并排放。
 */
public class Form {

    public interface Rule {
        /** 返回错误说明，没问题返回 null */
        String check(String value);
    }

    public interface Changed {
        void changed();
    }

    private final Context ctx;
    private final LinearLayout root;
    private final List<Field> fields = new ArrayList<>();

    public Form(Context c) {
        ctx = c;
        root = V.vbox(c);
    }

    public View view() {
        return root;
    }

    public LinearLayout layout() {
        return root;
    }

    // ---------- 字段基类 ----------

    public abstract static class Field {
        final LinearLayout box;
        final TextView label;
        final TextView error;
        final TextView help;
        boolean required;
        Changed onChange;

        Field(Context c, String labelText) {
            box = V.vbox(c);
            label = V.text(c, labelText, V.LABEL);
            V.pad(label, 2, 0, 0, 6);
            if (labelText != null) box.addView(label);
            error = V.text(c, "", V.CAPTION);
            error.setTextColor(Palette.of(c).danger);
            V.pad(error, 2, 4, 0, 0);
            error.setVisibility(View.GONE);
            help = V.text(c, "", V.CAPTION);
            V.pad(help, 2, 4, 0, 0);
            help.setVisibility(View.GONE);
        }

        void finish(View control) {
            box.addView(control, V.matchWrap());
            box.addView(error);
            box.addView(help);
        }

        /** 必填：标签后面加红星，空着不让过 */
        @SuppressWarnings("unchecked")
        public <T extends Field> T required() {
            required = true;
            label.setText(label.getText() + " *");
            return (T) this;
        }

        /** 输入项下面的灰色说明 */
        @SuppressWarnings("unchecked")
        public <T extends Field> T help(String text) {
            help.setText(text);
            help.setVisibility(TextUtils.isEmpty(text) ? View.GONE : View.VISIBLE);
            return (T) this;
        }

        @SuppressWarnings("unchecked")
        public <T extends Field> T onChange(Changed c) {
            onChange = c;
            return (T) this;
        }

        public void setError(String msg) {
            error.setText(msg == null ? "" : msg);
            error.setVisibility(msg == null ? View.GONE : View.VISIBLE);
        }

        public void setVisible(boolean on) {
            box.setVisibility(on ? View.VISIBLE : View.GONE);
        }

        public boolean visible() {
            return box.getVisibility() == View.VISIBLE;
        }

        public void setLabel(String text) {
            label.setText(required ? text + " *" : text);
        }

        public View view() {
            return box;
        }

        abstract boolean isEmpty();

        String validateSelf() {
            return required && isEmpty() ? "必填" : null;
        }

        void changed() {
            setError(null);
            if (onChange != null) onChange.changed();
        }
    }

    // ---------- 文本 ----------

    public static class Text extends Field {
        public final EditText edit;
        private final List<Rule> rules = new ArrayList<>();

        Text(Context c, String label, String value, String hint) {
            super(c, label);
            edit = Fields.input(c, hint);
            if (value != null) edit.setText(value);
            edit.addTextChangedListener(new TextWatcher() {
                @Override
                public void beforeTextChanged(CharSequence s, int st, int co, int af) {}

                @Override
                public void onTextChanged(CharSequence s, int st, int be, int co) {}

                @Override
                public void afterTextChanged(Editable s) {
                    edit.setActivated(false);
                    changed();
                }
            });
            finish(edit);
        }

        public String value() {
            return edit.getText().toString().trim();
        }

        /** 不去首尾空格的原文（题干、代码这类） */
        public String raw() {
            return edit.getText().toString();
        }

        public void set(String v) {
            edit.setText(v == null ? "" : v);
        }

        /** 数字值，没填或不是数字返回 null */
        public Double number() {
            try {
                String v = value();
                return v.isEmpty() ? null : Double.valueOf(v);
            } catch (NumberFormatException e) {
                return null;
            }
        }

        public Integer integer() {
            Double d = number();
            return d == null ? null : (int) Math.round(d);
        }

        public Text maxLength(int n) {
            edit.setFilters(new InputFilter[]{new InputFilter.LengthFilter(n)});
            return this;
        }

        public Text rule(Rule r) {
            rules.add(r);
            return this;
        }

        public Text hint(String h) {
            edit.setHint(h);
            return this;
        }

        @Override
        boolean isEmpty() {
            return value().isEmpty();
        }

        @Override
        String validateSelf() {
            String e = super.validateSelf();
            if (e != null) return e;
            if (isEmpty()) return null;
            for (Rule r : rules) {
                String m = r.check(value());
                if (m != null) return m;
            }
            return null;
        }

        @Override
        public void setError(String msg) {
            super.setError(msg);
            edit.setActivated(msg != null);
        }
    }

    public Text text(String label, String value) {
        return add(new Text(ctx, label, value, null));
    }

    public Text text(String label, String value, String hint) {
        return add(new Text(ctx, label, value, hint));
    }

    public Text password(String label, String hint) {
        Text t = new Text(ctx, label, null, hint);
        t.edit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        return add(t);
    }

    /** 数字。decimal = 允许小数 */
    public Text number(String label, Number value, boolean decimal) {
        Text t = new Text(ctx, label, value == null ? null : Fmt.num(value.doubleValue()), null);
        t.edit.setInputType(InputType.TYPE_CLASS_NUMBER
                | (decimal ? InputType.TYPE_NUMBER_FLAG_DECIMAL : 0));
        t.rule(v -> {
            try {
                Double.parseDouble(v);
                return null;
            } catch (NumberFormatException e) {
                return "要填数字";
            }
        });
        return add(t);
    }

    /** 多行文字 */
    public Text area(String label, String value, int minLines) {
        Text t = new Text(ctx, label, value, null);
        t.edit.setSingleLine(false);
        t.edit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        t.edit.setMinLines(minLines);
        t.edit.setGravity(Gravity.TOP | Gravity.START);
        return add(t);
    }

    // ---------- 下拉单选 ----------

    public static class Select extends Field {
        private final TextView box;
        private List<Option> options;
        private Object value;
        private final String title;
        private String placeholder = "请选择";

        Select(Context c, String label, List<Option> options, Object value) {
            super(c, label);
            this.options = options;
            this.value = value;
            this.title = label;
            box = pickerBox(c);
            box.setOnClickListener(v -> Dialogs.choose(c, title, this.options, this.value, o -> {
                set(o.value);
                changed();
            }));
            render();
            finish(box);
        }

        public Object value() {
            return value;
        }

        public String string() {
            return value == null ? "" : String.valueOf(value);
        }

        public void set(Object v) {
            value = v;
            render();
        }

        public void setOptions(List<Option> opts) {
            options = opts;
            render();
        }

        public Select placeholder(String p) {
            placeholder = p;
            render();
            return this;
        }

        private void render() {
            boolean has = false;
            for (Option o : options) if (Option.same(o.value, value)) has = true;
            box.setText(has ? Option.labelOf(options, value) : placeholder);
            box.setTextColor(has ? Palette.of(box.getContext()).text : Palette.of(box.getContext()).text3);
        }

        @Override
        boolean isEmpty() {
            return value == null || String.valueOf(value).isEmpty();
        }
    }

    public Select select(String label, List<Option> options, Object value) {
        return add(new Select(ctx, label, options, value));
    }

    // ---------- 多选 ----------

    public static class Multi extends Field {
        private final TextView box;
        private List<Option> options;
        private List<Object> values = new ArrayList<>();
        private String placeholder = "请选择（可多选）";

        Multi(Context c, String label, List<Option> options, List<?> values) {
            super(c, label);
            this.options = options;
            if (values != null) this.values.addAll(values);
            box = pickerBox(c);
            box.setSingleLine(false);
            box.setMaxLines(3);
            box.setOnClickListener(v -> Dialogs.chooseMany(c, label, this.options, this.values, vals -> {
                this.values = vals;
                render();
                changed();
            }));
            render();
            finish(box);
        }

        public List<Object> values() {
            return values;
        }

        public void set(List<?> v) {
            values = new ArrayList<>(v == null ? new ArrayList<>() : v);
            render();
        }

        public void setOptions(List<Option> opts) {
            options = opts;
            render();
        }

        public Multi placeholder(String p) {
            placeholder = p;
            render();
            return this;
        }

        private void render() {
            List<String> labels = new ArrayList<>();
            for (Object v : values) labels.add(Option.labelOf(options, v));
            boolean has = !labels.isEmpty();
            box.setText(has ? TextUtils.join("、", labels) : placeholder);
            box.setTextColor(has ? Palette.of(box.getContext()).text : Palette.of(box.getContext()).text3);
        }

        @Override
        boolean isEmpty() {
            return values.isEmpty();
        }
    }

    public Multi multi(String label, List<Option> options, List<?> values) {
        return add(new Multi(ctx, label, options, values));
    }

    // ---------- 平铺单选（选项少时，一排按钮直接点） ----------

    public static class Choice extends Field {
        private final FlowBox flow;
        private final List<Option> options;
        private Object value;
        private final List<TextView> chips = new ArrayList<>();

        Choice(Context c, String label, List<Option> options, Object value) {
            super(c, label);
            this.options = options;
            this.value = value;
            flow = new FlowBox(c, 8, 8);
            for (final Option o : options) {
                TextView chip = V.chip(c, o.label, Option.same(o.value, value), v -> {
                    set(o.value);
                    changed();
                });
                chips.add(chip);
                flow.addView(chip);
            }
            finish(flow);
        }

        public Object value() {
            return value;
        }

        public String string() {
            return value == null ? "" : String.valueOf(value);
        }

        public void set(Object v) {
            value = v;
            for (int i = 0; i < options.size(); i++) V.setChip(chips.get(i), Option.same(options.get(i).value, v));
        }

        @Override
        boolean isEmpty() {
            return value == null;
        }
    }

    public Choice choice(String label, List<Option> options, Object value) {
        return add(new Choice(ctx, label, options, value));
    }

    // ---------- 开关 ----------

    public static class Toggle extends Field {
        public final Switch sw;

        Toggle(Context c, String label, String desc, boolean on) {
            super(c, null);
            LinearLayout row = V.hbox(c);
            LinearLayout texts = V.vbox(c);
            texts.addView(V.text(c, label, V.BODY));
            if (!TextUtils.isEmpty(desc)) texts.addView(V.text(c, desc, V.CAPTION));
            row.addView(texts, V.fill());
            sw = new Switch(c);
            sw.setChecked(on);
            sw.setOnCheckedChangeListener((b, v) -> changed());
            row.addView(sw);
            row.setMinimumHeight(Ui.dp(c, 48));
            V.clickable(row, 8, v -> sw.toggle());
            finish(row);
        }

        public boolean value() {
            return sw.isChecked();
        }

        public void set(boolean on) {
            sw.setChecked(on);
        }

        @Override
        boolean isEmpty() {
            return false;
        }
    }

    public Toggle toggle(String label, boolean on) {
        return add(new Toggle(ctx, label, null, on));
    }

    public Toggle toggle(String label, String desc, boolean on) {
        return add(new Toggle(ctx, label, desc, on));
    }

    // ---------- 日期时间 ----------

    /**
     * 日期时间。值是本地时间字符串「yyyy-MM-ddTHH:mm:ss」（后端按这个格式收），可以清空。
     */
    public static class DateTime extends Field {
        private final TextView box;
        private String value;
        private final boolean withTime;

        DateTime(Context c, String label, String value, boolean withTime) {
            super(c, label);
            this.withTime = withTime;
            this.value = normalize(value);
            LinearLayout row = V.hbox(c);
            box = pickerBox(c);
            box.setCompoundDrawablesRelative(null, null, null, null);
            row.addView(box, V.fill());
            TextView clear = V.button(c, "清空", V.BTN_TEXT, v -> {
                set(null);
                changed();
            });
            V.addStart(row, clear, 4);
            box.setOnClickListener(v -> pick(c));
            render();
            finish(row);
        }

        private void pick(Context c) {
            final Calendar cal = Calendar.getInstance();
            if (value != null) {
                try {
                    cal.set(Integer.parseInt(value.substring(0, 4)), Integer.parseInt(value.substring(5, 7)) - 1,
                            Integer.parseInt(value.substring(8, 10)), Integer.parseInt(value.substring(11, 13)),
                            Integer.parseInt(value.substring(14, 16)), 0);
                } catch (Exception ignored) {
                    // 解析不了就从现在开始选
                }
            }
            new DatePickerDialog(c, (dp, y, m, d) -> {
                if (!withTime) {
                    set(String.format(Locale.ROOT, "%04d-%02d-%02dT00:00:00", y, m + 1, d));
                    changed();
                    return;
                }
                new TimePickerDialog(c, (tp, h, min) -> {
                    set(String.format(Locale.ROOT, "%04d-%02d-%02dT%02d:%02d:00", y, m + 1, d, h, min));
                    changed();
                }, cal.get(Calendar.HOUR_OF_DAY), cal.get(Calendar.MINUTE), true).show();
            }, cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show();
        }

        private static String normalize(String v) {
            if (v == null || v.length() < 16) return null;
            return v.substring(0, 16).replace(' ', 'T') + ":00";
        }

        /** 「yyyy-MM-ddTHH:mm:ss」或 null */
        public String value() {
            return value;
        }

        /** 只要日期「yyyy-MM-dd」 */
        public String date() {
            return value == null ? null : value.substring(0, 10);
        }

        public void set(String v) {
            value = normalize(v);
            render();
        }

        private void render() {
            if (value == null) {
                box.setText(withTime ? "选择日期和时间" : "选择日期");
                box.setTextColor(Palette.of(box.getContext()).text3);
            } else {
                box.setText(withTime ? value.substring(0, 16).replace('T', ' ') : value.substring(0, 10));
                box.setTextColor(Palette.of(box.getContext()).text);
            }
        }

        @Override
        boolean isEmpty() {
            return value == null;
        }
    }

    public DateTime dateTime(String label, String value) {
        return add(new DateTime(ctx, label, value, true));
    }

    public DateTime date(String label, String value) {
        return add(new DateTime(ctx, label, value, false));
    }

    // ---------- 数字加减 ----------

    public static class Stepper extends Field {
        public final EditText edit;
        private final int min, max;

        Stepper(Context c, String label, int value, int min, int max) {
            super(c, label);
            this.min = min;
            this.max = max;
            LinearLayout row = V.hbox(c);
            View minus = V.iconButton(c, R.drawable.ic_remove, "减少", v -> set(value() - 1));
            minus.setBackground(V.ripple(c, V.stroke(c, Palette.of(c).surface, Palette.of(c).border, 12), 12));
            edit = Fields.input(c, null);
            edit.setInputType(InputType.TYPE_CLASS_NUMBER);
            edit.setGravity(Gravity.CENTER);
            edit.setText(String.valueOf(value));
            edit.addTextChangedListener(new TextWatcher() {
                @Override
                public void beforeTextChanged(CharSequence s, int st, int co, int af) {}

                @Override
                public void onTextChanged(CharSequence s, int st, int be, int co) {}

                @Override
                public void afterTextChanged(Editable s) {
                    changed();
                }
            });
            View plus = V.iconButton(c, R.drawable.ic_add, "增加", v -> set(value() + 1));
            plus.setBackground(V.ripple(c, V.stroke(c, Palette.of(c).surface, Palette.of(c).border, 12), 12));
            row.addView(minus);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(Ui.dp(c, 88), V.WRAP);
            lp.setMarginStart(Ui.dp(c, 8));
            lp.setMarginEnd(Ui.dp(c, 8));
            row.addView(edit, lp);
            row.addView(plus);
            finish(row);
        }

        public int value() {
            try {
                return Integer.parseInt(edit.getText().toString().trim());
            } catch (NumberFormatException e) {
                return min;
            }
        }

        public void set(int v) {
            edit.setText(String.valueOf(Math.max(min, Math.min(max, v))));
        }

        @Override
        boolean isEmpty() {
            return edit.getText().toString().trim().isEmpty();
        }

        @Override
        String validateSelf() {
            String e = super.validateSelf();
            if (e != null) return e;
            int v = value();
            if (v < min || v > max) return "要在 " + min + " 到 " + max + " 之间";
            return null;
        }
    }

    public Stepper stepper(String label, int value, int min, int max) {
        return add(new Stepper(ctx, label, value, min, max));
    }

    // ---------- 排版 ----------

    private <T extends Field> T add(T f) {
        fields.add(f);
        LinearLayout.LayoutParams lp = V.matchWrap();
        lp.bottomMargin = Ui.dp(ctx, 16);
        root.addView(f.box, lp);
        return f;
    }

    /** 宽屏时把两个输入项并排放（手机上仍然上下排） */
    public void row(Field a, Field b) {
        if (!Ui.wide(ctx)) return;
        int idx = root.indexOfChild(a.box);
        root.removeView(a.box);
        root.removeView(b.box);
        LinearLayout row = V.hbox(ctx);
        row.setGravity(Gravity.TOP);
        row.addView(a.box, V.weight(1));
        row.addView(V.space(ctx, 16));
        row.addView(b.box, V.weight(1));
        LinearLayout.LayoutParams lp = V.matchWrap();
        lp.bottomMargin = Ui.dp(ctx, 16);
        root.addView(row, Math.max(0, idx), lp);
    }

    /** 分组小标题 */
    public TextView section(String title) {
        TextView t = V.text(ctx, title, V.H3);
        LinearLayout.LayoutParams lp = V.matchWrap();
        lp.topMargin = Ui.dp(ctx, fields.isEmpty() && root.getChildCount() == 0 ? 0 : 8);
        lp.bottomMargin = Ui.dp(ctx, 12);
        root.addView(t, lp);
        return t;
    }

    /** 灰色说明文字 */
    public TextView note(String text) {
        TextView t = V.text(ctx, text, V.CAPTION);
        LinearLayout.LayoutParams lp = V.matchWrap();
        lp.bottomMargin = Ui.dp(ctx, 12);
        root.addView(t, lp);
        return t;
    }

    /** 放任意视图 */
    public <T extends View> T custom(T v) {
        LinearLayout.LayoutParams lp = V.matchWrap();
        lp.bottomMargin = Ui.dp(ctx, 16);
        root.addView(v, lp);
        return v;
    }

    /**
     * 校验所有可见的输入项，没过的在下面标红说明并把第一个滚到眼前。
     * @return 全部通过返回 true
     */
    public boolean validate() {
        Field first = null;
        for (Field f : fields) {
            if (!f.visible()) continue;
            String e = f.validateSelf();
            f.setError(e);
            if (e != null && first == null) first = f;
        }
        if (first != null) {
            final View v = first.box;
            v.requestFocus();
            v.post(() -> v.requestRectangleOnScreen(new android.graphics.Rect(0, 0, v.getWidth(), v.getHeight()), false));
            return false;
        }
        return true;
    }

    /** 下拉框那种「点一下弹出选择」的外框 */
    static TextView pickerBox(Context c) {
        TextView t = V.text(c, "", V.BODY);
        t.setTextSize(16);
        t.setBackground(V.ripple(c, Fields.inputBg(c), 12));
        t.setMinHeight(Ui.dp(c, 48));
        t.setGravity(Gravity.CENTER_VERTICAL);
        V.pad(t, 14, 10, 12, 10);
        t.setSingleLine(true);
        t.setEllipsize(TextUtils.TruncateAt.END);
        android.graphics.drawable.Drawable d = c.getDrawable(R.drawable.ic_expand_more);
        if (d != null) {
            d = d.mutate();
            d.setTint(Palette.of(c).text3);
            int s = Ui.dp(c, 20);
            d.setBounds(0, 0, s, s);
            t.setCompoundDrawablesRelative(null, null, d, null);
        }
        t.setClickable(true);
        t.setFocusable(true);
        return t;
    }
}
