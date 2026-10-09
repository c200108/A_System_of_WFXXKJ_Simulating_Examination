package cn.wfxxkj.teacher;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.nav.TabSpec;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 导航：手机上是底部标签栏，宽屏是左侧竖排导航栏。
 * 选中项的图标换成实心、垫一个浅色圆角底。
 */
class NavBar extends LinearLayout {

    interface OnTab {
        void tab(String key);
    }

    private final List<TabSpec> tabs;
    private final List<ImageView> icons = new ArrayList<>();
    private final List<TextView> labels = new ArrayList<>();
    private final List<View> pills = new ArrayList<>();

    NavBar(Context c, List<TabSpec> tabs, boolean rail, OnTab onTab) {
        super(c);
        this.tabs = tabs;
        Palette p = Palette.of(c);
        setOrientation(rail ? VERTICAL : HORIZONTAL);
        setBackgroundColor(p.surface);
        if (rail) {
            setGravity(Gravity.CENTER_HORIZONTAL);
            ImageView logo = new ImageView(c);
            logo.setImageResource(R.drawable.logo_tile);
            LayoutParams llp = new LayoutParams(Ui.dp(c, 44), Ui.dp(c, 44));
            llp.topMargin = Ui.dp(c, 12);
            llp.bottomMargin = Ui.dp(c, 20);
            addView(logo, llp);
        } else {
            setElevation(Ui.dpf(c, 8));
        }
        for (final TabSpec t : tabs) {
            LinearLayout item = V.vbox(c);
            item.setGravity(Gravity.CENTER);
            FrameLayout iconBox = new FrameLayout(c);
            View pill = new View(c);
            pill.setBackground(V.round(c, p.primarySoft, 16));
            iconBox.addView(pill, new FrameLayout.LayoutParams(Ui.dp(c, 56), Ui.dp(c, 32), Gravity.CENTER));
            ImageView iv = new ImageView(c);
            iv.setImageResource(t.icon);
            iconBox.addView(iv, new FrameLayout.LayoutParams(Ui.dp(c, 24), Ui.dp(c, 24), Gravity.CENTER));
            item.addView(iconBox, new LayoutParams(Ui.dp(c, 64), Ui.dp(c, 32)));
            TextView label = new TextView(c);
            label.setText(t.title);
            label.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
            label.setGravity(Gravity.CENTER);
            LayoutParams tlp = new LayoutParams(V.WRAP, V.WRAP);
            tlp.topMargin = Ui.dp(c, 4);
            item.addView(label, tlp);
            V.pad(item, 0, rail ? 6 : 10, 0, rail ? 10 : 8);
            item.setContentDescription(t.title);
            item.setOnClickListener(v -> onTab.tab(t.key));
            item.setBackground(new android.graphics.drawable.RippleDrawable(
                    ColorStateList.valueOf(p.ripple), null, null));
            if (rail) addView(item, new LayoutParams(V.MATCH, V.WRAP));
            else addView(item, new LayoutParams(0, V.WRAP, 1f));
            icons.add(iv);
            labels.add(label);
            pills.add(pill);
        }
    }

    void select(String key) {
        Palette p = Palette.of(getContext());
        for (int i = 0; i < tabs.size(); i++) {
            boolean on = tabs.get(i).key.equals(key);
            icons.get(i).setImageResource(on ? tabs.get(i).iconSelected : tabs.get(i).icon);
            icons.get(i).setImageTintList(ColorStateList.valueOf(on ? p.primary : p.text2));
            labels.get(i).setTextColor(on ? p.primary : p.text2);
            labels.get(i).setTypeface(on ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
            pills.get(i).setVisibility(on ? VISIBLE : INVISIBLE);
        }
    }
}
