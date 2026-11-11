package cn.wfxxkj.teacher.dataapi;

import android.content.Context;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;
import cn.wfxxkj.teacher.core.ui.Charts;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tabs;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 某个 API 里面：数据 / 来源网页 / 图表 / 接入，和网页版的四个标签一一对应。
 * 字段命名、来源白名单这些复杂设置只在网页上做，「接入」页底下有说明。
 * 图表页每 10 秒刷新一次（只在这一页、APP 在前台时）。
 */
final class ApiDetailScreen extends Screen {
    private static final int T_DATA = 0, T_SOURCES = 1, T_CHARTS = 2, T_CONNECT = 3;

    private final int id;
    private String name;
    private final int startTab;
    private JSONObject info;

    private Tabs tabs;
    private FrameLayout body;
    private ItemList<JSONObject> records;
    private ItemList<JSONObject> sources;
    private LinearLayout charts, connect;
    private ScrollView chartsScroll, connectScroll;
    private int page = 1;
    private int total = 0;
    private String pageFilter = null;     // 来源网页筛选；"-" = 没注明来源
    private boolean shown;
    private int tick = 0;

    ApiDetailScreen(int id, String name) {
        this(id, name, T_DATA);
    }

    ApiDetailScreen(int id, String name, int tab) {
        this.id = id;
        this.name = name;
        this.startTab = tab;
    }

    @Override
    public String title() {
        return name;
    }

