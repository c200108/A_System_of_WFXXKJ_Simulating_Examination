package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.Editable;
import android.text.Html;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 提交反馈：称呼、联系方式（不公开）、类型、内容（可插表情），最多配 3 张图
 * （本机相册上传，或粘贴网络图片地址）。提交后需管理员审核才公开。
 * 关闭时带回 true 表示已提交。
 */
public class FeedbackComposeScreen extends Screen {
    private static final int MAX_IMAGES = 3;

    private Form form;
    private Form.Text author, contact, content;
    private Form.Choice category;
    private final List<String> images = new ArrayList<>();
    private FlowBox shots;
    private TextView localBtn, urlBtn;

    @Override
    public String title() {
        return "提交反馈";
    }

    @Override
    protected View onCreateView(Context c) {
        LinearLayout page = V.page(c);
        LinearLayout card = V.card(c);
        form = new Form(c);
        // 上次填过的称呼、联系方式记在本机；老师默认填自己的名字
        String savedA = session().prefs().ui("feedback.author", "");
        String savedC = session().prefs().ui("feedback.contact", "");
        author = form.text("您的称呼", savedA.isEmpty() ? session().displayName() : savedA).maxLength(64).required();
        contact = form.text("联系方式", savedC, "选填，不公开，只有管理员看得到").maxLength(64);
        form.row(author, contact);
        List<Option> cats = new ArrayList<>();
        for (String s : FeedbackScreen.CATEGORIES) cats.add(new Option(s, s));
        category = form.choice("类型", cats, "建议");
        content = form.area("内容", "", 5).maxLength(2000).required();
        content.hint("具体说说：想在哪个页面、做什么事、现在卡在哪里");
        content.rule(v -> v.length() < 5 ? "说得再具体一点吧，至少 5 个字" : null);
        content.help("0 / 2000");
        content.edit.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int a, int b, int d) {}

            @Override
            public void onTextChanged(CharSequence s, int a, int b, int d) {}

            @Override
            public void afterTextChanged(Editable s) {
                content.help(s.length() + " / 2000");
            }
        });
        card.addView(form.view());

        // 工具条：表情、本地图片、网络图片
        FlowBox tools = new FlowBox(c, 8, 8);
        tools.addView(V.button(c, "😀 表情", V.BTN_TONAL, v -> FeedbackSheets.emoji(c, content.edit)));
        localBtn = V.button(c, R.drawable.ic_image, "本地图片", V.BTN_TONAL, v -> pickLocal());
        tools.addView(localBtn);
        urlBtn = V.button(c, R.drawable.ic_link, "网络图片", V.BTN_TONAL, v -> addUrl());
        tools.addView(urlBtn);
        card.addView(tools);

        shots = new FlowBox(c, 10, 10);
        V.addTop(card, shots, 12);

        TextView tip = V.text(c, Html.fromHtml("最多 " + MAX_IMAGES + " 张图（png/jpg/gif/webp，5 MB 以内）。"
                + "提交后<b>需管理员审核</b>才会公开展示，联系方式不公开。", Html.FROM_HTML_MODE_LEGACY), V.CAPTION);
        V.addTop(card, tip, 12);
        page.addView(card, V.matchWrap());

        TextView submit = V.button(c, "提交反馈", V.BTN_PRIMARY, v -> submit());
        V.addTop(page, submit, 16);

        renderShots();
        ScrollView sv = V.scroll(c, page);
        sv.setBackgroundColor(Palette.of(c).page);
        return sv;
    }

    @Override
    public List<Action> actions() {
        return Collections.singletonList(Action.icon(R.drawable.ic_check, "提交", this::submit));
    }

    // ---------- 配图 ----------

    private void renderShots() {
        Context c = ctx();
        shots.removeAllViews();
        shots.setVisibility(images.isEmpty() ? View.GONE : View.VISIBLE);
        for (int i = 0; i < images.size(); i++) {
            final int idx = i;
            final String url = images.get(i);
            FrameLayout f = new FrameLayout(c);
            View th = FeedbackCard.thumb(c, url, 88, 88, v -> FeedbackSheets.preview(c, url));
            f.addView(th, new FrameLayout.LayoutParams(Ui.dp(c, 88), Ui.dp(c, 88)));
            ImageView x = V.icon(c, R.drawable.ic_close, 0xFFFFFFFF, 16);
            x.setScaleType(ImageView.ScaleType.CENTER);
            x.setBackground(V.round(c, 0x8C000000, 12));
            x.setContentDescription("移除");
            x.setOnClickListener(v -> {
                images.remove(idx);
                renderShots();
            });
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(Ui.dp(c, 24), Ui.dp(c, 24), Gravity.TOP | Gravity.END);
            lp.topMargin = Ui.dp(c, 4);
            lp.setMarginEnd(Ui.dp(c, 4));
            f.addView(x, lp);
            shots.addView(f);
        }
        boolean full = images.size() >= MAX_IMAGES;
        V.enable(localBtn, !full);
        V.enable(urlBtn, !full);
    }

    private void pickLocal() {
        if (images.size() >= MAX_IMAGES) {
            toast("最多配 " + MAX_IMAGES + " 张图");
            return;
        }
        pickFile(new String[]{"image/png", "image/jpeg", "image/gif", "image/webp"}, uri ->
                runBusy("正在上传图片…", () -> MeApi.feedbackUploadImage(uri), url -> {
                    images.add(url);
                    renderShots();
                    toast("图片已上传");
                }));
    }

    private void addUrl() {
        MeUi.prompt(ctx(), "添加网络图片", null, "粘贴图片网址，https:// 开头", "", "添加", false, text -> {
            String url = text.trim();
            if (url.isEmpty()) return "请粘贴图片网址";
            String low = url.toLowerCase();
            if (!low.startsWith("http://") && !low.startsWith("https://")) {
                return "网络图片要用 http:// 或 https:// 开头的完整地址";
            }
            if (images.size() >= MAX_IMAGES) return "最多配 " + MAX_IMAGES + " 张图";
            images.add(url);
            renderShots();
            return null;
        });
    }

    // ---------- 提交 ----------

    private void submit() {
        if (!form.validate()) return;
        final String a = author.value(), ct = contact.value(), cat = category.string(), body = content.value();
        final List<String> imgs = new ArrayList<>(images);
        runBusy("正在提交…", () -> MeApi.feedbackCreate(a, ct, cat, body, imgs), r -> {
            session().prefs().setUi("feedback.author", a);
            session().prefs().setUi("feedback.contact", ct);
            finish(Boolean.TRUE);
        });
    }
}
