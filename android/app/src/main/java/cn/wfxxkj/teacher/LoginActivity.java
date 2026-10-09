package cn.wfxxkj.teacher;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.ArrayAdapter;
import android.widget.AutoCompleteTextView;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.session.AuthApi;
import cn.wfxxkj.teacher.core.session.Prefs;
import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.ui.Fields;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Themes;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 原生登录页：服务器地址 + 账号 + 密码。
 *
 * 登录分两步：先认服务器（地址填错了当场说清楚是哪里不对），再登录。
 * 已经登录过的直接进主界面，不在这里停留。
 */
public class LoginActivity extends Activity {
    static final String EXTRA_MESSAGE = "message";

    private Prefs prefs;
    private AutoCompleteTextView serverInput;
    private EditText userInput;
    private EditText pwdInput;
    private CheckBox remember;
    private TextView errorText;
    private TextView loginBtn;
    private TextView brandText;
    private boolean busy;

    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    @Override
    protected void attachBaseContext(Context base) {
        super.attachBaseContext(Themes.wrap(base));
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Session.init(this);
        prefs = Session.get().prefs();
        if (Session.get().loggedIn() && getIntent().getStringExtra(EXTRA_MESSAGE) == null) {
            startActivity(new Intent(this, MainActivity.class));
            finish();
            return;
        }
        Ui.edgeToEdge(this);
        Ui.setLightBars(this, false); // 顶部是深蓝渐变，状态栏图标用白色
        setContentView(build());
        String msg = getIntent().getStringExtra(EXTRA_MESSAGE);
        if (!TextUtils.isEmpty(msg)) showError(msg);
        if (serverInput.length() == 0) serverInput.requestFocus();
        else if (userInput.length() == 0) userInput.requestFocus();
        else pwdInput.requestFocus();
    }

    private View build() {
        Palette p = Palette.of(this);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(p.page);

        // 顶部渐变
        final LinearLayout hero = V.vbox(this);
        hero.setBackgroundResource(R.drawable.hero_bg);
        hero.setGravity(Gravity.CENTER_HORIZONTAL);
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.logo_tile);
        hero.addView(logo, new LinearLayout.LayoutParams(Ui.dp(this, 64), Ui.dp(this, 64)));
        brandText = V.text(this, TextUtils.isEmpty(prefs.brand()) ? "教学平台" : prefs.brand(), V.H1);
        brandText.setTextColor(0xFFFFFFFF);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        blp.topMargin = Ui.dp(this, 14);
        hero.addView(brandText, blp);
        TextView sub = V.text(this, "教师端 · 组卷、考试、学情一手掌握", V.BODY2);
        sub.setTextColor(0xCCFFFFFF);
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        slp.topMargin = Ui.dp(this, 4);
        hero.addView(sub, slp);
        final int heroBottom = Ui.dp(this, 72);
        root.addView(hero, new FrameLayout.LayoutParams(V.MATCH, V.WRAP));

        // 表单卡片（叠在渐变下沿上）
        ScrollView scroll = new ScrollView(this);
        scroll.setClipToPadding(false);
        scroll.setFillViewport(true);
        LinearLayout column = V.vbox(this);
        column.setGravity(Gravity.CENTER_HORIZONTAL);
        scroll.addView(column);
        final View spacer = new View(this);
        column.addView(spacer, new LinearLayout.LayoutParams(1, Ui.dp(this, 220)));

        LinearLayout card = V.card(this);
        card.setElevation(Ui.dpf(this, 6));
        V.pad(card, 22, 24, 22, 22);
        card.addView(V.text(this, "登录", V.H2));
        card.addView(V.text(this, "用网页版教师端的账号密码登录", V.CAPTION));

