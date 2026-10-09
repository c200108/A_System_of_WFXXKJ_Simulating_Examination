package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.Html;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tabs;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 需求反馈（网页 Feedback.vue）。
 *
 * <p>先审后发：提交完是「待审核」，管理员审过才出现在公开区。老师能回复、点赞、撤回自己的回复；
 * 管理员多出「待审核」「已拒绝」两栏（看联系方式、通过/拒绝/批量审核/删除），公开区还能撤下、删除。
 */
public class FeedbackScreen extends Screen implements FeedbackCard.Handler {

    static final String[] CATEGORIES = {"建议", "问题", "表扬", "其他"};

    private Tabs tabs;
    private ItemList<JSONObject> publicList, pendingList, rejectedList;
    private ChipRow filter;
    private TextView countText;
    private TextView pendingTag;
    private int tab;
    private int pending;
    private int selCount = -1;
    private boolean loadedOnce;

    @Override
    public String title() {
        return selCount >= 0 ? "已选 " + selCount + " 条" : "需求反馈";
    }

    @Override
    public String subtitle() {
        if (selCount >= 0) return "批量审核";
        return pending > 0 ? pending + " 条待审核" : null;
    }

    @Override
    public boolean isAdmin() {
        return session().isAdmin();
    }

    @Override
    protected View onCreateView(Context c) {
        LinearLayout root = V.vbox(c);
        root.setBackgroundColor(Palette.of(c).page);
        if (isAdmin()) {
            tabs = new Tabs(c);
            tabs.add("大家的反馈").add("待审核").add("已拒绝");
            root.addView(tabs, V.matchWrap());
        }
        FrameLayout box = new FrameLayout(c);
        root.addView(box, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));

        publicList = newList(c, FeedbackCard.PUBLIC);
        publicList.addHeader(publicHeader(c));
        publicList.setEmpty("还没有反馈", "还没有人提过，来做第一个吧", "提交反馈", this::compose);
        box.addView(publicList);

