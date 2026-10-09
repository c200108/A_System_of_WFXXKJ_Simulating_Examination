package cn.wfxxkj.teacher.core.session;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;

import org.json.JSONObject;

import java.util.concurrent.CopyOnWriteArrayList;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Json;

/**
 * 当前登录状态，全 APP 一份（{@link #get()}）。
 *
 * <p>保存服务器地址、令牌、当前老师的账号信息；网络通断、账号信息变化、登录彻底失效
 * 都从这里广播出去，界面按需订阅（{@link #addListener}）。
 */
public final class Session {

    public interface Listener {
        /** 网络或服务器通/不通了（主线程） */
        default void onOnlineChanged(boolean online, String message) {}

        /** 当前账号的信息变了：改了姓名、管理员改了角色（主线程） */
        default void onUserChanged(JSONObject user) {}

        /** 登录彻底失效（密码被改、账号被停用），要回登录页（主线程） */
        default void onSessionLost(String message) {}
    }

    private static Session instance;

    private final Context app;
    private final Prefs prefs;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final CopyOnWriteArrayList<Listener> listeners = new CopyOnWriteArrayList<>();
    private volatile JSONObject user;
    private volatile boolean online = true;
    private static String userAgent = "WfxxTeacherApp";

    private Session(Context context) {
        app = context.getApplicationContext();
        prefs = new Prefs(app);
        user = Json.parse(prefs.userJson());
        try {
            PackageInfo pi = app.getPackageManager().getPackageInfo(app.getPackageName(), 0);
            userAgent = "WfxxTeacherApp/" + pi.versionName;
        } catch (Exception ignored) {
            // 取不到版本号就不带
        }
    }

    /** Application.onCreate 里调一次 */
    public static synchronized void init(Context context) {
        if (instance == null) instance = new Session(context);
    }

    public static Session get() {
        if (instance == null) throw new IllegalStateException("Session.init 没调");
        return instance;
    }

    public Context context() {
        return app;
    }

    public Prefs prefs() {
        return prefs;
    }

    public String server() {
        return prefs.server();
    }

    public String token() {
        return prefs.token();
    }

    public boolean loggedIn() {
        return prefs.loggedIn();
    }

    public String userAgent() {
        return userAgent;
    }

    static String userAgentStatic() {
        return userAgent;
    }

    // ---------- 当前老师 ----------

    /** 当前账号（{id, username, name, role, grade_class, contact, ...}），没登录是空对象 */
    public JSONObject user() {
        return user;
    }

    public long userId() {
        return user.optLong("id", 0);
    }

    public boolean isAdmin() {
        return "admin".equals(user.optString("role"));
    }

    /** 显示用的名字：有姓名用姓名，没有用账号 */
    public String displayName() {
        String n = Json.str(user, "name");
        return n.isEmpty() ? Json.str(user, "username") : n;
    }

    public void setUser(JSONObject u) {
        if (u == null) return;
        user = u;
        prefs.saveUserJson(u.toString());
        final JSONObject snapshot = u;
        main.post(() -> {
            for (Listener l : listeners) l.onUserChanged(snapshot);
        });
    }

    // ---------- 登录 / 退出 ----------

    /** 登录成功（原生登录页调） */
    public void loggedIn(String server, String username, String password, boolean remember,
                         JSONObject loginResult) {
        JSONObject u = loginResult.optJSONObject("user");
        prefs.saveLogin(server, username, password, remember, loginResult.optString("access_token"),
                u == null ? "" : u.toString());
        user = u == null ? new JSONObject() : u;
        online = true;
    }

    public void tokenRefreshed(String token, JSONObject u) {
        prefs.saveToken(token, u == null ? null : u.toString());
        if (u != null) setUser(u);
    }

    /** 在 APP 里改了自己的密码：存着的密码跟着换，不然下次自动重登会失败 */
    public void passwordChanged(String newPassword) {
        prefs.updatePassword(newPassword);
    }

    /** 主动退出：清令牌和密码，地址和账号留着方便下次登录 */
    public void logout() {
        prefs.logout();
        user = new JSONObject();
    }

    /**
     * 令牌失效时在当前（后台）线程里用保存的密码重新登录。
     * 几个请求同时 401 时只真正登录一次：后到的发现令牌已经换过就直接返回。
     *
     * @throws ApiException 登不上（没存密码、密码被改、账号被停用）时抛 401，并通知界面回登录页
     */
    public void reloginBlocking() throws ApiException {
        String before = prefs.token();
        synchronized (this) {
            if (!TextUtils.equals(before, prefs.token())) return; // 别的请求已经换好了
            String pwd = prefs.password();
            if (TextUtils.isEmpty(pwd)) {
                lose("登录已过期，请重新登录");
                throw new ApiException(401, "登录已过期，请重新登录");
            }
            try {
                JSONObject res = AuthApi.login(prefs.server(), prefs.username(), pwd);
                JSONObject u = res.optJSONObject("user");
                prefs.saveToken(res.optString("access_token"), u == null ? null : u.toString());
                if (u != null) setUser(u);
            } catch (ApiException e) {
                if (e.code == 400 || e.code == 401 || e.code == 403) {
                    String msg = e.getMessage() + "，请重新登录";
                    lose(msg);
                    throw new ApiException(401, msg);
                }
                throw e;
            }
        }
    }

    /** 登录彻底失效：清掉令牌，通知界面回登录页 */
    public void lose(final String message) {
        prefs.logout();
        main.post(() -> {
            for (Listener l : listeners) l.onSessionLost(message);
        });
    }

    // ---------- 在线状态 ----------

    public boolean isOnline() {
        return online;
    }

    public void markOnline() {
        if (online) return;
        online = true;
        main.post(() -> {
            for (Listener l : listeners) l.onOnlineChanged(true, null);
        });
    }

    public void markOffline(final String message) {
        if (!online) return;
        online = false;
        main.post(() -> {
            for (Listener l : listeners) l.onOnlineChanged(false, message);
        });
    }

    public void addListener(Listener l) {
        listeners.addIfAbsent(l);
    }

    public void removeListener(Listener l) {
        listeners.remove(l);
    }
}
