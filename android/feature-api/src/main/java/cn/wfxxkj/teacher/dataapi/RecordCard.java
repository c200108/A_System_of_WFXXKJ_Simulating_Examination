package cn.wfxxkj.teacher.dataapi;

import android.content.Context;
import android.graphics.Paint;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/** 数据列表里的一条：学生 + 名单标记 + 类型/活动 + 得分 + 评语或内容摘要 + 时间 */
final class RecordCard extends LinearLayout {
    private final TextView who, score, line2, line3;
    private final LinearLayout tags;

    RecordCard(Context c) {
        super(c);
        setOrientation(VERTICAL);
        LinearLayout card = V.card(c);
        LinearLayout top = V.hbox(c);
        who = V.oneLine(V.bold(V.text(c, "", V.BODY)));
        top.addView(who);
        tags = V.hbox(c);
        V.addStart(top, tags, 6);
        top.addView(V.spring(c));
        score = V.bold(V.text(c, "", V.H3));
        top.addView(score);
        card.addView(top);
        line2 = V.oneLine(V.text(c, "", V.BODY2));
        V.addTop(card, line2, 2);
        line3 = V.lines(V.text(c, "", V.CAPTION), 2);
        V.addTop(card, line3, 2);
        addView(card, V.matchWrap());
    }

    void bind(JSONObject r) {
        Context c = getContext();
        JSONObject st = Json.obj(r, "student");
        String name = Json.str(st, "name");
        if (name.isEmpty()) name = Json.str(st, "no");
        who.setText(name.isEmpty() ? "匿名" : name);
        tags.removeAllViews();
        if (Json.bool(r, "student_matched")) tags.addView(V.tag(c, "名单", Tone.SUCCESS));
        boolean invalid = "invalid".equals(Json.str(r, "flag"));
        if (invalid) V.addStart(tags, V.tag(c, "无效", Tone.DANGER), 4);
        else if (Json.bool(r, "superseded")) V.addStart(tags, V.tag(c, "被替代", Tone.NEUTRAL), 4);
        score.setText(ApiUi.score(r));
        JSONObject act = Json.obj(r, "activity");
        String a = Json.str(act, "name");
        if (a.isEmpty()) a = Json.str(act, "id");
        StringBuilder sb = new StringBuilder(ApiUi.typeName(Json.str(r, "type")));
        String cls = Json.str(st, "class");
        if (!cls.isEmpty()) sb.append(" · ").append(cls);
        if (!a.isEmpty()) sb.append(" · ").append(a);
        JSONObject t = Json.obj(r, "target");
        if (t != null && !(Json.str(t, "name") + Json.str(t, "no")).isEmpty())
            sb.append(" → ").append(Json.str(t, "name").isEmpty() ? Json.str(t, "no") : Json.str(t, "name"));
        line2.setText(sb);
        String cm = Json.str(r, "comment");
        if (cm.isEmpty()) {
            JSONObject f = Json.obj(r, "fields");
            StringBuilder s = new StringBuilder();
            if (f != null) {
                for (java.util.Iterator<String> it = f.keys(); it.hasNext() && s.length() < 80; ) {
                    String k = it.next();
                    if (s.length() > 0) s.append("；");
                    s.append(k).append("：").append(f.opt(k));
                }
            }
            cm = s.toString();
        }
        line3.setText(Fmt.shortDateTime(Json.str(r, "received_at")) + (cm.isEmpty() ? "" : "　" + cm));
        int flags = who.getPaintFlags();
        who.setPaintFlags(invalid ? flags | Paint.STRIKE_THRU_TEXT_FLAG : flags & ~Paint.STRIKE_THRU_TEXT_FLAG);
        who.setTextColor(invalid ? Palette.of(c).text3 : Palette.of(c).text);
    }
}
