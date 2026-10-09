package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 仿真操作题列表：按种类筛选，卡片显示检查点数、满分、被几道题引用。
 * 点卡片进详情（看环境、改名称、改检查点、试判、删除）；右下角「+」新建。
 */
final class SimListScreen extends Screen {
    private ItemList<JSONObject> list;
    private ChipRow kinds;
    private String kind = "";
    private int count = -1;

    @Override
    public String title() {
        return "仿真操作题";
    }

    @Override
    public String subtitle() {
        return count < 0 ? null : "共 " + count + " 个仿真任务";
    }

    @Override
    protected View onCreateView(Context ctx) {
        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return new SimCard(c);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((SimCard) v).bind(item);
            }
        });
        list.setCell(340, 3);
        LinearLayout head = V.vbox(ctx);
        kinds = new ChipRow(ctx);
        List<Option> opts = new ArrayList<>();
        opts.add(new Option("", "全部"));
        for (int i = 0; i < Bank.KINDS.length; i++) opts.add(new Option(Bank.KINDS[i], Bank.KIND_NAMES[i]));
        kinds.setOptions(opts, "");
        kinds.setOnPicked(o -> {
            kind = String.valueOf(o.value);
            load();
        });
        V.pad(kinds, 0, 8, 0, 4);
        head.addView(kinds, V.matchWrap());
        TextView intro = V.notice(ctx, "学生在网页里把操作真做一遍，交卷后按检查点自动判分，每小问一档分，做对几问得几问的分。"
                + "判出来的分会预填到成绩页，老师随时能改。建好之后到「题库管理」里把某道操作题挂上它。", Tone.INFO);
        V.addTop(head, intro, 6);
        head.addView(V.space(ctx, 10));
        list.addHeader(head);
        list.setEmpty("还没有仿真任务", "点右下角「+」新建", "新建", this::create);
        list.setOnRefresh(this::load);
        list.setOnItemClick((s, pos) -> open(s.optLong("id")));
        return list;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    void load() {
        list.loading();
        final String k = kind;
        run(() -> BankApi.sims(k), items -> {
            if (!k.equals(kind)) return;
            count = items.size();
            list.setItems(items);
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return false;
        });
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_help_outline, "出题说明", () -> SimCreate.explain(ctx())));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::load));
        return a;
    }

    @Override
    public Action fab() {
        return Action.icon(R.drawable.ic_add, "新建仿真任务", this::create);
    }

    private void create() {
        SimCreate.start(this, id -> {
            load();
            open(id);
        });
    }

    private void open(long id) {
        push(new SimDetailScreen(id), r -> load());
    }

    /** 列表卡片 */
    static final class SimCard extends LinearLayout {
        private final LinearLayout tags;
        private final TextView title;
        private final TextView meta;

        SimCard(Context c) {
            super(c);
            setOrientation(VERTICAL);
            Palette p = Palette.of(c);
            setBackground(V.stroke(c, p.surface, p.border, 16));
            V.pad(this, 16, 14, 16, 14);
            tags = V.hbox(c);
            addView(tags, V.matchWrap());
            title = V.lines(V.text(c, "", V.H3), 2);
            V.addTop(this, title, 8);
            meta = V.text(c, "", V.CAPTION);
            V.addTop(this, meta, 6);
        }

        void bind(JSONObject s) {
            Context c = getContext();
            String k = Json.str(s, "kind");
            tags.removeAllViews();
            tags.addView(V.tag(c, Bank.kindName(k), Bank.kindTone(k)));
            int checks = Json.arr(s, "checks").length();
            int used = s.optInt("question_count");
            if (!"ai".equals(k) && checks == 0) V.addStart(tags, V.tag(c, "未完成：没有检查点", Tone.DANGER), 6);
            if (used > 0) V.addStart(tags, V.tag(c, "已被引用", Tone.SUCCESS), 6);
            String t = Json.str(s, "title");
            title.setText(t.isEmpty() ? "（未命名）" : t);
            StringBuilder m = new StringBuilder();
            if ("ai".equals(k)) m.append("按题干自动判分");
            else m.append(checks).append(" 条检查点 · 满分 ").append(Bank.fullScore(s)).append(" 分");
            m.append(" · ");
            m.append(used > 0 ? "被 " + used + " 道题引用" : "还没有题目挂它");
            meta.setText(m);
            meta.setTextColor(Palette.of(c).text3);
            setMinimumHeight(Ui.dp(c, 96));
        }
    }
}
