package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 每个页面顶上的置顶提醒（网页 FeedbackNews.vue，服务端 2.24.0）：管理员在「需求反馈」里置顶的反馈，最多 5 条。
 *
 * <p>主界面把它放在顶栏下面，切页面时顺手刷新（最多一分钟一次）；管理员在 APP 里置顶 / 取消置顶后马上刷新。
 * 点 × 关掉的只是这一条（记在本机）；同一条取消后再置顶，id 变了会重新提醒。点内容进「需求反馈」。
 * 老服务器没有这个接口、没网：不显示就是了。
 */
public final class PinnedNews extends LinearLayout {
    private static final String PREFS = "feedback-pins";
    private static final String KEY = "closed";

    /** 上一次拿到的置顶（主界面转屏重建时先拿它画，不闪） */
    private static List<JSONObject> cache = new ArrayList<>();
    private static long lastLoad;
    private static final List<WeakReference<PinnedNews>> live = new ArrayList<>();

    private final Runnable openFeedback;

    public PinnedNews(Context c, Runnable openFeedback) {
        super(c);
        this.openFeedback = openFeedback;
        setOrientation(VERTICAL);
        V.pad(this, 12, 0, 12, 0);
        live.add(new WeakReference<>(this));
        render();
        load();
    }

    /** 切页面时调：离上次超过一分钟才重新问 */
    public void maybeRefresh() {
        if (System.currentTimeMillis() - lastLoad > 60000) load();
    }

    /** 管理员置顶 / 取消置顶后：所有黄条马上跟着变 */
    static void changed() {
        lastLoad = 0;
        for (WeakReference<PinnedNews> r : live) {
            PinnedNews p = r.get();
            if (p != null && p.isAttachedToWindow()) {
                p.load();
                return;
            }
        }
    }

    private void load() {
        lastLoad = System.currentTimeMillis();
        Screen.io().execute(() -> {
            List<JSONObject> got;
            try {
                got = Json.list(Json.arr(Http.getObj("/feedback/news", null), "items"));
            } catch (Throwable e) {
                return;
            }
            final List<JSONObject> items = got;
            Screen.main().post(() -> {
                cache = items;
                for (WeakReference<PinnedNews> r : new ArrayList<>(live)) {
                    PinnedNews p = r.get();
                    if (p == null) live.remove(r);
                    else p.render();
                }
            });
        });
    }

    private Set<String> closed() {
        SharedPreferences sp = getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        return new HashSet<>(sp.getStringSet(KEY, new HashSet<>()));
    }

    private void close(JSONObject n) {
        Set<String> s = closed();
        s.add(Json.str(n, "id"));
        // 只留还在置顶的那几条，不然越存越多
        Set<String> keep = new HashSet<>();
        for (JSONObject x : cache) if (s.contains(Json.str(x, "id"))) keep.add(Json.str(x, "id"));
        getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putStringSet(KEY, keep).apply();
        render();
    }

    private void render() {
        removeAllViews();
        Context c = getContext();
        Palette p = Palette.of(c);
        Set<String> shut = closed();
        int n = 0;
        for (final JSONObject item : cache) {
            if (shut.contains(Json.str(item, "id"))) continue;
            LinearLayout row = V.hbox(c);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setBackground(V.stroke(c, p.warningSoft, p.warning, 10));
            V.pad(row, 10, 6, 2, 6);

            TextView tag = V.text(c, "置顶", V.CAPTION);
            tag.setTextColor(0xFFFFFFFF);
            tag.setTypeface(Typeface.DEFAULT_BOLD);
            tag.setBackground(V.round(c, p.warning, 4));
            V.pad(tag, 6, 1, 6, 1);
            row.addView(tag);

            SpannableStringBuilder sb = new SpannableStringBuilder();
            int s0 = sb.length();
            sb.append(Json.str(item, "author"));
            sb.setSpan(new StyleSpan(Typeface.BOLD), s0, sb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            s0 = sb.length();
            sb.append("【").append(Json.str(item, "category")).append("】");
            sb.setSpan(new ForegroundColorSpan(p.text2), s0, sb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            sb.append(Json.str(item, "text"));
            JSONObject last = item.optJSONObject("last_reply");
            if (last != null) {
                sb.append(" · ").append(Json.str(last, "author")).append(Json.bool(last, "is_admin") ? "（管理员）" : "")
                        .append("回复：").append(Json.str(last, "text"));
            }
            String until = MeUi.time(Json.str(item, "pinned_until"));
            if (!TextUtils.isEmpty(until)) {
                s0 = sb.length();
                sb.append("  置顶到 ").append(until.substring(5));
                sb.setSpan(new ForegroundColorSpan(p.text3), s0, sb.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            }
            TextView body = V.text(c, sb, V.BODY2);
            body.setTextColor(p.text);
            V.lines(body, 2);
            V.pad(body, 8, 0, 4, 0);
            row.addView(body, V.fill());
            V.clickable(row, 10, v -> {
                if (openFeedback != null) openFeedback.run();
            });
            row.addView(V.iconButton(c, R.drawable.ic_close, "关掉这条提醒", v -> close(item)));

            LinearLayout.LayoutParams lp = V.matchWrap();
            lp.topMargin = Ui.dp(c, n == 0 ? 8 : 6);
            addView(row, lp);
            if (++n >= 5) break;
        }
        setVisibility(n == 0 ? GONE : VISIBLE);
    }
}
