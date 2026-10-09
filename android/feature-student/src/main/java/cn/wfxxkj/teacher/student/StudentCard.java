package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/** 学生列表里的一张卡片：头像、姓名、学号、班级、性别、状态 */
final class StudentCard extends LinearLayout {
    private final LinearLayout avatarBox;
    private final TextView name;
    private final LinearLayout tags;
    private final TextView line2;
    private final boolean showClass;

    StudentCard(Context c, boolean showClass) {
        super(c);
        this.showClass = showClass;
        setOrientation(HORIZONTAL);
        setGravity(Gravity.CENTER_VERTICAL);
        Palette p = Palette.of(c);
        setBackground(V.stroke(c, p.surface, p.border, 16));
        V.pad(this, 14, 12, 14, 12);

        avatarBox = new LinearLayout(c);
        addView(avatarBox, new LayoutParams(Ui.dp(c, 42), Ui.dp(c, 42)));

        LinearLayout texts = V.vbox(c);
        LinearLayout top = V.hbox(c);
        name = V.oneLine(V.text(c, "", V.H3));
        top.addView(name, new LayoutParams(V.WRAP, V.WRAP, 0f));
        tags = V.hbox(c);
        V.addStart(top, tags, 8);
        texts.addView(top);
        line2 = V.oneLine(V.text(c, "", V.BODY2));
        V.addTop(texts, line2, 2);
        LayoutParams tlp = V.fill();
        tlp.setMarginStart(Ui.dp(c, 12));
        addView(texts, tlp);
    }

    void bind(JSONObject s) {
        Context c = getContext();
        avatarBox.removeAllViews();
        TextView av = V.avatar(c, Json.str(s, "name"), 42);
        if (!Json.bool(s, "is_active")) av.setAlpha(0.4f);
        avatarBox.addView(av);

        name.setText(Json.str(s, "name"));
        name.setTextColor(Json.bool(s, "is_active") ? Palette.of(c).text : Palette.of(c).text3);
        tags.removeAllViews();
        String gender = Json.str(s, "gender");
        if (!gender.isEmpty()) {
            tags.addView(V.tag(c, gender, "男".equals(gender) ? Tone.INFO : Tone.VIOLET));
        }
        if (!Json.bool(s, "is_active")) {
            if (tags.getChildCount() > 0) tags.addView(V.space(c, 6));
            tags.addView(V.tag(c, "已停用", Tone.DANGER));
        }

        StringBuilder sb = new StringBuilder(Json.str(s, "student_no"));
        if (showClass) {
            String cls = Json.str(s, "student_class");
            sb.append("  ·  ").append(cls.isEmpty() ? "未分班" : cls);
        } else {
            String t = Fmt.date(Json.str(s, "created_at"));
            if (!t.isEmpty()) sb.append("  ·  ").append(t).append(" 建号");
        }
        line2.setText(sb);
    }
}