        if (isAdmin()) {
            pendingList = newList(c, FeedbackCard.PENDING);
            pendingList.addHeader(wrapNotice(c, "只有管理员看得到这一栏：提交的反馈要你审过才公开。"
                    + "长按卡片可多选，批量通过或拒绝。", Tone.WARNING));
            pendingList.setEmpty("没有待审核的反馈", null);
            pendingList.enableSelection(f -> f.optLong("id"), n -> {
                selCount = n;
                invalidateChrome();
            });
            box.addView(pendingList);

            rejectedList = newList(c, FeedbackCard.REJECTED);
            rejectedList.addHeader(wrapNotice(c, "拒绝的反馈不会出现在公开区，内容仍然保留在这里，可以改为通过。",
                    Tone.NEUTRAL));
            rejectedList.setEmpty("没有拒绝过任何反馈", null);
            box.addView(rejectedList);

            tabs.setOnSelected(i -> {
                if (pendingList.isSelecting()) pendingList.stopSelection();
                tab = i;
                publicList.setVisibility(i == 0 ? View.VISIBLE : View.GONE);
                pendingList.setVisibility(i == 1 ? View.VISIBLE : View.GONE);
                rejectedList.setVisibility(i == 2 ? View.VISIBLE : View.GONE);
                invalidateChrome();
            });
            tabs.select(0);
        }
        return root;
    }

    private ItemList<JSONObject> newList(Context c, final int mode) {
        ItemList<JSONObject> l = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new FeedbackCard(ctx, FeedbackScreen.this);
            }

            @Override
            public void bind(View v, JSONObject f, int pos) {
                ((FeedbackCard) v).bind(f, mode);
            }
        });
        // 反馈是一段段文字，宽屏两列就够了
        l.setCell(420, 2);
        l.setOnRefresh(this::load);
        return l;
    }

    private View wrapNotice(Context c, String text, Tone tone) {
        LinearLayout w = V.vbox(c);
        V.pad(w, 0, 4, 0, 8);
        w.addView(V.notice(c, text, tone));
        return w;
    }

    private View publicHeader(Context c) {
        LinearLayout head = V.vbox(c);
        V.pad(head, 0, 4, 0, 4);
        head.addView(V.notice(c, Html.fromHtml("用着不顺手、想要什么新功能，都可以说。提交后<b>需管理员审核</b>"
                + "才会公开展示，联系方式不公开。", Html.FROM_HTML_MODE_LEGACY), Tone.INFO));
        filter = new ChipRow(c);
        List<Option> opts = new ArrayList<>();
        opts.add(new Option("", "全部类型"));
        for (String s : CATEGORIES) opts.add(new Option(s, s));
        filter.setOptions(opts, session().prefs().ui("feedback.category", ""));
        filter.setOnPicked(o -> {
            session().prefs().setUi("feedback.category", String.valueOf(o.value));
            publicList.loading();
            load();
        });
        V.addTop(head, filter, 8);
        LinearLayout line = V.hbox(c);
        V.pad(line, 2, 10, 0, 0);
        countText = V.text(c, "大家的反馈", V.H3);
        line.addView(countText);
        pendingTag = V.tag(c, "", Tone.WARNING);
        pendingTag.setVisibility(View.GONE);
        V.addStart(line, pendingTag, 10);
        head.addView(line);
        return head;
    }

    // ---------- 加载 ----------

    @Override
    protected void onFirstShow() {
        publicList.loading();
        if (pendingList != null) {
            pendingList.loading();
            rejectedList.loading();
        }
        load();
    }

    void load() {
        final String cat = String.valueOf(filter.value() == null ? "" : filter.value());
        final boolean admin = isAdmin();
        run(() -> {
            Object[] r = new Object[3];
            r[0] = MeApi.feedbackList(cat);
            if (admin) r[1] = MeApi.feedbackAll();
            r[2] = MeApi.feedbackPending();
            return r;
        }, r -> {
            loadedOnce = true;
            @SuppressWarnings("unchecked") List<JSONObject> pub = (List<JSONObject>) r[0];
            publicList.setItems(pub);
            countText.setText("大家的反馈  " + pub.size());
            pending = (Integer) r[2];
            pendingTag.setText(pending + " 条待审核");
            pendingTag.setVisibility(pending > 0 ? View.VISIBLE : View.GONE);
            if (admin && r[1] != null) {
                @SuppressWarnings("unchecked") List<JSONObject> all = (List<JSONObject>) r[1];
                List<JSONObject> pend = new ArrayList<>(), rej = new ArrayList<>();
                for (JSONObject f : all) {
                    String st = Json.str(f, "status");
                    if ("pending".equals(st)) pend.add(f);
                    else if ("rejected".equals(st)) rej.add(f);
                }
                pendingList.setItems(pend);
                rejectedList.setItems(rej);
                tabs.setTitle(1, pend.isEmpty() ? "待审核" : "待审核 " + pend.size());
                tabs.setTitle(2, rej.isEmpty() ? "已拒绝" : "已拒绝 " + rej.size());
            }
            invalidateChrome();
        }, e -> {
            publicList.error(e.getMessage(), this::load);
            if (pendingList != null) {
                pendingList.error(e.getMessage(), this::load);
                rejectedList.error(e.getMessage(), this::load);
            }
            return false;
        });
    }

    // ---------- 顶栏 ----------

    @Override
    public List<Action> actions() {
        if (selCount >= 0) {
            return Arrays.asList(
                    Action.icon(R.drawable.ic_select_all, "全选", () -> pendingList.selectAll()),
                    Action.icon(R.drawable.ic_done_all, "批量通过", () -> reviewPicked("approved")),
                    Action.menu(R.drawable.ic_block, "批量拒绝", () -> reviewPicked("rejected")),
                    Action.menu(R.drawable.ic_close, "取消选择", () -> pendingList.stopSelection()));
        }
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_refresh, "刷新", () -> {
            currentList().loading();
            load();
        }));
        if (tab == 1 && pendingList != null) {
            a.add(Action.menu(R.drawable.ic_select_all, "多选审核", () -> pendingList.startSelection()));
        }
        return a;
    }

    private ItemList<JSONObject> currentList() {
        return tab == 1 ? pendingList : tab == 2 ? rejectedList : publicList;
    }

    @Override
    public Action fab() {
        if (selCount >= 0) return null;
        return Action.icon(R.drawable.ic_rate_review, "提交反馈", this::compose);
    }

    @Override
    public boolean onBack() {
        if (pendingList != null && pendingList.isSelecting()) {
            pendingList.stopSelection();
            return true;
        }
        return false;
    }

    @Override
    protected void onShow() {
        if (loadedOnce) load();
    }

    private void compose() {
        push(new FeedbackComposeScreen(), r -> {
            if (r == null) return;
            Dialogs.alert(ctx(), "提交成功",
                    "已提交，感谢反馈。\n\n内容要管理员审核通过后才会出现在评论区，请稍等。");
        });
    }

    // ---------- 卡片上的操作 ----------

    @Override
    public boolean canWithdraw(JSONObject reply) {
        // 能撤回的只有自己写的；管理员谁的都能撤
        return isAdmin() || Json.str(reply, "author").equals(session().displayName());
    }

    @Override
    public void like(JSONObject f) {
        final long id = f.optLong("id");
        run(() -> MeApi.feedbackLike(id), res -> {
            // 就地更新，不整页刷新，点起来跟手
            Json.put(f, "like_count", res.optInt("like_count"));
            Json.put(f, "liked_by_me", res.optBoolean("liked_by_me"));
            publicList.refreshViews();
        });
    }

    @Override
    public void reply(JSONObject f) {
        final long id = f.optLong("id");
        FeedbackSheets.reply(ctx(), Json.str(f, "author"), (text, sheet) ->
                runBusy("正在发布…", () -> MeApi.feedbackReply(id, text), res -> {
                    sheet.dismiss();
                    toast("已回复");
                    load();
                }));
    }

    @Override
    public void withdraw(JSONObject f, JSONObject reply) {
        final long rid = reply.optLong("id");
        Dialogs.confirm(ctx(), "撤回回复", "撤回这条回复？\n\n" + Json.str(reply, "content"), "撤回", true,
                () -> runBusy("正在撤回…", () -> {
                    MeApi.feedbackReplyDelete(rid);
                    return true;
                }, ok -> {
                    toast("已撤回");
                    load();
                }));
    }

    @Override
    public void more(JSONObject f) {
        Dialogs.actions(ctx(), Json.str(f, "author") + " 的反馈", Arrays.asList(
                Action.menu(R.drawable.ic_visibility_off, "撤下（改为已拒绝）", () -> review(f, "rejected")),
                Action.menu(R.drawable.ic_restart_alt, "退回待审核", () -> review(f, "pending")),
                Action.menu(R.drawable.ic_delete, "删除", () -> delete(f)).danger()));
    }

    @Override
    public void review(JSONObject f, String status) {
        final long id = f.optLong("id");
        if ("rejected".equals(status)) {
            MeUi.prompt(ctx(), "拒绝这条反馈", "拒绝后这条不会出现在公开区，内容仍然保留在管理端。\n可以写个原因，只有管理员看得到：",
                    "比如：内容不实 / 与平台无关", "", "确认拒绝", true, text -> {
                        doReview(id, status, text.trim());
                        return null;
                    });
        } else {
            doReview(id, status, "");
        }
    }

    private void doReview(long id, String status, String note) {
        runBusy("正在处理…", () -> {
            MeApi.feedbackReview(id, status, note);
            return true;
        }, ok -> {
            toast("approved".equals(status) ? "已通过，评论区可见了" : "rejected".equals(status) ? "已拒绝" : "已退回待审");
            load();
        });
    }

    private void reviewPicked(String status) {
        final List<Object> ids = pendingList.selectedKeys();
        if (ids.isEmpty()) {
            toast("先勾选要审的条目");
            return;
        }
        Runnable go = () -> runBusy("正在处理…", () -> MeApi.feedbackReviewBulk(ids, status), res -> {
            pendingList.stopSelection();
            toast("已" + ("approved".equals(status) ? "通过" : "拒绝") + " " + res.optInt("affected") + " 条");
            load();
        });
        if ("rejected".equals(status)) {
            Dialogs.confirm(ctx(), "批量拒绝", "拒绝选中的 " + ids.size() + " 条反馈？它们不会出现在公开区。",
                    "拒绝", true, go);
        } else {
            go.run();
        }
    }

    @Override
    public void delete(JSONObject f) {
        final long id = f.optLong("id");
        Dialogs.confirm(ctx(), "删除反馈", "彻底删除这条反馈？连同下面的回复一起删掉，不可恢复。", "删除", true,
                () -> runBusy("正在删除…", () -> {
                    MeApi.feedbackDelete(id);
                    return true;
                }, ok -> {
                    toast("已删除");
                    load();
                }));
    }

    @Override
    public void preview(String url) {
        FeedbackSheets.preview(ctx(), url);
    }
}
