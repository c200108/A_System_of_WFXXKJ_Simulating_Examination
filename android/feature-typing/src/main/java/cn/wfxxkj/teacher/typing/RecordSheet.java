package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/** 点一条成绩弹出来的详情：各项数据，看这个学生的学情，删除这条 */
final class RecordSheet {
    private RecordSheet() {}

    static void show(Screen s, JSONObject r, Runnable onDeleted) {
        Context c = s.ctx();
        String name = Json.str(r, "student_name");
        String cls = Json.str(r, "student_class");
        String module = Json.str(r, "module");
        Sheet sh = new Sheet(c, name + " 的练习成绩");

        LinearLayout box = V.vbox(c);
        TextView sub = V.text(c, cls + " · " + module + (Json.str(r, "difficulty").isEmpty() ? "" : " · " + Json.str(r, "difficulty")), V.BODY2);
        box.addView(sub);

        GridBox g = new GridBox(c, 120, 4, 10);
        int acc = Json.num(r, "accuracy");
        LinearLayout a = V.stat(c, acc + "%", "正确率", acc >= 80 ? Tone.SUCCESS : acc >= 60 ? Tone.WARNING : Tone.DANGER);
        g.addView(a);
        g.addView(V.stat(c, "键盘".equals(module) ? "—" : String.valueOf(Json.num(r, "speed")),
                "英文".equals(module) ? "速度（字母/分）" : "速度（字/分）", Tone.PRIMARY));
        g.addView(V.stat(c, TypingUi.mmss(Json.dblOrNull(r, "duration")), "用时", Tone.VIOLET));
        LinearLayout starBox = V.stat(c, TypingUi.stars(Json.num(r, "stars")), "评价", Tone.WARNING);
        g.addView(starBox);
        V.addTop(box, g, 12);

        LinearLayout kv = V.vbox(c);
        kv.addView(V.kv(c, "敲击字数", Json.num(r, "typed_chars") + ("键盘".equals(module) ? " 次按键" : " 字")));
        kv.addView(V.kv(c, "练习时间", Fmt.dateTime(Json.str(r, "created_at"))));
        V.addTop(box, kv, 8);
        sh.content(box);

        final String key = cls + "|" + name;
        sh.buttons("看他的学情", () -> {
            sh.dismiss();
            List<String> one = new ArrayList<>(Collections.singletonList(key));
            s.push(new AnalysisScreen(module, null, one));
        }, "删除", () -> Dialogs.confirm(c, "提示", "删除「" + name + "」这条 " + module + " 成绩？", "删除", true,
                () -> s.runBusy("正在删除…", () -> {
                    TypingApi.deleteOne(r.optLong("id"));
                    return true;
                }, ok -> {
                    sh.dismiss();
                    onDeleted.run();
                })), true);
        sh.show();
    }
}
