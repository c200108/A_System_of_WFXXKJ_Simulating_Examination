package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 打字主题（网页「练习文本」上方那一排主题卡）：每段文本属于一个主题，学生练习时先在启用的主题里随机挑一个，
 * 再只在这个主题里抽几段拼成长文。可以新增、改名、启用停用、上下挪顺序、删除（文本不删，归回「信息生活」）。
 * 内置主题「信息生活」不能删；至少要留一个启用的主题（服务器会拦）。
 */
final class ThemeScreen extends Screen {
    private final String mode;
    private final String[] difficulties;
    private final Runnable onChanged;
    private ItemList<JSONObject> list;
    private List<JSONObject> rows = new ArrayList<>();

    ThemeScreen(String mode, String[] difficulties, Runnable onChanged) {
        this.mode = mode;
        this.difficulties = difficulties;
        this.onChanged = onChanged;
    }

    @Override
    public String title() {
        return "打字主题";
    }

    @Override
    public String subtitle() {
        return rows.isEmpty() ? null : "共 " + rows.size() + " 个 · " + ("english".equals(mode) ? "英文" : "中文") + "段数";
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new Card(ctx);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((Card) v).bind(item, position);
            }
        });
        list.setCell(320, 2);
        LinearLayout head = V.vbox(c);
        V.pad(head, 0, 4, 0, 10);
        head.addView(V.notice(c, "学生每次练习先在启用的主题里随机挑一个，再从这个主题对应难度里随机抽几段拼成长文，"
                + "不会把不同主题拼在一起。每个启用的主题每档建议至少 8 段。点主题卡可以改名、调顺序、删除。", Tone.INFO));
        list.addHeader(head);
        list.setOnRefresh(this::load);
        list.setOnItemClick((t, pos) -> menu(t, pos));
        return list;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    @Override
    public List<Action> actions() {
        return Collections.singletonList(Action.icon(R.drawable.ic_refresh, "刷新", this::load));
    }

    @Override
    public Action fab() {
        return Action.icon(R.drawable.ic_add, "新增主题", this::add);
    }

    private void load() {
        list.loading();
        run(TypingApi::themes, r -> {
            rows = r;
            list.setEmpty("还没有主题", null);
            list.setItems(r);
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return true;
        });
    }

    private void changed() {
        load();
        if (onChanged != null) onChanged.run();
    }

    private void add() {
        Dialogs.prompt(ctx(), "新增主题", "主题名称，比如「人工智能」「网络安全」", "", 1, "新增", v -> {
            final String name = v.trim();
            if (name.isEmpty() || name.length() > 32) {
                toast("名称不能为空，不超过 32 个字");
                return;
            }
            runBusy("正在新增…", () -> TypingApi.createTheme(name), t -> {
                toast("已新增主题，添加或导入文本时选它就行");
                changed();
            });
        });
    }

    private void menu(final JSONObject t, final int pos) {
        List<Action> a = new ArrayList<>();
        a.add(Action.menu(R.drawable.ic_edit, "改名", () -> rename(t)));
        if (pos > 0) a.add(Action.menu("往前挪", () -> swap(pos, pos - 1)));
        if (pos < rows.size() - 1) a.add(Action.menu("往后挪", () -> swap(pos, pos + 1)));
        if (!Json.bool(t, "is_builtin")) a.add(Action.menu(R.drawable.ic_delete, "删除主题", () -> remove(t)).danger());
        Dialogs.actions(ctx(), Json.str(t, "name"), a);
    }

    private void rename(final JSONObject t) {
        Dialogs.prompt(ctx(), "改名", "新的主题名称", Json.str(t, "name"), 1, "保存", v -> {
            final String name = v.trim();
            if (name.isEmpty() || name.length() > 32) {
                toast("名称不能为空，不超过 32 个字");
                return;
            }
            runBusy("正在保存…", () -> TypingApi.updateTheme(Json.num(t, "id"), Json.of("name", name)), r -> changed());
        });
    }

    /** 两个主题互换 sort_order（网页是拖动排序，手机上一格一格挪） */
    private void swap(int i, int j) {
        final JSONObject a = rows.get(i), b = rows.get(j);
        final int sa = Json.num(a, "sort_order"), sb = Json.num(b, "sort_order");
        // 两个序号一样（老数据）时拉开一点，免得换了等于没换
        final int na = sa == sb ? sb + (j > i ? 1 : -1) : sb;
        runBusy("正在调整顺序…", () -> {
            TypingApi.updateTheme(Json.num(a, "id"), Json.of("sort_order", na));
            TypingApi.updateTheme(Json.num(b, "id"), Json.of("sort_order", sa));
            return true;
        }, r -> changed());
    }

    private void toggle(final JSONObject t, final boolean on, final Switch sw) {
        run(() -> TypingApi.updateTheme(Json.num(t, "id"), Json.of("is_enabled", on)), r -> {
            toast(on ? "已启用" : "已停用，学生练习时不会再抽到它");
            changed();
        }, e -> {
            // 被拦下（至少留一个启用）时开关弹回原样
            sw.setChecked(!on);
            return false;
        });
    }

    private void remove(final JSONObject t) {
        Dialogs.confirm(ctx(), "删除主题", "删除主题「" + Json.str(t, "name") + "」？它下面的 " + Json.num(t, "total")
                        + " 段文本不会删，会归回「信息生活」。可以在回收站还原。", "删除主题", true,
                () -> runBusy("正在删除…", () -> TypingApi.deleteTheme(Json.num(t, "id")), r -> {
                    toast("已删除，" + Json.num(r, "moved") + " 段文本归回「信息生活」");
                    changed();
                }));
    }

    /** 一个主题：名称、内置 / 停用标签、启用开关、当前语言各难度几段 */
    private final class Card extends LinearLayout {
        private final LinearLayout tags;
        private final TextView counts;
        private final Switch sw;
        private JSONObject row;
        private boolean binding;

        Card(Context c) {
            super(c);
            setOrientation(VERTICAL);
            Palette p = Palette.of(c);
            setBackground(V.stroke(c, p.surface, p.border, 16));
            V.pad(this, 16, 10, 8, 12);
            LinearLayout top = V.hbox(c);
            tags = V.hbox(c);
            top.addView(tags, V.fill());
            sw = new Switch(c);
            sw.setOnCheckedChangeListener((b, on) -> {
                if (!binding && row != null) toggle(row, on, sw);
            });
            top.addView(sw);
            addView(top);
            counts = V.text(c, "", V.BODY2);
            V.addTop(this, counts, 4);
        }

        void bind(JSONObject t, int pos) {
            row = t;
            Context c = getContext();
            boolean on = Json.bool(t, "is_enabled");
            tags.removeAllViews();
            tags.addView(V.bold(V.oneLine(V.text(c, Json.str(t, "name"), V.H3))));
            if (Json.bool(t, "is_builtin")) V.addStart(tags, V.tag(c, "内置", Tone.INFO), 6);
            if (!on) V.addStart(tags, V.tag(c, "已停用", Tone.NEUTRAL), 6);
            binding = true;
            sw.setChecked(on);
            binding = false;
            JSONObject cnt = Json.obj(Json.obj(t, "counts"), mode);
            StringBuilder sb = new StringBuilder();
            for (String d : difficulties) {
                if (sb.length() > 0) sb.append(" · ");
                sb.append(d).append(' ').append(cnt == null ? 0 : cnt.optInt(d));
            }
            sb.append("　共启用 ").append(Json.num(t, "total")).append(" 段");
            counts.setText(sb);
            setAlpha(on ? 1f : 0.6f);
        }
    }
}
