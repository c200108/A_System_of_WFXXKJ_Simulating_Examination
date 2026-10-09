package cn.wfxxkj.teacher.exam;

import android.content.Context;
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
import cn.wfxxkj.teacher.core.io.Printer;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 样卷（网页「样卷」对话框）：这场考试的完整试卷，带答案，老师讲评用。
 * 按大题分组，顶上一排大题标签点一下跳过去。
 */
final class SamplePaperScreen extends Screen {

    private final long examId;
    private JSONObject paper;
    private ScrollView scroll;
    private LinearLayout page;
    private final List<View> groupViews = new ArrayList<>();

    SamplePaperScreen(long examId) {
        this.examId = examId;
    }

    @Override
    public String title() {
        return "样卷";
    }

    @Override
    public String subtitle() {
        return paper == null ? null : Json.str(paper, "title");
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (paper != null) {
            a.add(Action.icon(R.drawable.ic_print, "打印 / 存 PDF",
                    () -> Printer.print(activity(), page, "样卷-" + Json.str(paper, "title"))));
        }
        return a;
    }

    @Override
    protected View onCreateView(Context c) {
        page = V.page(c);
        scroll = V.scroll(c, page);
        StateView state = new StateView(c);
        page.addView(state, V.matchWrap());
        return scroll;
    }

    @Override
    protected void onFirstShow() {
        run(() -> ExamApi.paper(examId), p -> {
            paper = p;
            invalidateChrome();
            render();
        }, e -> {
            ((StateView) page.getChildAt(0)).error(e.getMessage(), this::onFirstShow);
            return true;
        });
    }

    private void render() {
        Context c = ctx();
        Palette pal = Palette.of(c);
        page.removeAllViews();
        groupViews.clear();

        LinearLayout head = V.card(c);
        head.addView(V.text(c, Json.str(paper, "paper_title"), V.H2));
        FlowBox info = ExamUi.tags(c);
        if (!Json.str(paper, "school").isEmpty()) info.addView(ExamUi.tag(c, Json.str(paper, "school"), Tone.NEUTRAL));
        if (!Json.str(paper, "duration").isEmpty()) {
            info.addView(ExamUi.tag(c, "考试时长 " + Json.str(paper, "duration") + " 分钟", Tone.INFO));
        }
        info.addView(ExamUi.tag(c, "满分 " + Json.num(paper, "full_score"), Tone.PRIMARY));
        V.addTop(head, info, 8);
        page.addView(head, V.matchWrap());

        List<JSONObject> groups = Json.list(Json.arr(paper, "groups"));
        if (groups.size() > 1) {
            ChipRow jump = new ChipRow(c);
            List<Option> opts = new ArrayList<>();
            for (int i = 0; i < groups.size(); i++) opts.add(new Option(i, Json.str(groups.get(i), "name")));
            jump.setOptions(opts, null);
            jump.setOnPicked(o -> {
                View g = groupViews.get(((Number) o.value).intValue());
                scroll.smoothScrollTo(0, g.getTop() - Ui.dp(c, 8));
            });
            V.addTop(page, jump, 10);
        }

        for (JSONObject g : groups) {
            List<JSONObject> items = Json.list(Json.arr(g, "items"));
            LinearLayout sec = V.hbox(c);
            sec.addView(V.text(c, Json.str(g, "name"), V.H2));
            V.addStart(sec, V.text(c, "共 " + items.size() + " 题，" + Json.num(g, "score") + " 分", V.CAPTION), 8);
            V.pad(sec, 4, 0, 0, 0);
            V.addTop(page, sec, 20);
            groupViews.add(sec);
            for (JSONObject q : items) V.addTop(page, question(c, pal, q), 10);
        }
    }

    private View question(Context c, Palette pal, JSONObject q) {
        LinearLayout card = V.card(c);
        FlowBox tags = ExamUi.tags(c);
        tags.addView(ExamUi.tag(c, "第 " + Json.num(q, "no") + " 题", Tone.NEUTRAL));
        tags.addView(ExamUi.tag(c, Json.str(q, "type"), Tone.PRIMARY));
        if (Json.num(q, "score") > 0) tags.addView(ExamUi.tag(c, Json.num(q, "score") + " 分", Tone.NEUTRAL));
        if (!Json.str(q, "scope").isEmpty()) tags.addView(ExamUi.tag(c, Json.str(q, "scope"), Tone.INFO));
        card.addView(tags);

        TextView stem = V.text(c, Json.str(q, "stem"), V.BODY);
        stem.setTextIsSelectable(true);
        V.addTop(card, stem, 8);

        String img = Json.str(q, "image_url");
        if (!img.isEmpty()) {
            ImageView iv = new ImageView(c);
            iv.setAdjustViewBounds(true);
            iv.setMaxHeight(Ui.dp(c, 240));
            iv.setScaleType(ImageView.ScaleType.FIT_START);
            Images.load(iv, img, Ui.dp(c, 600));
            V.addTop(card, iv, 8);
        }

        String answer = Json.str(q, "answer");
        List<JSONObject> opts = Json.list(Json.arr(q, "options"));
        if (!opts.isEmpty()) {
            LinearLayout ol = V.vbox(c);
            for (JSONObject o : opts) {
                String label = Json.str(o, "label");
                TextView t = V.text(c, label + ". " + Json.str(o, "content"), V.BODY2);
                if (!label.isEmpty() && answer.contains(label)) {
                    t.setTextColor(pal.success);
                    V.bold(t);
                }
                V.pad(t, 0, 2, 0, 2);
                ol.addView(t);
            }
            V.addTop(card, ol, 6);
        }
        if (!answer.isEmpty()) {
            TextView a = V.text(c, "参考答案：" + answer, V.BODY2);
            a.setTextColor(pal.success);
            a.setTextIsSelectable(true);
            a.setBackground(V.round(c, pal.successSoft, 10));
            V.pad(a, 12, 8, 12, 8);
            V.addTop(card, a, 8);
        }
        List<String> checks = Json.strings(Json.arr(q, "checks"));
        if (!checks.isEmpty()) {
            LinearLayout cl = V.vbox(c);
            for (int i = 0; i < checks.size(); i++) {
                TextView t = V.text(c, "判分点 " + (i + 1) + "：" + checks.get(i), V.CAPTION);
                V.pad(t, 0, 2, 0, 2);
                cl.addView(t);
            }
            V.addTop(card, cl, 6);
        }
        return card;
    }
}
