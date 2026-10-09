package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「练习文本」页签：打字练习文本库（对应网页 TypingTexts.vue）。
 *
 * <ul>
 *   <li>上方两张小卡：中文 / 英文各难度启用了多少段，少于 10 段标黄提醒；</li>
 *   <li>语言、难度点选，内容可搜；</li>
 *   <li>卡片上直接开关启用；点卡片编辑；长按多选后批量启用 / 停用 / 删除；</li>
 *   <li>右下角「添加一段」，右上角「上传 txt 批量导入」。</li>
 * </ul>
 */
final class TextListScreen extends Screen {
    static final List<Option> MODES = Option.pairs("chinese", "中文", "english", "英文");
    /** 每档少于这么多段就提醒（同网页） */
    private static final int LOW = 10;

    private String mode = "chinese";
    private String difficulty = "";
    private String keyword = "";
    private String[] difficulties = TypingApi.DIFFICULTIES;
    private int seq;

    private ItemList<JSONObject> list;
    private SelectBar bar;
    private GridBox summary;
    private ChipRow modeRow;
    private ChipRow diffRow;
    private TextView countText;

    @Override
    public String title() {
        return "练习文本";
    }

    @Override
    public String subtitle() {
        if (list != null && list.isSelecting()) return "已选 " + list.selection().size() + " 段";
        return null;
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new TextCard(ctx);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((TextCard) v).bind(item);
            }
        });
        list.setCell(360, 3);
        list.addHeader(buildHeader(c));
        list.setEmpty("这个筛选条件下还没有文本", "点右下角「添加一段」，或上传 txt 批量导入", "添加一段", this::openCreate);
        list.setOnRefresh(this::load);
        list.setOnItemClick((it, pos) -> TextEditSheet.show(this, it, mode, difficulty, difficulties, this::load));
        list.enableSelection(it -> it.optLong("id"), n -> {
            bar.show(n, "段");
            invalidateChrome();
        });

        bar = new SelectBar(c);
        bar.add("全选", V.BTN_TONAL, v -> list.selectAll());
        SelectBar.needSelection(bar.add("启用", V.BTN_TONAL, v -> bulk("enable")));
        SelectBar.needSelection(bar.add("停用", V.BTN_OUTLINE, v -> bulk("disable")));
        SelectBar.needSelection(bar.add("删除", V.BTN_DANGER_TONAL, v -> bulk("delete")));
        return bar.wrap(list);
    }

    private View buildHeader(Context c) {
        LinearLayout h = V.vbox(c);
        V.pad(h, 0, 4, 0, 4);
        h.addView(V.notice(c, "学生每次练习会从对应难度里随机抽几段拼成长文，所以每档的段数越多，重复感越低。建议每档至少 "
                + LOW + " 段。", Tone.INFO));
        summary = new GridBox(c, 260, 2, 10);
        V.addTop(h, summary, 10);

        modeRow = new ChipRow(c);
        modeRow.setOptions(MODES, mode);
        modeRow.setOnPicked(o -> {
            mode = String.valueOf(o.value);
            load();
        });
        V.addTop(h, modeRow, 12);

        diffRow = new ChipRow(c);
        renderDiffRow();
        V.addTop(h, diffRow, 2);

        SearchBox sb = new SearchBox(c, "搜内容");
        sb.setOnSearch(k -> {
            keyword = k;
            load();
        });
        V.addTop(h, sb, 6);

        countText = V.text(c, "", V.CAPTION);
        V.pad(countText, 4, 10, 0, 2);
        h.addView(countText);
        return h;
    }

    private void renderDiffRow() {
        List<Option> o = new ArrayList<>();
        o.add(new Option("", "全部难度"));
        for (String d : difficulties) o.add(new Option(d, d));
        diffRow.setOptions(o, difficulty);
        diffRow.setOnPicked(op -> {
            difficulty = String.valueOf(op.value);
            load();
        });
    }

    private void renderSummary(JSONObject stats) {
        Context c = ctx();
        summary.removeAllViews();
        Palette p = Palette.of(c);
        for (Option m : MODES) {
            JSONObject counts = Json.obj(stats, String.valueOf(m.value));
            LinearLayout card = V.card(c);
            V.pad(card, 14, 12, 14, 12);
            LinearLayout head = V.hbox(c);
            head.addView(V.text(c, m.label, V.H3), V.fill());
            int total = 0;
            for (String d : difficulties) total += counts.optInt(d);
            head.addView(V.text(c, "启用 " + total + " 段", V.CAPTION));
            card.addView(head);
            LinearLayout row = V.hbox(c);
            for (int i = 0; i < difficulties.length; i++) {
                String d = difficulties[i];
                int n = counts.optInt(d);
                boolean low = n < LOW;
                LinearLayout cell = V.vbox(c);
                cell.setGravity(Gravity.CENTER_HORIZONTAL);
                int[] t = p.tone(low ? Tone.WARNING : Tone.NEUTRAL);
                cell.setBackground(V.round(c, t[1], 10));
                V.pad(cell, 4, 6, 4, 6);
                TextView num = V.text(c, String.valueOf(n), V.H2);
                num.setTextColor(low ? t[0] : p.text);
                cell.addView(num);
                cell.addView(V.text(c, d + (low ? " · 偏少" : ""), V.CAPTION));
                LinearLayout.LayoutParams lp = V.weight(1);
                if (i > 0) lp.setMarginStart(Ui.dp(c, 8));
                row.addView(cell, lp);
            }
            V.addTop(card, row, 10);
            summary.addView(card);
        }
    }

    // ---------------------------------------------------------------- 顶栏

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (list != null && list.isSelecting()) {
            a.add(Action.icon(R.drawable.ic_select_all, "全选当前", () -> list.selectAll()));
            a.add(Action.menu("批量启用", () -> bulk("enable")));
            a.add(Action.menu("批量停用", () -> bulk("disable")));
            a.add(Action.menu(R.drawable.ic_delete, "批量删除", () -> bulk("delete")).danger());
            a.add(Action.menu("退出多选", () -> list.stopSelection()));
            return a;
        }
        a.add(Action.icon(R.drawable.ic_upload_file, "上传 txt 批量导入", this::openImport));
        a.add(Action.menu(R.drawable.ic_done_all, "多选（批量启用 / 停用 / 删除）", () -> list.startSelection()));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::load));
        return a;
    }

    @Override
    public Action fab() {
        if (list != null && list.isSelecting()) return null;
        return Action.icon(R.drawable.ic_add, "添加一段", this::openCreate);
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
        list.loading();
        run(TypingApi::difficulties, d -> {
            difficulties = d;
            renderDiffRow();
            load();
        });
    }

    private void load() {
        final int my = ++seq;
        final String m = mode, d = difficulty, k = keyword;
        list.loading();
        run(() -> new Object[]{TypingApi.texts(m, d, k), TypingApi.textStats()}, r -> {
            if (my != seq) return;
            @SuppressWarnings("unchecked") List<JSONObject> items = (List<JSONObject>) r[0];
            // 换了筛选，勾选清掉，免得误删看不见的那些（同网页）
            if (list.isSelecting()) list.stopSelection();
            list.setItems(items);
            renderSummary((JSONObject) r[1]);
            countText.setText("共 " + items.size() + " 段" + (items.size() >= 500 ? "（最多显示 500 段，可用难度或搜索缩小范围）" : "")
                    + " · 长按卡片可多选");
        }, e -> {
            if (my != seq) return true;
            list.error(e.getMessage(), this::load);
            return false;
        });
    }

    // ---------------------------------------------------------------- 操作

    private void openCreate() {
        TextEditSheet.show(this, null, mode, difficulty, difficulties, this::load);
    }

    private void openImport() {
        TextImportSheet.show(this, mode, difficulty, difficulties, this::load);
    }

    private void toggleActive(final JSONObject row, final boolean on, final Switch sw) {
        run(() -> TypingApi.updateText(row.optLong("id"), Json.of("is_active", on)), r -> {
            Json.put(row, "is_active", on);
            toast(on ? "已启用" : "已停用");
            load();
        }, e -> {
            sw.setChecked(!on);
            return false;
        });
    }

    private void remove(final JSONObject row) {
        Dialogs.confirm(ctx(), "提示", "删除这段练习文本？", "删除", true,
                () -> runBusy("正在删除…", () -> {
                    TypingApi.deleteText(row.optLong("id"));
                    return true;
                }, ok -> {
                    toast("已删除");
                    load();
                }));
    }

    private static final String[][] BULK = {{"delete", "删除"}, {"enable", "启用"}, {"disable", "停用"}};

    private void bulk(final String action) {
        final List<Object> ids = list.selectedKeys();
        if (ids.isEmpty()) {
            toast("先勾选要处理的文本");
            return;
        }
        String label = "";
        for (String[] b : BULK) if (b[0].equals(action)) label = b[1];
        final String l = label;
        Runnable go = () -> runBusy("正在" + l + "…", () -> TypingApi.bulkTexts(ids, action), n -> {
            list.stopSelection();
            toast("已" + l + " " + n + " 段");
            load();
        });
        if ("delete".equals(action)) {
            Dialogs.confirm(ctx(), "批量删除", "确定删除选中的 " + ids.size() + " 段文本？删掉就找不回来了。",
                    "删除 " + ids.size() + " 段", true, go);
        } else {
            go.run();
        }
    }

    // ---------------------------------------------------------------- 卡片

    /** 一段文本：难度、来源、字数、启用开关；内容最多 4 行；右下角删除 */
    final class TextCard extends LinearLayout {
        private final LinearLayout tags;
        private final TextView content, meta;
        private final Switch sw;
        private JSONObject row;
        private boolean binding;

        TextCard(Context c) {
            super(c);
            setOrientation(VERTICAL);
            Palette p = Palette.of(c);
            setBackground(V.stroke(c, p.surface, p.border, 16));
            V.pad(this, 16, 12, 8, 8);
            LinearLayout top = V.hbox(c);
            tags = V.hbox(c);
            top.addView(tags, V.fill());
            sw = new Switch(c);
            sw.setOnCheckedChangeListener((b, on) -> {
                if (!binding && row != null) toggleActive(row, on, sw);
            });
            top.addView(sw);
            addView(top);
            content = V.lines(V.text(c, "", V.BODY), 4);
            V.pad(content, 0, 6, 8, 0);
            addView(content);
            LinearLayout bottom = V.hbox(c);
            meta = V.text(c, "", V.CAPTION);
            bottom.addView(meta, V.fill());
            View del = V.iconButton(c, R.drawable.ic_delete, "删除", v -> {
                if (row != null) remove(row);
            });
            ((android.widget.ImageView) del).setImageTintList(android.content.res.ColorStateList.valueOf(p.text3));
            del.setLayoutParams(new LayoutParams(Ui.dp(c, 40), Ui.dp(c, 40)));
            bottom.addView(del);
            addView(bottom);
        }

        void bind(JSONObject r) {
            row = r;
            Context c = getContext();
            boolean active = Json.bool(r, "is_active");
            tags.removeAllViews();
            String d = Json.str(r, "difficulty");
            tags.addView(V.tag(c, d, TypingUi.difficultyTone(d)));
            if (!active) V.addStart(tags, V.tag(c, "已停用", Tone.NEUTRAL), 6);
            String src = Json.str(r, "source");
            binding = true;
            sw.setChecked(active);
            binding = false;
            String text = Json.str(r, "content");
            content.setText(text);
            content.setAlpha(active ? 1f : 0.55f);
            meta.setText(text.length() + " 字" + (src.isEmpty() ? "" : " · " + src)
                    + " · " + cn.wfxxkj.teacher.core.util.Fmt.date(Json.str(r, "created_at")));
        }
    }
}
