package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Charts;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tabs;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 学生学情（5.1.2）：和网页版学生名单「学情」一列点进去的页面一样，
 * 考试（成绩、全体名次、班内名次）、打字、教学网页数据（API 收到的）三块。
 * 教学网页数据只算自己建的 API（管理员看全部），后端 routers/insight.py 拦。
 */
final class StudentInsightScreen extends Screen {
    private final int sid;
    private final String name;
    private JSONObject data;
    private Tabs tabs;
    private LinearLayout page;
    private StateView state;

    StudentInsightScreen(int sid, String name) {
        this.sid = sid;
        this.name = name;
    }

    @Override
    public String title() {
        return name + " 的学情";
    }

    @Override
    public String subtitle() {
        if (data == null) return null;
        JSONObject s = Json.obj(data, "student");
        return Json.str(s, "student_no") + " · " + (Json.str(s, "student_class").isEmpty() ? "未分班" : Json.str(s, "student_class"));
    }

    @Override
    protected View onCreateView(Context ctx) {
        LinearLayout col = V.vbox(ctx);
        tabs = new Tabs(ctx).add("考试").add("打字").add("教学网页");
        tabs.setOnSelected(i -> render());
        col.addView(tabs, V.matchWrap());
        FrameLayout body = new FrameLayout(ctx);
        page = V.page(ctx);
        ScrollView sv = V.scroll(ctx, page);
        body.addView(sv, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        state = new StateView(ctx);
        body.addView(state, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        col.addView(body, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));
        return col;
    }

    @Override
    protected void onFirstShow() {
        tabs.select(0);
        load();
    }

    private void load() {
        state.loading();
        run(() -> Http.getObj("/students/" + sid + "/insight", null), d -> {
            data = d;
            state.hide();
            invalidateChrome();
            render();
        }, e -> {
            state.error(e.getMessage(), this::load);
            return true;
        });
    }

    private void render() {
        if (data == null) return;
        Context c = ctx();
        page.removeAllViews();
        JSONObject ex = Json.obj(data, "exams"), ty = Json.obj(data, "typing"), web = Json.obj(data, "web");

        GridBox kpi = new GridBox(c, 100, 6, 8);
        Double rate = Json.dblOrNull(ex, "avg_rate");
        kpi.addView(V.stat(c, String.valueOf(Json.num(ex, "count")), "参加考试", Tone.PRIMARY));
        kpi.addView(V.stat(c, rate == null ? "—" : Fmt.num(rate) + "%", "平均得分率", Tone.WARNING));
        kpi.addView(V.stat(c, Json.isNull(ex, "class_rank") ? "—" : Json.num(ex, "class_rank") + "/" + Json.num(ex, "class_size"),
                "班内综合名次", Tone.SUCCESS));
        kpi.addView(V.stat(c, String.valueOf(Json.num(ty, "count")), "打字练习", Tone.INFO));
        kpi.addView(V.stat(c, String.valueOf(Json.num(web, "count")), "教学网页数据", Tone.VIOLET));
        page.addView(kpi, V.matchWrap());

        int t = tabs.current();
        if (t == 0) renderExams(c, ex);
        else if (t == 1) renderTyping(c, ty);
        else renderWeb(c, web);
    }

    private void renderExams(Context c, JSONObject ex) {
        List<JSONObject> items = Json.list(Json.arr(ex, "items"));
        if (items.isEmpty()) {
            V.addTop(page, V.notice(c, "还没有参加过你看得到的考试。", Tone.NEUTRAL), 12);
            return;
        }
        List<Charts.Point> pts = new ArrayList<>();
        for (JSONObject i : items) if (!Json.isNull(i, "rate")) pts.add(new Charts.Point(Json.str(i, "title"), Json.dbl(i, "rate")));
        if (pts.size() > 1) {
            page.addView(V.section(c, "得分率走势", null, null));
            page.addView(card(c, new Charts.Line(c, 170).setData(pts)), V.matchWrap());
        }
        page.addView(V.section(c, "每场考试", null, null));
        List<JSONObject> rev = new ArrayList<>(items);
        Collections.reverse(rev);
        for (JSONObject i : rev) {
            LinearLayout card = V.card(c);
            LinearLayout top = V.hbox(c);
            top.addView(V.oneLine(V.bold(V.text(c, Json.str(i, "title"), V.BODY))), V.fill());
            top.addView(V.bold(V.text(c, Json.num(i, "score") + " / " + Json.num(i, "full"), V.H3)));
            card.addView(top);
            String sub = "全体第 " + Json.num(i, "rank") + " / " + Json.num(i, "takers")
                    + " · 班内第 " + Json.num(i, "class_rank") + " / " + Json.num(i, "class_takers");
            if (!Json.isNull(i, "rate")) sub = "得分率 " + Fmt.num(Json.dbl(i, "rate")) + "% · " + sub;
            card.addView(V.text(c, sub, V.BODY2));
            String sub2 = Fmt.shortDateTime(Json.str(i, "submitted_at"));
            if (!Json.isNull(i, "avg")) sub2 += " · 全体平均 " + Fmt.num(Json.dbl(i, "avg"));
            if (!Json.isNull(i, "class_avg")) sub2 += " · 班级平均 " + Fmt.num(Json.dbl(i, "class_avg"));
            if (Json.bool(i, "pending")) sub2 += " · 操作题待批";
            card.addView(V.text(c, sub2, V.CAPTION));
            V.addTop(page, card, 8);
        }
        TextView tip = V.text(c, "名次按每场考试里各学生最新一次交卷的分数算，同分同名次。", V.CAPTION);
        V.addTop(page, tip, 10);
    }

    private void renderTyping(Context c, JSONObject ty) {
        if (Json.num(ty, "count") == 0) {
            V.addTop(page, V.notice(c, "还没有打字练习记录。", Tone.NEUTRAL), 12);
            return;
        }
        page.addView(V.section(c, "各模块", null, null));
        for (JSONObject m : Json.list(Json.arr(ty, "modules"))) {
            LinearLayout card = V.card(c);
            card.addView(V.bold(V.text(c, Json.str(m, "module"), V.BODY)));
            String s = "练习 " + Json.num(m, "count") + " 次 · " + Json.num(m, "minutes") + " 分钟 · 平均正确率 " + Json.num(m, "avg_accuracy") + "%";
            if (!"键盘".equals(Json.str(m, "module")))
                s += "\n最快 " + Json.num(m, "best_speed") + " · 平均 " + Json.num(m, "avg_speed") + " 字/分";
            card.addView(V.text(c, s, V.BODY2));
            V.addTop(page, card, 8);
        }
        List<Charts.Point> pts = new ArrayList<>();
        for (JSONObject t : Json.list(Json.arr(ty, "trend")))
            if (!"键盘".equals(Json.str(t, "module"))) pts.add(new Charts.Point(Fmt.date(Json.str(t, "at")), Json.num(t, "speed")));
        if (pts.size() > 1) {
            page.addView(V.section(c, "打字速度走势（字/分）", null, null));
            page.addView(card(c, new Charts.Line(c, 170).setData(pts.subList(Math.max(0, pts.size() - 30), pts.size()))), V.matchWrap());
        }
        page.addView(V.section(c, "最近的练习", null, null));
        LinearLayout list = V.card(c);
        List<JSONObject> recent = Json.list(Json.arr(ty, "recent"));
        for (JSONObject r : recent.subList(0, Math.min(30, recent.size()))) {
            list.addView(V.kv(c, Fmt.shortDateTime(Json.str(r, "at")), Json.str(r, "module") + " " + Json.str(r, "difficulty")
                    + " · " + Json.num(r, "speed") + " 字/分 · 正确率 " + Json.num(r, "accuracy") + "%"));
        }
        page.addView(list, V.matchWrap());
    }

    private void renderWeb(Context c, JSONObject web) {
        V.addTop(page, V.notice(c, "第三方教学网页通过「API」送来的、学号对得上这个学生的数据。只显示你自己建的 API（管理员看全部）。",
                Tone.INFO), 12);
        List<JSONObject> apis = Json.list(Json.arr(web, "apis"));
        List<JSONObject> peer = Json.list(Json.arr(web, "peer_received"));
        if (apis.isEmpty() && peer.isEmpty()) {
            V.addTop(page, V.notice(c, "还没有这个学生的教学网页数据。", Tone.NEUTRAL), 8);
            return;
        }
        for (JSONObject a : apis) {
            LinearLayout card = V.card(c);
            card.addView(V.bold(V.text(c, Json.str(a, "name"), V.BODY)));
            String s = Json.num(a, "count") + " 条 · 最近 " + Fmt.shortDateTime(Json.str(a, "last_at"));
            if (!Json.isNull(a, "avg_rate")) s += " · 平均得分率 " + Fmt.num(Json.dbl(a, "avg_rate")) + "%";
            card.addView(V.text(c, s, V.BODY2));
            List<String> acts = Json.strings(Json.arr(a, "activities"));
            if (!acts.isEmpty()) card.addView(V.lines(V.text(c, String.join("、", acts), V.CAPTION), 2));
            V.addTop(page, card, 8);
        }
        List<JSONObject> dims = Json.list(Json.arr(web, "dimensions"));
        if (!dims.isEmpty()) {
            page.addView(V.section(c, "自评与同伴评价", null, null));
            LinearLayout box = V.card(c);
            Palette p = Palette.of(c);
            String[][] kinds = {{"self", "自评"}, {"peer", "同伴评价"}};
            for (String[] k : kinds) {
                List<Charts.Point> pts = new ArrayList<>();
                double max = 0;
                for (JSONObject d : dims) {
                    Double v = Json.dblOrNull(d, k[0]);
                    if (v == null) continue;
                    max = Math.max(max, v);
                    pts.add(new Charts.Point(Json.str(d, "item"), v, k[0].equals("peer") ? p.series(1) : 0, Fmt.num(v)));
                }
                if (pts.isEmpty()) continue;
                V.addTop(box, V.text(c, k[1], V.LABEL), box.getChildCount() == 0 ? 0 : 10);
                box.addView(new Charts.HBars(c).setMax(max > 10 ? 100 : Math.max(5, Math.ceil(max))).setData(pts), V.matchWrap());
            }
            page.addView(box, V.matchWrap());
        }
        List<JSONObject> recent = Json.list(Json.arr(web, "recent"));
        if (!recent.isEmpty()) {
            page.addView(V.section(c, "他提交的数据", null, null));
            for (JSONObject r : recent.subList(0, Math.min(40, recent.size()))) V.addTop(page, recordCard(c, r, false), 6);
        }
        if (!peer.isEmpty()) {
            page.addView(V.section(c, "同伴给他的评价（" + peer.size() + "）", null, null));
            for (JSONObject r : peer) V.addTop(page, recordCard(c, r, true), 6);
        }
    }

    private View recordCard(Context c, JSONObject r, boolean byPeer) {
        LinearLayout card = V.card(c);
        LinearLayout top = V.hbox(c);
        String head = byPeer ? Json.str(r, "student") + " 评" : Json.str(r, "type_name") + " · " + Json.str(r, "api_name");
        top.addView(V.oneLine(V.bold(V.text(c, head, V.BODY2))), V.fill());
        Double s = Json.dblOrNull(r, "score");
        if (s != null) {
            Double m = Json.dblOrNull(r, "max_score");
            top.addView(V.bold(V.text(c, Fmt.num(s) + (m == null ? "" : " / " + Fmt.num(m)), V.BODY)));
        }
        card.addView(top);
        String act = Json.str(r, "activity");
        String line = Fmt.shortDateTime(Json.str(r, "at")) + (act.isEmpty() ? "" : " · " + act);
        card.addView(V.text(c, line, V.CAPTION));
        String cm = Json.str(r, "comment");
        if (!cm.isEmpty()) card.addView(V.lines(V.text(c, cm, V.BODY2), 3));
        return card;
    }

    private View card(Context c, View content) {
        LinearLayout card = V.card(c);
        card.addView(content, V.matchWrap());
        return card;
    }
}
