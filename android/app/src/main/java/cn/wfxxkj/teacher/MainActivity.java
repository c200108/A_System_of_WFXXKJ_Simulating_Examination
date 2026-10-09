package cn.wfxxkj.teacher;

import android.app.Activity;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.content.res.Configuration;
import android.net.Uri;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Host;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.nav.TabSpec;
import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.session.SessionKeeper;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Themes;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 主界面：装所有页面的容器。
 *
 * <ul>
 *   <li>手机竖屏：顶栏 + 内容 + 底部五个标签；</li>
 *   <li>宽屏（≥600dp：大屏手机横屏、折叠屏、平板）：左侧导航栏 + 顶栏 + 内容；</li>
 *   <li>每个标签各自一个页面栈，切标签不丢进度；再点一次当前标签回到它的首页；</li>
 *   <li>转屏、分屏改变大小时不重建页面，只把外框换成适合新宽度的样子。</li>
 * </ul>
 */
public class MainActivity extends Activity implements Host, Session.Listener {
    private static final int REQ_PICK = 41;

    private List<TabSpec> tabs;
    private final Map<String, ArrayList<Screen>> stacks = new HashMap<>();
    private String current;

    private FrameLayout root;
    private FrameLayout content;
    private AppBar appBar;
    private NavBar navBar;
    private TextView offline;
    private ImageView fab;
    private TextView snackBar;
    private FrameLayout busy;
    private TextView busyText;
    private SessionKeeper keeper;
    private Host.FilesPicked pendingPick;
    private int[] insets = {0, 0, 0, 0};
    private long lastBack;

    @Override
    protected void attachBaseContext(Context base) {
        super.attachBaseContext(Themes.wrap(base));
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Session.init(this);
        if (!Session.get().loggedIn()) {
            toLogin(null);
            return;
        }
        Ui.edgeToEdge(this);
        tabs = Features.tabs();
        keeper = new SessionKeeper(this);
        Session.get().addListener(this);
        buildShell();
        switchTab(tabs.get(0).key);
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (keeper != null) keeper.start();
    }

    @Override
    protected void onStop() {
        if (keeper != null) keeper.stop();
        super.onStop();
    }

    @Override
    protected void onDestroy() {
        Session.get().removeListener(this);
        if (keeper != null) keeper.shutdown();
        for (List<Screen> st : stacks.values()) for (Screen s : st) s.dispatchDestroy();
        super.onDestroy();
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        // 宽窄变了：外框在底部标签栏和左侧导航栏之间切换，页面本身原样保留
        if (root != null) {
            View page = top().view();
            if (page != null && page.getParent() != null) ((ViewGroup) page.getParent()).removeView(page);
            buildShell();
            showTop(false);
        }
    }

    // ---------- 外框 ----------

