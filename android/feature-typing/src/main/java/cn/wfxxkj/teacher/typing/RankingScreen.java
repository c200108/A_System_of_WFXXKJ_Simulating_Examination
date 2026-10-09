package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 学情分析里的「学生名单」全表：可按名次、练习次数、速度、正确率、达标率、进步、最近一次排序，
 * 搜姓名 / 班级；点一个学生看他自己的学情（学生对比视角）。
 */
final class RankingScreen extends Screen {
    private final List<JSONObject> all;
    private final boolean speedy;
    private final String unit;
    private final String module;
    private String sort;
    private String keyword = "";
    private ItemList<JSONObject> list;

    RankingScreen(List<JSONObject> ranking, boolean speedy, String unit, String sort, String module) {
        this.all = ranking;
        this.speedy = speedy;
        this.unit = unit;
        this.sort = sort;
        this.module = module;
    }

    @Override
    public String title() {
        return "学生名单";
    }

    @Override
    public String subtitle() {
        return module + " · " + all.size() + " 人";
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                LinearLayout box = V.vbox(ctx);
                box.setBackground(V.stroke(ctx, Palette.of(ctx).surface, Palette.of(ctx).border, 14));
                return box;
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                LinearLayout box = (LinearLayout) v;
                box.removeAllViews();
                box.addView(row(v.getContext(), item, speedy, unit), V.matchWrap());
            }
        });
        list.setCell(360, 3);
        LinearLayout head = V.vbox(c);
        SearchBox sb = new SearchBox(c, "搜姓名或班级");
        sb.setOnSearch(k -> {
            keyword = k.toLowerCase();
            refresh();
        });
        head.addView(sb.padded());
        ChipRow sr = new ChipRow(c);
        sr.setOptions(sorts(speedy), sort);
        sr.setOnPicked(o -> {
            sort = String.valueOf(o.value);
            refresh();
        });
        head.addView(sr);
        TextView note = V.text(c, "进步：这段时间里最后 3 次的平均" + (speedy ? "速度" : "正确率")
                + "减最初 3 次的，练满 4 次才算。", V.CAPTION);
        V.pad(note, 4, 4, 0, 6);
        head.addView(note);
        list.addHeader(head);
        list.setEmpty("没有找到学生", null);
        list.setOnItemClick((o, pos) -> {
            List<String> one = new ArrayList<>(Collections.singletonList(Json.str(o, "key")));
            push(new AnalysisScreen(module, null, one));
        });
        refresh();
        return list;
    }

    private void refresh() {
        List<JSONObject> out = new ArrayList<>();
        for (JSONObject o : sort(all, sort)) {
            String s = (Json.str(o, "name") + " " + Json.str(o, "class")).toLowerCase();
            if (keyword.isEmpty() || s.contains(keyword)) out.add(o);
        }
        list.setItems(out);
    }

    // ---------------------------------------------------------------- 共用（分析页的前 10 名也用）

    static List<Option> sorts(boolean speedy) {
        List<Option> o = new ArrayList<>();
        o.add(new Option("rank", "名次"));
        o.add(new Option("count", "练习次数"));
        if (speedy) {
            o.add(new Option("best_speed", "最快"));
            o.add(new Option("avg_speed", "平均速度"));
        }
        o.add(new Option("avg_accuracy", "正确率"));
        o.add(new Option("reach_rate", "达标率"));
        o.add(new Option("progress", "进步"));
        o.add(new Option("last_at", "最近练习"));
        return o;
    }

    /** 名次从小到大；其余从高到低（没值的排最后） */
    static List<JSONObject> sort(List<JSONObject> src, final String key) {
        List<JSONObject> out = new ArrayList<>(src);
        if ("last_at".equals(key)) {
            Collections.sort(out, (a, b) -> Json.str(b, "last_at").compareTo(Json.str(a, "last_at")));
        } else if ("rank".equals(key)) {
            Collections.sort(out, (a, b) -> Json.num(a, "rank") - Json.num(b, "rank"));
        } else {
            Collections.sort(out, new Comparator<JSONObject>() {
                @Override
                public int compare(JSONObject a, JSONObject b) {
                    Double x = Json.dblOrNull(a, key), y = Json.dblOrNull(b, key);
                    if (x == null && y == null) return 0;
                    if (x == null) return 1;
                    if (y == null) return -1;
                    return Double.compare(y, x);
                }
            });
        }
        return out;
    }

    /** 一行：名次圆标、姓名班级、各项数字 */
    static View row(Context c, JSONObject o, boolean speedy, String unit) {
        Palette p = Palette.of(c);
        LinearLayout row = V.hbox(c);
        row.setGravity(Gravity.CENTER_VERTICAL);
        V.pad(row, 12, 10, 12, 10);
        int rank = Json.num(o, "rank");
        TextView r = V.text(c, String.valueOf(rank), V.LABEL);
        r.setGravity(Gravity.CENTER);
        int[] tone = p.tone(rank == 1 ? cn.wfxxkj.teacher.core.ui.Tone.WARNING
                : rank <= 3 ? cn.wfxxkj.teacher.core.ui.Tone.PRIMARY : cn.wfxxkj.teacher.core.ui.Tone.NEUTRAL);
        r.setTextColor(tone[0]);
        r.setBackground(V.round(c, tone[1], 14));
        row.addView(r, new LinearLayout.LayoutParams(Ui.dp(c, 28), Ui.dp(c, 28)));

        LinearLayout mid = V.vbox(c);
        V.pad(mid, 12, 0, 8, 0);
        LinearLayout nl = V.hbox(c);
        nl.addView(V.oneLine(V.text(c, Json.str(o, "name"), V.H3)));
        TextView cls = V.oneLine(V.text(c, Json.str(o, "class"), V.CAPTION));
        V.pad(cls, 8, 0, 0, 0);
        nl.addView(cls, V.fill());
        mid.addView(nl);
        StringBuilder b = new StringBuilder();
        b.append("练 ").append(Json.num(o, "count")).append(" 次");
        if (speedy) b.append(" · 均速 ").append(TypingUi.num(o, "avg_speed")).append(" · 最快 ").append(TypingUi.num(o, "best_speed"));
        b.append(" · 达标 ").append(TypingUi.pct(o, "reach_rate"));
        mid.addView(V.lines(V.text(c, b.toString(), V.BODY2), 2));
        String last = Json.str(o, "last_at");
        if (!last.isEmpty()) mid.addView(V.oneLine(V.text(c, "最近 " + last, V.CAPTION)));
        row.addView(mid, V.fill());

        LinearLayout right = V.vbox(c);
        right.setGravity(Gravity.END);
        Double acc = Json.dblOrNull(o, "avg_accuracy");
        TextView a = V.text(c, TypingUi.pct(o, "avg_accuracy"), V.H3);
        if (acc != null) a.setTextColor(TypingUi.accuracyColor(c, acc));
        right.addView(a);
        Double prog = Json.dblOrNull(o, "progress");
        TextView pr = V.text(c, "进步 " + TypingUi.signed(prog), V.CAPTION);
        if (prog != null && prog != 0) pr.setTextColor(prog > 0 ? p.success : p.danger);
        right.addView(pr);
        row.addView(right);
        return row;
    }
}
