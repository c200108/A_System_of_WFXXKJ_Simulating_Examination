package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.graphics.drawable.GradientDrawable;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 班级卡片：班名、年级、人数、班主任。
 * 自己带的班绿底并标「我的班」；没分配老师的班虚线边框，一眼看得出还没人管。
 */
final class ClassCard extends LinearLayout {
    private final TextView name;
    private final TextView grade;
    private final LinearLayout tags;
    private final TextView count;
    private final TextView owner;
    private final android.widget.ImageView ownerIcon;

    ClassCard(Context c) {
        super(c);
        setOrientation(VERTICAL);
        V.pad(this, 16, 14, 16, 14);
        LinearLayout top = V.hbox(c);
        name = V.oneLine(V.text(c, "", V.H2));
        top.addView(name, new LayoutParams(V.WRAP, V.WRAP));
        tags = V.hbox(c);
        V.addStart(top, tags, 8);
        addView(top);
        grade = V.oneLine(V.text(c, "", V.CAPTION));
        addView(grade);

        LinearLayout mid = V.hbox(c);
        mid.setGravity(android.view.Gravity.BOTTOM);
        count = V.text(c, "", V.DISPLAY);
        mid.addView(count);
        V.addStart(mid, V.text(c, "名学生", V.BODY2), 4).setPadding(0, 0, 0, Ui.dp(c, 4));
        V.addTop(this, mid, 8);

        LinearLayout bottom = V.hbox(c);
        ownerIcon = V.icon(c, R.drawable.ic_person, Palette.of(c).text3, 16);
        bottom.addView(ownerIcon);
        owner = V.oneLine(V.text(c, "", V.BODY2));
        LinearLayout.LayoutParams olp = V.fill();
        olp.setMarginStart(Ui.dp(c, 4));
        bottom.addView(owner, olp);
        V.addTop(this, bottom, 6);
    }

    void bind(JSONObject cls, long myId) {
        Context c = getContext();
        Palette p = Palette.of(c);
        Integer ownerId = Kit.intOrNull(cls, "owner_id");
        boolean mine = ownerId != null && ownerId == myId;
        boolean orphan = ownerId == null;

        GradientDrawable bg = V.round(c, mine ? p.successSoft : p.surface, 16);
        if (orphan) {
            bg.setStroke(Math.max(1, Ui.dp(c, 1.2f)), p.border, Ui.dpf(c, 6), Ui.dpf(c, 4));
        } else {
            bg.setStroke(Math.max(1, Ui.dp(c, 1)), mine ? (p.success & 0x00FFFFFF) | 0x66000000 : p.border);
        }
        setBackground(bg);

        name.setText(Json.str(cls, "name"));
        grade.setText(Json.str(cls, "grade"));
        tags.removeAllViews();
        if (mine) tags.addView(V.tag(c, "我的班", Tone.SUCCESS));
        if (!Json.bool(cls, "is_active")) {
            if (tags.getChildCount() > 0) tags.addView(V.space(c, 6));
            tags.addView(V.tag(c, "已停用", Tone.NEUTRAL));
        }
        int n = Json.num(cls, "student_count");
        count.setText(String.valueOf(n));
        count.setTextColor(n == 0 ? p.text3 : p.text);
        String o = Json.str(cls, "owner_name");
        owner.setText(orphan ? "未分配老师" : o);
        owner.setTextColor(orphan ? p.warning : p.text2);
        ownerIcon.setImageTintList(android.content.res.ColorStateList.valueOf(orphan ? p.warning : p.text3));
    }
}
