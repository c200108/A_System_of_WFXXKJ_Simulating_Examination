package cn.wfxxkj.teacher.dataapi;

import android.content.Context;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/** 列表里的一张 API 卡片：名称、状态、描述、总条数、今天、最后收到 */
final class ApiCard extends LinearLayout {
    private final TextView name, desc, nums, foot;
    private final LinearLayout tags;

    ApiCard(Context c) {
        super(c);
        setOrientation(VERTICAL);
        LinearLayout card = V.card(c);
        LinearLayout top = V.hbox(c);
        name = V.oneLine(V.bold(V.text(c, "", V.H3)));
        top.addView(name, V.fill());
        tags = V.hbox(c);
        top.addView(tags);
        card.addView(top);
        desc = V.lines(V.text(c, "", V.BODY2), 2);
        V.addTop(card, desc, 4);
        nums = V.text(c, "", V.BODY);
        V.addTop(card, nums, 8);
        foot = V.oneLine(V.text(c, "", V.CAPTION));
        V.addTop(card, foot, 4);
        addView(card, V.matchWrap());
    }

    void bind(JSONObject a, boolean admin) {
        Context c = getContext();
        name.setText(Json.str(a, "name"));
        tags.removeAllViews();
        boolean on = "active".equals(Json.str(a, "status"));
        tags.addView(V.tag(c, on ? "接收中" : "已暂停", on ? Tone.SUCCESS : Tone.NEUTRAL));
        String d = Json.str(a, "description");
        desc.setText(d.isEmpty() ? "（没有描述）" : d);
        nums.setText("共 " + Json.num(a, "record_count") + " 条 · 今天 " + Json.num(a, "today_count") + " 条");
        String last = Json.str(a, "last_received_at");
        String f = Json.str(a, "template_name") + " · " + (last.isEmpty() ? "还没收到过数据" : "最后收到 " + Fmt.shortDateTime(last));
        if (admin) f += " · " + Json.str(a, "owner_name");
        foot.setText(f);
    }
}
