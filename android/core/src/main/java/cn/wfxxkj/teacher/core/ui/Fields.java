package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.text.InputType;
import android.util.TypedValue;
import android.widget.EditText;

/** 输入框的统一外观 */
public final class Fields {
    private Fields() {}

    /** 单行输入框：浅灰底、圆角，获得焦点时描主题色边 */
    public static EditText input(Context c, String hint) {
        EditText e = new EditText(c);
        e.setHint(hint);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_TEXT);
        e.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        Palette p = Palette.of(c);
        e.setTextColor(p.text);
        e.setHintTextColor(p.text3);
        e.setBackground(inputBg(c));
        e.setMinHeight(Ui.dp(c, 48));
        V.pad(e, 14, 10, 14, 10);
        e.setBackgroundTintList((ColorStateList) null);
        return e;
    }

    public static StateListDrawable inputBg(Context c) {
        Palette p = Palette.of(c);
        GradientDrawable normal = V.round(c, p.surfaceAlt, 12);
        normal.setStroke(Ui.dp(c, 1), p.border);
        GradientDrawable focused = V.round(c, p.surface, 12);
        focused.setStroke(Ui.dp(c, 1.5f), p.primary);
        GradientDrawable error = V.round(c, p.surface, 12);
        error.setStroke(Ui.dp(c, 1.5f), p.danger);
        StateListDrawable s = new StateListDrawable();
        s.addState(new int[]{android.R.attr.state_activated}, error);
        s.addState(new int[]{android.R.attr.state_focused}, focused);
        s.addState(new int[]{}, normal);
        return s;
    }
}
