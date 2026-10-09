package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「打字学情」页签：打字成绩列表（对应网页 TypingAdmin.vue）。
 *
 * <ul>
 *   <li>上方：学生练习地址（复制 / 分享）、全站概况、进学情分析的入口；</li>
 *   <li>筛选：模块一排点选、姓名搜索，班级 / 难度 / 日期 / 排序收在「筛选」弹层里；</li>
 *   <li>列表滑到底自动加载下一页（服务端排序，翻页不乱）；</li>
 *   <li>长按进多选，批量删除；右上角菜单里「删除筛选出的全部」删的正是列表里看到的那些；</li>
 *   <li>导出 Excel 也按当前筛选。</li>
 * </ul>
 */
final class RecordListScreen extends Screen {
    private static final int PAGE_SIZE = 50;

    private final TypingApi.Filter filter = new TypingApi.Filter();
    private ItemList<JSONObject> list;
    private SelectBar bar;
    private SearchBox search;
    private ChipRow modules;
    private FlowBox pills;
    private TextView countText;
    private TextView filterBtn;
    private TextView urlText;
    private GridBox kpis;
    private TextView moduleText;
    private View kpiBox;
    private TextView deleteAllBtn;

    private int page = 1;
    private int total;
    private int loadSeq;
    private List<String> classes = new ArrayList<>();
    private String studentUrl = "";

    @Override
    public String title() {
        return "打字学情";
    }

