package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 考试管理首页：考试卡片列表，按状态筛选、按名称搜索，右下角「发布考试」，
 * 长按多选后批量开放 / 关闭 / 删除。点卡片进考试详情。
 */
final class ExamListScreen extends Screen {

    private static final String ALL = "all", OPEN = "open", CLOSED = "closed", PENDING = "pending",
            MINE = "mine", READONLY = "readonly";

    private ItemList<JSONObject> list;
    private ChipRow filter;
    private SearchBox search;
    private TextView summary;
    private final List<JSONObject> all = new ArrayList<>();
    private int selCount = -1;

    @Override
    public String title() {
        return "考试管理";
    }

    @Override
    public String subtitle() {
        return selCount >= 0 ? "已选 " + selCount + " 场考试" : null;
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new ExamCard(ctx, new ExamCard.Quick() {
                    @Override
                    public void copyLink(JSONObject exam) {
                        String link = ExamApi.linkOf(exam);
                        Sys.copy(ctx, "考试链接", link);
                        toast("链接已复制：" + link);
                    }

                    @Override
                    public void showQr(JSONObject exam) {
                        QrSheet.show(ExamListScreen.this, Json.str(exam, "title"), ExamApi.linkOf(exam));
                    }

                    @Override
                    public void analysis(JSONObject exam) {
                        push(new AnalysisScreen(exam.optLong("id"), Json.str(exam, "title")));
                    }
                });
            }