    @Override
    public String subtitle() {
        if (info == null) return null;
        boolean on = "active".equals(Json.str(info, "status"));
        return (on ? "接收中" : "已暂停") + " · 共 " + Json.num(info, "record_count") + " 条";
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (info == null) return a;
        boolean on = "active".equals(Json.str(info, "status"));
        a.add(Action.icon(on ? R.drawable.ic_stop : R.drawable.ic_play_arrow, on ? "暂停接收" : "恢复接收", this::togglePause));
        a.add(Action.menu(R.drawable.ic_download, "导出 Excel", this::export));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::reloadAll));
        if (session().isAdmin()) a.add(Action.menu(R.drawable.ic_person, "转给其他老师", this::transfer));
        a.add(Action.menu(R.drawable.ic_delete, "删除这个 API", this::deleteApi));
        return a;
    }

    @Override
    protected View onCreateView(Context ctx) {
        LinearLayout col = V.vbox(ctx);
        tabs = new Tabs(ctx).add("数据").add("来源网页").add("图表").add("接入");
        col.addView(tabs, V.matchWrap());
        body = new FrameLayout(ctx);
        col.addView(body, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));

        records = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return new RecordCard(c);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((RecordCard) v).bind(item);
            }
        });
        records.setCell(320, 3);
        records.setOnRefresh(() -> loadRecords(true));
        records.setOnLoadMore(() -> loadRecords(false));
        records.setOnItemClick((r, pos) -> openRecord(r));
        records.setEmpty("还没有数据", "把接收地址放进教学网页，学生提交后这里就有了");

        sources = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                LinearLayout card = V.card(c);
                card.addView(V.lines(V.text(c, "", V.BODY), 2));
                card.addView(V.text(c, "", V.CAPTION));
                LinearLayout wrap = V.vbox(c);
                wrap.addView(card, V.matchWrap());
                return wrap;
            }

            @Override
            public void bind(View v, JSONObject s, int position) {
                LinearLayout card = (LinearLayout) ((LinearLayout) v).getChildAt(0);
                String p = Json.str(s, "page");
                ((TextView) card.getChildAt(0)).setText(p.isEmpty() ? "（未注明来源网页）" : p);
                Double avg = Json.dblOrNull(s, "avg_score");
                ((TextView) card.getChildAt(1)).setText(Json.num(s, "records") + " 条 · " + Json.num(s, "people") + " 人 · 对上名单 "
                        + Json.num(s, "matched") + (avg == null ? "" : " · 平均 " + Fmt.num(avg))
                        + "\n最近 " + Fmt.shortDateTime(Json.str(s, "last_at")));
            }
        });
        sources.setCell(320, 3);
        sources.setOnRefresh(this::loadSources);
        sources.setEmpty("还没有数据", "同一个 API 可以给好几个网页用，这里按网页分开看");
        sources.setOnItemClick((s, pos) -> {
            String p = Json.str(s, "page");
            pageFilter = p.isEmpty() ? "-" : p;
            tabs.select(T_DATA);
            loadRecords(true);
            toast("只看这个网页的数据，回到「来源网页」可换");
        });

        charts = V.page(ctx);
        chartsScroll = V.scroll(ctx, charts);
        connect = V.page(ctx);
        connectScroll = V.scroll(ctx, connect);

        body.addView(records, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        body.addView(sources, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        body.addView(chartsScroll, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        body.addView(connectScroll, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        tabs.setOnSelected(this::showTab);
        return col;
    }

    @Override
    protected void onFirstShow() {
        tabs.select(startTab);
        if (startTab == T_DATA) showTab(T_DATA);
        loadInfo();
        loadRecords(true);
    }

    @Override
    protected void onShow() {
        shown = true;
        scheduleTick();
    }

    @Override
    protected void onHide() {
        shown = false;
    }

    private void showTab(int i) {
        records.setVisibility(i == T_DATA ? View.VISIBLE : View.GONE);
        sources.setVisibility(i == T_SOURCES ? View.VISIBLE : View.GONE);
        chartsScroll.setVisibility(i == T_CHARTS ? View.VISIBLE : View.GONE);
        connectScroll.setVisibility(i == T_CONNECT ? View.VISIBLE : View.GONE);
        if (i == T_SOURCES) loadSources();
        if (i == T_CHARTS) loadCharts(false);
        if (i == T_CONNECT) renderConnect();
    }

    private void reloadAll() {
        loadInfo();
        loadRecords(true);
        if (tabs.current() == T_SOURCES) loadSources();
        if (tabs.current() == T_CHARTS) loadCharts(false);
    }

    /** 图表页每 10 秒刷新 */
    private void scheduleTick() {
        final int my = ++tick;
        post(() -> {
            if (my != tick || isDestroyed() || !shown) return;
            if (tabs.current() == T_CHARTS) loadCharts(true);
            scheduleTick();
        }, 10_000);
    }

    // ---------------------------------------------------------------- 取数
    private void loadInfo() {
        run(() -> DataApiClient.get(id), a -> {
            info = a;
            name = Json.str(a, "name");
            invalidateChrome();
            if (tabs.current() == T_CONNECT) renderConnect();
        });
    }

    private Params filters() {
        Params p = Params.of();
        if (pageFilter != null) p.add("page_url", pageFilter);
        return p;
    }

    private void loadRecords(final boolean fresh) {
        if (fresh) {
            page = 1;
            records.loading();
        }
        final int pg = page;
        final Params f = filters();
        run(() -> DataApiClient.records(id, pg, f), r -> {
            List<JSONObject> items = Json.list(Json.arr(r, "items"));
            total = Json.num(r, "total");
            boolean more = pg * 30 < total;
            if (fresh) records.setItems(items, more);
            else records.appendItems(items, more);
            page = pg + 1;
        }, e -> {
            records.error(e.getMessage(), () -> loadRecords(true));
            return true;
        });
    }

    private void loadSources() {
        sources.loading();
        run(() -> DataApiClient.sources(id), sources::setItems, e -> {
            sources.error(e.getMessage(), this::loadSources);
            return true;
        });
    }

    private void loadCharts(boolean quiet) {
        if (!quiet && charts.getChildCount() == 0) {
            charts.addView(V.text(ctx(), "正在取数…", V.BODY2));
        }
        run(() -> DataApiClient.stats(id, null), this::renderCharts, e -> quiet);
    }

    // ---------------------------------------------------------------- 一条数据
    private void openRecord(JSONObject r) {
        Context c = ctx();
        Sheet s = new Sheet(c, "数据 #" + Json.num(r, "id"));
        LinearLayout b = V.vbox(c);
        JSONObject st = Json.obj(r, "student");
        b.addView(V.kv(c, "学生", (Json.str(st, "name") + " " + Json.str(st, "no") + " " + Json.str(st, "class")).trim()
                + (Json.bool(r, "student_matched") ? "（对上名单）" : "")));
        b.addView(V.kv(c, "类型", ApiUi.typeName(Json.str(r, "type"))));
        JSONObject act = Json.obj(r, "activity");
        b.addView(V.kv(c, "活动", Json.str(act, "name").isEmpty() ? Json.str(act, "id") : Json.str(act, "name")));
        b.addView(V.kv(c, "得分", ApiUi.score(r)));
        b.addView(V.kv(c, "评语", Json.str(r, "comment")));
        b.addView(V.kv(c, "来源网页", Json.str(r, "page")));
        b.addView(V.kv(c, "收到时间", Fmt.dateTime(Json.str(r, "received_at"))));
        TextView raw = V.text(c, ApiUi.pretty(r.opt("payload")), V.CAPTION);
        raw.setTypeface(android.graphics.Typeface.MONOSPACE);
        raw.setTextIsSelectable(true);
        raw.setBackground(V.round(c, Palette.of(c).surfaceAlt, 10));
        V.pad(raw, 10);
        V.addTop(b, V.text(c, "原始数据", V.LABEL), 10);
        V.addTop(b, raw, 4);
        s.content(b);
        final boolean invalid = "invalid".equals(Json.str(r, "flag"));
        final List<Integer> ids = Collections.singletonList(Json.num(r, "id"));
        s.buttons("删除", () -> Dialogs.confirm(c, "删除这条数据", "删掉的在回收站放 7 天，可以还原。", "删除", true, () ->
                        runBusy("正在删除…", () -> {
                            DataApiClient.deleteRecords(id, ids);
                            return true;
                        }, ok -> {
                            s.dismiss();
                            changed();
                        })),
                invalid ? "恢复有效" : "标为无效", () -> runBusy("正在保存…", () -> {
                    DataApiClient.flag(id, ids, invalid ? "normal" : "invalid");
                    return true;
                }, ok -> {
                    s.dismiss();
                    toast(invalid ? "已恢复" : "已标成无效，不再计入统计");
                    loadRecords(true);
                }));
        s.show();
    }

    private void changed() {
        ApiListScreen.version++;
        loadInfo();
        loadRecords(true);
    }

    // ---------------------------------------------------------------- 图表
    private void renderCharts(JSONObject d) {
        Context c = ctx();
        Palette p = Palette.of(c);
        charts.removeAllViews();
        if (Json.num(d, "records") == 0) {
            charts.addView(V.notice(c, "还没有数据。把接收地址放进教学网页，学生提交后这里就会动起来（每 10 秒刷新）。", Tone.INFO));
            return;
        }
        GridBox kpi = new GridBox(c, 100, 6, 8);
        kpi.addView(V.stat(c, String.valueOf(Json.num(d, "people")), "提交人数", Tone.PRIMARY));
        if (!Json.isNull(d, "expected")) {
            int exp = Json.num(d, "expected"), got = Json.num(d, "submitted_roster");
            kpi.addView(V.stat(c, got + "/" + exp, "名单完成 " + (exp > 0 ? Math.round(got * 100f / exp) : 0) + "%", Tone.SUCCESS));
        }
        kpi.addView(V.stat(c, String.valueOf(Json.num(d, "records")), "提交条数", Tone.NEUTRAL));
        Double rate = Json.dblOrNull(d, "avg_rate"), avg = Json.dblOrNull(d, "avg_score");
        if (rate != null) kpi.addView(V.stat(c, Fmt.num(rate) + "%", "平均得分率", Tone.WARNING));
        else if (avg != null) kpi.addView(V.stat(c, Fmt.num(avg), "平均分", Tone.WARNING));
        kpi.addView(V.stat(c, String.valueOf(Json.num(d, "last5min")), "最近 5 分钟", Tone.INFO));
        charts.addView(kpi, V.matchWrap());

        // 提交时间线
        List<Charts.Point> tl = new ArrayList<>();
        for (JSONObject t : Json.list(Json.arr(d, "timeline"))) tl.add(new Charts.Point(Json.str(t, "t"), Json.num(t, "n")));
        if (tl.size() > 1) {
            charts.addView(V.section(c, "提交时间线", null, null));
            charts.addView(card(new Charts.Line(c, 180).setData(tl)), V.matchWrap());
        }
        // 成绩分布
        if (avg != null) {
            JSONObject dist = Json.obj(d, "distribution");
            List<String> labels = Json.strings(Json.arr(dist, "labels"));
            List<Integer> vals = Json.ints(Json.arr(dist, "values"));
            List<Charts.Point> bars = new ArrayList<>();
            for (int i = 0; i < Math.min(labels.size(), vals.size()); i++) {
                String l = labels.get(i);
                bars.add(new Charts.Point(l.contains("~") ? l.substring(0, l.indexOf('~')) : l, vals.get(i)));
            }
            charts.addView(V.section(c, "成绩分布", null, null));
            charts.addView(card(new Charts.Bars(c, 170).setData(bars)), V.matchWrap());
        }
        // 逐题正确率（从低到高）
        List<JSONObject> qs = new ArrayList<>();
        for (JSONObject q : Json.list(Json.arr(d, "questions"))) if (!Json.isNull(q, "rate")) qs.add(q);
        if (!qs.isEmpty()) {
            Collections.sort(qs, (a, b) -> Double.compare(Json.dbl(a, "rate"), Json.dbl(b, "rate")));
            List<Charts.Point> pts = new ArrayList<>();
            for (JSONObject q : qs.subList(0, Math.min(30, qs.size()))) {
                double r = Json.dbl(q, "rate");
                int color = r < 60 ? p.danger : r < 85 ? p.warning : p.success;
                pts.add(new Charts.Point("第" + Json.str(q, "q") + "题", r, color, Fmt.num(r) + "%"));
            }
            charts.addView(V.section(c, "逐题正确率", null, null));
            charts.addView(card(new Charts.HBars(c).setMax(100).setData(pts)), V.matchWrap());
        }
        // 评价维度：自评、互评各一组横条
        List<JSONObject> radar = Json.list(Json.arr(d, "radar"));
        if (!radar.isEmpty()) {
            charts.addView(V.section(c, "评价维度", null, null));
            LinearLayout box = V.card(c);
            String[][] kinds = {{"self", "自评"}, {"peer", "互评"}, {"other", "评分"}};
            for (String[] k : kinds) {
                List<Charts.Point> pts = new ArrayList<>();
                double max = 0;
                for (JSONObject r : radar) {
                    Double v = Json.dblOrNull(r, k[0]);
                    if (v == null) continue;
                    max = Math.max(max, v);
                    pts.add(new Charts.Point(Json.str(r, "item"), v, k[0].equals("peer") ? p.series(1) : 0, Fmt.num(v)));
                }
                if (pts.isEmpty()) continue;
                V.addTop(box, V.text(c, k[1], V.LABEL), box.getChildCount() == 0 ? 0 : 10);
                box.addView(new Charts.HBars(c).setMax(max > 10 ? 100 : Math.max(5, Math.ceil(max))).setData(pts), V.matchWrap());
            }
            charts.addView(box, V.matchWrap());
        }
        // 班级对比
        List<JSONObject> cls = Json.list(Json.arr(d, "classes"));
        if (cls.size() > 1) {
            List<Charts.Point> pts = new ArrayList<>();
            for (JSONObject x : cls) pts.add(new Charts.Point(Json.str(x, "class"), Json.num(x, "people"), 0, Json.num(x, "people") + " 人"));
            charts.addView(V.section(c, "班级对比（人数）", null, null));
            charts.addView(card(new Charts.HBars(c).setData(pts)), V.matchWrap());
        }
        // 数据类型
        List<JSONObject> types = Json.list(Json.arr(d, "types"));
        if (types.size() > 1) {
            List<Charts.Point> pts = new ArrayList<>();
            for (JSONObject t : types) pts.add(new Charts.Point(Json.str(t, "name"), Json.num(t, "n")));
            charts.addView(V.section(c, "数据类型", null, null));
            charts.addView(card(Charts.donut(c, pts, String.valueOf(Json.num(d, "records")), "条")), V.matchWrap());
        }
        // 评语高频词
        JSONArray kw = Json.arr(d, "keywords");
        if (kw != null && kw.length() > 0) {
            List<Charts.Point> pts = new ArrayList<>();
            for (int i = 0; i < Math.min(10, kw.length()); i++) {
                JSONArray w = kw.optJSONArray(i);
                if (w != null) pts.add(new Charts.Point(w.optString(0), w.optDouble(1), p.violet, null));
            }
            charts.addView(V.section(c, "评语高频词", null, null));
            charts.addView(card(new Charts.HBars(c).setData(pts)), V.matchWrap());
        }
        // 还没交的
        List<JSONObject> miss = Json.list(Json.arr(d, "missing"));
        if (!miss.isEmpty()) {
            StringBuilder sb = new StringBuilder();
            for (JSONObject m : miss) sb.append(sb.length() > 0 ? "、" : "").append(Json.str(m, "name"));
            charts.addView(V.section(c, "名单里还没交的（" + miss.size() + "）", null, null));
            charts.addView(card(V.text(c, sb, V.BODY)), V.matchWrap());
        }
        // 最新提交
        LinearLayout feed = V.card(c);
        for (JSONObject x : Json.list(Json.arr(d, "latest"))) {
            String sc = ApiUi.score(x);
            feed.addView(V.kv(c, Fmt.shortDateTime(Json.str(x, "at")),
                    Json.str(x, "student") + "  " + Json.str(x, "class") + (sc.isEmpty() ? "" : "  " + sc)));
        }
        charts.addView(V.section(c, "最新提交", null, null));
        charts.addView(feed, V.matchWrap());
        TextView tip = V.text(c, "每 10 秒自动刷新。互评矩阵、投屏大图请在电脑网页上看。", V.CAPTION);
        V.addTop(charts, tip, 12);
    }

    private View card(View content) {
        LinearLayout card = V.card(ctx());
        card.addView(content, V.matchWrap());
        return card;
    }

    // ---------------------------------------------------------------- 接入
    private void renderConnect() {
        Context c = ctx();
        connect.removeAllViews();
        if (info == null) {
            connect.addView(V.text(c, "正在取…", V.BODY2));
            return;
        }
        final String ep = DataApiClient.endpoint(info);
        final String wt = Json.str(info, "write_token");
        final String rt = Json.str(info, "read_token");
        connect.addView(V.notice(c, "把接收地址和写入密钥放进你的教学网页，学生提交时 POST 一条 JSON 过来就行。"
                + "写入密钥只能往这个 API 里写，看不到任何数据。", Tone.INFO), V.matchWrap());

        // AI 专用提示词：老师整段发给 AI，做出来的网页直接接上这个 API
        LinearLayout ai = V.vbox(c);
        Palette p = Palette.of(c);
        ai.setBackground(V.stroke(c, p.surface, p.border, 16));
        ai.setClipToOutline(true);
        ai.addView(V.row(c, R.drawable.ic_content_copy, Tone.PRIMARY, "复制 AI 提示词",
                "发给 AI 做教学网页、问卷网页，数据自动接进来", null, v ->
                        runBusy("正在生成…", () -> DataApiClient.aiPrompt(id), text -> {
                            Sys.copy(c, "AI 提示词", text);
                            toast("已复制，在最后「老师的要求」里写上要做的网页");
                        })));
        ai.addView(V.divider(c));
        ai.addView(V.row(c, R.drawable.ic_share, Tone.INFO, "分享 AI 提示词", "发到电脑上再交给 AI", null, v ->
                runBusy("正在生成…", () -> DataApiClient.aiPrompt(id), text ->
                        Sys.share(c, Json.str(info, "name") + " AI 提示词", text))));
        V.addTop(connect, ai, 10);

        LinearLayout keys = V.card(c);
        keys.addView(V.kv(c, "接收地址", ep));
        keys.addView(V.kv(c, "写入密钥", wt));
        keys.addView(V.kv(c, "读取密钥", rt.isEmpty() ? "未开启（给服务器端程序取数据用）" : rt));
        V.addTop(connect, keys, 10);

        LinearLayout ops = V.vbox(c);
        ops.setBackground(V.stroke(c, p.surface, p.border, 16));
        ops.setClipToOutline(true);
        ops.addView(V.row(c, R.drawable.ic_content_copy, Tone.PRIMARY, "复制接收地址", null, null, v -> {
            Sys.copy(c, "接收地址", ep);
            toast("已复制接收地址");
        }));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, R.drawable.ic_key, Tone.PRIMARY, "复制写入密钥", null, null, v -> {
            Sys.copy(c, "写入密钥", wt);
            toast("已复制写入密钥");
        }));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, R.drawable.ic_share, Tone.INFO, "分享接入信息", "发到电脑上，粘进网页代码里", null, v ->
                Sys.share(c, Json.str(info, "name") + " 接入信息", sample(ep, wt))));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, R.drawable.ic_playlist_add, Tone.SUCCESS, "发一条测试数据", "看看数据列表和图表是不是都有了", null, v ->
                runBusy("正在发送…", () -> DataApiClient.test(id), r -> {
                    toast("已发一条测试数据");
                    changed();
                })));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, R.drawable.ic_restart_alt, Tone.WARNING, "重新生成写入密钥", "旧密钥立刻失效，网页里的要换成新的", null, v ->
                Dialogs.confirm(c, "重新生成写入密钥", "旧密钥立刻失效，已经写进网页里的要换成新的。确定？", "重新生成", true, () ->
                        runBusy("正在生成…", () -> DataApiClient.rotate(id, "write", true), a -> {
                            info = a;
                            renderConnect();
                            toast("已生成新密钥");
                        }))));
        ops.addView(V.divider(c));
        ops.addView(V.row(c, R.drawable.ic_lock, Tone.NEUTRAL, rt.isEmpty() ? "开启读取接口" : "关闭读取接口",
                "读取密钥给服务器端程序取回数据用，不要写进网页", null, v ->
                        runBusy("正在保存…", () -> DataApiClient.rotate(id, "read", rt.isEmpty()), a -> {
                            info = a;
                            renderConnect();
                        })));
        V.addTop(connect, ops, 12);

        connect.addView(V.section(c, "网页里这样写", "复制", v -> {
            Sys.copy(c, "示例代码", sample(ep, wt));
            toast("已复制示例代码");
        }));
        TextView code = V.text(c, sample(ep, wt), V.CAPTION);
        code.setTypeface(android.graphics.Typeface.MONOSPACE);
        code.setTextIsSelectable(true);
        code.setBackground(V.round(c, p.surfaceAlt, 10));
        V.pad(code, 12);
        connect.addView(code, V.matchWrap());
        TextView tip = V.text(c, "接收时间段、只算最新一条、关联班级、来源网站白名单、字段中文名这些设置，请在电脑网页「API → 设置」里改。", V.CAPTION);
        V.addTop(connect, tip, 12);
    }

    private String sample(String ep, String wt) {
        String sdk = DataApiClient.sdk();
        return "<script src=\"" + sdk + "\"></script>\n<script>\n"
                + "  const api = WFXX.api('" + Json.str(info, "key") + "', '" + wt + "');\n"
                + "  api.send({\n"
                + "    type: 'answer',\n"
                + "    student: { no: '20250101', name: '张三', class: '七年级1班' },\n"
                + "    activity: { id: 'L3-T1', name: '第3课 任务1' },\n"
                + "    score: 8, max_score: 10,\n"
                + "    answers: [{ q: '1', answer: 'B', correct: true }]\n"
                + "  });\n</script>\n\n"
                + "接收地址：" + ep + "\n写入密钥：" + wt + "\n"
                + "也可以直接 POST JSON 到接收地址，请求头带 X-Api-Key: 写入密钥。";
    }

    // ---------------------------------------------------------------- 操作
    private void togglePause() {
        final boolean on = "active".equals(Json.str(info, "status"));
        runBusy(on ? "正在暂停…" : "正在恢复…", () -> DataApiClient.update(id, Json.of("status", on ? "paused" : "active")), a -> {
            info = a;
            ApiListScreen.version++;
            invalidateChrome();
            toast(on ? "已暂停，第三方网页再提交会被拒收" : "已恢复接收");
        });
    }

    private void export() {
        Files.export(this, "正在导出…", () -> DataApiClient.export(id), Files.safeName(name) + "-数据.xlsx");
    }

    /** 管理员把这个 API 连同数据转给另一位老师（同网页「设置 → 转给其他老师」） */
    private void transfer() {
        runBusy("正在读取老师名单…", () -> DataApiClient.list(null), r -> {
            List<cn.wfxxkj.teacher.core.ui.Option> opts = new ArrayList<>();
            int owner = Json.num(info, "owner_id");
            for (JSONObject t : Json.list(Json.arr(r, "teachers"))) {
                if (Json.num(t, "id") == owner) continue;
                opts.add(new cn.wfxxkj.teacher.core.ui.Option(Json.num(t, "id"), Json.str(t, "name")));
            }
            if (opts.isEmpty()) {
                toast("没有别的老师可以转");
                return;
            }
            Dialogs.choose(ctx(), "把「" + name + "」转给", opts, null, o -> Dialogs.confirm(ctx(), "转给其他老师",
                    "把「" + name + "」和它的全部数据转给 " + o.label + "？转过去以后归 " + o.label + " 管理。", "转过去", false,
                    () -> runBusy("正在转交…", () -> DataApiClient.transfer(id, ((Number) o.value).intValue()), a -> {
                        info = a;
                        ApiListScreen.version++;
                        toast("已转给 " + o.label);
                        reloadAll();
                    })));
        });
    }

    private void deleteApi() {
        Dialogs.confirm(ctx(), "删除 API", "删除「" + name + "」和它的 " + (info == null ? 0 : Json.num(info, "record_count"))
                + " 条数据？会放进回收站 7 天，可以在网页上还原。", "删除", true, () ->
                runBusy("正在删除…", () -> {
                    DataApiClient.delete(id);
                    return true;
                }, ok -> {
                    ApiListScreen.version++;
                    toast("已删除");
                    finish();
                }));
    }
}
