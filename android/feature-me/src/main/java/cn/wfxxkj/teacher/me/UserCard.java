package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.TextUtils;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/** 账号列表里的一张卡：头像、姓名、角色/状态、登录名、带的班、删除权 */
final class UserCard extends LinearLayout {
    private final android.widget.FrameLayout avatarSlot;
    private final LinearLayout nameRow;
    private final TextView sub;
    private final FlowBox tags;
    private final LinearLayout head;

    UserCard(Context c) {
        super(c);
        setOrientation(VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 16));
        V.pad(this, 16, 14, 16, 14);

        head = V.hbox(c);
        avatarSlot = new android.widget.FrameLayout(c);
        head.addView(avatarSlot, new LinearLayout.LayoutParams(Ui.dp(c, 44), Ui.dp(c, 44)));
        LinearLayout texts = V.vbox(c);
        V.pad(texts, 12, 0, 0, 0);
        nameRow = V.hbox(c);
        texts.addView(nameRow);
        sub = V.oneLine(V.text(c, "", V.CAPTION));
        V.addTop(texts, sub, 2);
        head.addView(texts, V.fill());
        addView(head);

        tags = new FlowBox(c, 6, 6);
        V.addTop(this, tags, 10);
    }

    void bind(JSONObject u, int index, long selfId) {
        Context c = getContext();
        avatarSlot.removeAllViews();
        TextView av = V.avatar(c, MeUi.nameOf(u), 44);
        if (!Json.bool(u, "is_active")) av.setAlpha(0.4f);
        avatarSlot.addView(av, new android.widget.FrameLayout.LayoutParams(V.MATCH, V.MATCH));

        nameRow.removeAllViews();
        TextView name = V.oneLine(V.text(c, MeUi.nameOf(u), V.H3));
        name.setMaxWidth(Ui.dp(c, 150));
        nameRow.addView(name);
        V.addStart(nameRow, MeUi.roleTag(c, u, false), 8);
        if (!Json.bool(u, "is_active")) V.addStart(nameRow, V.tag(c, "已停用", Tone.NEUTRAL), 6);
        if (u.optLong("id") == selfId) V.addStart(nameRow, V.tag(c, "我", Tone.SUCCESS), 6);

        String s = "#" + (index + 1) + "  ·  " + Json.str(u, "username");
        String contact = Json.str(u, "contact");
        s += "  ·  " + (contact.isEmpty() ? "未填联系方式" : contact);
        sub.setText(s);

        tags.removeAllViews();
        List<String> classes = Json.strings(Json.arr(u, "class_names"));
        if (classes.isEmpty()) {
            tags.addView(V.text(c, "未分配班级", V.CAPTION));
        } else {
            for (String n : classes) tags.addView(V.tag(c, n, Tone.INFO));
        }
        if (MeUi.isAdmin(u)) {
            tags.addView(V.tag(c, "全部权限", Tone.DANGER));
        } else if (Json.bool(u, "can_delete")) {
            tags.addView(V.tag(c, "删除权", Tone.WARNING));
        }
        String created = Json.str(u, "created_at");
        if (!TextUtils.isEmpty(created)) {
            // 放在最后，淡一点
            TextView t = V.text(c, "创建于 " + MeUi.time(created), V.CAPTION);
            tags.addView(t);
        }
    }
}
