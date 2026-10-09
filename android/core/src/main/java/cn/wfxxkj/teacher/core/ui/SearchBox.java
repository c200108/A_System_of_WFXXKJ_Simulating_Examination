package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.TypedValue;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;

import cn.wfxxkj.teacher.core.R;

/**
 * 搜索框：圆角输入框 + 放大镜 + 清空按钮。打字停顿 400ms 或按键盘上的「搜索」触发搜索。
 */
public class SearchBox extends LinearLayout {

    public interface OnSearch {
        void search(String keyword);
    }

    private final EditText edit;
    private final ImageView clear;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private OnSearch listener;
    private String last = "";
    private final Runnable fire = this::fire;

    public SearchBox(Context c, String hint) {
        super(c);
        setOrientation(HORIZONTAL);
        setGravity(android.view.Gravity.CENTER_VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.round(c, p.surfaceAlt, 22));
        V.pad(this, 12, 0, 4, 0);
        setMinimumHeight(Ui.dp(c, 44));
        addView(V.icon(c, R.drawable.ic_search, p.text3, 20));
        edit = new EditText(c);
        edit.setHint(hint);
        edit.setSingleLine(true);
        edit.setBackground(null);
        edit.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        edit.setTextColor(p.text);
        edit.setHintTextColor(p.text3);
        edit.setImeOptions(EditorInfo.IME_ACTION_SEARCH);
        V.pad(edit, 8, 8, 8, 8);
        addView(edit, V.fill());
        clear = V.iconButton(c, R.drawable.ic_cancel, "清空", v -> {
            edit.setText("");
            fire();
        });
        clear.setImageTintList(android.content.res.ColorStateList.valueOf(p.text3));
        clear.setLayoutParams(new LayoutParams(Ui.dp(c, 36), Ui.dp(c, 36)));
        clear.setVisibility(GONE);
        addView(clear);
        edit.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int st, int co, int af) {}

            @Override
            public void onTextChanged(CharSequence s, int st, int be, int co) {}

            @Override
            public void afterTextChanged(Editable s) {
                clear.setVisibility(s.length() > 0 ? VISIBLE : GONE);
                handler.removeCallbacks(fire);
                handler.postDelayed(fire, 400);
            }
        });
        edit.setOnEditorActionListener((v, id, ev) -> {
            if (id == EditorInfo.IME_ACTION_SEARCH || (ev != null && ev.getKeyCode() == KeyEvent.KEYCODE_ENTER)) {
                handler.removeCallbacks(fire);
                fire();
                Ui.hideKeyboard(edit);
                return true;
            }
            return false;
        });
    }

    public void setOnSearch(OnSearch s) {
        listener = s;
    }

    public String keyword() {
        return edit.getText().toString().trim();
    }

    public void setKeyword(String k) {
        last = k == null ? "" : k.trim();
        edit.setText(k);
    }

    public EditText edit() {
        return edit;
    }

    private void fire() {
        String k = keyword();
        if (k.equals(last)) return;
        last = k;
        if (listener != null) listener.search(k);
    }

    @Override
    protected void onDetachedFromWindow() {
        handler.removeCallbacks(fire);
        super.onDetachedFromWindow();
    }

    /** 搜索框所在的那一条（带上下边距），放在列表头部用 */
    public View padded() {
        LinearLayout wrap = new LinearLayout(getContext());
        V.pad(wrap, 0, 8, 0, 4);
        wrap.addView(this, V.matchWrap());
        return wrap;
    }
}
