package cn.wfxxkj.teacher.core.session;

import android.content.Context;
import android.content.SharedPreferences;
import android.text.TextUtils;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * 本机保存的登录状态：服务器地址、账号、令牌、（加密后的）密码、最近用过的地址。
 *
 * 密码只在勾了「记住密码」时才存，而且是用系统密钥库加密过的（见 {@link CredentialStore}），
 * 存它只为一件事：令牌过期后在后台悄悄重新登录，老师不用每天输一遍。
 */
public final class Prefs {
    private static final String FILE = "wfxx_teacher";
    private static final String K_SERVER = "server";
    private static final String K_USERNAME = "username";
    private static final String K_TOKEN = "token";
    private static final String K_USER_JSON = "user_json";
    private static final String K_PASSWORD = "password_enc";
    private static final String K_REMEMBER = "remember";
    private static final String K_RECENT = "recent_servers";
    private static final String K_BRAND = "brand";
    private static final String K_HEARTBEAT = "heartbeat_seconds";
    private static final String K_THEME = "theme_mode";
    private static final String K_SERVER_VERSION = "server_version";
    private static final String K_PROTOCOL = "protocol";
    private static final int MAX_RECENT = 5;

    /** 深浅色：跟随系统 / 浅色 / 深色 */
    public static final int THEME_SYSTEM = 0;
    public static final int THEME_LIGHT = 1;
    public static final int THEME_DARK = 2;

    private final SharedPreferences sp;

    public Prefs(Context context) {
        sp = context.getApplicationContext().getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    public String server() { return sp.getString(K_SERVER, ""); }
    public String username() { return sp.getString(K_USERNAME, ""); }
    public String token() { return sp.getString(K_TOKEN, ""); }
    public String userJson() { return sp.getString(K_USER_JSON, ""); }
    public boolean remember() { return sp.getBoolean(K_REMEMBER, true); }
    public String brand() { return sp.getString(K_BRAND, ""); }
    public int heartbeatSeconds() { return sp.getInt(K_HEARTBEAT, 300); }

    public int themeMode() { return sp.getInt(K_THEME, THEME_SYSTEM); }
    public void setThemeMode(int mode) { sp.edit().putInt(K_THEME, mode).apply(); }
    public String serverVersion() { return sp.getString(K_SERVER_VERSION, ""); }
    public int protocol() { return sp.getInt(K_PROTOCOL, 0); }

    public void saveServerMeta(String version, int protocol) {
        sp.edit().putString(K_SERVER_VERSION, version == null ? "" : version)
                .putInt(K_PROTOCOL, protocol).apply();
    }

    /** 各页面记住自己的小设置（上次选的筛选、展开的分组），key 自己起，别和别的页面撞 */
    public String ui(String key, String def) { return sp.getString("ui." + key, def); }
    public void setUi(String key, String value) { sp.edit().putString("ui." + key, value).apply(); }

    public boolean loggedIn() {
        return !TextUtils.isEmpty(server()) && !TextUtils.isEmpty(token());
    }

    /** 登录成功：记下地址、账号、令牌，按需保存密码 */
    public void saveLogin(String server, String username, String password, boolean remember,
                   String token, String userJson) {
        SharedPreferences.Editor e = sp.edit()
                .putString(K_SERVER, server)
                .putString(K_USERNAME, username)
                .putString(K_TOKEN, token)
                .putString(K_USER_JSON, userJson)
                .putBoolean(K_REMEMBER, remember);
        String enc = remember ? CredentialStore.encrypt(password) : null;
        if (enc != null) e.putString(K_PASSWORD, enc);
        else e.remove(K_PASSWORD);
        e.apply();
        addRecent(server);
    }

    public void saveToken(String token, String userJson) {
        SharedPreferences.Editor e = sp.edit().putString(K_TOKEN, token);
        if (!TextUtils.isEmpty(userJson)) e.putString(K_USER_JSON, userJson);
        e.apply();
    }

    public void saveUserJson(String userJson) {
        if (!TextUtils.isEmpty(userJson)) sp.edit().putString(K_USER_JSON, userJson).apply();
    }

    public void saveServerInfo(String brand, int heartbeatSeconds) {
        SharedPreferences.Editor e = sp.edit();
        if (!TextUtils.isEmpty(brand)) e.putString(K_BRAND, brand);
        if (heartbeatSeconds >= 30) e.putInt(K_HEARTBEAT, heartbeatSeconds);
        e.apply();
    }

    /** 保存的密码（解不开或没存就返回 null） */
    public String password() {
        String enc = sp.getString(K_PASSWORD, null);
        return enc == null ? null : CredentialStore.decrypt(enc);
    }

    /** 在 APP 里改了密码：存着的那份跟着换，不然下次自动登录会失败 */
    public void updatePassword(String password) {
        if (!remember() || TextUtils.isEmpty(password)) return;
        String enc = CredentialStore.encrypt(password);
        if (enc != null) sp.edit().putString(K_PASSWORD, enc).apply();
    }

    /** 退出登录：令牌和密码都清掉，地址和账号留着方便下次登录 */
    public void logout() {
        sp.edit().remove(K_TOKEN).remove(K_USER_JSON).remove(K_PASSWORD).apply();
    }

    public List<String> recentServers() {
        String raw = sp.getString(K_RECENT, "");
        List<String> out = new ArrayList<>();
        if (!TextUtils.isEmpty(raw)) out.addAll(Arrays.asList(raw.split("\n")));
        return out;
    }

    private void addRecent(String server) {
        List<String> list = recentServers();
        list.remove(server);
        list.add(0, server);
        while (list.size() > MAX_RECENT) list.remove(list.size() - 1);
        sp.edit().putString(K_RECENT, TextUtils.join("\n", list)).apply();
    }
}
