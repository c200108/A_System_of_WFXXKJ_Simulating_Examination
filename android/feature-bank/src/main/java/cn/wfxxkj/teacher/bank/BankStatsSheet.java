package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.widget.LinearLayout;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Charts;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 题库概况：总数、带图、必出、各题型数量、难度分布、知识范围分布。
 * 网页把这些写成表格上方的一段统计文字，这里做成图。
 */
final class BankStatsSheet {
    private BankStatsSheet() {}

    static void show(Context c, JSONObject stats) {
        Sheet s = new Sheet(c, "题库概况");
        LinearLayout body = V.vbox(c);

        GridBox grid = new GridBox(c, 96, 4, 10);
        grid.addView(V.stat(c, String.valueOf(stats.optInt("total")), "题目总数", Tone.PRIMARY));
        grid.addView(V.stat(c, String.valueOf(stats.optInt("with_image")), "带图", Tone.INFO));
        grid.addView(V.stat(c, String.valueOf(stats.optInt("pinned")), "必出", Tone.WARNING));
        grid.addView(V.stat(c, String.valueOf(Json.arr(stats, "sources").length()), "来源", Tone.NEUTRAL));
        body.addView(grid, V.matchWrap());

        // 各题型
        JSONObject byType = Json.obj(stats, "by_type");
        if (byType.length() > 0) {
            V.addTop(body, V.text(c, "题型", V.LABEL), 18);
            List<Charts.Point> pts = new ArrayList<>();
            Iterator<String> it = byType.keys();
            while (it.hasNext()) {
                String k = it.next();
                pts.add(new Charts.Point(k, byType.optInt(k)));
            }
            V.addTop(body, Charts.donut(c, pts, String.valueOf(stats.optInt("total")), "题"), 8);
        }

        // 难度分布：组卷时按难度给每道题分配分值
        JSONObject byLv = Json.obj(stats, "by_difficulty");
        V.addTop(body, V.text(c, "难度分布", V.LABEL), 18);
        List<Charts.Point> lv = new ArrayList<>();
        Palette p = Palette.of(c);
        for (int i = 1; i <= 5; i++) {
            Tone t = Bank.levelTone(i);
            int color = t == Tone.NEUTRAL ? p.text3 : p.tone(t)[0];
            lv.add(new Charts.Point(i + " 级", byLv.optInt(String.valueOf(i)), color, null));
        }
        V.addTop(body, new Charts.Bars(c, 150).setData(lv), 8);
        V.addTop(body, V.text(c, "组卷时按难度给每道题分配分值", V.CAPTION), 4);

        // 知识范围
        JSONObject byScope = Json.obj(stats, "by_scope");
        if (byScope.length() > 0) {
            V.addTop(body, V.text(c, "知识范围", V.LABEL), 18);
            List<Charts.Point> sp = new ArrayList<>();
            Iterator<String> it = byScope.keys();
            while (it.hasNext()) {
                String k = it.next();
                sp.add(new Charts.Point(k, byScope.optInt(k)));
            }
            V.addTop(body, new Charts.HBars(c).setData(sp), 8);
        }

        s.content(body);
        s.buttons(null, null, "关闭", s::dismiss);
        s.show();
    }
}
