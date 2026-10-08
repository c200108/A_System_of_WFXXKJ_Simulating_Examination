package cn.wfxxkj.teacher;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.TextUtils;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.inputmethod.EditorInfo;
import android.widget.ArrayAdapter;
import android.widget.AutoCompleteTextView;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 原生登录页：服务器地址 + 账号 + 密码。
 *
 * 登录分两步：先认服务器（地址填错了当场说清楚是哪里不对），再登录。
 * 已经登录过的直接进主界面，不在这里停留。
 */
public class LoginActivity extends Activity {
    static final String EXTRA_MESSAGE = "message";
    /** 从主界面点「切换服务器」进来：不自动跳走，让老师改地址 */
    static final String EXTRA_EDIT = "edit";

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
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new Prefs(this);
        boolean edit = getIntent().getBooleanExtra(EXTRA_EDIT, false);
        if (prefs.loggedIn() && !edit) {
            startActivity(new Intent(this, MainActivity.class));
            finish();
            return;
        }

        setContentView(R.layout.activity_login);
        Ui.edgeToEdge(this, false);

        final View hero = findViewById(R.id.hero);
        final View scroll = findViewById(R.id.scroll);
        final int heroPad = hero.getPaddingTop();
        scroll.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                int[] in = Ui.insets(insets);
                hero.setPadding(hero.getPaddingLeft(), heroPad + in[0], hero.getPaddingRight(),
                        hero.getPaddingBottom());
                v.setPadding(in[2], 0, in[3], in[1]);
                return insets;
            }
        });

        serverInput = findViewById(R.id.server);
        userInput = findViewById(R.id.username);
        pwdInput = findViewById(R.id.password);
        remember = findViewById(R.id.remember);
        errorText = findViewById(R.id.error);
        loginBtn = findViewById(R.id.login);
        brandText = findViewById(R.id.brand);

        ((TextView) findViewById(R.id.version)).setText(
                "v" + BuildConfig.VERSION_NAME + " · 功能与网页版教师端一致");
        if (!TextUtils.isEmpty(prefs.brand())) brandText.setText(prefs.brand());

        serverInput.setText(prefs.server().replaceFirst("^http://", ""));
        userInput.setText(prefs.username());
        remember.setChecked(prefs.remember());
        serverInput.setAdapter(new ArrayAdapter<>(this, R.layout.item_server, prefs.recentServers()));
        serverInput.setThreshold(0);
        serverInput.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override
            public void onFocusChange(View v, boolean hasFocus) {
                if (hasFocus && serverInput.getAdapter().getCount() > 0) serverInput.showDropDown();
            }
        });

        final TextView toggle = findViewById(R.id.toggle_pwd);
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

        pwdInput.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(TextView v, int actionId, KeyEvent event) {
                if (actionId == EditorInfo.IME_ACTION_DONE || actionId == EditorInfo.IME_ACTION_GO) {
                    submit();
                    return true;
                }
                return false;
            }
        });
        loginBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                submit();
            }
        });

        String msg = getIntent().getStringExtra(EXTRA_MESSAGE);
        if (!TextUtils.isEmpty(msg)) showError(msg);

        // 光标放在第一个没填的格子里
        if (serverInput.length() == 0) serverInput.requestFocus();
        else if (userInput.length() == 0) userInput.requestFocus();
        else pwdInput.requestFocus();
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
        loginBtn.setEnabled(!value);
        loginBtn.setText(label);
        serverInput.setEnabled(!value);
        userInput.setEnabled(!value);
        pwdInput.setEnabled(!value);
    }

    private void submit() {
        if (busy) return;
        final String server = Api.normalizeServer(serverInput.getText().toString());
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
        setBusy(true, "正在连接服务器…");

        io.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    JSONObject info = Api.info(server);
                    final String brand = info.optString("brand", "");
                    prefs.saveServerInfo(brand, info.optInt("heartbeat_seconds", 0));
                    main.post(new Runnable() {
                        @Override
                        public void run() {
                            if (!brand.isEmpty()) brandText.setText(brand);
                            setBusy(true, "正在登录…");
                        }
                    });
                    JSONObject res = Api.login(server, username, password);
                    JSONObject user = res.optJSONObject("user");
                    prefs.saveLogin(server, username, password, keep, res.getString("access_token"),
                            user == null ? "" : user.toString());
                    main.post(new Runnable() {
                        @Override
                        public void run() {
                            startActivity(new Intent(LoginActivity.this, MainActivity.class)
                                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
                            finish();
                        }
                    });
                } catch (final Exception e) {
                    main.post(new Runnable() {
                        @Override
                        public void run() {
                            setBusy(false, "登 录");
                            showError(e instanceof Api.ApiException ? e.getMessage() : "登录失败：" + e);
                        }
                    });
                }
            }
        });
    }
}
