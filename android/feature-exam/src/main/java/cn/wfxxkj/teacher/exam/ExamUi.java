package cn.wfxxkj.teacher.exam;

import android.content.Context;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.FlowBox;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;
import cn.wfxxkj.teacher.core.util.Fmt;

/** 考试模块里几个页面共用的小块界面和判断 */
final class ExamUi {
    private ExamUi() {}

    /** 及格没有。卷面总分不一定是 100，按比例比（和网页 passed 一致） */
    static boolean passed(double score, double full) {
        if (full <= 0) full = 100;
        return score / full * 100 >= ExamApi.passScore;
    }

    /** 得分率（百分数）的颜色：及格线以上绿，以下红 */
    static int rateColor(Context c, Double rate) {
        Palette p = Palette.of(c);
        if (rate == null) return p.text3;
        return rate >= ExamApi.passScore ? p.success : p.danger;
    }

    static String pct(Double v) {
        return v == null ? "—" : Fmt.num(v) + "%";
    }

    /** 发给哪些班的说明 */
    static String targetsText(JSONObject exam) {
        String t = Json.str(exam, "target_classes");
        return t.isEmpty() ? "全体学生" : t.replace(",", "、");
    }

    /** 自动换行的一排小标签 */
    static FlowBox tags(Context c) {
        return new FlowBox(c, 6, 6);
    }

    static TextView tag(Context c, String s, Tone tone) {
        return V.tag(c, s, tone);
    }

    /** 「大数字 / 小字满分」的分数文字，例如 86 / 100 */
    static TextView score(Context c, double score, double full, int style) {
        TextView t = V.text(c, Fmt.num(score), style);
        if (full > 0) {
            android.text.SpannableStringBuilder sb = new android.text.SpannableStringBuilder(Fmt.num(score));
            int start = sb.length();
            sb.append(" / ").append(Fmt.num(full));
            sb.setSpan(new android.text.style.RelativeSizeSpan(0.62f), start, sb.length(), 0);
            sb.setSpan(new android.text.style.ForegroundColorSpan(Palette.of(c).text3), start, sb.length(), 0);
            t.setText(sb);
        }
        return t;
    }

    /** 卡片里的小节标题（卡片内用，比 V.section 紧凑） */
    static TextView cardTitle(Context c, String s) {
        TextView t = V.text(c, s, V.H3);
        V.pad(t, 0, 0, 0, 8);
        return t;
    }

    /** 竖排容器里加一个带上间距的子视图 */
    static <T extends View> T addTop(LinearLayout parent, T v, int dp) {
        return V.addTop(parent, v, dp);
    }

    /** 两个字段之间加点分隔：「八年级1班 · 2026001」 */
    static String dot(String... parts) {
        StringBuilder sb = new StringBuilder();
        for (String p : parts) {
            if (TextUtils.isEmpty(p)) continue;
            if (sb.length() > 0) sb.append(" · ");
            sb.append(p);
        }
        return sb.toString();
    }

    /** 统计小格：数字 + 说明，用于 GridBox */
    static LinearLayout stat(Context c, String number, String label, Tone tone) {
        return V.stat(c, number, label, tone);
    }

    static int dp(Context c, float v) {
        return Ui.dp(c, v);
    }
}
