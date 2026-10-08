package cn.wfxxkj.teacher;

import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 保持登录不掉线，又不费电、不费流量。
 *
 * <ul>
 *   <li><b>只在前台跑</b>：APP 在屏幕上时每隔几分钟（服务器定，默认 5 分钟）发一次心跳，
 *       退到后台立刻停，一个请求都不发；回到前台马上补一次。没有后台服务、没有长连接。</li>
 *   <li><b>令牌自动续期</b>：心跳时服务器发现令牌用掉四分之一寿命，就换一张新的，
 *       只要隔三差五打开过 APP，令牌永远不会过期。</li>
 *   <li><b>过期了自动重登</b>：手机放了好几天没开、令牌真过期了，用保存的账号密码
 *       在后台悄悄重新登录；只有密码被改了才回到登录页。</li>
 *   <li><b>断网自动重连</b>：心跳失败按 5、10、20、40、60 秒退避重试，网络一恢复
 *       （系统通知）立刻重试，页面上的「连接已断开」提示跟着收起。</li>
 * </ul>
 */
final class SessionKeeper {

    interface Listener {
        /** 网络或服务器通/不通了 */
        void onOnlineChanged(boolean online, String message);

        /** 换了新令牌，要塞给页面 */
        void onTokenRefreshed(String token, String userJson);

        /** 彻底登不上了（密码被改、账号被停用），回登录页 */
        void onSessionLost(String message);
    }

    private static final long[] BACKOFF_MS = {5000, 10000, 20000, 40000, 60000};

    private final Prefs prefs;
    private final Listener listener;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();

    private boolean running;
    private boolean busy;
    private boolean online = true;
    private int failures;

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            beat(false);
        }
    };

    SessionKeeper(Prefs prefs, Listener listener) {
        this.prefs = prefs;
        this.listener = listener;
    }

    /** 回到前台：马上心跳一次，然后按间隔继续 */
    void start() {
        running = true;
        main.removeCallbacks(tick);
        beat(false);
    }

    /** 退到后台：停掉，什么都不发 */
    void stop() {
        running = false;
        main.removeCallbacks(tick);
    }

    /** 网络恢复了：别等退避，马上试 */
    void kick() {
        if (!running) return;
        main.removeCallbacks(tick);
        beat(false);
    }

    /** 页面上的接口回了 401：马上重新登录 */
    void forceRelogin() {
        main.removeCallbacks(tick);
        beat(true);
    }

    void shutdown() {
        stop();
        io.shutdownNow();
    }

    private void schedule(long delayMs) {
        main.removeCallbacks(tick);
        if (running) main.postDelayed(tick, delayMs);
    }

    private void beat(final boolean relogin) {
        if (busy) return;
        busy = true;
        final String server = prefs.server();
        final String token = prefs.token();
        io.execute(new Runnable() {
            @Override
            public void run() {
                Result r = relogin ? doRelogin(server) : doBeat(server, token);
                deliver(r);
            }
        });
    }

    /** 后台线程里跑的结果，回主线程再处理 */
    private static final class Result {
        int kind; // 0 正常 1 断网 2 登不上了
        String message;
        String newToken;
        String userJson;
        int heartbeat;
    }

    private Result doBeat(String server, String token) {
        Result r = new Result();
        try {
            JSONObject res = Api.session(server, token);
            String t = res.optString("token", "");
            if (!TextUtils.isEmpty(t) && !"null".equals(t)) r.newToken = t;
            JSONObject user = res.optJSONObject("user");
            if (user != null) r.userJson = user.toString();
            r.heartbeat = res.optInt("heartbeat_seconds", 0);
            return r;
        } catch (Api.ApiException e) {
            if (e.code == 401) return doRelogin(server);
            r.kind = 1;
            r.message = e.getMessage();
            return r;
        }
    }

    private Result doRelogin(String server) {
        Result r = new Result();
        String user = prefs.username();
        String pwd = prefs.password();
        if (TextUtils.isEmpty(pwd)) {
            r.kind = 2;
            r.message = "登录已过期，请重新登录";
            return r;
        }
        try {
            JSONObject res = Api.login(server, user, pwd);
            r.newToken = res.getString("access_token");
            JSONObject u = res.optJSONObject("user");
            if (u != null) r.userJson = u.toString();
            return r;
        } catch (Api.ApiException e) {
            if (e.code == 400 || e.code == 401 || e.code == 403) {
                r.kind = 2; // 密码被改了、账号被停用
                r.message = e.getMessage() + "，请重新登录";
            } else {
                r.kind = 1;
                r.message = e.getMessage();
            }
            return r;
        } catch (Exception e) {
            r.kind = 1;
            r.message = "服务器返回的内容看不懂";
            return r;
        }
    }

    private void deliver(final Result r) {
        main.post(new Runnable() {
            @Override
            public void run() {
                busy = false;
                if (r.kind == 2) {
                    running = false;
                    listener.onSessionLost(r.message);
                    return;
                }
                if (r.kind == 1) {
                    failures++;
                    if (online) {
                        online = false;
                        listener.onOnlineChanged(false, r.message);
                    }
                    schedule(BACKOFF_MS[Math.min(failures, BACKOFF_MS.length) - 1]);
                    return;
                }
                failures = 0;
                if (!online) {
                    online = true;
                    listener.onOnlineChanged(true, null);
                }
                if (r.heartbeat > 0) prefs.saveServerInfo(null, r.heartbeat);
                if (r.newToken != null) {
                    prefs.saveToken(r.newToken, r.userJson);
                    listener.onTokenRefreshed(r.newToken, r.userJson);
                } else {
                    prefs.saveUserJson(r.userJson);
                }
                schedule(prefs.heartbeatSeconds() * 1000L);
            }
        });
    }
}
