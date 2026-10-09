package cn.wfxxkj.teacher.core.nav;

import android.content.Context;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.ui.Tabs;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 工作台：顶部一排分页标签，下面是当前分页的页面。底部标签栏的「题库」「考试」「学生」用它，
 * 和网页版把几块功能收在一个工作台里的做法一致。
 *
 * <p>分页按需创建（点到才建），切走时保留状态。顶栏按钮、浮动按钮跟着当前分页走。
 * 上次停在哪个分页会记住。
 */
public class HubScreen extends Screen {

    /** 分页定义 */
    public interface Page {
        String title();

        Screen create();
    }

    public static Page page(final String title, final java.util.concurrent.Callable<Screen> factory) {
        return new Page() {
            @Override
            public String title() {
                return title;
            }

            @Override
            public Screen create() {
                try {
                    return factory.call();
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }
        };
    }

    private final String title;
    private final String key;
    private final List<Page> pages;
    private final Screen[] screens;
    private FrameLayout container;
    private Tabs tabs;
    private int current = -1;
    private boolean skipShow;

    /** key 用来记住上次停在哪个分页 */
    public HubScreen(String title, String key, List<Page> pages) {
        this.title = title;
        this.key = key;
        this.pages = new ArrayList<>(pages);
        this.screens = new Screen[pages.size()];
    }

    @Override
    public String title() {
        return title;
    }

    @Override
    protected View onCreateView(Context ctx) {
        LinearLayout root = V.vbox(ctx);
        tabs = new Tabs(ctx);
        for (Page p : pages) tabs.add(p.title());
        if (pages.size() > 1) root.addView(tabs, V.matchWrap());
        container = new FrameLayout(ctx);
        root.addView(container, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));
        tabs.setOnSelected(this::show);
        return root;
    }

    @Override
    protected void onFirstShow() {
        int start = 0;
        try {
            start = Integer.parseInt(Session.get().prefs().ui("hub." + key, "0"));
        } catch (NumberFormatException ignored) {
            // 用第一页
        }
        if (start < 0 || start >= pages.size()) start = 0;
        skipShow = true; // 紧接着的 onShow 不用再通知一遍分页
        tabs.select(start);
    }

    /** 外部跳到某个分页（例如从别处带参数打开） */
    public void select(int index) {
        if (tabs != null) tabs.select(index);
    }

    public Screen currentScreen() {
        return current < 0 ? null : screens[current];
    }

    private void show(int index) {
        if (current >= 0 && screens[current] != null) {
            screens[current].view().setVisibility(View.GONE);
            screens[current].dispatchHide();
        }
        current = index;
        Session.get().prefs().setUi("hub." + key, String.valueOf(index));
        Screen s = screens[index];
        if (s == null) {
            s = pages.get(index).create();
            s.setParent(this);
            screens[index] = s;
            View v = s.attach(host(), ctx());
            container.addView(v, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        }
        s.view().setVisibility(View.VISIBLE);
        s.dispatchShow();
        invalidateChrome();
    }

    @Override
    protected void onShow() {
        // 从别的页面返回：当前分页也算重新显示
        if (skipShow) {
            skipShow = false;
            return;
        }
        if (current >= 0 && screens[current] != null && screens[current].view() != null) {
            screens[current].dispatchShow();
        }
    }

    @Override
    protected void onHide() {
        Screen s = currentScreen();
        if (s != null) s.dispatchHide();
    }

    @Override
    protected void onDestroy() {
        for (Screen s : screens) if (s != null) s.dispatchDestroy();
    }

    @Override
    public String subtitle() {
        Screen s = currentScreen();
        return s == null ? null : s.subtitle();
    }

    @Override
    public List<Action> actions() {
        Screen s = currentScreen();
        return s == null ? super.actions() : s.actions();
    }

    @Override
    public Action fab() {
        Screen s = currentScreen();
        return s == null ? null : s.fab();
    }

    @Override
    public boolean onBack() {
        Screen s = currentScreen();
        return s != null && s.onBack();
    }
}
