package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 题库管理：搜索 + 题型标签 + 筛选弹层，卡片列表滑到底自动翻页。
 * 点卡片看详情，右下角「+」新增，长按进入多选做批量操作（设必出、改难度、改知识范围、删除）。
 * 顶栏：筛选、题库概况、「⋮」里三种导出。
 */
final class QuestionListScreen extends Screen {
    private static final int PAGE_SIZE = 20;

    private ItemList<JSONObject> list;
    private SearchBox search;
    private ChipRow typeRow;
    private TextView summary;
    private final BankApi.Filter filter = new BankApi.Filter();
    private BankApi.Dicts dicts;
    private JSONObject stats;
    private int page = 1;
    private int total = -1;
    private int selected = -1;
    /** 每次重新查询加一，丢掉过时的翻页结果 */
    private int generation;

    @Override
    public String title() {
        return "题库管理";
    }

    @Override
    public String subtitle() {
        if (selected >= 0) return "已选 " + selected + " 题";
        return total < 0 ? null : (filter.isEmpty() ? "共 " + total + " 题" : "筛出 " + total + " 题");
    }

    @Override
    protected View onCreateView(Context ctx) {
        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return QuestionCard.create(c, QuestionListScreen.this::togglePin);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((QuestionCard) v).bind(item);
            }
        });
        list.setCell(360, 3);

        LinearLayout head = V.vbox(ctx);
        search = new SearchBox(ctx, "搜题干关键字");
        search.setOnSearch(k -> {
            filter.keyword = k;
            reload();
        });
        head.addView(search.padded());
        typeRow = new ChipRow(ctx);
        typeRow.setOptions(Arrays.asList(new Option("", "全部题型")), "");
        typeRow.setOnPicked(o -> {
            filter.type = String.valueOf(o.value);
            reload();
        });
        head.addView(typeRow, V.matchWrap());
        summary = V.text(ctx, "", V.CAPTION);
        V.pad(summary, 4, 6, 4, 6);
        V.clickable(summary, 8, v -> showStats());
        head.addView(summary, V.matchWrap());
        list.addHeader(head);

        list.setEmpty("没有符合条件的题目", "换个关键字或筛选条件试试");
        list.setOnRefresh(this::reload);
        list.setOnLoadMore(this::loadMore);
        list.setOnItemClick((q, pos) -> openDetail(q));
        list.enableSelection(q -> q.optLong("id"), n -> {
            selected = n;
            invalidateChrome();
        });
        return list;
    }

    @Override
    protected void onFirstShow() {
        list.loading();
        run(BankApi::dicts, d -> {
            dicts = d;
            renderTypes();
        });
        reload();
    }

    // ---------- 数据 ----------

    void reload() {
        final int gen = ++generation;
        page = 1;
        list.loading();
        final BankApi.Filter f = filter.copy();
        run(() -> new Object[]{BankApi.questions(f, 1, PAGE_SIZE), BankApi.stats()}, r -> {
            if (gen != generation) return;
            JSONObject res = (JSONObject) r[0];
            stats = (JSONObject) r[1];
            total = res.optInt("total");
            List<JSONObject> items = Json.list(Json.arr(res, "items"));
            list.setItems(items, items.size() < total);
            renderTypes();
            renderSummary();
            invalidateChrome();
        }, e -> {
            if (gen != generation) return true;
            list.error(e.getMessage(), this::reload);
            return false;
        });
    }

    private void loadMore() {
        final int gen = generation;
        final int next = page + 1;
        final BankApi.Filter f = filter.copy();
        run(() -> BankApi.questions(f, next, PAGE_SIZE), res -> {
            if (gen != generation) return;
            page = next;
            total = res.optInt("total");
            List<JSONObject> items = Json.list(Json.arr(res, "items"));
            list.appendItems(items, !items.isEmpty() && list.size() + items.size() < total);
        }, e -> {
            list.appendItems(null, true);
            return false;
        });
    }

    private void renderTypes() {
        List<Option> opts = new ArrayList<>();
        opts.add(new Option("", stats == null ? "全部题型" : "全部 " + stats.optInt("total")));
        JSONObject byType = stats == null ? new JSONObject() : Json.obj(stats, "by_type");
        List<String> types = dicts != null ? dicts.types : new ArrayList<>();
        for (String t : types) {
            int n = byType.optInt(t, -1);
            opts.add(new Option(t, n < 0 ? t : t + " " + n));
        }
        typeRow.setOptions(opts, filter.type);
    }

    private void renderSummary() {
        if (stats == null) return;
        StringBuilder sb = new StringBuilder();
        sb.append("题库共 ").append(stats.optInt("total")).append(" 题 · 带图 ")
                .append(stats.optInt("with_image")).append(" · 必出 ").append(stats.optInt("pinned"));
        JSONObject lv = Json.obj(stats, "by_difficulty");
        sb.append("\n难度 ");
        for (int i = 1; i <= 5; i++) {
            sb.append(i).append("级 ").append(lv.optInt(String.valueOf(i)));
            if (i < 5) sb.append(" · ");
        }
        sb.append("　概况 ›");
        summary.setText(sb);
    }

    // ---------- 顶栏 ----------

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (selected >= 0) {
            a.add(Action.icon(R.drawable.ic_select_all, "全选", () -> list.selectAll()));
            a.add(Action.icon(R.drawable.ic_tune, "批量操作", this::batchMenu).enabled(selected > 0));
            a.add(Action.icon(R.drawable.ic_close, "退出多选", () -> list.stopSelection()));
            return a;
        }
        a.add(Action.icon(R.drawable.ic_filter_list, "筛选", this::openFilter).badge(filter.extraCount()));
        a.add(Action.icon(R.drawable.ic_analytics, "题库概况", this::showStats));
        a.add(Action.menu(R.drawable.ic_download, "导出完整题库", () -> export("all")));
        a.add(Action.menu(R.drawable.ic_download, "导出我补充的题（来源=自定义）", () -> export("custom")));
        a.add(Action.menu(R.drawable.ic_download, "按当前筛选条件导出", () -> export("filtered")));
        a.add(Action.menu(R.drawable.ic_select_all, "多选（批量操作）", () -> list.startSelection()));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::reload));
        return a;
    }

    @Override
    public Action fab() {
        if (selected >= 0) return null;
        return Action.icon(R.drawable.ic_add, "新增题目", this::openCreate);
    }

    @Override
    public boolean onBack() {
        if (list != null && list.isSelecting()) {
            list.stopSelection();
            return true;
        }
        return false;
    }

    private void openFilter() {
        List<String> scopes = dicts != null ? dicts.scopes : new ArrayList<>();
        List<String> sources = stats != null ? Json.strings(Json.arr(stats, "sources")) : new ArrayList<>();
        if (!sources.contains("自定义")) sources.add("自定义");
        QuestionFilterSheet.show(ctx(), filter, scopes, sources, f -> {
            filter.scope = f.scope;
            filter.source = f.source;
            filter.difficulty = f.difficulty;
            filter.onlyPinned = f.onlyPinned;
            invalidateChrome();
            reload();
        });
    }

    private void showStats() {
        if (stats == null) {
            run(BankApi::stats, s -> {
                stats = s;
                BankStatsSheet.show(ctx(), s);
            });
        } else {
            BankStatsSheet.show(ctx(), stats);
        }
    }

    /** 和网页导出下拉的三项一致 */
    private void export(String which) {
        final Params p;
        final String name;
        if ("custom".equals(which)) {
            p = Params.of("source", "自定义");
            name = "信息技术题库_我补充的题";
        } else if ("filtered".equals(which)) {
            p = filter.params();
            name = "信息技术题库_筛选结果";
        } else {
            p = Params.of();
            name = "信息技术题库_全部";
        }
        Files.export(this, "正在导出题库…", () -> BankApi.exportBank(p, name), name + ".xlsx");
    }

    // ---------- 单题 ----------

    private void openCreate() {
        push(new QuestionEditScreen(null), r -> {
            if (r != null) reload();
        });
    }

    private void openDetail(JSONObject q) {
        push(new QuestionDetailScreen(q), r -> {
            if (r == null) return;
            reload();
            if (r instanceof Long) {
                // 删除：后端是软删除，给个「撤销」
                final long id = (Long) r;
                snack("已删除", "撤销", () -> run(() -> {
                    BankApi.restore(id);
                    return true;
                }, ok -> {
                    toast("已恢复");
                    reload();
                }));
            }
        });
    }

    private void togglePin(final JSONObject q) {
        final boolean to = !Json.bool(q, "is_pinned");
        final long id = q.optLong("id");
        run(() -> BankApi.update(id, Json.of("is_pinned", to)), saved -> {
            Json.put(q, "is_pinned", to);
            list.refreshViews();
            if (stats != null) {
                Json.put(stats, "pinned", Math.max(0, stats.optInt("pinned") + (to ? 1 : -1)));
                renderSummary();
            }
            toast(to ? "已设为必出题" : "已取消必出");
        });
    }

    // ---------- 批量 ----------

    private interface Change {
        void apply(BankApi.Dicts d, long id) throws Exception;
    }

    private void batchMenu() {
        final List<JSONObject> sel = list.selection();
        if (sel.isEmpty()) return;
        List<Action> acts = new ArrayList<>();
        acts.add(Action.menu(R.drawable.ic_star, "设为必出", () ->
                batch(sel, "设为必出", (d, id) -> BankApi.update(id, Json.of("is_pinned", true)))));
        acts.add(Action.menu(R.drawable.ic_remove, "取消必出", () ->
                batch(sel, "取消必出", (d, id) -> BankApi.update(id, Json.of("is_pinned", false)))));
        acts.add(Action.menu(R.drawable.ic_bar_chart, "修改难度", () ->
                Dialogs.choose(ctx(), "把 " + sel.size() + " 题的难度改成", Bank.levelOptions(), null, o -> {
                    final int lv = ((Number) o.value).intValue();
                    batch(sel, "难度改为 " + lv + " 级", (d, id) -> BankApi.update(id, Json.of("difficulty", lv)));
                })));
        acts.add(Action.menu(R.drawable.ic_class, "修改知识范围", () -> {
            if (dicts == null) return;
            List<Option> opts = new ArrayList<>();
            for (String s : dicts.scopes) opts.add(new Option(s, s));
            Dialogs.choose(ctx(), "把 " + sel.size() + " 题的知识范围改成", opts, null, o -> {
                final String scope = String.valueOf(o.value);
                batch(sel, "知识范围改为「" + scope + "」", (d, id) -> BankApi.update(id, Json.of("scope", scope)));
            });
        }));
        acts.add(Action.menu(R.drawable.ic_delete, "删除", () -> {
            if (!Bank.canDelete(ctx())) return;
            Dialogs.confirm(ctx(), "删除 " + sel.size() + " 道题？",
                    "删除后可以在数据库里恢复。已经组好的试卷和考完的成绩不受影响。", "删除", true,
                    () -> batch(sel, "删除", (d, id) -> BankApi.delete(id)));
        }).danger());
        Dialogs.actions(ctx(), "已选 " + sel.size() + " 题", acts);
    }

    private void batch(final List<JSONObject> sel, final String what, final Change change) {
        runBusy("正在" + what + "…", () -> {
            int ok = 0;
            String firstErr = null;
            for (JSONObject q : sel) {
                try {
                    change.apply(dicts, q.optLong("id"));
                    ok++;
                } catch (Exception e) {
                    if (firstErr == null) firstErr = e.getMessage();
                }
            }
            return new Object[]{ok, firstErr};
        }, r -> {
            int ok = (Integer) r[0];
            String err = (String) r[1];
            list.stopSelection();
            reload();
            if (err == null) toast(what + "：" + ok + " 题完成");
            else Dialogs.alert(ctx(), what + "：成功 " + ok + " 题，失败 " + (sel.size() - ok) + " 题", err);
        });
    }
}
