package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.view.View;
import android.widget.FrameLayout;
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
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「学生」→「学生账号」：按班级筛选、搜姓名学号，长按多选做批量操作（重置密码、调班、启用、停用、删除）。
 * 顶栏：导入 Excel、导出名单，「更多」里是粘贴名单、下载模板；右下角添加一个。
 *
 * <p>管理员看全校；老师只看得到、只管得着自己名下班级的学生（后端 _scope 拦，这里只是把说明和下拉对上）。
 */
final class StudentListScreen extends Screen {
    private ItemList<JSONObject> list;
    private SearchBox search;
    private TextView classChip;
    private TextView teacherWarn;
    private SelectBar bar;
    private List<JSONObject> classes = new ArrayList<>();
    /** 当前筛选的班级，null = 全部 */
    private Integer classFilter;
    private int seen = -1;
    private int total;

    @Override
    public String title() {
        return "学生账号";
    }

    @Override
    public String subtitle() {
        if (list != null && list.isSelecting()) return "已选 " + list.selection().size() + " 人";
        if (seen < 0) return null;
        return "共 " + total + " 人" + (classFilter == null ? "" : " · " + className(classFilter));
    }

    @Override
    protected View onCreateView(Context ctx) {
        FrameLayout root = new FrameLayout(ctx);
        LinearLayout col = V.vbox(ctx);
        root.addView(col, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));

