package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.net.Uri;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Images;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 新增 / 编辑题目（独立的表单页，字段多，弹层放不下）。
 * 字段和后端 QuestionCreate 一致：题型、题干、选项、答案、知识范围、来源、难度、必出、
 * 仿真任务（只有操作题）、配图。保存成功后把保存后的题目带回给打开者。
 */
final class QuestionEditScreen extends Screen {
    private final JSONObject orig;
    private BankApi.Dicts dicts;
    private List<JSONObject> sims = new ArrayList<>();

    private LinearLayout root;
    private Form form;
    private Form.Choice type;
    private Form.Toggle pinned;
    private Form.Text stem;
    private OptionsEditor options;
    private AnswerChips choiceAnswer;
    private Form.Choice judgeAnswer;
    private Form.Text textAnswer;
    private Form.Select scope;
    private Form.Text source;
    private Form.Select level;
    private Form.Select sim;
    private String imageUrl = "";
    private ImageView imageView;
    private TextView imageHint;
    private View imageRemove;
    private String initial;

    /** q 为 null 表示新增 */
    QuestionEditScreen(JSONObject q) {
        this.orig = q;
    }

    @Override
    public String title() {
        return orig == null ? "新增题目" : "编辑题目";
    }

    @Override
    public String subtitle() {
        return orig == null ? null : Json.str(orig, "code");
    }

    @Override
    protected View onCreateView(Context ctx) {
        root = V.vbox(ctx);
        root.setBackgroundColor(Palette.of(ctx).page);
        root.addView(new StateView(ctx).loading(), V.matchWrap());
        return root;
    }

    @Override
    protected void onFirstShow() {
        run(() -> {
            BankApi.Dicts d = BankApi.dicts();
            List<JSONObject> s;
            try {
                s = BankApi.sims(null);
            } catch (Exception e) {
                s = new ArrayList<>(); // 拿不到不影响出题，只是仿真任务下拉是空的
            }
            return new Object[]{d, s};
        }, r -> {
            dicts = (BankApi.Dicts) r[0];
            @SuppressWarnings("unchecked") List<JSONObject> s = (List<JSONObject>) r[1];
            sims = s;
            build();
        }, e -> {
            root.removeAllViews();
            root.addView(new StateView(ctx()).error(e.getMessage(), this::onFirstShow), V.matchWrap());
            return true;
        });
    }

    @Override
    public List<Action> actions() {
        if (form == null) return new ArrayList<>();
        return Arrays.asList(Action.icon(R.drawable.ic_check, "保存", this::save));
    }

    @Override
    public boolean onBack() {
        if (form != null && initial != null && !initial.equals(payload().toString())) {
            Dialogs.confirm(ctx(), "放弃修改？", "改动还没保存，退出后就没了。", "放弃", true, this::finish);
            return true;
        }
        return false;
    }

    // ---------- 建表单 ----------

    private void build() {
        Context c = ctx();
        root.removeAllViews();
        LinearLayout page = V.page(c);
        ScrollView sv = V.scroll(c, page);
        root.addView(sv, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));

        JSONObject q = orig != null ? orig : new JSONObject();
        String qType = orig != null ? Json.str(q, "type") : (dicts.types.contains("选择题") ? "选择题"
                : (dicts.types.isEmpty() ? "" : dicts.types.get(0)));
        List<String> types = new ArrayList<>(dicts.types);
        if (!qType.isEmpty() && !types.contains(qType)) types.add(qType);

        form = new Form(c);
        type = form.choice("题型", Option.of(types.toArray(new String[0])), qType).required();
        type.onChange(this::onTypeChanged);
        pinned = form.toggle("设为必出题", "组卷时一定会抽到这道题", Json.bool(q, "is_pinned"));
        stem = form.area("题干", Json.str(q, "stem"), 4).required();

        // 选项（选择题）
        List<String[]> opts = new ArrayList<>();
        for (JSONObject o : Json.list(Json.arr(q, "options"))) {
            opts.add(new String[]{Json.str(o, "label"), Json.str(o, "content")});
        }
        if (opts.isEmpty() || !"选择题".equals(qType)) {
            opts.clear();
            for (String l : new String[]{"A", "B", "C", "D"}) opts.add(new String[]{l, ""});
        }
        options = form.custom(new OptionsEditor(c, opts, this::onOptionsChanged));