        serverInput = new AutoCompleteTextView(this);
        styleInput(serverInput, "例如 192.168.1.10:8080");
        serverInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        serverInput.setText(prefs.server().replaceFirst("^http://", ""));
        serverInput.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, prefs.recentServers()));
        serverInput.setThreshold(1);
        serverInput.setOnFocusChangeListener((v, has) -> {
            if (has && serverInput.getAdapter() != null && serverInput.getAdapter().getCount() > 0
                    && serverInput.length() == 0) serverInput.showDropDown();
        });
        addField(card, "服务器地址", serverInput);

        userInput = Fields.input(this, "账号");
        userInput.setText(prefs.username());
        addField(card, "账号", userInput);

        pwdInput = Fields.input(this, "密码");
        pwdInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        pwdInput.setImeOptions(EditorInfo.IME_ACTION_GO);
        pwdInput.setOnEditorActionListener((v, id, ev) -> {
            if (id == EditorInfo.IME_ACTION_GO || id == EditorInfo.IME_ACTION_DONE) {
                submit();
                return true;
            }
            return false;
        });
        FrameLayout pwdBox = new FrameLayout(this);
        pwdBox.addView(pwdInput, new FrameLayout.LayoutParams(V.MATCH, V.WRAP));
        final TextView toggle = V.button(this, "显示", V.BTN_TEXT, null);
        toggle.setOnClickListener(new View.OnClickListener() {
            boolean shown;

            @Override
            public void onClick(View v) {
                shown = !shown;
                pwdInput.setInputType(InputType.TYPE_CLASS_TEXT | (shown
                        ? InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                        : InputType.TYPE_TEXT_VARIATION_PASSWORD));
                pwdInput.setSelection(pwdInput.length());
                toggle.setText(shown ? "隐藏" : "显示");
            }
        });
        pwdBox.addView(toggle, new FrameLayout.LayoutParams(V.WRAP, V.WRAP, Gravity.END | Gravity.CENTER_VERTICAL));
        pwdInput.setPadding(pwdInput.getPaddingLeft(), pwdInput.getPaddingTop(), Ui.dp(this, 64), pwdInput.getPaddingBottom());
        addField(card, "密码", pwdBox);

        remember = new CheckBox(this);
        remember.setText("记住密码（登录过期时自动重新登录）");
        remember.setTextColor(p.text2);
        remember.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        remember.setChecked(prefs.remember());
        V.addTop(card, remember, 10);

        errorText = V.notice(this, "", Tone.DANGER);
        errorText.setVisibility(View.GONE);
        V.addTop(card, errorText, 10);

        loginBtn = V.button(this, "登 录", V.BTN_PRIMARY, v -> submit());
        loginBtn.setMinHeight(Ui.dp(this, 50));
        loginBtn.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        V.addTop(card, loginBtn, 18);

        int maxW = Ui.dp(this, 440);
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(V.MATCH, V.WRAP);
        clp.leftMargin = clp.rightMargin = Ui.dp(this, 16);
        column.addView(card, clp);
        column.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> {
            int w = r - l;
            int side = w > maxW + Ui.dp(this, 32) ? (w - maxW) / 2 : Ui.dp(this, 16);
            LinearLayout.LayoutParams lp = (LinearLayout.LayoutParams) card.getLayoutParams();
            if (lp.leftMargin != side) {
                lp.leftMargin = lp.rightMargin = side;
                card.setLayoutParams(lp);
            }
        });

        TextView version = V.text(this, "v" + BuildConfig.VERSION_NAME + " · 安卓 10 及以上", V.CAPTION);
        version.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams vlp = new LinearLayout.LayoutParams(V.WRAP, V.WRAP);
        vlp.topMargin = Ui.dp(this, 20);
        vlp.bottomMargin = Ui.dp(this, 24);
        column.addView(version, vlp);

        root.addView(scroll, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));

        root.setOnApplyWindowInsetsListener((v, in) -> {
            int[] i = Ui.insets(in);
            hero.setPadding(i[2], i[0] + Ui.dp(this, 40), i[3], heroBottom + Ui.dp(this, 24));
            scroll.setPadding(i[2], 0, i[3], i[1]);
            hero.post(() -> {
                LinearLayout.LayoutParams lp = (LinearLayout.LayoutParams) spacer.getLayoutParams();
                int h = Math.max(0, hero.getHeight() - heroBottom);
                if (lp.height != h) {
                    lp.height = h;
                    spacer.setLayoutParams(lp);
                }
            });
            return in;
        });
        return root;
    }

    private void styleInput(EditText e, String hint) {
        EditText ref = Fields.input(this, hint);
        e.setHint(hint);
        e.setSingleLine(true);
        e.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        e.setTextColor(ref.getCurrentTextColor());
        e.setHintTextColor(Palette.of(this).text3);
        e.setBackground(Fields.inputBg(this));
        e.setMinHeight(Ui.dp(this, 48));
        e.setPadding(ref.getPaddingLeft(), ref.getPaddingTop(), ref.getPaddingRight(), ref.getPaddingBottom());
    }

    private void addField(LinearLayout card, String label, View input) {
        TextView l = V.text(this, label, V.LABEL);
        V.addTop(card, l, 16);
        V.addTop(card, input, 6);
    }

    @Override
    protected void onDestroy() {
        io.shutdownNow();
        super.onDestroy();
    }

    private void showError(String msg) {
        errorText.setText(msg);
        errorText.setVisibility(TextUtils.isEmpty(msg) ? View.GONE : View.VISIBLE);
    }

    private void setBusy(boolean value, String label) {
        busy = value;
        V.enable(loginBtn, !value);
        loginBtn.setText(label);
        serverInput.setEnabled(!value);
        userInput.setEnabled(!value);
        pwdInput.setEnabled(!value);
    }

    private void submit() {
        if (busy) return;
        final String server = AuthApi.normalizeServer(serverInput.getText().toString());
        final String username = userInput.getText().toString().trim();
        final String password = pwdInput.getText().toString();
        final boolean keep = remember.isChecked();
        if (server.isEmpty()) {
            showError("请填服务器地址，例如 192.168.1.10:8080");
            serverInput.requestFocus();
            return;
        }
        if (username.isEmpty()) {
            showError("请填账号");
            userInput.requestFocus();
            return;
        }
        if (password.isEmpty()) {
            showError("请填密码");
            pwdInput.requestFocus();
            return;
        }
        showError(null);
        Ui.hideKeyboard(pwdInput);
        setBusy(true, "正在连接服务器…");
        io.execute(() -> {
            try {
                JSONObject info = AuthApi.info(server);
                final String brand = info.optString("brand", "");
                prefs.saveServerInfo(brand, info.optInt("heartbeat_seconds", 0));
                prefs.saveServerMeta(info.optString("server_version", ""), info.optInt("protocol", 0));
                main.post(() -> {
                    if (!brand.isEmpty()) brandText.setText(brand);
                    setBusy(true, "正在登录…");
                });
                JSONObject res = AuthApi.login(server, username, password);
                Session.get().loggedIn(server, username, password, keep, res);
                main.post(() -> {
                    startActivity(new Intent(LoginActivity.this, MainActivity.class)
                            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
                    finish();
                });
            } catch (final Exception e) {
                main.post(() -> {
                    setBusy(false, "登 录");
                    showError(e instanceof ApiException ? e.getMessage() : "登录失败：" + e);
                });
            }
        });
    }
}
