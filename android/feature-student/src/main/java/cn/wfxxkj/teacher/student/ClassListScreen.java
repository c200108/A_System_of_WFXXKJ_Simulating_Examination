package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「学生」→「班级」：按年级分开看（顶上一排年级），卡片上看人数和班主任，点进去看班里都有谁。
 *
 * <p>班级归属决定谁能给谁发考试，所以「把班分给谁」是这一页最要紧的操作。
 * 增删改和分配只有管理员能做（后端 require_admin 拦），老师只能看、能认出「我的班」。
 * 管理员长按多选 → 批量分配老师 / 批量删除；先点年级再「全选」就是整个年级一起选。
 */
final class ClassListScreen extends Screen {
    private ItemList<JSONObject> list;
    private ChipRow grades;
    private TextView orphanWarn;
    private SelectBar bar;
    private List<JSONObject> all = new ArrayList<>();
    private List<JSONObject> teachers = new ArrayList<>();
    /** 当前年级，"" = 全部 */
    private String grade = "";
    private int seen = -1;

    @Override
    public String title() {
        return "班级";
    }

    @Override
    public String subtitle() {
        if (list != null && list.isSelecting()) return "已选 " + list.selection().size() + " 个班";
        if (seen < 0) return null;
        int people = 0;
        for (JSONObject c : all) people += Json.num(c, "student_count");
        return "共 " + all.size() + " 个班 · " + people + " 名学生";
    }

    private boolean admin() {
        return session().isAdmin();
    }

    @Override
    protected View onCreateView(Context ctx) {
        FrameLayout root = new FrameLayout(ctx);
        LinearLayout col = V.vbox(ctx);
        root.addView(col, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));