        // 答案：按题型三选一
        String ans = Json.str(q, "answer");
        choiceAnswer = new AnswerChips(c, ans);
        form.custom(choiceAnswer);
        judgeAnswer = form.choice("答案", Option.of("正确", "错误"), normalizeJudge(ans));
        textAnswer = form.area("答案", ans, 2);

        List<Option> scopeOpts = new ArrayList<>();
        for (String s : dicts.scopes) scopeOpts.add(new Option(s, s));
        String qScope = Json.str(q, "scope");
        if (!qScope.isEmpty() && !dicts.scopes.contains(qScope)) scopeOpts.add(new Option(qScope, qScope));
        scope = form.select("知识范围", scopeOpts, qScope.isEmpty() ? null : qScope).required();

        List<Option> lv = new ArrayList<>();
        lv.add(new Option(0, "自动判断"));
        lv.addAll(Bank.levelOptions());
        level = form.select("难度", lv, orig == null ? 0 : q.optInt("difficulty", 3));
        level.help("只用数字 1~5。选「自动判断」就按题型和题干长度估一个，之后随时能改。组卷时按它分配分值。");
        form.row(scope, level);

        source = form.text("来源", orig == null ? "自定义" : Json.str(q, "source"), "如：自定义、原卷");

        List<Option> simOpts = new ArrayList<>();
        simOpts.add(new Option(0L, "不挂（老师人工评阅）"));
        for (JSONObject s : sims) {
            simOpts.add(new Option(s.optLong("id"), Bank.kindName(Json.str(s, "kind")) + " · " + Json.str(s, "title"),
                    Json.list(Json.arr(s, "checks")).size() + " 条检查点"));
        }
        long simId = Json.isNull(q, "sim_task_id") ? 0L : q.optLong("sim_task_id");
        if (simId != 0 && !hasOption(simOpts, simId)) {
            JSONObject st = q.optJSONObject("sim_task");
            simOpts.add(new Option(simId, st == null ? "仿真任务 #" + simId
                    : Bank.kindName(Json.str(st, "kind")) + " · " + Json.str(st, "title")));
        }
        sim = form.select("仿真任务", simOpts, simId);
        sim.help("挂上之后，学生在网页里把操作真做一遍，交卷按检查点自动判分，分数预填到成绩页、老师能改。"
                + "去「题库 → 仿真操作题」里建。");

        // 配图
        imageUrl = Json.str(q, "image_url");
        form.custom(imageBlock(c));

        page.addView(form.view());
        LinearLayout btns = V.hbox(c);
        btns.addView(V.button(c, "取消", V.BTN_OUTLINE, v -> {
            if (!onBack()) finish();
        }), V.weight(1));
        btns.addView(V.space(c, 12));
        btns.addView(V.button(c, "保存", V.BTN_PRIMARY, v -> save()), V.weight(1));
        V.addTop(page, btns, 8);

