package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.Html;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 账号管理（网页 Users.vue，仅管理员）：教师账号卡片列表。
 * 点卡片进详情（重置密码、改姓名、改角色、启停、删除权、分配班级）；
 * 长按多选后批量启用 / 停用 / 删除；右下角「新增账号」。
 */
public class UsersScreen extends Screen {

    private ItemList<JSONObject> list;
    private SearchBox search;
    private List<JSONObject> all = new ArrayList<>();
    private int selCount = -1;
    private boolean loadedOnce;

    @Override
    public String title() {
        return selCount >= 0 ? "已选 " + selCount + " 个账号" : "账号管理";
    }

    @Override
    public String subtitle() {
        if (selCount >= 0) return pickedNames();
        return all.isEmpty() ? null : "共 " + all.size() + " 个账号";
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new UserCard(ctx);
            }

            @Override
            public void bind(View v, JSONObject u, int pos) {
                ((UserCard) v).bind(u, all.indexOf(u), session().userId());
            }
        });
        list.setCell(360, 3);

        LinearLayout head = V.vbox(c);
        head.addView(V.notice(c, Html.fromHtml("系统里没有邮箱，老师忘记密码<b>只能由管理员重置</b>。"
                + "重置后新密码只显示一次，请当场发给本人。<br/><b>带的班</b>决定这位老师能给谁发考试；"
                + "<b>删除权</b>控制他能不能删题库、练习文本、更新日志这些全校共用的内容，默认关着。"
                + "<br/>长按卡片可多选，批量启用、停用或删除。", Html.FROM_HTML_MODE_LEGACY), Tone.INFO));
        search = new SearchBox(c, "按姓名、用户名、联系方式查找");
        search.setOnSearch(k -> applyFilter());
        head.addView(search.padded());
        list.addHeader(head);

        list.setEmpty("没有账号", null);
        list.setOnRefresh(this::load);
        list.setOnItemClick((u, pos) -> push(new UserDetailScreen(u)));
        list.enableSelection(u -> u.optLong("id"), n -> {
            selCount = n;
            invalidateChrome();
        });
        return list;
    }

    @Override
    protected void onFirstShow() {
        list.loading();
        load();
    }

    @Override
    protected void onShow() {
        // 从详情页回来刷新一下（改了角色、启停、班级）
        if (loadedOnce) load();
    }

    void load() {
        run(MeApi::users, users -> {
            loadedOnce = true;
            all = users;
            applyFilter();
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return false;
        });
    }

    private void applyFilter() {
        String k = search.keyword().toLowerCase();
        if (k.isEmpty()) {
            list.setItems(all);
            return;
        }
        List<JSONObject> out = new ArrayList<>();
        for (JSONObject u : all) {
            String hay = (Json.str(u, "name") + " " + Json.str(u, "username") + " " + Json.str(u, "contact"))
                    .toLowerCase();
            if (hay.contains(k)) out.add(u);
        }
        list.setItems(out);
    }

    private String pickedNames() {
        List<String> names = new ArrayList<>();
        for (JSONObject u : list.selection()) names.add(MeUi.nameOf(u));
        return TextUtils.join("、", names);
    }

    // ---------- 顶栏 ----------

    @Override
    public List<Action> actions() {
        if (selCount >= 0) {
            return Arrays.asList(
                    Action.icon(R.drawable.ic_select_all, "全选", () -> list.selectAll()),
                    Action.menu(R.drawable.ic_check_circle, "批量启用", () -> bulk("enable")),
                    Action.menu(R.drawable.ic_block, "批量停用", () -> bulk("disable")),
                    Action.menu(R.drawable.ic_delete, "批量删除", () -> bulk("delete")).danger(),
                    Action.menu(R.drawable.ic_close, "取消选择", () -> list.stopSelection()));
        }
        return Arrays.asList(
                Action.icon(R.drawable.ic_refresh, "刷新", () -> {
                    list.loading();
                    load();
                }),
                Action.menu(R.drawable.ic_key, "修改我的密码", () -> UserSheets.changeMyPassword(this)),
                Action.menu(R.drawable.ic_select_all, "多选", () -> list.startSelection()));
    }

    @Override
    public Action fab() {
        if (selCount >= 0) return null;
        return Action.icon(R.drawable.ic_person_add, "新增账号", () -> UserSheets.create(this, this::load));
    }

    @Override
    public boolean onBack() {
        if (list.isSelecting()) {
            list.stopSelection();
            return true;
        }
        return false;
    }

    // ---------- 批量 ----------

    private void bulk(String action) {
        // 自己不能停用、删除 —— 那会把自己锁在门外
        List<JSONObject> picked = new ArrayList<>();
        boolean skippedSelf = false;
        for (JSONObject u : list.selection()) {
            if (u.optLong("id") == session().userId() && !"enable".equals(action)) skippedSelf = true;
            else picked.add(u);
        }
        if (picked.isEmpty()) {
            toast(skippedSelf ? "不能停用或删除自己的账号" : "先勾选账号");
            return;
        }
        final List<Object> ids = new ArrayList<>();
        List<String> names = new ArrayList<>();
        int admins = 0;
        for (JSONObject u : picked) {
            ids.add(u.optLong("id"));
            names.add(MeUi.nameOf(u));
            if (MeUi.isAdmin(u)) admins++;
        }
        String who = TextUtils.join("、", names);
        String selfNote = skippedSelf ? "\n（你自己的账号已自动跳过）" : "";
        Runnable go = () -> runBusy("正在处理…", () -> MeApi.bulkUsers(ids, action), res -> {
            list.stopSelection();
            String verb = "delete".equals(action) ? "删除" : "disable".equals(action) ? "停用" : "启用";
            toast("已" + verb + " " + res.optInt("affected") + " 个账号");
            load();
        });
        if ("delete".equals(action)) {
            // 删除不可恢复：要求手工敲「删除」两个字，把误点挡在外面
            String msg = "即将永久删除 " + ids.size() + " 个账号：" + who + "\n"
                    + (admins > 0 ? "其中有 " + admins + " 个管理员账号。\n" : "")
                    + "\n他们建过的题目、试卷、考试和成绩都会保留，只是不再记录「是谁建的」。\n"
                    + "删除无法撤销。只是想让人登不上的话，用「批量停用」，随时能再启用。" + selfNote
                    + "\n\n确认请输入「删除」两个字：";
            MeUi.confirmTyped(ctx(), "危险操作", msg, "确认删除", go);
        } else if ("disable".equals(action)) {
            Dialogs.confirm(ctx(), "批量停用", "停用 " + ids.size() + " 个账号：" + who
                    + "？\n停用后他们登不上，但数据都在，随时可以再启用。" + selfNote, "停用", true, go);
        } else {
            go.run();
        }
    }
}