        grades = new ChipRow(ctx);
        V.pad(grades, wide() ? 24 : 16, 6, wide() ? 24 : 16, 2);
        grades.setOnPicked(o -> {
            grade = String.valueOf(o.value);
            show();
        });
        col.addView(grades, V.matchWrap());

        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return new ClassCard(c);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((ClassCard) v).bind(item, session().userId());
            }
        });
        list.setCell(170, 6);
        list.addHeader(header(ctx));
        list.setOnRefresh(this::load);
        list.setOnItemClick((c, pos) -> push(new ClassDetailScreen(c, teachers)));
        if (admin()) list.enableSelection(Kit::id, n -> onSelection());
        col.addView(list, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));

        bar = new SelectBar(ctx)
                .add(R.drawable.ic_manage_accounts, "分配老师", false, this::bulkOwner)
                .add(R.drawable.ic_delete, "删除", true, this::bulkDelete);
        root.addView(bar, SelectBar.bottom(ctx));
        return root;
    }

    private View header(Context c) {
        LinearLayout h = V.vbox(c);
        V.pad(h, 0, 4, 0, 10);
        String text = admin()
                ? "班级决定谁能给谁发考试：老师只能给自己名下的班发，管理员发的考试全体学生都收得到。"
                + "点班级看名单，长按可多选批量分配老师或删除。"
                : "这里显示全校班级，标「我的班」的是你带的班，发考试时只能选这些班。"
                + "点班级看名单；班级的增删改和分配由管理员操作。";
        h.addView(V.notice(c, text, Tone.INFO), V.matchWrap());
        orphanWarn = V.notice(c, "", Tone.WARNING);
        orphanWarn.setVisibility(View.GONE);
        V.addTop(h, orphanWarn, 8);
        return h;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    @Override
    protected void onShow() {
        if (seen >= 0 && seen != Kit.version()) load();
    }

    void load() {
        seen = Kit.version();
        list.loading();
        final boolean admin = admin();
        run(() -> new Object[]{StudentApi.classes(false, true),
                admin ? StudentApi.teachers() : new ArrayList<JSONObject>()}, r -> {
            @SuppressWarnings("unchecked") List<JSONObject> cl = (List<JSONObject>) r[0];
            @SuppressWarnings("unchecked") List<JSONObject> ts = (List<JSONObject>) r[1];
            all = cl;
            teachers = ts;
            int orphans = 0;
            for (JSONObject c : all) if (Json.isNull(c, "owner_id")) orphans++;
            orphanWarn.setText("还有 " + orphans + " 个班没有分配老师，这些班的学生只能收到管理员发的考试。");
            orphanWarn.setVisibility(admin && orphans > 0 ? View.VISIBLE : View.GONE);
            renderGrades();
            show();
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return false;
        });
    }

    /** 年级按出现顺序（后端已按 sort_order、年级排好） */
    private Map<String, Integer> gradeCounts() {
        Map<String, Integer> m = new LinkedHashMap<>();
        for (JSONObject c : all) {
            String g = Json.str(c, "grade");
            Integer n = m.get(g);
            m.put(g, n == null ? 1 : n + 1);
        }
        return m;
    }

    private void renderGrades() {
        Map<String, Integer> m = gradeCounts();
        if (!grade.isEmpty() && !m.containsKey(grade)) grade = "";
        List<Option> opts = new ArrayList<>();
        opts.add(new Option("", "全部 " + all.size()));
        for (Map.Entry<String, Integer> e : m.entrySet()) opts.add(new Option(e.getKey(), e.getKey() + " " + e.getValue()));
        grades.setOptions(opts, grade);
        grades.setVisibility(m.size() > 1 ? View.VISIBLE : View.GONE);
    }

    private void show() {
        List<JSONObject> rows = new ArrayList<>();
        for (JSONObject c : all) if (grade.isEmpty() || grade.equals(Json.str(c, "grade"))) rows.add(c);
        if (admin()) {
            list.setEmpty("还没有班级", "先用「按年级批量建班」建一批", "按年级批量建班",
                    () -> ClassForms.batch(this, this::load));
        } else {
            list.setEmpty("还没有班级", "班级由管理员建好后会出现在这里");
        }
        list.setItems(rows);
    }

    // ---------- 顶栏 ----------

    @Override
    public List<Action> actions() {
        if (list != null && list.isSelecting()) {
            return Arrays.asList(
                    Action.icon(R.drawable.ic_select_all, grade.isEmpty() ? "全选" : "全选" + grade, () -> list.selectAll()),
                    Action.icon(R.drawable.ic_close, "取消选择", () -> list.stopSelection()));
        }
        if (!admin()) {
            return Collections.singletonList(Action.icon(R.drawable.ic_refresh, "刷新", this::load));
        }
        return Arrays.asList(
                Action.icon(R.drawable.ic_playlist_add, "按年级批量建班", () -> ClassForms.batch(this, this::load)),
                Action.menu(R.drawable.ic_add, "新建班级", this::create),
                Action.menu(R.drawable.ic_check_circle, "多选", () -> list.startSelection()),
                Action.menu(R.drawable.ic_refresh, "刷新", this::load));
    }

    @Override
    public Action fab() {
        if (!admin() || (list != null && list.isSelecting())) return null;
        return Action.icon(R.drawable.ic_add, "新建班级", this::create);
    }

    @Override
    public boolean onBack() {
        if (list.isSelecting()) {
            list.stopSelection();
            return true;
        }
        return false;
    }

    private void create() {
        ClassForms.edit(this, null, teachers, row -> load());
    }

    // ---------- 多选 ----------

    private void onSelection() {
        boolean on = list.isSelecting();
        bar.setVisibility(on ? View.VISIBLE : View.GONE);
        if (on) {
            List<JSONObject> sel = list.selection();
            bar.setSummary(sel.isEmpty() ? "点卡片勾选班级" : "已选 " + sel.size() + " 个班：" + Kit.names(sel, "display", 8, "个班"));
        }
        invalidateChrome();
    }

    private List<JSONObject> picked() {
        List<JSONObject> sel = list.selection();
        if (sel.isEmpty()) {
            toast("先勾选班级");
            return null;
        }
        return sel;
    }

    private void afterBulk() {
        list.stopSelection();
        load();
    }

    private void bulkOwner() {
        List<JSONObject> sel = picked();
        if (sel != null) ClassForms.owner(this, sel, teachers, this::afterBulk);
    }

    private void bulkDelete() {
        List<JSONObject> sel = picked();
        if (sel != null) ClassForms.deleteMany(this, sel, this::afterBulk);
    }
}
