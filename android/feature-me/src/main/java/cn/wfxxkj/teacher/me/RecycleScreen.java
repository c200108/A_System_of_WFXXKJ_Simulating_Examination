package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.TextUtils;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 数据回收站（网页端「我的账号」里的回收站）：删掉的考试、答卷、试卷、题目、学生、班级、打字成绩、
 * 练习文本、仿真任务、反馈都先放这里几天，可以还原；到期自动彻底删除。
 * 老师只看得到自己删的，管理员看得到所有人删的，清空只有管理员能做。
 */
final class RecycleScreen extends Screen {
    private ItemList<JSONObject> list;
    private ChipRow kinds;
    private TextView tip;
    private List<JSONObject> all = new ArrayList<>();
    private String kind = "";
    private int keepDays = 7;

    @Override
    public String title() {
        return "回收站";
    }

    @Override
    public String subtitle() {
        if (list != null && list.isSelecting()) return "已选 " + list.selection().size() + " 条";
        return all.isEmpty() ? null : "共 " + all.size() + " 条";
    }

    @Override
    protected View onCreateView(Context ctx) {
        LinearLayout col = V.vbox(ctx);
        kinds = new ChipRow(ctx);
        V.pad(kinds, 16, 6, 16, 2);
        kinds.setOnPicked(o -> {
            kind = String.valueOf(o.value);
            show();
        });
        col.addView(kinds, V.matchWrap());
        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return V.card(c);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                bindCard((LinearLayout) v, item);
            }
        });
        list.setCell(320, 2);
        tip = V.notice(ctx, "", Tone.INFO);
        LinearLayout head = V.vbox(ctx);
        V.pad(head, 0, 4, 0, 10);
        head.addView(tip, V.matchWrap());
        list.addHeader(head);
        list.setOnRefresh(this::load);
        list.setOnItemClick((item, pos) -> itemMenu(item));
        list.enableSelection(it -> it.optInt("id"), n -> invalidateChrome());
        col.addView(list, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));
        FrameLayout root = new FrameLayout(ctx);
        root.addView(col, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        return root;
    }

    private void bindCard(LinearLayout card, JSONObject it) {
        Context c = card.getContext();
        card.removeAllViews();
        LinearLayout head = V.hbox(c);
        head.addView(V.tag(c, Json.str(it, "kind_name"), Tone.INFO));
        V.addStart(head, V.oneLine(V.bold(V.text(c, Json.str(it, "title"), V.BODY))), 8);
        card.addView(head);
        String detail = Json.str(it, "detail");
        if (!detail.isEmpty()) V.addTop(card, V.lines(V.text(c, detail, V.BODY2), 2), 4);
        int left = Json.num(it, "days_left");
        String who = session().isAdmin() ? Json.str(it, "deleted_by_name") + " · " : "";
        TextView meta = V.text(c, who + stamp(Json.str(it, "deleted_at")) + " 删除 · 还剩 " + left + " 天", V.CAPTION);
        if (left <= 1) meta.setTextColor(Palette.of(c).danger);
        V.addTop(card, meta, 6);
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    private void load() {
        list.loading();
        run(MeApi::recycle, r -> {
            all = Json.list(Json.arr(r, "items"));
            keepDays = r.optInt("keep_days", 7);
            tip.setText("删掉的东西先在这里放 " + keepDays + " 天：点一条可以还原（回到原来的位置）或彻底删除，长按可以多选。"
                    + "不管它，" + keepDays + " 天后自动彻底删除。" + (session().isAdmin() ? "管理员看得到所有老师删的。" : "这里只有你自己删的。"));
            Map<String, Integer> counts = new LinkedHashMap<>();
            for (JSONObject it : all) {
                String k = Json.str(it, "kind");
                counts.put(k, counts.containsKey(k) ? counts.get(k) + 1 : 1);
            }
            JSONObject names = Json.obj(r, "kinds");
            List<Option> opts = new ArrayList<>();
            opts.add(new Option("", "全部 " + all.size()));
            for (Iterator<String> it = names == null ? Collections.<String>emptyIterator() : names.keys(); it.hasNext(); ) {
                String k = it.next();
                if (counts.containsKey(k)) opts.add(new Option(k, names.optString(k) + " " + counts.get(k)));
            }
            if (!kind.isEmpty() && !counts.containsKey(kind)) kind = "";
            kinds.setOptions(opts, kind);
            kinds.setVisibility(opts.size() > 2 ? View.VISIBLE : View.GONE);
            show();
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return true;
        });
    }

    private void show() {
        List<JSONObject> rows = new ArrayList<>();
        for (JSONObject it : all) if (kind.isEmpty() || kind.equals(Json.str(it, "kind"))) rows.add(it);
        list.setEmpty("回收站是空的", "删掉的考试、题目、学生等会先放到这里");
        list.setItems(rows);
    }

    @Override
    public List<Action> actions() {
        if (list != null && list.isSelecting()) {
            return Arrays.asList(
                    Action.icon(R.drawable.ic_restart_alt, "还原选中的", () -> restore(list.selection())),
                    Action.icon(R.drawable.ic_delete, "彻底删除选中的", () -> destroy(list.selection())),
                    Action.menu(R.drawable.ic_select_all, "全选", () -> list.selectAll()),
                    Action.menu(R.drawable.ic_close, "取消选择", () -> list.stopSelection()));
        }
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_refresh, "刷新", this::load));
        a.add(Action.menu(R.drawable.ic_check_circle, "多选", () -> list.startSelection()));
        if (session().isAdmin()) a.add(Action.menu(R.drawable.ic_delete, "清空回收站", this::clearAll).danger());
        return a;
    }

    @Override
    public boolean onBack() {
        if (list.isSelecting()) {
            list.stopSelection();
            return true;
        }
        return false;
    }

    private void itemMenu(JSONObject it) {
        Dialogs.actions(ctx(), Json.str(it, "kind_name") + " · " + Json.str(it, "title"), Arrays.asList(
                Action.menu(R.drawable.ic_restart_alt, "还原", () -> restore(Collections.singletonList(it))),
                Action.menu(R.drawable.ic_delete, "彻底删除", () -> destroy(Collections.singletonList(it))).danger()));
    }

    private static List<Integer> ids(List<JSONObject> rows) {
        List<Integer> out = new ArrayList<>();
        for (JSONObject r : rows) out.add(r.optInt("id"));
        return out;
    }

    private void restore(List<JSONObject> rows) {
        if (rows.isEmpty()) {
            toast("先勾选要还原的");
            return;
        }
        final List<Integer> ids = ids(rows);
        runBusy("正在还原…", () -> MeApi.recycleRestore(ids), r -> {
            List<String> failed = Json.strings(Json.arr(r, "failed"));
            if (!failed.isEmpty()) {
                Dialogs.alert(ctx(), "还原了 " + Json.num(r, "restored") + " 条，" + failed.size() + " 条没还原",
                        TextUtils.join("\n\n", failed));
            } else {
                toast("已还原 " + Json.num(r, "restored") + " 条，回到原来的位置了");
            }
            if (list.isSelecting()) list.stopSelection();
            load();
        });
    }

    private void destroy(List<JSONObject> rows) {
        if (rows.isEmpty()) {
            toast("先勾选要删除的");
            return;
        }
        final List<Integer> ids = ids(rows);
        Dialogs.confirm(ctx(), "彻底删除", "彻底删除这 " + rows.size() + " 条？彻底删除后就再也找不回来了。", "彻底删除", true,
                () -> runBusy("正在删除…", () -> MeApi.recycleDestroy(ids), r -> {
                    toast("已彻底删除");
                    if (list.isSelecting()) list.stopSelection();
                    load();
                }));
    }

    private void clearAll() {
        Dialogs.confirm(ctx(), "清空回收站", "清空回收站里全部 " + all.size() + " 条（包括所有老师删的）？清空后就再也找不回来了。",
                "清空", true, () -> runBusy("正在清空…", () -> {
                    MeApi.recycleClear();
                    return true;
                }, r -> {
                    toast("回收站已清空");
                    load();
                }));
    }

    private static String stamp(String s) {
        s = s == null ? "" : s.replace('T', ' ');
        return s.length() >= 16 ? s.substring(0, 16) : s;
    }
}
