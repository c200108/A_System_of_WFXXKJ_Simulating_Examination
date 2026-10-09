package cn.wfxxkj.teacher.paper;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 组卷历史：存档的试卷。点开看卷面；每张卡片的「⋮」可以导出、删除；
 * 长按进入多选，批量删除。顶部搜索按标题、卷号、学校过滤。
 */
final class HistoryScreen extends Screen {

    private ItemList<JSONObject> list;
    private SearchBox search;
    private final List<JSONObject> all = new ArrayList<>();
    private int selected = -1;

    @Override
    public String title() {
        return selected >= 0 ? "已选 " + selected + " 份" : "组卷历史";
    }

    @Override
    public String subtitle() {
        return selected >= 0 ? null : (all.isEmpty() ? null : "共 " + all.size() + " 份存档 · 长按可多选");
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (selected >= 0) {
            a.add(Action.icon(R.drawable.ic_select_all, "全选", () -> list.selectAll()));
            a.add(Action.icon(R.drawable.ic_delete, "删除", this::deleteSelected).enabled(selected > 0));
            a.add(Action.icon(R.drawable.ic_close, "退出多选", () -> list.stopSelection()));
        } else {
            a.add(Action.icon(R.drawable.ic_refresh, "刷新", this::load));
        }
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

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return new Card(c);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((Card) v).bind(item);
            }
        });
        list.setCell(360, 3);
        search = new SearchBox(c, "搜索标题、卷号、学校");
        search.setOnSearch(k -> filter());
        View sp = search.padded();
        list.addHeader(sp);
        list.setEmpty("还没有存档的试卷", "组卷时打开「把这套卷子存档」，生成的卷子就会出现在这里");
        list.setOnRefresh(this::load);
        list.setOnItemClick((p, pos) -> push(PaperScreen.open(p.optLong("id"), Json.str(p, "title"))));
        list.enableSelection(p -> p.optLong("id"), n -> {
            selected = n;
            invalidateChrome();
        });
        return list;
    }

    @Override
    protected void onShow() {
        load();
    }

    private void load() {
        list.loading();
        run(PaperApi::papers, rows -> {
            all.clear();
            all.addAll(rows);
            filter();
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return true;
        });
    }

    private void filter() {
        String k = search.keyword().trim().toLowerCase(Locale.ROOT);
        List<JSONObject> out = new ArrayList<>();
        for (JSONObject p : all) {
            String hay = (Json.str(p, "title") + " " + Json.str(p, "code") + " " + Json.str(p, "school")).toLowerCase(Locale.ROOT);
            if (k.isEmpty() || hay.contains(k)) out.add(p);
        }
        if (!k.isEmpty() && out.isEmpty()) list.setEmpty("没有找到「" + search.keyword() + "」", "换个关键词试试");
        else list.setEmpty("还没有存档的试卷", "组卷时打开「把这套卷子存档」，生成的卷子就会出现在这里");
        list.setItems(out);
    }

    // ---------- 单份操作 ----------

    private void menu(final JSONObject p) {
        List<Action> a = new ArrayList<>();
        a.add(Action.menu(R.drawable.ic_visibility, "打开", () -> push(PaperScreen.open(p.optLong("id"), Json.str(p, "title")))));
        a.add(Action.menu(R.drawable.ic_table_view, "导出本卷 Excel", () -> withPaper(p, full -> Exporter.xlsx(this, full))));
        a.add(Action.menu(R.drawable.ic_quiz, "导出学生答题网页", () -> withPaper(p, full -> Exporter.studentHtml(this, full))));
        a.add(Action.menu(R.drawable.ic_print, "打印 / 存 PDF", () -> withPaper(p, full ->
                PrintDoc.print(activity(), full, false, PaperScreen.numerals))));
        a.add(Action.menu(R.drawable.ic_delete, "删除", () -> deleteOne(p)).danger());
        Dialogs.actions(ctx(), Json.str(p, "title"), a);
    }

    private interface WithPaper {
        void got(JSONObject paper);
    }

    /** 列表里只有摘要，导出要整份卷子，先取一下 */
    private void withPaper(JSONObject row, WithPaper cb) {
        runBusy("正在读取试卷…", () -> PaperApi.paper(row.optLong("id")), cb::got);
    }

    private void deleteOne(final JSONObject p) {
        Dialogs.confirm(ctx(), "删除这份试卷？", "确定删除《" + Json.str(p, "title") + "》？删除后不能恢复。", "删除", true,
                () -> runBusy("正在删除…", () -> {
                    PaperApi.delete(p.optLong("id"));
                    return true;
                }, ok -> {
                    toast("已删除");
                    load();
                }));
    }

    private void deleteSelected() {
        final List<Object> ids = list.selectedKeys();
        if (ids.isEmpty()) return;
        Dialogs.confirm(ctx(), "删除 " + ids.size() + " 份试卷？", "删除后不能恢复。已经用这些试卷发布的考试不受影响。",
                "删除", true, () -> runBusy("正在删除…", () -> {
                    int n = 0;
                    for (Object id : ids) {
                        PaperApi.delete(((Number) id).longValue());
                        n++;
                    }
                    return n;
                }, n -> {
                    toast("已删除 " + n + " 份");
                    list.stopSelection();
                    load();
                }));
    }

    /** 一份试卷的卡片 */
    private final class Card extends LinearLayout {
        private final TextView title, sub, count, time;
        private JSONObject item;

        Card(Context c) {
            super(c);
            setOrientation(HORIZONTAL);
            Palette p = Palette.of(c);
            setBackground(V.stroke(c, p.surface, p.border, 16));
            V.pad(this, 14, 14, 4, 14);
            setGravity(android.view.Gravity.CENTER_VERTICAL);
            addView(V.iconTile(c, R.drawable.ic_description, Tone.PRIMARY));
            LinearLayout texts = V.vbox(c);
            title = V.lines(V.text(c, "", V.H3), 2);
            texts.addView(title);
            sub = V.oneLine(V.text(c, "", V.BODY2));
            V.addTop(texts, sub, 2);
            LinearLayout meta = V.hbox(c);
            count = V.tag(c, "", Tone.INFO);
            meta.addView(count);
            time = V.text(c, "", V.CAPTION);
            V.addStart(meta, time, 8);
            V.addTop(texts, meta, 6);
            LayoutParams lp = V.fill();
            lp.setMarginStart(Ui.dp(c, 12));
            addView(texts, lp);
            addView(V.iconButton(c, R.drawable.ic_more_vert, "更多", v -> {
                if (item != null && !list.isSelecting()) menu(item);
            }));
        }

        void bind(JSONObject p) {
            item = p;
            title.setText(Json.str(p, "title"));
            String school = Json.str(p, "school");
            sub.setText(Json.str(p, "code") + (school.isEmpty() ? "" : "  ·  " + school));
            count.setText(Json.num(p, "question_count") + " 题");
            time.setText(Fmt.dateTime(Json.str(p, "created_at")));
        }
    }
}
