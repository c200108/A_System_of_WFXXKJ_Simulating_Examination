package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.net.Uri;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.StyleSpan;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.GridBox;
import cn.wfxxkj.teacher.core.ui.MaxWidthLinearLayout;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 批量导入：选 Excel/CSV 上传 → 显示导入结果（成功、失败、重复、各题型数量、逐行错误）；
 * 下面是导入记录。宽屏时右边一栏放模板格式说明和「下载空白模板」，手机上排在最后。
 */
final class ImportScreen extends Screen {
    private LinearLayout resultBox;
    private LinearLayout logsBox;
    private boolean uploading;

    @Override
    public String title() {
        return "批量导入";
    }

    @Override
    protected View onCreateView(Context ctx) {
        LinearLayout page = V.page(ctx);
        if (wide()) {
            // 平板：左边上传和记录，右边模板说明，和网页 14:10 的分栏一致（两栏放宽到 1100dp）
            LinearLayout widePage = new MaxWidthLinearLayout(ctx, dp(1100));
            widePage.setOrientation(LinearLayout.VERTICAL);
            widePage.setPadding(page.getPaddingLeft(), page.getPaddingTop(), page.getPaddingRight(), page.getPaddingBottom());
            page = widePage;
            LinearLayout cols = V.hbox(ctx);
            cols.setGravity(Gravity.TOP);
            LinearLayout left = V.vbox(ctx);
            LinearLayout right = V.vbox(ctx);
            fillMain(ctx, left);
            fillTemplate(ctx, right);
            cols.addView(left, V.weight(14));
            cols.addView(V.space(ctx, 16));
            cols.addView(right, V.weight(10));
            page.addView(cols, V.matchWrap());
        } else {
            fillMain(ctx, page);
            fillTemplate(ctx, page);
        }
        ScrollView sv = V.scroll(ctx, page);
        sv.setBackgroundColor(Palette.of(ctx).page);
        return sv;
    }

