package cn.wfxxkj.teacher;

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
final class Prefs {
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
    private static final int MAX_RECENT = 5;

    private final SharedPreferences sp;

    Prefs(Context context) {
        sp = context.getApplicationContext().getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    String server() { return sp.getString(K_SERVER, ""); }
    String username() { return sp.getString(K_USERNAME, ""); }
    String token() { return sp.getString(K_TOKEN, ""); }
    String userJson() { return sp.getString(K_USER_JSON, ""); }
    boolean remember() { return sp.getBoolean(K_REMEMBER, true); }
    String brand() { return sp.getString(K_BRAND, ""); }
    int heartbeatSeconds() { return sp.getInt(K_HEARTBEAT, 300); }

    boolean loggedIn() {
        return !TextUtils.isEmpty(server()) && !TextUtils.isEmpty(token());
    }

    /** 登录成功：记下地址、账号、令牌，按需保存密码 */
    void saveLogin(String server, String username, String password, boolean remember,
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

    void saveToken(String token, String userJson) {
        SharedPreferences.Editor e = sp.edit().putString(K_TOKEN, token);
        if (!TextUtils.isEmpty(userJson)) e.putString(K_USER_JSON, userJson);
        e.apply();
    }

    void saveUserJson(String userJson) {
        if (!TextUtils.isEmpty(userJson)) sp.edit().putString(K_USER_JSON, userJson).apply();
    }

    void saveServerInfo(String brand, int heartbeatSeconds) {
        SharedPreferences.Editor e = sp.edit();
        if (!TextUtils.isEmpty(brand)) e.putString(K_BRAND, brand);
        if (heartbeatSeconds >= 30) e.putInt(K_HEARTBEAT, heartbeatSeconds);
        e.apply();
    }

    /** 保存的密码（解不开或没存就返回 null） */
    String password() {
        String enc = sp.getString(K_PASSWORD, null);
        return enc == null ? null : CredentialStore.decrypt(enc);
    }

    /** 在 APP 里改了密码：存着的那份跟着换，不然下次自动登录会失败 */
    void updatePassword(String password) {
        if (!remember() || TextUtils.isEmpty(password)) return;
        String enc = CredentialStore.encrypt(password);
        if (enc != null) sp.edit().putString(K_PASSWORD, enc).apply();
    }

    /** 退出登录：令牌和密码都清掉，地址和账号留着方便下次登录 */
    void logout() {
        sp.edit().remove(K_TOKEN).remove(K_USER_JSON).remove(K_PASSWORD).apply();
    }

    List<String> recentServers() {
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
