package cn.wfxxkj.teacher.paper;

import android.content.Context;
import android.graphics.Typeface;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 紧凑的数字加减器：[−] 30 [+]，放在一行的右边（题量、分值）。
 * core 的 Form.Stepper 带标签、占整行，这里要和题型标签挤在同一行，所以自己做一个小的。
 */
final class NumberStepper extends LinearLayout {

    interface Changed {
        void changed(int value);
    }

    private final EditText edit;
    private final ImageView minus, plus;
    private final int min, max;
    private Changed listener;
    private boolean muted;

    NumberStepper(Context c, int value, int min, int max) {
        super(c);
        this.min = min;
        this.max = max;
        setOrientation(HORIZONTAL);
        setGravity(Gravity.CENTER_VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 10));

        minus = btn(c, R.drawable.ic_remove, "减少");
        minus.setOnClickListener(v -> set(value() - 1, true));
        addView(minus);

        edit = new EditText(c);
        edit.setInputType(InputType.TYPE_CLASS_NUMBER);
        edit.setSingleLine(true);
        edit.setGravity(Gravity.CENTER);
        edit.setBackground(null);
        edit.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        edit.setTypeface(Typeface.DEFAULT_BOLD);
        edit.setTextColor(p.text);
        edit.setPadding(0, 0, 0, 0);
        edit.setSelectAllOnFocus(true);
        edit.setText(String.valueOf(value));
        edit.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int st, int co, int af) {}

            @Override
            public void onTextChanged(CharSequence s, int st, int be, int co) {}

            @Override
            public void afterTextChanged(Editable s) {
                renderButtons();
                if (!muted && listener != null) listener.changed(value());
            }
        });
        // 输完离开时把超范围的数改回范围内
        edit.setOnFocusChangeListener((v, has) -> {
            if (!has) set(value(), false);
        });
        addView(edit, new LayoutParams(Ui.dp(c, 44), Ui.dp(c, 36)));

        plus = btn(c, R.drawable.ic_add, "增加");
        plus.setOnClickListener(v -> set(value() + 1, true));
        addView(plus);
        renderButtons();
    }

    private ImageView btn(Context c, int icon, String desc) {
        ImageView iv = V.icon(c, icon, Palette.of(c).primary, 18);
        int s = Ui.dp(c, 36);
        iv.setLayoutParams(new LayoutParams(s, s));
        iv.setScaleType(ImageView.ScaleType.CENTER);
        iv.setContentDescription(desc);
        V.clickable(iv, 10, null);
        return iv;
    }

    void setOnChanged(Changed c) {
        listener = c;
    }

    int value() {
        try {
            int v = Integer.parseInt(edit.getText().toString().trim());
            return Math.max(min, Math.min(max, v));
        } catch (NumberFormatException e) {
            return min;
        }
    }

    /** 改值；notify = false 时不回调（例如「恢复默认」统一刷新） */
    void set(int v, boolean notify) {
        int nv = Math.max(min, Math.min(max, v));
        String s = String.valueOf(nv);
        if (s.equals(edit.getText().toString())) return;
        muted = !notify;
        edit.setText(s);
        muted = false;
    }

    private void renderButtons() {
        int v = value();
        minus.setAlpha(v <= min ? 0.35f : 1f);
        plus.setAlpha(v >= max ? 0.35f : 1f);
    }
}