    @Override
    public String subtitle() {
        if (list != null && list.isSelecting()) return "已选 " + list.selection().size() + " 条";
        return null;
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new RecordCard(ctx);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((RecordCard) v).bind(item);
            }
        });
        list.setCell(360, 3);
        list.addHeader(buildHeader(c));
        list.setEmpty("没有符合条件的成绩", "学生在练习页完成练习后，成绩会自动出现在这里");
        list.setOnRefresh(this::refresh);
        list.setOnLoadMore(this::loadMore);
        list.setOnItemClick((item, pos) -> openRecord(item));
        list.enableSelection(it -> it.optLong("id"), n -> {
            bar.show(n, "条");
            invalidateChrome();
        });

        bar = new SelectBar(c);
        bar.add("全选已加载", V.BTN_TONAL, v -> list.selectAll());
        bar.add("取消", V.BTN_OUTLINE, v -> list.stopSelection());
        SelectBar.needSelection(bar.add("删除勾选", V.BTN_DANGER_TONAL, v -> removePicked()));
        return bar.wrap(list);
    }

    // ---------------------------------------------------------------- 头部

    private View buildHeader(Context c) {
        LinearLayout h = V.vbox(c);
        V.pad(h, 0, 4, 0, 4);
        Palette p = Palette.of(c);

        // 学生练习地址
        LinearLayout link = V.card(c);
        V.pad(link, 14, 12, 6, 12);
        LinearLayout top = V.hbox(c);
        top.addView(V.iconTile(c, R.drawable.ic_keyboard, Tone.PRIMARY));
        LinearLayout texts = V.vbox(c);
        V.pad(texts, 12, 0, 4, 0);
        texts.addView(V.text(c, "学生练习地址", V.CAPTION));
        urlText = V.oneLine(V.text(c, "正在获取…", V.BODY));
        V.bold(urlText);
        urlText.setTextColor(p.primary);
        texts.addView(urlText);
        top.addView(texts, V.fill());
        top.addView(V.iconButton(c, R.drawable.ic_content_copy, "复制链接", v -> copyUrl()));
        top.addView(V.iconButton(c, R.drawable.ic_share, "发给学生", v -> {
            if (!studentUrl.isEmpty()) Sys.share(ctx(), "发送练习地址", "打字练习地址：" + studentUrl);
        }));
        link.addView(top);
        TextView tip = V.text(c, "学生打开即可练习（班级、姓名要和学生名单一致），完成后成绩自动进入这里。", V.CAPTION);
        V.pad(tip, 0, 0, 8, 0);
        V.addTop(link, tip, 8);
        h.addView(link, V.matchWrap());

        // 概况
        LinearLayout kb = V.vbox(c);
        kb.addView(V.section(c, "概况", "学情分析", v -> openAnalysis()));
        kpis = new GridBox(c, 100, 6, 8);
        kb.addView(kpis, V.matchWrap());
        moduleText = V.text(c, "", V.CAPTION);
        V.pad(moduleText, 4, 8, 0, 0);
        kb.addView(moduleText);
        kpiBox = kb;
        kb.setVisibility(View.GONE);
        V.addTop(h, kb, 8);

        // 搜索 + 筛选
        LinearLayout sr = V.hbox(c);
        search = new SearchBox(c, "搜姓名");
        search.setOnSearch(k -> {
            filter.keyword = k;
            reload();
        });
        sr.addView(search, V.fill());
        filterBtn = V.button(c, R.drawable.ic_filter_list, "筛选", V.BTN_OUTLINE, v -> openFilter());
        filterBtn.setMinHeight(Ui.dp(c, 44));
        V.pad(filterBtn, 12, 0, 14, 0);
        V.addStart(sr, filterBtn, 8);
        V.addTop(h, sr, 16);

        modules = new ChipRow(c);
        List<Option> mo = new ArrayList<>();
        mo.add(new Option("", "全部模块"));
        for (String m : TypingApi.MODULES) mo.add(new Option(m, m));
        modules.setOptions(mo, "");
        modules.setOnPicked(o -> {
            filter.module = String.valueOf(o.value);
            reload();
        });
        V.addTop(h, modules, 8);

        pills = new FlowBox(c, 8, 8);
        V.addTop(h, pills, 6);

        LinearLayout cr = V.hbox(c);
        countText = V.text(c, "", V.BODY2);
        cr.addView(countText, V.fill());
        deleteAllBtn = V.button(c, "", V.BTN_TEXT, v -> removeFiltered());
        deleteAllBtn.setTextColor(p.danger);
        deleteAllBtn.setTextSize(13);
        cr.addView(deleteAllBtn);
        V.pad(cr, 4, 4, 0, 0);
        V.addTop(h, cr, 2);
        return h;
    }

    private void renderPills() {
        pills.removeAllViews();
        Context c = ctx();
        if (!filter.studentClass.isEmpty()) {
            pills.addView(TypingUi.pill(c, filter.studentClass, v -> {
                filter.studentClass = "";
                reload();
            }));
        }
        if (!filter.difficulty.isEmpty()) {
            pills.addView(TypingUi.pill(c, filter.difficulty, v -> {
                filter.difficulty = "";
                reload();
            }));
        }
        if (!filter.dateFrom.isEmpty() || !filter.dateTo.isEmpty()) {
            String d = (filter.dateFrom.isEmpty() ? "…" : filter.dateFrom) + " 至 "
                    + (filter.dateTo.isEmpty() ? "…" : filter.dateTo);
            pills.addView(TypingUi.pill(c, d, v -> {
                filter.dateFrom = "";
                filter.dateTo = "";
                reload();
            }));
        }
        if (!"time".equals(filter.sort) || !"desc".equals(filter.order)) {
            pills.addView(TypingUi.pill(c, "按" + RecordFilterSheet.sortLabel(filter), v -> {
                filter.sort = "time";
                filter.order = "desc";
                reload();
            }));
        }
        pills.setVisibility(pills.getChildCount() > 0 ? View.VISIBLE : View.GONE);
        int n = filter.sheetCount();
        filterBtn.setText(n > 0 ? "筛选 " + n : "筛选");
    }

    private void renderCount() {
        boolean f = filter.filtered();
        countText.setText("共 " + total + " 条" + (f ? "（已筛选）" : ""));
        deleteAllBtn.setText(f ? "删除筛选出的全部" : "清空全部");
        deleteAllBtn.setVisibility(total > 0 ? View.VISIBLE : View.GONE);
    }

    private void renderStats(JSONObject s) {
        kpis.removeAllViews();
        int n = Json.num(s, "total");
        kpiBox.setVisibility(n > 0 ? View.VISIBLE : View.GONE);
        if (n <= 0) return;
        Context c = ctx();
        kpis.addView(TypingUi.mini(c, String.valueOf(n), "练习人次", Tone.PRIMARY));
        kpis.addView(TypingUi.mini(c, String.valueOf(Json.num(s, "students")), "参与人数", Tone.SUCCESS));
        kpis.addView(TypingUi.mini(c, Json.num(s, "avg_accuracy") + "%", "平均正确率", Tone.WARNING));
        kpis.addView(TypingUi.mini(c, TypingUi.mmss(Json.dblOrNull(s, "avg_duration")), "平均用时", Tone.VIOLET));
        JSONObject bm = Json.obj(s, "by_module");
        Iterator<String> it = bm.keys();
        List<String> keys = new ArrayList<>();
        while (it.hasNext()) keys.add(it.next());
        // 按 中文 / 英文 / 键盘 的固定顺序
        Collections.sort(keys, (a, b) -> idx(a) - idx(b));
        List<String> parts = new ArrayList<>();
        for (String k : keys) parts.add(k + " " + bm.optInt(k) + " 次");
        moduleText.setText("各模块练习：" + android.text.TextUtils.join(" · ", parts));
    }

    private static int idx(String m) {
        int i = Arrays.asList(TypingApi.MODULES).indexOf(m);
        return i < 0 ? 99 : i;
    }

    // ---------------------------------------------------------------- 顶栏

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (list != null && list.isSelecting()) {
            a.add(Action.icon(R.drawable.ic_select_all, "全选已加载", () -> list.selectAll()));
            a.add(Action.icon(R.drawable.ic_delete, "删除勾选", this::removePicked));
            a.add(Action.menu("退出多选", () -> list.stopSelection()));
            return a;
        }
        a.add(Action.icon(R.drawable.ic_analytics, "学情分析", this::openAnalysis));
        a.add(Action.icon(R.drawable.ic_download, "导出 Excel", this::exportXlsx));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::refresh));
        a.add(Action.menu(R.drawable.ic_done_all, "多选删除", () -> list.startSelection()));
        a.add(Action.menu(R.drawable.ic_delete, filter.filtered() ? "删除筛选出的全部" : "清空全部成绩",
                this::removeFiltered).danger().enabled(total > 0));
        return a;
    }

    @Override
    public boolean onBack() {
        if (list != null && list.isSelecting()) {
            list.stopSelection();
            return true;
        }
        return false;
    }

    // ---------------------------------------------------------------- 取数

    @Override
    protected void onFirstShow() {
        renderPills();
        list.loading();
        refresh();
        run(TypingApi::studentUrl, u -> {
            studentUrl = u;
            urlText.setText(u);
        }, e -> {
            urlText.setText("取不到地址");
            return true;
        });
    }

    /** 列表 + 概况 + 班级一起重取 */
    private void refresh() {
        reload();
        run(() -> new Object[]{TypingApi.stats(), TypingApi.classes()}, r -> {
            renderStats((JSONObject) r[0]);
            @SuppressWarnings("unchecked") List<String> cl = (List<String>) r[1];
            classes = cl;
        });
    }

    /** 条件变了：从第一页重取 */
    private void reload() {
        renderPills();
        page = 1;
        final int seq = ++loadSeq;
        final TypingApi.Filter f = filter.copy();
        list.loading();
        run(() -> TypingApi.search(f, 1, PAGE_SIZE), r -> {
            if (seq != loadSeq) return;
            total = Json.num(r, "total");
            List<JSONObject> items = Json.list(Json.arr(r, "items"));
            list.setItems(items, items.size() < total);
            renderCount();
            invalidateChrome();
        }, e -> {
            if (seq != loadSeq) return true;
            list.error(e.getMessage(), this::reload);
            return false;
        });
    }

    private void loadMore() {
        final int seq = loadSeq;
        final int next = page + 1;
        final TypingApi.Filter f = filter.copy();
        run(() -> TypingApi.search(f, next, PAGE_SIZE), r -> {
            if (seq != loadSeq) return;
            page = next;
            total = Json.num(r, "total");
            List<JSONObject> items = Json.list(Json.arr(r, "items"));
            list.appendItems(items, !items.isEmpty() && list.size() + items.size() < total);
            renderCount();
        }, e -> {
            list.appendItems(null, false);
            return false;
        });
    }

    // ---------------------------------------------------------------- 操作

    private void openFilter() {
        RecordFilterSheet.show(ctx(), filter, classes, f -> {
            filter.studentClass = f.studentClass;
            filter.difficulty = f.difficulty;
            filter.dateFrom = f.dateFrom;
            filter.dateTo = f.dateTo;
            filter.sort = f.sort;
            filter.order = f.order;
            reload();
        });
    }

    private void copyUrl() {
        if (studentUrl.isEmpty()) return;
        Sys.copy(ctx(), "打字练习地址", studentUrl);
        toast("已复制：" + studentUrl);
    }

    /** 学情分析：带上当前的模块和班级筛选（同网页） */
    private void openAnalysis() {
        List<String> cls = new ArrayList<>();
        if (!filter.studentClass.isEmpty()) cls.add(filter.studentClass);
        push(new AnalysisScreen(filter.module.isEmpty() ? "中文" : filter.module, cls, null));
    }

    private void openRecord(JSONObject r) {
        RecordSheet.show(this, r, () -> afterDelete(1));
    }

    private void exportXlsx() {
        final TypingApi.Filter f = filter.copy();
        Files.export(this, "正在导出…", () -> TypingApi.export(f), "打字训练成绩.xlsx");
    }

    private void removePicked() {
        final List<Object> ids = list.selectedKeys();
        if (ids.isEmpty()) {
            toast("先点卡片勾选要删除的成绩");
            return;
        }
        Dialogs.confirm(ctx(), "批量删除", "删除勾选的 " + ids.size() + " 条成绩？删除后无法恢复。",
                "删除 " + ids.size() + " 条", true,
                () -> runBusy("正在删除…", () -> TypingApi.deleteMany(ids), n -> {
                    list.stopSelection();
                    afterDelete(n);
                }));
    }

    private void removeFiltered() {
        if (total <= 0) return;
        final TypingApi.Filter f = filter.copy();
        String scope = f.filtered() ? "筛选出的全部 " + total + " 条" : "全部 " + total + " 条";
        Dialogs.confirm(ctx(), "删除确认", "将删除" + scope + "打字成绩（不只是已加载的这些），且无法恢复。确定吗？",
                "确认删除", true,
                () -> runBusy("正在删除…", () -> TypingApi.deleteFiltered(f), this::afterDelete));
    }

    private void afterDelete(int n) {
        toast("已删除 " + n + " 条");
        refresh();
    }

    // ---------------------------------------------------------------- 卡片

    /** 一条成绩：姓名班级 + 正确率大字，下面模块难度、速度、用时、星级、时间 */
    static final class RecordCard extends LinearLayout {
        private final TextView name, cls, acc, speed, dur, stars, time;
        private final LinearLayout tags;

        RecordCard(Context c) {
            super(c);
            setOrientation(VERTICAL);
            Palette p = Palette.of(c);
            setBackground(V.stroke(c, p.surface, p.border, 16));
            V.pad(this, 16, 14, 16, 14);

            LinearLayout top = V.hbox(c);
            LinearLayout who = V.vbox(c);
            name = V.oneLine(V.text(c, "", V.H3));
            who.addView(name);
            cls = V.oneLine(V.text(c, "", V.CAPTION));
            who.addView(cls);
            top.addView(who, V.fill());
            LinearLayout accBox = V.vbox(c);
            accBox.setGravity(Gravity.END);
            acc = V.text(c, "", V.H2);
            accBox.addView(acc);
            accBox.addView(V.text(c, "正确率", V.CAPTION));
            V.addStart(top, accBox, 8);
            addView(top);

            LinearLayout mid = V.hbox(c);
            tags = V.hbox(c);
            mid.addView(tags);
            stars = V.text(c, "", V.BODY);
            stars.setTextColor(p.warning);
            V.addStart(mid, stars, 10);
            mid.addView(V.spring(c));
            time = V.text(c, "", V.CAPTION);
            mid.addView(time);
            V.addTop(this, mid, 10);

            LinearLayout bottom = V.hbox(c);
            speed = V.text(c, "", V.BODY2);
            bottom.addView(speed, V.weight(1));
            dur = V.text(c, "", V.BODY2);
            bottom.addView(dur, V.weight(1));
            V.addTop(this, bottom, 8);
        }

        void bind(JSONObject r) {
            Context c = getContext();
            name.setText(Json.str(r, "student_name"));
            cls.setText(Json.str(r, "student_class"));
            int a = Json.num(r, "accuracy");
            acc.setText(a + "%");
            acc.setTextColor(TypingUi.accuracyColor(c, a));
            String module = Json.str(r, "module");
            tags.removeAllViews();
            tags.addView(V.tag(c, module, TypingUi.moduleTone(module)));
            String diff = Json.str(r, "difficulty");
            if (!diff.isEmpty()) V.addStart(tags, V.tag(c, diff, TypingUi.difficultyTone(diff)), 6);
            stars.setText(TypingUi.stars(Json.num(r, "stars")));
            time.setText(cn.wfxxkj.teacher.core.util.Fmt.shortDateTime(Json.str(r, "created_at")));
            speed.setText("键盘".equals(module) ? "速度  —"
                    : "速度  " + Json.num(r, "speed") + ("英文".equals(module) ? " 字母/分" : " 字/分"));
            dur.setText("用时  " + TypingUi.mmss(Json.dblOrNull(r, "duration")));
        }
    }
}