        onTypeChanged();
        initial = payload().toString();
        invalidateChrome();
    }

    private static boolean hasOption(List<Option> opts, long v) {
        for (Option o : opts) if (Option.same(o.value, v)) return true;
        return false;
    }

    private static String normalizeJudge(String a) {
        String s = a == null ? "" : a.trim();
        if (s.equals("正确") || s.equals("对") || s.equals("√") || s.equalsIgnoreCase("A")) return "正确";
        if (s.equals("错误") || s.equals("错") || s.equals("×") || s.equalsIgnoreCase("B")) return "错误";
        return null;
    }

    private void onTypeChanged() {
        String t = type.string();
        boolean choice = "选择题".equals(t);
        boolean judge = "判断题".equals(t);
        options.setVisibility(choice ? View.VISIBLE : View.GONE);
        choiceAnswer.setVisibility(choice ? View.VISIBLE : View.GONE);
        judgeAnswer.setVisible(judge);
        textAnswer.setVisible(!choice && !judge);
        sim.setVisible("操作题".equals(t));
        if (choice) onOptionsChanged();
    }

    private void onOptionsChanged() {
        choiceAnswer.setLabels(options.labels());
    }

    // ---------- 配图 ----------

    private View imageBlock(Context c) {
        LinearLayout box = V.vbox(c);
        box.addView(V.pad(V.text(c, "配图", V.LABEL), 2, 0, 0, 6));
        LinearLayout row = V.hbox(c);
        row.setGravity(android.view.Gravity.TOP);
        imageView = new ImageView(c);
        imageView.setScaleType(ImageView.ScaleType.CENTER_CROP);
        imageView.setBackground(V.round(c, Palette.of(c).surfaceAlt, 12));
        imageView.setClipToOutline(true);
        int s = Ui.dp(c, 96);
        row.addView(imageView, new LinearLayout.LayoutParams(s, s));
        V.clickable(imageView, 12, v -> {
            if (!imageUrl.isEmpty()) Bank.showImage(c, imageUrl);
            else pickImage();
        });
        LinearLayout side = V.vbox(c);
        side.addView(V.button(c, R.drawable.ic_image, "上传图片", V.BTN_TONAL, v -> pickImage()));
        imageRemove = V.button(c, "移除配图", V.BTN_TEXT, v -> {
            imageUrl = "";
            renderImage();
        });
        V.addTop(side, imageRemove, 4);
        imageHint = V.text(c, "", V.CAPTION);
        V.addTop(side, imageHint, 4);
        LinearLayout.LayoutParams lp = V.fill();
        lp.setMarginStart(Ui.dp(c, 14));
        row.addView(side, lp);
        box.addView(row, V.matchWrap());
        renderImage();
        return box;
    }

    private void renderImage() {
        boolean has = !imageUrl.isEmpty();
        if (has) {
            Images.load(imageView, imageUrl, Ui.dp(ctx(), 192));
            imageView.setImageTintList(null);
            imageView.setScaleType(ImageView.ScaleType.CENTER_CROP);
        } else {
            imageView.setImageResource(R.drawable.ic_image);
            imageView.setImageTintList(android.content.res.ColorStateList.valueOf(Palette.of(ctx()).text3));
            imageView.setScaleType(ImageView.ScaleType.CENTER);
        }
        imageRemove.setVisibility(has ? View.VISIBLE : View.GONE);
        imageHint.setText(has ? "点图片看大图" : "支持 png / jpg / gif / webp");
    }

    private void pickImage() {
        pickFile(new String[]{"image/*"}, (Uri uri) -> runBusy("正在上传图片…", () -> BankApi.uploadImage(uri), url -> {
            imageUrl = url;
            renderImage();
            toast("图片已上传");
        }));
    }

    // ---------- 保存 ----------

    private JSONObject payload() {
        String t = type.string();
        JSONArray opts = new JSONArray();
        String answer;
        if ("选择题".equals(t)) {
            for (String[] o : options.values()) {
                if (!o[1].trim().isEmpty()) opts.put(Json.of("label", o[0], "content", o[1].trim()));
            }
            answer = choiceAnswer.value();
        } else if ("判断题".equals(t)) {
            opts.put(Json.of("label", "A", "content", "正确"));
            opts.put(Json.of("label", "B", "content", "错误"));
            answer = judgeAnswer.string();
        } else {
            answer = textAnswer.value();
        }
        int lv = level.value() instanceof Number ? ((Number) level.value()).intValue() : 0;
        long simId = "操作题".equals(t) && sim.value() instanceof Number ? ((Number) sim.value()).longValue() : 0;
        JSONObject p = Json.of(
                "type", t,
                "stem", stem.value(),
                "answer", answer,
                "scope", scope.string(),
                "source", source.value().isEmpty() ? "自定义" : source.value(),
                "image_url", imageUrl.isEmpty() ? null : imageUrl,
                "is_pinned", pinned.value(),
                "sim_task_id", simId == 0 ? null : simId,
                "options", opts);
        // 「自动判断」：新增时传 null 由后端估；编辑时不传，保留原来的
        if (lv > 0) Json.put(p, "difficulty", lv);
        else if (orig == null) Json.put(p, "difficulty", null);
        return p;
    }

    private void save() {
        if (form == null || !form.validate()) return;
        String t = type.string();
        if ("选择题".equals(t)) {
            int filled = 0;
            for (String[] o : options.values()) if (!o[1].trim().isEmpty()) filled++;
            if (filled < 2) {
                toast("选择题至少要填两个选项");
                return;
            }
            if (choiceAnswer.value().isEmpty()) {
                toast("请选出正确答案");
                return;
            }
            for (char ch : choiceAnswer.value().toCharArray()) {
                if (options.contentOf(String.valueOf(ch)).isEmpty()) {
                    toast("答案 " + ch + " 那一项还没填内容");
                    return;
                }
            }
        }
        final JSONObject body = payload();
        final long id = orig == null ? 0 : orig.optLong("id");
        runBusy("正在保存…", () -> id == 0 ? BankApi.create(body) : BankApi.update(id, body), saved -> {
            toast("已保存");
            initial = null;
            finish(saved);
        });
    }
}