            @Override
            public void bind(View v, JSONObject exam, int pos) {
                ((ExamCard) v).bind(exam);
            }
        });
        list.setCell(360, 3);

        LinearLayout header = V.vbox(c);
        boolean admin = session().isAdmin();
        TextView hint = V.notice(c, admin
                ? "把存档的试卷发布成考试，学生打开链接直接答题，不需要账号；判分在服务器上做，成绩自动汇总。你是管理员，这里列的是全校所有老师发布的考试。"
                : "把存档的试卷发布成考试，学生打开链接直接答题，不需要账号。这里列你自己发布的考试，以及管理员发布的（多半是全校统考，只能查成绩、导出，改不了设置也删不掉）。",
                Tone.INFO);
        V.addTop(header, hint, 4);
        search = new SearchBox(c, "搜考试名称、发布人、班级");
        V.addTop(header, search, 10);
        filter = new ChipRow(c);
        List<Option> opts = new ArrayList<>(Arrays.asList(
                new Option(ALL, "全部"), new Option(OPEN, "开放中"), new Option(CLOSED, "已关闭"),
                new Option(PENDING, "待阅卷")));
        if (!admin) {
            opts.add(new Option(MINE, "我发布的"));
            opts.add(new Option(READONLY, "管理员发布"));
        }
        filter.setOptions(opts, ALL);
        V.addTop(header, filter, 6);
        summary = V.text(c, "", V.CAPTION);
        V.pad(summary, 4, 4, 0, 4);
        header.addView(summary);
        list.addHeader(header);

        search.setOnSearch(k -> render());
        filter.setOnPicked(o -> render());
        list.setOnRefresh(this::load);
        list.setOnItemClick((exam, pos) -> openDetail(exam));
        list.enableSelection(e -> e.optLong("id"), n -> {
            selCount = n;
            invalidateChrome();
        });
        list.setEmpty("还没有发布过考试", "把组好的试卷发布成考试，学生凭链接答题", "发布考试", this::publish);
        return list;
    }

    @Override
    protected void onFirstShow() {
        list.loading();
        load();
    }

    @Override
    public Action fab() {
        if (selCount >= 0) return null;
        return Action.icon(R.drawable.ic_add, "发布考试", this::publish);
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (selCount >= 0) {
            a.add(Action.icon(R.drawable.ic_select_all, "全选", () -> list.selectAll()));
            a.add(Action.icon(R.drawable.ic_close, "退出多选", () -> list.stopSelection()));
            a.add(Action.menu(R.drawable.ic_play_arrow, "开放选中的考试", () -> batchToggle(true)));
            a.add(Action.menu(R.drawable.ic_stop, "关闭选中的考试", () -> batchToggle(false)));
            a.add(Action.menu(R.drawable.ic_delete, "删除选中的考试", this::batchDelete).danger());
            return a;
        }
        a.add(Action.icon(R.drawable.ic_refresh, "刷新", () -> {
            list.loading();
            load();
        }));
        a.add(Action.menu(R.drawable.ic_done_all, "多选", () -> list.startSelection()));
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

    @Override
    protected void onShow() {
        // 从详情页回来：数字（交卷、待阅）可能变了，静默刷新
        if (!all.isEmpty()) load();
    }

    void load() {
        run(ExamApi::exams, rows -> {
            all.clear();
            all.addAll(rows);
            render();
        }, e -> {
            list.error(e.getMessage(), () -> {
                list.loading();
                load();
            });
            return all.isEmpty();
        });
    }

    private void render() {
        String k = search.keyword().toLowerCase(Locale.ROOT);
        Object f = filter.value();
        List<JSONObject> shown = new ArrayList<>();
        int nOpen = 0, nClosed = 0, nPending = 0, nMine = 0, nRo = 0;
        for (JSONObject e : all) {
            boolean open = Json.bool(e, "is_open");
            boolean pending = Json.num(e, "ungraded_count") > 0;
            boolean mine = Json.bool(e, "can_edit");
            if (open) nOpen++;
            else nClosed++;
            if (pending) nPending++;
            if (mine) nMine++;
            else nRo++;
            boolean ok = ALL.equals(f) || OPEN.equals(f) && open || CLOSED.equals(f) && !open
                    || PENDING.equals(f) && pending || MINE.equals(f) && mine || READONLY.equals(f) && !mine;
            if (!ok) continue;
            if (!k.isEmpty()) {
                String hay = (Json.str(e, "title") + " " + Json.str(e, "owner_name") + " "
                        + Json.str(e, "target_classes")).toLowerCase(Locale.ROOT);
                if (!hay.contains(k)) continue;
            }
            shown.add(e);
        }
        filter.setLabel(ALL, "全部 " + all.size());
        filter.setLabel(OPEN, "开放中 " + nOpen);
        filter.setLabel(CLOSED, "已关闭 " + nClosed);
        filter.setLabel(PENDING, "待阅卷 " + nPending);
        filter.setLabel(MINE, "我发布的 " + nMine);
        filter.setLabel(READONLY, "管理员发布 " + nRo);
        summary.setText(shown.size() == all.size() ? "共 " + all.size() + " 场考试 · 长按卡片可多选"
                : "筛出 " + shown.size() + " / " + all.size() + " 场");
        if (!all.isEmpty() && shown.isEmpty()) list.setEmpty("没有符合条件的考试", "换个筛选条件或关键词试试");
        else list.setEmpty("还没有发布过考试", "把组好的试卷发布成考试，学生凭链接答题", "发布考试", this::publish);
        list.setItems(shown);
    }

    private void openDetail(JSONObject exam) {
        push(new ExamDetailScreen(exam));
    }

    private void publish() {
        PublishSheet.create(this, saved -> {
            load();
            snack("已发布《" + Json.str(saved, "title") + "》", "查看", () -> push(new ExamDetailScreen(saved)));
        });
    }

    // ---------- 批量 ----------

    /** 选中的里面能改的（管理员发布的老师改不了） */
    private List<JSONObject> editable(List<JSONObject> sel) {
        List<JSONObject> out = new ArrayList<>();
        for (JSONObject e : sel) if (Json.bool(e, "can_edit")) out.add(e);
        return out;
    }

    private void batchToggle(boolean open) {
        List<JSONObject> sel = list.selection();
        if (sel.isEmpty()) {
            toast("先点选要操作的考试");
            return;
        }
        List<JSONObject> ok = editable(sel);
        if (ok.isEmpty()) {
            toast("选中的都是管理员发布的考试，改不了设置");
            return;
        }
        int skipped = sel.size() - ok.size();
        runBusy(open ? "正在开放…" : "正在关闭…", () -> {
            for (JSONObject e : ok) ExamApi.updateExam(e.optLong("id"), Json.of("is_open", open));
            return ok.size();
        }, n -> {
            toast((open ? "已开放 " : "已关闭 ") + n + " 场" + (skipped > 0 ? "，" + skipped + " 场管理员发布的跳过了" : ""));
            list.stopSelection();
            load();
        });
    }

    private void batchDelete() {
        List<JSONObject> sel = list.selection();
        if (sel.isEmpty()) {
            toast("先点选要删除的考试");
            return;
        }
        List<JSONObject> ok = editable(sel);
        if (ok.isEmpty()) {
            toast("选中的都是管理员发布的考试，删不掉");
            return;
        }
        int subs = 0;
        for (JSONObject e : ok) subs += Json.num(e, "submission_count");
        int skipped = sel.size() - ok.size();
        Dialogs.confirm(ctx(), "删除 " + ok.size() + " 场考试？",
                "已经收到的 " + subs + " 份答卷会一起删掉，删了找不回来。"
                        + (skipped > 0 ? "\n另有 " + skipped + " 场是管理员发布的，不会删。" : ""),
                "删除 " + ok.size() + " 场", true, () -> runBusy("正在删除…", () -> {
                    for (JSONObject e : ok) ExamApi.deleteExam(e.optLong("id"));
                    return ok.size();
                }, n -> {
                    toast("已删除 " + n + " 场考试");
                    list.stopSelection();
                    load();
                }));
    }
}
