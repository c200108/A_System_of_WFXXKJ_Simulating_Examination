package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.InputFilter;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/** 反馈用到的弹层：表情面板、看大图、写回复 */
final class FeedbackSheets {
    private FeedbackSheets() {}

    /** 常用表情，按用得上的场景挑的，不求全（和网页同一组） */
    static final String[] EMOJI = {
            "😀", "😄", "🙂", "😊", "🥳", "🤔", "😅", "😣", "😭", "😡",
            "👍", "👎", "👏", "🙏", "💪", "🎉", "✨", "🔥", "❤️", "💡",
            "✅", "❌", "⚠️", "❓", "❗", "📝", "📚", "⌨️", "🖥️", "🌙"
    };

    /** 弹出表情面板，点一个就插到输入框的光标处 */
    static void emoji(Context c, EditText target) {
        Sheet s = new Sheet(c, "插入表情");
        GridBox grid = new GridBox(c, 44, 10, 2);
        for (final String e : EMOJI) {
            TextView t = new TextView(c);
            t.setText(e);
            t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
            t.setGravity(Gravity.CENTER);
            t.setMinHeight(Ui.dp(c, 48));
            V.clickable(t, 10, v -> {
                insert(target, e);
                s.dismiss();
                Ui.showKeyboard(target);
            });
            grid.addView(t);
        }
        s.content(grid);
        s.show();
    }

    /** 把表情插到光标处，而不是追加到末尾；插完光标放在表情后面 */
    static void insert(EditText e, String text) {
        int start = Math.max(0, e.getSelectionStart());
        int end = Math.max(start, e.getSelectionEnd());
        if (!e.hasFocus() && e.getSelectionStart() < 0) start = end = e.length();
        e.getText().replace(start, end, text);
        e.setSelection(Math.min(e.length(), start + text.length()));
    }

    /** 看大图 */
    static void preview(Context c, String url) {
        Sheet s = new Sheet(c, "查看配图");
        ImageView iv = new ImageView(c);
        iv.setAdjustViewBounds(true);
        iv.setScaleType(ImageView.ScaleType.FIT_CENTER);
        iv.setMaxHeight((int) (c.getResources().getDisplayMetrics().heightPixels * 0.65f));
        iv.setMinimumHeight(Ui.dp(c, 160));
        MeImages.load(iv, url, c.getResources().getDisplayMetrics().widthPixels);
        s.content(iv);
        s.buttons("浏览器打开", () -> {
            if (!Sys.openUrl(c, Http.absolute(url))) {
                android.widget.Toast.makeText(c, "没有能打开网页的应用", android.widget.Toast.LENGTH_SHORT).show();
            }
        }, "关闭", s::dismiss);
        s.show();
    }

    interface Send {
        void send(String text, Sheet sheet);
    }

    /** 写回复：多行输入 + 表情，「发布回复」 */
    static void reply(Context c, String toWhom, Send onSend) {
        Sheet s = new Sheet(c, "回复 " + toWhom);
        EditText e = Fields.input(c, "写给提交者看的，会公开显示，署你的名字");
        e.setSingleLine(false);
        e.setMinLines(3);
        e.setGravity(Gravity.TOP | Gravity.START);
        e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        e.setFilters(new InputFilter[]{new InputFilter.LengthFilter(2000)});
        s.content(e);
        LinearLayout tools = V.hbox(c);
        V.pad(tools, 0, 6, 0, 0);
        tools.addView(V.button(c, "😀 表情", V.BTN_TONAL, v -> emoji(c, e)));
        s.content(tools);
        s.buttons("取消", null, "发布回复", () -> {
            String text = e.getText().toString().trim();
            if (text.isEmpty()) {
                e.setActivated(true);
                android.widget.Toast.makeText(c, "回复内容不能为空", android.widget.Toast.LENGTH_SHORT).show();
                return;
            }
            onSend.send(text, s);
        });
        s.show();
        Ui.showKeyboard(e);
    }
}
