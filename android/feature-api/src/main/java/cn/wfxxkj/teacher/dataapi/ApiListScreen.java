package cn.wfxxkj.teacher.dataapi;

import android.content.Context;
import android.view.View;
import android.widget.LinearLayout;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「API」标签首页：我建的 API，一张卡一个；右下角新建。管理员看全部，右上角可按老师筛选。
 */
final class ApiListScreen extends Screen {
    static int version = 0;           // 详情页改过东西就 +1，回到列表时重拉

    private ItemList<JSONObject> list;
    private List<JSONObject> teachers = new ArrayList<>();
    private JSONObject templates = new JSONObject();
    private Integer owner;
    private int seen = -1;
    private int total = -1;

    @Override
    public String title() {
        return "API";
    }

    @Override
    public String subtitle() {
        return total < 0 ? null : "共 " + total + " 个 API";
    }

    @Override
    protected View onCreateView(Context ctx) {
        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                return new ApiCard(c);
            }

            @Override
            public void bind(View v, JSONObject item, int position) {
                ((ApiCard) v).bind(item, session().isAdmin());
            }
        });
        list.setCell(300, 3);
        LinearLayout h = V.vbox(ctx);
        V.pad(h, 0, 4, 0, 10);
        h.addView(V.notice(ctx, "建一个 API，把接收地址给你做的答题网页、自评互评表或问卷，学生提交的数据就收进来。"
                + "名单里对得上的学生，数据会汇总进他的「学情」。", Tone.INFO), V.matchWrap());
        list.addHeader(h);
        list.setOnRefresh(this::load);
        list.setOnItemClick((a, pos) -> push(new ApiDetailScreen(Json.num(a, "id"), Json.str(a, "name"))));
        list.setEmpty("还没有 API", "点右下角新建一个，拿到接收地址", "新建 API", this::create);
        return list;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    @Override
    protected void onShow() {
        if (seen >= 0 && seen != version) load();
    }

    @Override
    public Action fab() {
        return Action.icon(R.drawable.ic_add, "新建 API", this::create);
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (session().isAdmin()) a.add(Action.icon(R.drawable.ic_filter_list, "按老师筛选", this::pickOwner));
        a.add(Action.icon(R.drawable.ic_refresh, "刷新", this::load));
        return a;
    }

    void load() {
        seen = version;
        list.loading();
        final Integer o = owner;
        run(() -> DataApiClient.list(o), r -> {
            List<JSONObject> items = Json.list(Json.arr(r, "items"));
            templates = Json.obj(r, "templates");
            teachers = Json.list(Json.arr(r, "teachers"));
            total = items.size();
            list.setItems(items);
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return true;
        });
    }

    private void pickOwner() {
        List<Option> opts = new ArrayList<>();
        opts.add(new Option(-1, "全部老师"));
        for (JSONObject t : teachers) opts.add(new Option(Json.num(t, "id"), Json.str(t, "name")));
        Dialogs.choose(ctx(), "看哪位老师的", opts, owner == null ? -1 : owner, o -> {
            int v = (Integer) o.value;
            owner = v < 0 ? null : v;
            load();
        });
    }

    private void create() {
        List<Option> opts = new ArrayList<>();
        List<String> keys = new ArrayList<>(Arrays.asList("answer", "self_eval", "peer_eval", "survey", "custom"));
        for (Iterator<String> it = templates.keys(); it.hasNext(); ) {
            String k = it.next();
            if (!keys.contains(k)) keys.add(k);
        }
        for (String k : keys) opts.add(new Option(k, Json.str(templates, k, ApiUi.templateName(k))));
        Dialogs.choose(ctx(), "这个 API 用来收什么", opts, "answer", t ->
                Dialogs.prompt(ctx(), "API 名称", "如：第3课 网页答题回收", "", 1, "下一步", name -> {
                    if (name.trim().isEmpty()) {
                        toast("请填 API 名称");
                        return;
                    }
                    Dialogs.prompt(ctx(), "描述（可不填）", "用在哪节课、哪个网页", "", 3, "建好", desc ->
                            runBusy("正在新建…", () -> DataApiClient.create(name.trim(), desc.trim(), String.valueOf(t.value)), a -> {
                                version++;
                                toast("建好了，在「接入」里复制 AI 提示词交给 AI 做网页");
                                push(new ApiDetailScreen(Json.num(a, "id"), Json.str(a, "name"), 3));
                            }));
                }));
    }
}
