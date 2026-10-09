package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.graphics.Typeface;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.security.SecureRandom;

import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/** 本模块共用的小部件：分组卡片、随机密码、账号信息弹窗、带说明的输入框 */
final class MeUi {
    private MeUi() {}

    // ---------- 分组卡片（设置项那种一组行） ----------

    /** 圆角白底、无内边距的一组行，行之间自动加分隔线。行用 V.row 建 */
    static LinearLayout group(Context c, View... rows) {
        LinearLayout g = V.vbox(c);
        Palette p = Palette.of(c);
        g.setBackground(V.stroke(c, p.surface, p.border, 16));
        g.setClipToOutline(true);
        for (View r : rows) addRow(g, r);
        return g;
    }

    static void addRow(LinearLayout group, View row) {
        if (row == null) return;
        if (group.getChildCount() > 0) {
            View d = V.divider(group.getContext());
            LinearLayout.LayoutParams lp = (LinearLayout.LayoutParams) d.getLayoutParams();
            lp.setMarginStart(Ui.dp(group.getContext(), 68));
            group.addView(d, lp);
        }
        group.addView(row, V.matchWrap());
    }

    /** 分组上方的小标题 */
    static TextView groupTitle(Context c, String title) {
        TextView t = V.text(c, title, V.LABEL);
        V.pad(t, 6, 18, 0, 8);
        return t;
    }

    /** 在 V.row 的右箭头前面塞一个视图（标签、徽标） */
    static void putTrailing(LinearLayout row, View v) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        lp.setMarginStart(Ui.dp(row.getContext(), 8));
        int at = row.getChildCount();
        // V.row 可点时最后一个是箭头
        if (row.isClickable() && at > 0) at--;
        row.addView(v, at, lp);
    }

    /** 带标题的白卡片 */
    static LinearLayout titledCard(Context c, String title) {
        LinearLayout card = V.card(c);
        TextView t = V.text(c, title, V.H3);
        V.pad(t, 0, 0, 0, 12);
        card.addView(t);
        return card;
    }

    // ---------- 账号 ----------

    static String nameOf(JSONObject u) {
        String n = Json.str(u, "name");
        return n.isEmpty() ? Json.str(u, "username") : n;
    }

    static boolean isAdmin(JSONObject u) {
        return "admin".equals(Json.str(u, "role"));
    }

    static TextView roleTag(Context c, JSONObject u, boolean longLabel) {
        boolean admin = isAdmin(u);
        return V.tag(c, admin ? (longLabel ? "系统管理员" : "管理员") : "教师", admin ? Tone.DANGER : Tone.PRIMARY);
    }

    /** 「2026-10-08T07:36:47」→「2026-10-08 07:36」 */
    static String time(String iso) {
        if (TextUtils.isEmpty(iso) || "null".equals(iso)) return "";
        String s = iso.replace('T', ' ');
        return s.length() > 16 ? s.substring(0, 16) : s;
    }

    private static final String PWD_CHARS = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    private static final SecureRandom RNG = new SecureRandom();

    /** 随机口令：去掉了 0/O/1/l/I 这些容易看错的字符，念给老师抄不会错 */
    static String randomPassword() {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 12; i++) sb.append(PWD_CHARS.charAt(RNG.nextInt(PWD_CHARS.length())));
        // 保证不是纯数字（后端不收纯数字）——字符集里字母占大多数，这里再兜一下
        if (sb.toString().matches("\\d+")) sb.setCharAt(0, 'a');
        return sb.toString();
    }

    /**
     * 账号 / 新密码只显示这一次：大字等宽显示，带「复制」，点「我记下了」才关。
     */
    static void showCredential(Context c, String title, String text) {
        Sheet s = new Sheet(c, title);
        TextView box = V.text(c, text, V.BODY);
        box.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        box.setTextSize(17);
        box.setTextIsSelectable(true);
        box.setBackground(V.round(c, Palette.of(c).surfaceAlt, 12));
        V.pad(box, 16, 14, 16, 14);
        s.content(box);
        TextView tip = V.text(c, "这串密码只显示这一次，请当场记下或复制发给本人。", V.CAPTION);
        V.pad(tip, 2, 10, 0, 0);
        s.content(tip);
        s.cancelable(false);
        s.buttons("复制", () -> {
            Sys.copy(c, title, text);
            android.widget.Toast.makeText(c, "已复制", android.widget.Toast.LENGTH_SHORT).show();
        }, "我记下了", s::dismiss);
        s.show();
    }

    // ---------- 输入 ----------

    interface TextOk {
        /** 返回 null 表示通过并关闭；返回一句话就显示在输入框下方，不关 */
        String done(String text);
    }

    /** 带一段说明的输入弹窗（Dialogs.prompt 没有说明文字） */
    static Sheet prompt(Context c, String title, CharSequence message, String hint, String initial,
                        String okLabel, boolean danger, TextOk ok) {
        Sheet s = new Sheet(c, title);
        if (!TextUtils.isEmpty(message)) {
            TextView m = V.text(c, message, V.BODY2);
            V.pad(m, 0, 0, 0, 12);
            s.content(m);
        }
        EditText e = Fields.input(c, hint);
        if (initial != null) {
            e.setText(initial);
            e.setSelection(e.length());
        }
        s.content(e);
        TextView err = V.text(c, "", V.CAPTION);
        err.setTextColor(Palette.of(c).danger);
        V.pad(err, 2, 6, 0, 0);
        err.setVisibility(View.GONE);
        s.content(err);
        s.buttons("取消", null, okLabel, () -> {
            String msg = ok.done(e.getText().toString());
            if (msg == null) {
                s.dismiss();
            } else {
                err.setText(msg);
                err.setVisibility(View.VISIBLE);
                e.setActivated(true);
            }
        }, danger);
        s.show();
        Ui.showKeyboard(e);
        return s;
    }

    /** 密码输入框 + 「换一个」：重置密码、新增账号用 */
    static LinearLayout passwordRow(Context c, EditText edit) {
        LinearLayout row = V.hbox(c);
        edit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        edit.setTypeface(Typeface.MONOSPACE);
        row.addView(edit, V.fill());
        TextView again = V.button(c, "换一个", V.BTN_TONAL, v -> edit.setText(randomPassword()));
        V.addStart(row, again, 8);
        row.setGravity(Gravity.CENTER_VERTICAL);
        return row;
    }

    /** 危险操作：要求手工敲「删除」两个字才放行 */
    static void confirmTyped(Context c, String title, CharSequence message, String okLabel, Runnable onOk) {
        prompt(c, title, message, "在这里输入：删除", "", okLabel, true, text -> {
            if (!"删除".equals(text.trim())) return "请准确输入「删除」两个字";
            onOk.run();
            return null;
        });
    }

    static void alert(Context c, String title, String msg) {
        Dialogs.alert(c, title, msg);
    }
}