    @Override
    protected void onFirstShow() {
        loadLogs();
    }

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        a.add(Action.icon(R.drawable.ic_download, "下载空白模板", this::downloadTemplate));
        a.add(Action.menu(R.drawable.ic_refresh, "刷新导入记录", this::loadLogs));
        return a;
    }

    // ---------- 上传 ----------

    private void fillMain(Context c, LinearLayout col) {
        Palette p = Palette.of(c);
        LinearLayout card = V.card(c);
        card.addView(V.text(c, "上传补充题库", V.H3));

        // 虚线框的「点我选文件」区域（手机上没有拖放，点一下打开文件选择）
        LinearLayout drop = V.vbox(c);
        drop.setGravity(Gravity.CENTER_HORIZONTAL);
        android.graphics.drawable.GradientDrawable bg = V.round(c, p.surfaceAlt, 14);
        bg.setStroke(Ui.dp(c, 1.5f), p.border, Ui.dp(c, 6), Ui.dp(c, 4));
        drop.setBackground(bg);
        V.pad(drop, 16, 24, 16, 22);
        drop.addView(V.iconTile(c, R.drawable.ic_upload_file, Tone.PRIMARY));
        TextView t = V.text(c, "点这里选择题库文件", V.BODY);
        t.setGravity(Gravity.CENTER);
        V.addTop(drop, t, 10);
        TextView h = V.text(c, "支持 .xlsx 和 .csv；Excel 的多张工作表会一起读取", V.CAPTION);
        h.setGravity(Gravity.CENTER);
        V.addTop(drop, h, 4);
        V.clickable(drop, 14, v -> pick());
        V.addTop(card, drop, 12);

        resultBox = V.vbox(c);
        card.addView(resultBox, V.matchWrap());
        col.addView(card, V.matchWrap());

        LinearLayout logs = V.card(c);
        logs.setPadding(0, Ui.dp(c, 12), 0, Ui.dp(c, 4));
        TextView lt = V.text(c, "导入记录", V.H3);
        V.pad(lt, 16, 0, 16, 4);
        logs.addView(lt);
        logsBox = V.vbox(c);
        logs.addView(logsBox, V.matchWrap());
        V.addTop(col, logs, 12);
    }

    private void pick() {
        if (uploading) return;
        pickFile(new String[]{Files.XLSX, Files.XLS, "text/csv", "text/comma-separated-values",
                "application/csv", "application/octet-stream"}, this::upload);
    }

    private void upload(final Uri file) {
        String name = Http.displayName(ctx().getContentResolver(), file).toLowerCase();
        if (!(name.endsWith(".xlsx") || name.endsWith(".xlsm") || name.endsWith(".csv"))) {
            toast("只支持 .xlsx 或 .csv 文件（.xls 请先在 WPS/Excel 里另存为 .xlsx）");
            return;
        }
        uploading = true;
        resultBox.removeAllViews();
        runBusy("正在导入…", () -> BankApi.importFile(file), r -> {
            uploading = false;
            showResult(r);
            toast("导入成功 " + r.optInt("success") + " 题");
            loadLogs();
        }, e -> {
            uploading = false;
            return false;
        });
    }

    private void showResult(JSONObject r) {
        Context c = ctx();
        resultBox.removeAllViews();
        int failed = r.optInt("failed");
        V.addTop(resultBox, V.notice(c, "扫描 " + r.optInt("total") + " 行：成功 " + r.optInt("success")
                + " 题，失败 " + failed + " 行，重复跳过 " + r.optInt("skipped") + " 行",
                failed > 0 ? Tone.WARNING : Tone.SUCCESS), 14);

        GridBox grid = new GridBox(c, 72, 4, 8);
        grid.addView(V.stat(c, String.valueOf(r.optInt("total")), "扫描行数", Tone.NEUTRAL));
        grid.addView(V.stat(c, String.valueOf(r.optInt("success")), "成功", Tone.SUCCESS));
        grid.addView(V.stat(c, String.valueOf(failed), "失败", failed > 0 ? Tone.DANGER : Tone.NEUTRAL));
        grid.addView(V.stat(c, String.valueOf(r.optInt("skipped")), "重复跳过", Tone.WARNING));
        V.addTop(resultBox, grid, 10);

        JSONObject byType = Json.obj(r, "by_type");
        if (byType.length() > 0) {
            FlowBox tags = new FlowBox(c, 6, 6);
            Iterator<String> it = byType.keys();
            while (it.hasNext()) {
                String k = it.next();
                tags.addView(V.tag(c, k + " " + byType.optInt(k), Tone.PRIMARY));
            }
            V.addTop(resultBox, tags, 10);
        }

        List<JSONObject> errors = Json.list(Json.arr(r, "errors"));
        if (!errors.isEmpty()) {
            V.addTop(resultBox, V.text(c, "逐行说明（" + errors.size() + " 条）", V.LABEL), 14);
            LinearLayout list = V.vbox(c);
            list.setBackground(V.stroke(c, Palette.of(c).surface, Palette.of(c).border, 12));
            int shown = 0;
            for (JSONObject e : errors) {
                if (shown > 0) list.addView(V.divider(c));
                LinearLayout row = V.hbox(c);
                row.setGravity(Gravity.TOP);
                V.pad(row, 12, 8, 12, 8);
                TextView where = V.text(c, Json.str(e, "sheet") + "\n第 " + Json.str(e, "row") + " 行", V.CAPTION);
                where.setMinWidth(Ui.dp(c, 84));
                row.addView(where);
                String reason = Json.str(e, "reason");
                TextView rt = V.text(c, reason, V.BODY2);
                if (!reason.contains("重复")) rt.setTextColor(Palette.of(c).danger);
                row.addView(rt, V.fill());
                list.addView(row);
                shown++;
            }
            V.addTop(resultBox, list, 6);
        }
        TextView go = V.button(c, "去题库查看新题", V.BTN_TONAL,
                v -> push(new QuestionListScreen()));
        V.addTop(resultBox, go, 12);
    }

    // ---------- 导入记录 ----------

    private void loadLogs() {
        run(BankApi::importLogs, this::renderLogs, e -> {
            logsBox.removeAllViews();
            TextView t = V.text(ctx(), "导入记录加载失败：" + e.getMessage(), V.CAPTION);
            V.pad(t, 16, 8, 16, 12);
            logsBox.addView(t);
            return true;
        });
    }

    private void renderLogs(List<JSONObject> logs) {
        Context c = ctx();
        logsBox.removeAllViews();
        if (logs.isEmpty()) {
            TextView t = V.text(c, "还没有导入过", V.BODY2);
            V.pad(t, 16, 8, 16, 12);
            logsBox.addView(t);
            return;
        }
        for (int i = 0; i < logs.size(); i++) {
            JSONObject l = logs.get(i);
            if (i > 0) logsBox.addView(V.margins(V.divider(c), 16, 0, 16, 0));
            LinearLayout row = V.hbox(c);
            V.pad(row, 16, 10, 16, 10);
            row.addView(V.iconTile(c, R.drawable.ic_table_view, l.optInt("failed") > 0 ? Tone.WARNING : Tone.SUCCESS));
            LinearLayout texts = V.vbox(c);
            texts.addView(V.oneLine(V.text(c, Json.str(l, "filename"), V.BODY)));
            texts.addView(V.oneLine(V.text(c, Fmt.dateTime(Json.str(l, "created_at")) + " · "
                    + Json.str(l, "operator"), V.CAPTION)));
            LinearLayout.LayoutParams lp = V.fill();
            lp.setMarginStart(Ui.dp(c, 12));
            row.addView(texts, lp);
            LinearLayout nums = V.vbox(c);
            nums.setGravity(Gravity.END);
            TextView ok = V.text(c, "成功 " + l.optInt("success"), V.LABEL);
            ok.setTextColor(Palette.of(c).success);
            nums.addView(ok);
            nums.addView(V.text(c, "失败 " + l.optInt("failed") + " · 重复 " + l.optInt("skipped"), V.CAPTION));
            V.addStart(row, nums, 8);
            logsBox.addView(row);
        }
    }

    // ---------- 模板说明 ----------

    private void fillTemplate(Context c, LinearLayout col) {
        LinearLayout card = V.card(c);
        LinearLayout head = V.hbox(c);
        head.addView(V.text(c, "模板格式", V.H3), V.fill());
        head.addView(V.button(c, R.drawable.ic_download, "下载空白模板", V.BTN_TONAL, v -> downloadTemplate()));
        card.addView(head, V.matchWrap());

        V.addTop(card, V.text(c, rich("表头顺序可以不同；**题型、题干、答案、知识范围** 必填，**图片** 和 **难度** 选填。"),
                V.BODY2), 10);

        // 两行示例（网页是一张小表格，手机上做成两张小卡片）
        V.addTop(card, sample(c, "选择题", "切换活动窗口的快捷键是（ ）。", "A.Alt+Tab\nB.Ctrl+C", "A",
                "Windows系统操作", "2"), 12);
        V.addTop(card, sample(c, "判断题", "计算机病毒可以自我复制。", "（留空）", "正确",
                "信息安全与网络道德", "（留空）"), 8);

        String[] rules = {
                "**可选项**：一行一个，写成 A.内容 的形式；判断题留空，系统自动补正确/错误。",
                "**答案**：选择题填 A/B/C/D；判断题填 正确/错误/√/×/对/错 都认。",
                "**知识范围**：只能填十类之一，写错会在导入结果里逐行提示。",
                "**图片**：填图片网址或已上传的 /uploads/... 路径。",
                "**难度**：只填数字 **1~5**（1 最容易，5 最难）。**留空不影响导入** —— 系统会按题型和题干长度自动估一个，"
                        + "之后随时能在题库里改。组卷时按它给每道题分配分值。",
                "题干重复的行会自动跳过，同一份文件重复上传不会产生重复题。",
                "**CSV** 也能传，表头和上面一样；WPS/Excel 存出来的 GBK 编码能自动识别。"};
        for (String r : rules) {
            LinearLayout row = V.hbox(c);
            row.setGravity(Gravity.TOP);
            TextView dot = V.text(c, "•", V.BODY2);
            row.addView(dot);
            TextView t = V.text(c, rich(r), V.BODY2);
            LinearLayout.LayoutParams lp = V.fill();
            lp.setMarginStart(Ui.dp(c, 8));
            row.addView(t, lp);
            V.addTop(card, row, 8);
        }
        V.addTop(col, card, 12);
    }

    private View sample(Context c, String type, String stem, String opts, String ans, String scope, String lv) {
        LinearLayout box = V.vbox(c);
        box.setBackground(V.round(c, Palette.of(c).surfaceAlt, 12));
        V.pad(box, 12, 10, 12, 10);
        box.addView(V.kv(c, "题型", type));
        box.addView(V.kv(c, "题干", stem));
        box.addView(V.kv(c, "可选项", opts));
        box.addView(V.kv(c, "答案", ans));
        box.addView(V.kv(c, "知识范围", scope));
        box.addView(V.kv(c, "难度", lv));
        return box;
    }

    /** 把 **粗体** 标记转成加粗 */
    private static CharSequence rich(String s) {
        SpannableStringBuilder sb = new SpannableStringBuilder();
        String[] parts = s.split("\\*\\*", -1);
        for (int i = 0; i < parts.length; i++) {
            int start = sb.length();
            sb.append(parts[i]);
            if (i % 2 == 1) {
                sb.setSpan(new StyleSpan(android.graphics.Typeface.BOLD), start, sb.length(),
                        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
        }
        return sb;
    }

    private void downloadTemplate() {
        Files.export(this, "正在下载模板…", BankApi::template, "题库导入模板.xlsx");
    }
}
