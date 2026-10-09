package cn.wfxxkj.teacher;

import android.content.Context;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.Menu;
import android.view.MenuItem;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 顶栏：返回箭头、标题（副标题）、右侧操作图标、「更多」菜单。
 * 图标位不够时（手机上最多 2 个，宽屏 4 个）多出来的自动收进「更多」。
 */
class AppBar extends LinearLayout {
    private final ImageView back;
    private final TextView title;
    private final TextView subtitle;
    private final LinearLayout actions;
    private int topInset;

    AppBar(Context c) {
        super(c);
        setOrientation(HORIZONTAL);
        setGravity(Gravity.CENTER_VERTICAL);
        Palette p = Palette.of(c);
        setBackgroundColor(p.surface);
        setMinimumHeight(Ui.dp(c, 56));
        back = V.iconButton(c, R.drawable.ic_arrow_back, "返回", null);
        back.setImageTintList(android.content.res.ColorStateList.valueOf(p.text));
        addView(back);
        LinearLayout texts = V.vbox(c);
        title = V.oneLine(V.text(c, "", V.H2));
        subtitle = V.oneLine(V.text(c, "", V.CAPTION));
        texts.addView(title);
        texts.addView(subtitle);
        LayoutParams tlp = new LayoutParams(0, V.WRAP, 1f);
        addView(texts, tlp);
        actions = V.hbox(c);
        addView(actions);
        // 底部一条细线和内容区分开
        setDividerDrawable(null);
    }

    void setInsets(int top, int left, int right) {
        topInset = top;
        setPadding(left + Ui.dp(getContext(), 4), top, right + Ui.dp(getContext(), 4), 0);
        setMinimumHeight(Ui.dp(getContext(), 56) + top);
    }

    void render(String titleText, String sub, Runnable onBack, List<Action> list) {
        Context c = getContext();
        title.setText(titleText);
        subtitle.setText(sub == null ? "" : sub);
        subtitle.setVisibility(TextUtils.isEmpty(sub) ? GONE : VISIBLE);
        if (onBack != null) {
            back.setVisibility(VISIBLE);
            back.setOnClickListener(v -> onBack.run());
            title.setPadding(0, 0, 0, 0);
        } else {
            back.setVisibility(GONE);
        }
        View texts = (View) title.getParent();
        texts.setPadding(onBack != null ? 0 : Ui.dp(c, 12), 0, 0, 0);

        actions.removeAllViews();
        int maxIcons = Ui.wide(c) ? 4 : 2;
        List<Action> shown = new ArrayList<>();
        final List<Action> overflow = new ArrayList<>();
        for (Action a : list) {
            if (!a.overflow && a.icon != 0 && shown.size() < maxIcons) shown.add(a);
            else overflow.add(a);
        }
        Palette p = Palette.of(c);
        for (Action a : shown) {
            FrameLayout box = new FrameLayout(c);
            ImageView iv = V.iconButton(c, a.icon, a.label, a.listener());
            iv.setImageTintList(android.content.res.ColorStateList.valueOf(p.text));
            iv.setAlpha(a.enabled ? 1f : 0.35f);
            iv.setOnLongClickListener(v -> {
                android.widget.Toast.makeText(c, a.label, android.widget.Toast.LENGTH_SHORT).show();
                return true;
            });
            box.addView(iv);
            if (a.badge > 0) {
                TextView b = V.badge(c, a.badge);
                FrameLayout.LayoutParams blp = new FrameLayout.LayoutParams(V.WRAP, V.WRAP, Gravity.TOP | Gravity.END);
                blp.topMargin = Ui.dp(c, 4);
                box.addView(b, blp);
            }
            actions.addView(box);
        }
        if (!overflow.isEmpty()) {
            final ImageView more = V.iconButton(c, R.drawable.ic_more_vert, "更多", null);
            more.setImageTintList(android.content.res.ColorStateList.valueOf(p.text));
            more.setOnClickListener(v -> {
                PopupMenu pm = new PopupMenu(c, more, Gravity.END);
                Menu m = pm.getMenu();
                for (int i = 0; i < overflow.size(); i++) {
                    Action a = overflow.get(i);
                    MenuItem item = m.add(0, i, i, a.danger
                            ? colored(a.label, p.danger) : a.label);
                    item.setEnabled(a.enabled);
                }
                pm.setOnMenuItemClickListener(item -> {
                    Action a = overflow.get(item.getItemId());
                    if (a.run != null) a.run.run();
                    return true;
                });
                pm.show();
            });
            actions.addView(more);
        }
    }

    private static CharSequence colored(String s, int color) {
        android.text.SpannableString sp = new android.text.SpannableString(s);
        sp.setSpan(new android.text.style.ForegroundColorSpan(color), 0, s.length(), 0);
        return sp;
    }

    int topInset() {
        return topInset;
    }
}