        // 筛选条：班级 + 搜索
        LinearLayout filter = V.hbox(ctx);
        V.pad(filter, wide() ? 24 : 16, 8, wide() ? 24 : 16, 4);
        classChip = Kit.dropChip(ctx, "全部班级", v -> pickClassFilter());
        filter.addView(classChip);
        search = new SearchBox(ctx, "搜姓名或学号");
        LinearLayout.LayoutParams slp = V.fill();
        slp.setMarginStart(dp(8));
        filter.addView(search, slp);
        search.setOnSearch(k -> load());
        col.addView(filter, V.matchWrap());

        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return new StudentCard(c, true);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((StudentCard) v).bind(item);
            }
        });
        list.setCell(320, 3);
        list.addHeader(header(ctx));
        list.setOnRefresh(this::load);
        list.setOnItemClick((s, pos) -> push(new StudentDetailScreen(s, classes)));
        list.enableSelection(Kit::id, n -> onSelection());
        col.addView(list, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));

        bar = new SelectBar(ctx)
                .add(R.drawable.ic_key, "重置密码", false, this::bulkResetPassword)
                .add(R.drawable.ic_class, "调班", false, this::bulkMove)
                .add(R.drawable.ic_check_circle, "启用", false, () -> bulk("enable"))
                .add(R.drawable.ic_block, "停用", false, this::bulkDisable)
                .add(R.drawable.ic_delete, "删除", true, this::bulkDelete);
        root.addView(bar, SelectBar.bottom(ctx));
        return root;
    }

    /** 列表上方的说明（跟着列表一起滚走） */
    private View header(Context c) {
        LinearLayout h = V.vbox(c);
        V.pad(h, 0, 4, 0, 10);
        boolean admin = session().isAdmin();
        String text = "学生选班级填姓名（或填学号）登录学生平台，初始密码 123456；系统里没有邮箱，忘了密码只能由老师重置。"
                + "班级要先在「班级」页建好。长按卡片可多选，批量重置密码、调班、停用或删除。";
        if (!admin) {
            text += "\n这里只列你带的班的学生，加学生、导入名单也只能进这几个班。";
        }
        h.addView(V.notice(c, text, Tone.INFO), V.matchWrap());
        teacherWarn = V.notice(c, "你名下还没有班级，请管理员在「班级」页把班分给你。", Tone.WARNING);
        teacherWarn.setVisibility(View.GONE);
        V.addTop(h, teacherWarn, 8);
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
        final Integer cls = classFilter;
        final String kw = search.keyword();
        final boolean admin = session().isAdmin();
        run(() -> new Object[]{StudentApi.pickableClasses(admin), StudentApi.students(cls, kw)}, r -> {
            @SuppressWarnings("unchecked") List<JSONObject> cl = (List<JSONObject>) r[0];
            @SuppressWarnings("unchecked") List<JSONObject> rows = (List<JSONObject>) r[1];
            classes = cl;
            if (classFilter != null && className(classFilter).isEmpty()) classFilter = null;
            Kit.setDropChip(classChip, classFilter == null ? "全部班级" : className(classFilter), classFilter != null);
            teacherWarn.setVisibility(!admin && classes.isEmpty() ? View.VISIBLE : View.GONE);
            total = rows.size();
            if (!kw.isEmpty() || classFilter != null) {
                list.setEmpty("没找到符合条件的学生", "换个班级或关键词试试");
            } else {
                list.setEmpty("还没有学生账号", "先从 Excel 导入一批，或点右下角添加",
                        "导入名单", () -> RosterImport.excel(this, classes, classFilter, this::load));
            }
            list.setItems(rows);
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return false;
        });
    }

    private String className(Integer id) {
        for (JSONObject c : classes) if (Kit.id(c) == id) return Json.str(c, "display");
        return "";
    }

    private void pickClassFilter() {
        List<Option> opts = Kit.classOptions(classes, "全部班级");
        Dialogs.choose(ctx(), "按班级筛选", opts, classFilter == null ? Kit.NONE : classFilter, o -> {
            classFilter = Kit.idOf(o.value);
            load();
        });
    }

    // ---------- 顶栏 ----------

    @Override
    public List<Action> actions() {
        if (list != null && list.isSelecting()) {
            return Arrays.asList(
                    Action.icon(R.drawable.ic_select_all, "全选", () -> list.selectAll()),
                    Action.icon(R.drawable.ic_close, "取消选择", () -> list.stopSelection()));
        }
        return Arrays.asList(
                Action.icon(R.drawable.ic_upload_file, "从 Excel/CSV 导入", () -> RosterImport.excel(this, classes, classFilter, this::load)),
                Action.icon(R.drawable.ic_download, "导出名单", this::export),
                Action.menu(R.drawable.ic_upload_file, "从 Excel/CSV 导入", () -> RosterImport.excel(this, classes, classFilter, this::load)),
                Action.menu(R.drawable.ic_playlist_add, "粘贴名单", () -> RosterImport.paste(this, classes, classFilter, this::load)),
                Action.menu(R.drawable.ic_description, "下载导入模板", () -> RosterImport.template(this)),
                Action.menu(R.drawable.ic_check_circle, "多选", () -> list.startSelection()),
                Action.menu(R.drawable.ic_refresh, "刷新", this::load));
    }

    @Override
    public Action fab() {
        if (list != null && list.isSelecting()) return null;
        return Action.icon(R.drawable.ic_person_add, "添加学生",
                () -> StudentForm.open(this, null, classes, classFilter, row -> load()));
    }

    @Override
    public boolean onBack() {
        if (list.isSelecting()) {
            list.stopSelection();
            return true;
        }
        return false;
    }

    /** 导出当前筛选结果，导出的表和导入模板同构，改完能直接再导回来 */
    private void export() {
        final Integer cls = classFilter;
        final String kw = search.keyword();
        String name = "学生名单_" + (cls == null ? "全部" : className(cls)) + ".xlsx";
        Files.export(this, "正在导出…", () -> StudentApi.export(cls, kw), name);
    }

    // ---------- 多选 ----------

    private void onSelection() {
        boolean on = list.isSelecting();
        bar.setVisibility(on ? View.VISIBLE : View.GONE);
        if (on) {
            List<JSONObject> sel = list.selection();
            bar.setSummary(sel.isEmpty() ? "点卡片勾选学生" : "已选 " + sel.size() + " 人：" + Kit.names(sel, "name", 8, "人"));
        }
        invalidateChrome();
    }

    /** 选中的人；一个没选就提示一句返回 null */
    private List<JSONObject> picked() {
        List<JSONObject> sel = list.selection();
        if (sel.isEmpty()) {
            toast("先勾选学生");
            return null;
        }
        return sel;
    }

    private void bulk(final String action) {
        List<JSONObject> sel = picked();
        if (sel == null) return;
        final List<Integer> ids = Kit.ids(sel);
        runBusy("正在处理…", () -> StudentApi.bulk(ids, action), n -> {
            String verb = "delete".equals(action) ? "删除" : "disable".equals(action) ? "停用"
                    : "enable".equals(action) ? "启用" : "重置密码";
            toast("已" + verb + " " + n + " 个账号");
            Kit.touch();
            list.stopSelection();
            load();
        });
    }

    private void bulkResetPassword() {
        List<JSONObject> sel = picked();
        if (sel == null) return;
        Dialogs.confirm(ctx(), "重置密码", "把这 " + sel.size() + " 个学生的密码重置成各自的学号？\n"
                + Kit.names(sel, "name", 20, "人"), "重置", false, () -> bulk("reset_password"));
    }

    private void bulkDisable() {
        List<JSONObject> sel = picked();
        if (sel == null) return;
        Dialogs.confirm(ctx(), "批量停用", "停用 " + sel.size() + " 个账号？停用后他们登不上，数据都在，随时可以再启用。",
                "停用", true, () -> bulk("disable"));
    }

    private void bulkDelete() {
        List<JSONObject> sel = picked();
        if (sel == null) return;
        Kit.confirmTyped(ctx(), "删除学生账号", "即将永久删除 " + sel.size() + " 个学生账号："
                        + Kit.names(sel, "name", 20, "人") + "\n\n他们交过的卷子和练过的字都会保留，只是不再挂在账号上。"
                        + "删除无法撤销；只是想让人登不上的话，用「停用」。",
                "确认删除", () -> bulk("delete"));
    }

    /** 调班：后端没有批量接口，逐个改班级 */
    private void bulkMove() {
        final List<JSONObject> sel = picked();
        if (sel == null) return;
        boolean admin = session().isAdmin();
        if (classes.isEmpty() && !admin) {
            toast("你名下还没有班级");
            return;
        }
        Dialogs.choose(ctx(), "把 " + sel.size() + " 人调到", Kit.classOptions(classes, admin ? "未分班" : null),
                null, o -> {
                    final Integer target = Kit.idOf(o.value);
                    runBusy("正在调班…", () -> {
                        int n = 0;
                        for (JSONObject s : sel) {
                            StudentApi.updateStudent(Kit.id(s), Json.of("class_id", target));
                            n++;
                        }
                        return n;
                    }, n -> {
                        toast("已把 " + n + " 人调到「" + o.label + "」");
                        Kit.touch();
                        list.stopSelection();
                        load();
                    }, e -> {
                        // 中途失败：前面的已经调过去了，刷新一下让列表和服务器对上
                        Kit.touch();
                        load();
                        return false;
                    });
                });
    }
}
