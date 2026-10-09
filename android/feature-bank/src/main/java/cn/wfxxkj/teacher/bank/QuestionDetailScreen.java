package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Images;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 一道题的详情：题干、配图（点开看大图）、选项（标出正确答案）、答案、知识范围、难度、
 * 挂着的仿真任务。顶栏：编辑、「⋮」里设必出 / 复制题干 / 删除。
 * 改过或删过之后返回列表时带回结果，列表据此刷新。
 */
final class QuestionDetailScreen extends Screen {
    private JSONObject q;
    private LinearLayout page;
    private boolean changed;

    QuestionDetailScreen(JSONObject q) {
        this.q = q;
    }

    @Override
    public String title() {
        return "题目详情";
    }

    @Override
    public String subtitle() {
        String code = Json.str(q, "code");
        return code.isEmpty() ? null : code;
    }

    @Override
    protected View onCreateView(Context ctx) {
        page = V.page(ctx);
        ScrollView sv = V.scroll(ctx, page);
        sv.setBackgroundColor(Palette.of(ctx).page);
        render();
        return sv;
    }

    @Override
    protected void onFirstShow() {
        // 列表里的数据可能是旧的，拉一次最新的
        run(() -> BankApi.question(q.optLong("id")), fresh -> {
            q = fresh;
            render();
            invalidateChrome();
        });
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_edit, "编辑", this::edit));
        boolean pinned = Json.bool(q, "is_pinned");
        a.add(Action.menu(R.drawable.ic_star, pinned ? "取消必出" : "设为必出", this::togglePin));
        a.add(Action.menu(R.drawable.ic_content_copy, "复制题干", () -> {
            Sys.copy(ctx(), "题干", Json.str(q, "stem"));
            toast("题干已复制");
        }));
        a.add(Action.menu(R.drawable.ic_delete, "删除", this::delete).danger());
        return a;
    }

    @Override
    public boolean onBack() {
        if (changed) {
            changed = false;
            finish(Boolean.TRUE);
            return true;
        }
        return false;
    }

    // ---------- 界面 ----------

    private void render() {
        Context c = ctx();
        Palette p = Palette.of(c);
        page.removeAllViews();
        String type = Json.str(q, "type");

        // 题干卡
        LinearLayout card = V.card(c);
        FlowBox tags = new FlowBox(c, 6, 6);
        tags.addView(V.tag(c, type, Bank.typeTone(type)));
        tags.addView(V.tag(c, Json.str(q, "scope"), Tone.NEUTRAL));
        int lv = q.optInt("difficulty", 3);
        tags.addView(V.tag(c, "难度 " + lv + " · " + Bank.LEVEL_TEXT[Math.max(1, Math.min(5, lv))], Bank.levelTone(lv)));
        if (Json.bool(q, "is_pinned")) tags.addView(V.tag(c, "必出", Tone.WARNING));
        card.addView(tags, V.matchWrap());

        TextView stem = V.text(c, Json.str(q, "stem"), V.BODY);
        stem.setTextSize(17);
        stem.setTextIsSelectable(true);
        V.addTop(card, stem, 12);

        final String img = Json.str(q, "image_url");
        if (!img.isEmpty()) {
            ImageView iv = new ImageView(c);
            iv.setAdjustViewBounds(true);
            iv.setScaleType(ImageView.ScaleType.FIT_START);
            iv.setMaxHeight(Ui.dp(c, 280));
            iv.setBackground(V.round(c, p.surfaceAlt, 12));
            iv.setClipToOutline(true);
            iv.setMinimumHeight(Ui.dp(c, 80));
            Images.load(iv, img, Ui.dp(c, 640));
            V.clickable(iv, 12, v -> Bank.showImage(c, img));
            V.addTop(card, iv, 12);
            V.addTop(card, V.text(c, "点图片看大图", V.CAPTION), 4);
        }

        // 选项
        String answer = Json.str(q, "answer").trim();
        List<JSONObject> opts = Json.list(Json.arr(q, "options"));
        if ("判断题".equals(type) && opts.isEmpty()) {
            opts.add(Json.of("label", "A", "content", "正确"));
            opts.add(Json.of("label", "B", "content", "错误"));
        }
        if (!opts.isEmpty()) {
            LinearLayout box = V.vbox(c);
            for (JSONObject o : opts) {
                String label = Json.str(o, "label");
                String content = Json.str(o, "content");
                boolean right = isRight(type, answer, label, content);
                V.addTop(box, optionRow(c, label, content, right), 8);
            }
            V.addTop(card, box, 6);
        }
        page.addView(card, V.matchWrap());

        // 答案
        LinearLayout ans = V.card(c);
        ans.addView(V.text(c, "答案", V.LABEL));
        TextView at = V.text(c, answer.isEmpty() ? "（没有填写答案）" : answer, V.BODY);
        if (answer.isEmpty()) at.setTextColor(p.text3);
        else {
            at.setTextColor(p.success);
            V.bold(at);
        }
        at.setTextIsSelectable(true);
        V.addTop(ans, at, 6);
        V.addTop(page, ans, 12);

        // 仿真任务
        final JSONObject sim = q.optJSONObject("sim_task");
        if ("操作题".equals(type) || sim != null) {
            LinearLayout sc = V.card(c);
            sc.setPadding(0, 0, 0, 0);
            if (sim != null) {
                sc.addView(V.row(c, R.drawable.ic_computer, Bank.kindTone(Json.str(sim, "kind")),
                        Bank.kindName(Json.str(sim, "kind")) + " · " + Json.str(sim, "title"),
                        "挂着仿真任务：学生在网页里真做一遍，交卷按检查点自动判分", null,
                        v -> push(new SimDetailScreen(sim.optLong("id")))));
            } else {
                sc.addView(V.row(c, R.drawable.ic_computer, Tone.NEUTRAL, "没有挂仿真任务",
                        "老师人工评阅。编辑题目可以挂上「仿真操作题」里建好的任务", null, null));
            }
            V.addTop(page, sc, 12);
        }

        // 其它信息
        LinearLayout info = V.card(c);
        info.addView(V.kv(c, "编号", Json.str(q, "code")));
        info.addView(V.kv(c, "题型", type));
        info.addView(V.kv(c, "知识范围", Json.str(q, "scope")));
        info.addView(V.kv(c, "难度", lv + " 级（" + Bank.LEVEL_TEXT[Math.max(1, Math.min(5, lv))] + "）"));
        info.addView(V.kv(c, "来源", Json.str(q, "source")));
        info.addView(V.kv(c, "必出题", Json.bool(q, "is_pinned") ? "是（组卷时一定抽到）" : "否"));
        info.addView(V.kv(c, "配图", img.isEmpty() ? "无" : "有"));
        info.addView(V.kv(c, "创建时间", Fmt.dateTime(Json.str(q, "created_at"))));
        V.addTop(page, info, 12);

        // 底部按钮
        LinearLayout btns = V.hbox(c);
        btns.addView(V.button(c, R.drawable.ic_edit, "编辑", V.BTN_PRIMARY, v -> edit()), V.weight(1));
        btns.addView(V.space(c, 12));
        boolean pinned = Json.bool(q, "is_pinned");
        btns.addView(V.button(c, R.drawable.ic_star, pinned ? "取消必出" : "设为必出", V.BTN_TONAL,
                v -> togglePin()), V.weight(1));
        btns.addView(V.space(c, 12));
        btns.addView(V.button(c, R.drawable.ic_delete, "删除", V.BTN_DANGER_TONAL, v -> delete()), V.weight(1));
        V.addTop(page, btns, 16);
    }

    /** 选择题答案是字母（可能多个，如 AB），判断题答案是 正确/错误/√/× 等 */
    static boolean isRight(String type, String answer, String label, String content) {
        if (answer.isEmpty()) return false;
        if ("判断题".equals(type)) {
            boolean yes = "正确".equals(content);
            String a = answer.replace(" ", "");
            boolean ansYes = a.equals("正确") || a.equals("对") || a.equals("√") || a.equalsIgnoreCase("A")
                    || a.equalsIgnoreCase("T") || a.equalsIgnoreCase("true");
            boolean ansNo = a.equals("错误") || a.equals("错") || a.equals("×") || a.equalsIgnoreCase("B")
                    || a.equalsIgnoreCase("F") || a.equalsIgnoreCase("false");
            return yes ? ansYes : ansNo;
        }
        return !TextUtils.isEmpty(label) && answer.toUpperCase().contains(label.toUpperCase());
    }

    static View optionRow(Context c, String label, String content, boolean right) {
        Palette p = Palette.of(c);
        LinearLayout row = V.hbox(c);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setBackground(right ? V.stroke(c, p.successSoft, p.success, 12) : V.stroke(c, p.surface, p.border, 12));
        V.pad(row, 10, 10, 12, 10);
        TextView l = V.text(c, label, V.LABEL);
        l.setGravity(Gravity.CENTER);
        l.setTextColor(right ? 0xFFFFFFFF : p.text2);
        l.setBackground(V.round(c, right ? p.success : p.surfaceAlt, 13));
        int s = Ui.dp(c, 26);
        row.addView(l, new LinearLayout.LayoutParams(s, s));
        TextView t = V.text(c, content, V.BODY);
        t.setTextIsSelectable(true);
        LinearLayout.LayoutParams lp = V.fill();
        lp.setMarginStart(Ui.dp(c, 10));
        row.addView(t, lp);
        if (right) {
            row.addView(V.icon(c, R.drawable.ic_check_circle, p.success, 20));
        }
        return row;
    }

    // ---------- 操作 ----------

    private void edit() {
        push(new QuestionEditScreen(q), r -> {
            if (r instanceof JSONObject) {
                q = (JSONObject) r;
                changed = true;
                render();
                invalidateChrome();
            }
        });
    }

    private void togglePin() {
        final boolean to = !Json.bool(q, "is_pinned");
        run(() -> BankApi.update(q.optLong("id"), Json.of("is_pinned", to)), saved -> {
            q = saved;
            changed = true;
            render();
            invalidateChrome();
            toast(to ? "已设为必出题" : "已取消必出");
        });
    }

    private void delete() {
        if (!Bank.canDelete(ctx())) return;
        Dialogs.confirm(ctx(), "删除这道题？", "删除后可以在数据库里恢复，确定删除？", "删除", true, () -> {
            final long id = q.optLong("id");
            runBusy("正在删除…", () -> {
                BankApi.delete(id);
                return true;
            }, ok -> finish(id));
        });
    }
}
