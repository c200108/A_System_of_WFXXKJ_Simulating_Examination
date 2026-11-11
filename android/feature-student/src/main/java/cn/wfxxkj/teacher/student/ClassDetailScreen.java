package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 班级详情：班主任、人数、男女人数、停用人数，下面是这个班的学生名单（可搜学号姓名，点人进学生详情）。
 * 管理员在这里改班名、换班主任、删班；带这个班的老师和管理员可以直接往班里加学生、导出本班名单。
 */
final class ClassDetailScreen extends Screen {
    private JSONObject cls;
    private List<JSONObject> teachers;
    private List<JSONObject> allClasses = new ArrayList<>();
    private List<JSONObject> students = new ArrayList<>();
    private ItemList<JSONObject> list;
    private SearchBox search;
    private GridBox stats;
    private LinearLayout ownerRow;
    private TextView seatInfo;
    private int seen = -1;

    ClassDetailScreen(JSONObject cls, List<JSONObject> teachers) {
        this.cls = cls;
        this.teachers = teachers == null ? new ArrayList<>() : teachers;
    }

    @Override
    public String title() {
        return Json.str(cls, "display");
    }

    @Override
    public String subtitle() {
        String o = Json.str(cls, "owner_name");
        return "班主任：" + (o.isEmpty() ? "未分配" : o);
    }

    private boolean admin() {
        return session().isAdmin();
    }

    /** 能往这个班里加学生：管理员，或者这个班就是自己带的 */
    private boolean canManage() {
        Integer o = Kit.intOrNull(cls, "owner_id");
        return admin() || (o != null && o == session().userId());
    }