    private void buildShell() {
        Palette p = Palette.of(this);
        boolean wide = Ui.wide(this);
        root = new FrameLayout(this);
        root.setBackgroundColor(p.page);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        navBar = new NavBar(this, tabs, wide, this::onTabClicked);
        if (wide) row.addView(navBar, new LinearLayout.LayoutParams(Ui.dp(this, 88), V.MATCH));

        LinearLayout col = V.vbox(this);
        appBar = new AppBar(this);
        col.addView(appBar, V.matchWrap());
        offline = V.text(this, "", V.BODY2);
        offline.setTextColor(p.warning);
        offline.setBackgroundColor(p.warningSoft);
        offline.setGravity(Gravity.CENTER);
        V.pad(offline, 16, 8, 16, 8);
        offline.setVisibility(Session.get().isOnline() ? View.GONE : View.VISIBLE);
        offline.setOnClickListener(v -> keeper.kick());
        col.addView(offline, V.matchWrap());
        content = new FrameLayout(this);
        col.addView(content, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));
        if (!wide) col.addView(navBar, V.matchWrap());
        row.addView(col, new LinearLayout.LayoutParams(0, V.MATCH, 1f));
        root.addView(row, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));

        // 浮动按钮
        fab = new ImageView(this);
        fab.setScaleType(ImageView.ScaleType.CENTER);
        fab.setImageTintList(ColorStateList.valueOf(p.onPrimary));
        fab.setBackground(V.ripple(this, V.round(this, p.primary, 18), 18));
        fab.setElevation(Ui.dpf(this, 6));
        fab.setVisibility(View.GONE);
        root.addView(fab, new FrameLayout.LayoutParams(Ui.dp(this, 58), Ui.dp(this, 58), Gravity.BOTTOM | Gravity.END));

        // 底部提示条
        snackBar = V.text(this, "", V.BODY);
        snackBar.setTextColor(0xFFFFFFFF);
        snackBar.setBackground(V.round(this, 0xF0262B36, 14));
        snackBar.setElevation(Ui.dpf(this, 8));
        V.pad(snackBar, 16, 13, 16, 13);
        snackBar.setVisibility(View.GONE);
        FrameLayout.LayoutParams slp = new FrameLayout.LayoutParams(V.MATCH, V.WRAP, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        root.addView(snackBar, slp);

        // 「正在处理…」遮罩
        busy = new FrameLayout(this);
        busy.setBackgroundColor(p.scrim);
        busy.setClickable(true);
        LinearLayout box = V.hbox(this);
        box.setBackground(V.round(this, p.surface, 16));
        V.pad(box, 20, 16, 24, 16);
        ProgressBar pb = new ProgressBar(this);
        pb.setIndeterminateTintList(ColorStateList.valueOf(p.primary));
        box.addView(pb, new LinearLayout.LayoutParams(Ui.dp(this, 28), Ui.dp(this, 28)));
        busyText = V.text(this, "", V.BODY);
        V.addStart(box, busyText, 14);
        busy.addView(box, new FrameLayout.LayoutParams(V.WRAP, V.WRAP, Gravity.CENTER));
        busy.setVisibility(View.GONE);
        root.addView(busy, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));

        root.setOnApplyWindowInsetsListener((v, in) -> {
            insets = Ui.insets(in);
            applyInsets();
            return in;
        });
        setContentView(root);
        if (current != null) navBar.select(current);
    }

    private void applyInsets() {
        boolean wide = Ui.wide(this);
        int top = insets[0], bottom = insets[1], left = insets[2], right = insets[3];
        appBar.setInsets(top, wide ? 0 : left, right);
        if (wide) {
            navBar.setPadding(left, top, 0, bottom);
            content.setPadding(0, 0, right, bottom);
        } else {
            navBar.setPadding(left, 0, right, bottom);
            content.setPadding(left, 0, right, 0);
        }
        int navH = wide ? 0 : navBar.getMeasuredHeight();
        if (!wide && navH == 0) navH = Ui.dp(this, 64) + bottom;
        FrameLayout.LayoutParams flp = (FrameLayout.LayoutParams) fab.getLayoutParams();
        flp.bottomMargin = (wide ? bottom : navH) + Ui.dp(this, 18);
        flp.rightMargin = right + Ui.dp(this, 18);
        fab.setLayoutParams(flp);
        FrameLayout.LayoutParams slp = (FrameLayout.LayoutParams) snackBar.getLayoutParams();
        int side = Ui.dp(this, 16);
        slp.leftMargin = (wide ? Ui.dp(this, 88) + left : left) + side;
        slp.rightMargin = right + side;
        slp.bottomMargin = (wide ? bottom : navH) + Ui.dp(this, 12);
        if (wide && Ui.widthDp(this) > 760) {
            slp.width = Ui.dp(this, 520);
            slp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        }
        snackBar.setLayoutParams(slp);
    }

    // ---------- 标签与页面栈 ----------

    private void onTabClicked(String key) {
        if (key.equals(current)) {
            // 再点当前标签：回到这个标签的首页
            ArrayList<Screen> st = stacks.get(key);
            if (st != null && st.size() > 1) {
                while (st.size() > 1) {
                    Screen s = st.remove(st.size() - 1);
                    s.dispatchHide();
                    s.dispatchDestroy();
                }
                showTop(false);
            }
            return;
        }
        switchTab(key);
    }

    private ArrayList<Screen> stack() {
        ArrayList<Screen> st = stacks.get(current);
        if (st == null) {
            st = new ArrayList<>();
            for (TabSpec t : tabs) {
                if (t.key.equals(current)) st.add(t.root.create());
            }
            stacks.put(current, st);
        }
        return st;
    }

    private Screen top() {
        ArrayList<Screen> st = stack();
        return st.get(st.size() - 1);
    }

    @Override
    public void switchTab(String key) {
        boolean known = false;
        for (TabSpec t : tabs) if (t.key.equals(key)) known = true;
        if (!known) return;
        if (current != null && stacks.get(current) != null) top().dispatchHide();
        current = key;
        navBar.select(key);
        showTop(false);
    }

    /** 把当前标签栈顶的页面放进内容区 */
    private void showTop(boolean animate) {
        Screen s = top();
        View v = s.attach(this, this);
        if (v.getParent() != null) ((ViewGroup) v.getParent()).removeView(v);
        content.removeAllViews();
        content.addView(v, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        if (animate) {
            v.setAlpha(0f);
            v.setTranslationX(Ui.dp(this, 24));
            v.animate().alpha(1f).translationX(0).setDuration(200)
                    .setInterpolator(new DecelerateInterpolator(1.5f)).start();
        }
        renderChrome();
        s.dispatchShow();
    }

    @Override
    public void push(Screen screen) {
        Ui.hideKeyboard(content);
        top().dispatchHide();
        stack().add(screen);
        showTop(true);
    }

    @Override
    public void pop(Screen screen) {
        for (Map.Entry<String, ArrayList<Screen>> e : stacks.entrySet()) {
            ArrayList<Screen> st = e.getValue();
            int idx = st.indexOf(screen);
            if (idx <= 0) continue; // 栈底（标签首页）不能关
            boolean wasTop = idx == st.size() - 1 && e.getKey().equals(current);
            Ui.hideKeyboard(content);
            st.remove(idx);
            screen.dispatchHide();
            screen.dispatchDestroy();
            if (wasTop) showTop(false);
            return;
        }
    }

    @Override
    public void invalidateChrome(Screen screen) {
        if (screen == top()) renderChrome();
    }

    private void renderChrome() {
        Screen s = top();
        boolean canBack = stack().size() > 1 && s.showBack();
        appBar.render(s.title(), s.subtitle(), canBack ? () -> onBackPressed() : null, s.actions());
        Action f = s.fab();
        if (f == null) {
            fab.setVisibility(View.GONE);
        } else {
            fab.setImageResource(f.icon != 0 ? f.icon : cn.wfxxkj.teacher.core.R.drawable.ic_add);
            fab.setContentDescription(f.label);
            fab.setOnClickListener(f.listener());
            if (fab.getVisibility() != View.VISIBLE) {
                fab.setVisibility(View.VISIBLE);
                fab.setScaleX(0.6f);
                fab.setScaleY(0.6f);
                fab.animate().scaleX(1f).scaleY(1f).setDuration(160).start();
            }
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (busy != null && busy.getVisibility() == View.VISIBLE) return;
        if (root == null) {
            super.onBackPressed();
            return;
        }
        Screen s = top();
        if (s.onBack()) return;
        if (stack().size() > 1) {
            pop(s);
            return;
        }
        if (!current.equals(tabs.get(0).key)) {
            switchTab(tabs.get(0).key);
            return;
        }
        long now = System.currentTimeMillis();
        if (now - lastBack < 2000) {
            super.onBackPressed();
        } else {
            lastBack = now;
            toast("再按一次退出");
        }
    }

    // ---------- Host 其余 ----------

    @Override
    public Activity activity() {
        return this;
    }

    @Override
    public void pickFiles(String[] mimeTypes, boolean multiple, FilesPicked callback) {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType(mimeTypes.length == 1 ? mimeTypes[0] : "*/*");
        if (mimeTypes.length > 1) i.putExtra(Intent.EXTRA_MIME_TYPES, mimeTypes);
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, multiple);
        pendingPick = callback;
        try {
            startActivityForResult(i, REQ_PICK);
        } catch (Exception e) {
            pendingPick = null;
            toast("手机上没有可用的文件管理器");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_PICK) return;
        FilesPicked cb = pendingPick;
        pendingPick = null;
        if (cb == null || resultCode != RESULT_OK || data == null) return;
        List<Uri> out = new ArrayList<>();
        ClipData clip = data.getClipData();
        if (clip != null) {
            for (int i = 0; i < clip.getItemCount(); i++) out.add(clip.getItemAt(i).getUri());
        } else if (data.getData() != null) {
            out.add(data.getData());
        }
        if (!out.isEmpty()) cb.onPicked(out);
    }

    @Override
    public void toast(CharSequence message) {
        snack(message, null, null);
    }

    private final Runnable hideSnack = () -> snackBar.animate().alpha(0f).setDuration(180)
            .withEndAction(() -> snackBar.setVisibility(View.GONE)).start();

    @Override
    public void snack(CharSequence message, String action, Runnable onAction) {
        if (snackBar == null || TextUtils.isEmpty(message)) return;
        snackBar.removeCallbacks(hideSnack);
        if (action != null) {
            android.text.SpannableStringBuilder sb = new android.text.SpannableStringBuilder(message);
            sb.append("    ");
            int start = sb.length();
            sb.append(action);
            sb.setSpan(new android.text.style.ForegroundColorSpan(0xFF9DB0FF), start, sb.length(), 0);
            sb.setSpan(new android.text.style.StyleSpan(android.graphics.Typeface.BOLD), start, sb.length(), 0);
            snackBar.setText(sb);
            snackBar.setOnClickListener(v -> {
                hideSnack.run();
                if (onAction != null) onAction.run();
            });
        } else {
            snackBar.setText(message);
            snackBar.setOnClickListener(v -> hideSnack.run());
        }
        snackBar.setVisibility(View.VISIBLE);
        snackBar.setAlpha(0f);
        snackBar.setTranslationY(Ui.dp(this, 12));
        snackBar.animate().alpha(1f).translationY(0).setDuration(180).start();
        snackBar.postDelayed(hideSnack, action != null ? 6000 : 2600);
    }

    @Override
    public void showBusy(CharSequence message) {
        busyText.setText(message);
        busy.setVisibility(View.VISIBLE);
        Ui.hideKeyboard(content);
    }

    @Override
    public void hideBusy() {
        busy.setVisibility(View.GONE);
    }

    @Override
    public void logout(String message) {
        Session.get().logout();
        toLogin(message);
    }

    private void toLogin(String message) {
        Intent i = new Intent(this, LoginActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK);
        i.putExtra(LoginActivity.EXTRA_MESSAGE, message == null ? "" : message);
        startActivity(i);
        finish();
    }

    // ---------- 登录状态 ----------

    @Override
    public void onOnlineChanged(boolean online, String message) {
        if (offline == null) return;
        if (online) {
            offline.setVisibility(View.GONE);
        } else {
            offline.setText("连接已断开：" + (message == null ? "" : message) + "（点此重试）");
            offline.setVisibility(View.VISIBLE);
        }
    }

    @Override
    public void onUserChanged(JSONObject user) {
        if (root != null) renderChrome();
    }

    @Override
    public void onSessionLost(String message) {
        toLogin(message);
    }

    /** 主题切换后整页重建（深浅色的颜色都是建视图时取的） */
    public static void restartForTheme(Activity a) {
        a.recreate();
    }
}