    @Override
    protected View onCreateView(Context ctx) {
        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return new StudentCard(c, false);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((StudentCard) v).bind(item);
            }
        });
        list.setCell(320, 3);
        list.addHeader(header(ctx));
        list.setOnRefresh(this::load);
        list.setOnItemClick((s, pos) -> push(new StudentDetailScreen(s, pickable())));
        return list;
    }

    private View header(Context c) {
        LinearLayout h = V.vbox(c);
        V.pad(h, 0, 4, 0, 4);
        LinearLayout card = V.card(c);
        ownerRow = V.hbox(c);
        card.addView(ownerRow);
        stats = new GridBox(c, 56, 5, 6);
        V.addTop(card, stats, 12);
        h.addView(card, V.matchWrap());

        // 在线座次、课堂日志、上机座次表文件（网页端「班级」页的三样）
        LinearLayout seat = V.card(c);
        LinearLayout btns = V.hbox(c);
        btns.addView(V.button(c, R.drawable.ic_table_view, "在线座次", V.BTN_TONAL, v -> push(new SeatScreen(cls))),
                V.weight(1));
        LinearLayout.LayoutParams second = V.weight(1);
        second.setMarginStart(dp(8));
        btns.addView(V.button(c, R.drawable.ic_edit_note, "课堂日志", V.BTN_TONAL,
                v -> push(new ClassLogScreen(cls, canManage()))), second);
        seat.addView(btns, V.matchWrap());
        seatInfo = V.text(c, "", V.CAPTION);
        V.clickable(seatInfo, 6, v -> seatFileMenu());
        V.addTop(seat, seatInfo, 10);
        V.addTop(h, seat, 12);

        search = new SearchBox(c, "按学号或姓名找人");
        search.setOnSearch(k -> filter());
        V.addTop(h, search, 12);
        return h;
    }

    @Override
    protected void onFirstShow() {
        renderHeader();
        load();
    }

    @Override
    protected void onShow() {
        if (seen >= 0 && seen != Kit.version()) load();
    }

    void load() {
        seen = Kit.version();
        list.loading();
        final int id = Kit.id(cls);
        final boolean admin = admin();
        run(() -> new Object[]{StudentApi.classes(false, true), StudentApi.students(id, null),
                admin && teachers.isEmpty() ? StudentApi.teachers() : teachers}, r -> {
            @SuppressWarnings("unchecked") List<JSONObject> cl = (List<JSONObject>) r[0];
            @SuppressWarnings("unchecked") List<JSONObject> st = (List<JSONObject>) r[1];
            @SuppressWarnings("unchecked") List<JSONObject> ts = (List<JSONObject>) r[2];
            allClasses = cl;
            teachers = ts;
            JSONObject fresh = null;
            for (JSONObject c : cl) if (Kit.id(c) == id) fresh = c;
            if (fresh == null) {
                // 班被删了（别处删的），回上一页
                toast("这个班已经不存在了");
                finish();
                return;
            }
            cls = fresh;
            students = st;
            renderHeader();
            filter();
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return false;
        });
    }

    /** 学生表单、调班能选的班：管理员全校（启用的），老师只有自己带的 */
    private List<JSONObject> pickable() {
        List<JSONObject> out = new ArrayList<>();
        long me = session().userId();
        for (JSONObject c : allClasses) {
            if (!Json.bool(c, "is_active")) continue;
            Integer o = Kit.intOrNull(c, "owner_id");
            if (admin() || (o != null && o == me)) out.add(c);
        }
        return out;
    }

    private void renderHeader() {
        Context c = ctx();
        String sn = Json.str(cls, "seat_name");
        seatInfo.setText(sn.isEmpty()
                ? "上机座次表文件：还没有" + (canManage() ? "（点这里上传图片或 Excel）" : "")
                : "上机座次表文件：" + sn + "（点这里查看" + (canManage() ? "、更换或删除" : "") + "）");
        Palette p = Palette.of(c);
        ownerRow.removeAllViews();
        String o = Json.str(cls, "owner_name");
        boolean orphan = Json.isNull(cls, "owner_id");
        ownerRow.addView(V.iconTile(c, R.drawable.ic_school, orphan ? Tone.WARNING : Tone.PRIMARY));
        LinearLayout texts = V.vbox(c);
        texts.addView(V.text(c, "班主任 / 任课老师", V.CAPTION));
        TextView name = V.oneLine(V.text(c, orphan ? "未分配" : o, V.H3));
        if (orphan) name.setTextColor(p.warning);
        texts.addView(name);
        LinearLayout.LayoutParams tlp = V.fill();
        tlp.setMarginStart(dp(12));
        ownerRow.addView(texts, tlp);
        Integer ownerId = Kit.intOrNull(cls, "owner_id");
        if (ownerId != null && ownerId == session().userId()) ownerRow.addView(V.tag(c, "我的班", Tone.SUCCESS));
        if (admin()) {
            ownerRow.addView(V.button(c, orphan ? "分配" : "更换", V.BTN_TONAL,
                    v -> ClassForms.owner(this, Collections.singletonList(cls), teachers, this::load)));
        }

        int male = 0, female = 0, unknown = 0, inactive = 0;
        for (JSONObject s : students) {
            String g = Json.str(s, "gender");
            if ("男".equals(g)) male++;
            else if ("女".equals(g)) female++;
            else unknown++;
            if (!Json.bool(s, "is_active")) inactive++;
        }
        stats.removeAllViews();
        stats.addView(V.stat(c, String.valueOf(students.size()), "学生", Tone.PRIMARY));
        stats.addView(V.stat(c, String.valueOf(male), "男", Tone.INFO));
        stats.addView(V.stat(c, String.valueOf(female), "女", Tone.VIOLET));
        stats.addView(V.stat(c, String.valueOf(unknown), "未填", Tone.NEUTRAL));
        stats.addView(V.stat(c, String.valueOf(inactive), "停用", inactive > 0 ? Tone.DANGER : Tone.NEUTRAL));
    }

    private void filter() {
        String kw = search.keyword();
        List<JSONObject> shown = new ArrayList<>();
        for (JSONObject s : students) {
            if (kw.isEmpty() || Json.str(s, "student_no").contains(kw) || Json.str(s, "name").contains(kw)) shown.add(s);
        }
        if (!kw.isEmpty()) list.setEmpty("没找到这个人", "换个学号或姓名试试");
        else if (canManage()) list.setEmpty("这个班还没有学生", "点右下角添加，或到「学生账号」页导入名单");
        else list.setEmpty("这个班还没有学生", admin() ? null : "不是你带的班时，这里看不到学生名单");
        list.setItems(shown);
    }

    // ---------- 顶栏 ----------

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (admin()) {
            a.add(Action.icon(R.drawable.ic_edit, "修改班级",
                    () -> ClassForms.edit(this, cls, teachers, row -> load())));
        }
        a.add(Action.icon(R.drawable.ic_download, "导出本班名单", this::export));
        if (admin()) {
            a.add(Action.menu(R.drawable.ic_manage_accounts, "分配老师",
                    () -> ClassForms.owner(this, Collections.singletonList(cls), teachers, this::load)));
            a.add(Action.menu(R.drawable.ic_delete, "删除班级", () -> ClassForms.delete(this, cls, this::finish)).danger());
        }
        if (canManage()) {
            a.add(Action.menu(R.drawable.ic_upload_file, "从 Excel/CSV 导入到本班",
                    () -> RosterImport.excel(this, pickable(), Kit.id(cls), this::load)));
            a.add(Action.menu(R.drawable.ic_playlist_add, "粘贴名单到本班",
                    () -> RosterImport.paste(this, pickable(), Kit.id(cls), this::load)));
        }
        a.add(Action.menu(R.drawable.ic_refresh, "刷新", this::load));
        return a;
    }

    @Override
    public Action fab() {
        if (!canManage()) return null;
        return Action.icon(R.drawable.ic_person_add, "添加学生",
                () -> StudentForm.open(this, null, pickable(), Kit.id(cls), row -> load()));
    }

    /** 上机座次表文件（图片或 Excel）：查看 / 上传更换 / 删除 */
    private void seatFileMenu() {
        final int id = Kit.id(cls);
        final String sn = Json.str(cls, "seat_name");
        List<Action> a = new ArrayList<>();
        if (!sn.isEmpty()) {
            a.add(Action.menu(R.drawable.ic_download, "下载查看「" + sn + "」",
                    () -> Files.export(this, "正在下载…", () -> StudentApi.seatFile(id), sn)));
        }
        if (canManage()) {
            a.add(Action.menu(R.drawable.ic_upload_file, sn.isEmpty() ? "上传座次表（图片或 Excel）" : "换一个文件",
                    () -> pickFile(new String[]{"image/*", Files.XLSX, Files.XLS, "application/octet-stream"},
                            uri -> runBusy("正在上传…", () -> StudentApi.uploadSeatFile(id, uri), row -> {
                                cls = row;
                                Kit.touch();
                                renderHeader();
                                toast("座次表已上传");
                            }))));
            if (!sn.isEmpty()) {
                a.add(Action.menu(R.drawable.ic_delete, "删除座次表文件", () -> cn.wfxxkj.teacher.core.ui.Dialogs.confirm(ctx(),
                        "删除座次表文件", "删掉「" + sn + "」？在线座次不受影响。", "删除", true,
                        () -> runBusy("正在删除…", () -> StudentApi.deleteSeatFile(id), row -> {
                            cls = row;
                            Kit.touch();
                            renderHeader();
                            toast("已删除");
                        }))).danger());
            }
        }
        if (a.isEmpty()) {
            toast("这个班还没有上传座次表文件");
            return;
        }
        cn.wfxxkj.teacher.core.ui.Dialogs.actions(ctx(), "上机座次表文件", a);
    }

    private void export() {
        final int id = Kit.id(cls);
        Files.export(this, "正在导出…", () -> StudentApi.export(id, null),
                "学生名单_" + Json.str(cls, "display") + ".xlsx");
    }

}
