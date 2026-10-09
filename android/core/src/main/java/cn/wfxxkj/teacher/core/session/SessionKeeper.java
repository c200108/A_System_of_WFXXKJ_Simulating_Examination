package cn.wfxxkj.teacher.core.session;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import cn.wfxxkj.teacher.core.net.ApiException;

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
 *       （系统通知）立刻重试，「连接已断开」提示跟着收起。</li>
 * </ul>
 *
 * 主界面在 onStart/onStop 里调 {@link #start()} / {@link #stop()}。
 */
public final class SessionKeeper {
    private static final long[] BACKOFF_MS = {5000, 10000, 20000, 40000, 60000};

    private final Session session;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ConnectivityManager cm;
    private ConnectivityManager.NetworkCallback netCallback;

    private boolean running;
    private boolean busy;
    private int failures;

    private final Runnable tick = () -> beat();

    public SessionKeeper(Context context) {
        session = Session.get();
        cm = context.getSystemService(ConnectivityManager.class);
    }

    /** 回到前台：马上心跳一次，然后按间隔继续；同时盯着网络恢复 */
    public void start() {
        running = true;
        main.removeCallbacks(tick);
        beat();
        if (cm != null && netCallback == null) {
            netCallback = new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    main.post(() -> kick());
                }
            };
            try {
                cm.registerDefaultNetworkCallback(netCallback);
            } catch (Exception e) {
                netCallback = null;
            }
        }
    }

    /** 退到后台：停掉，什么都不发 */
    public void stop() {
        running = false;
        main.removeCallbacks(tick);
        if (cm != null && netCallback != null) {
            try {
                cm.unregisterNetworkCallback(netCallback);
            } catch (Exception ignored) {
                // 没注册上就算了
            }
            netCallback = null;
        }
    }

    /** 网络恢复了，或者老师点了「重试」：别等退避，马上试 */
    public void kick() {
        if (!running) return;
        main.removeCallbacks(tick);
        beat();
    }

    public void shutdown() {
        stop();
        io.shutdownNow();
    }

    private void schedule(long delayMs) {
        main.removeCallbacks(tick);
        if (running) main.postDelayed(tick, delayMs);
    }

    private void beat() {
        if (busy || !session.loggedIn()) return;
        busy = true;
        final String server = session.server();
        final String token = session.token();
        io.execute(() -> {
            int kind; // 0 正常 1 断网 2 登不上了
            String message = null;
            try {
                JSONObject res = AuthApi.session(server, token);
                String t = res.optString("token", "");
                JSONObject user = res.optJSONObject("user");
                if (!TextUtils.isEmpty(t) && !"null".equals(t)) session.tokenRefreshed(t, user);
                else if (user != null) session.setUser(user);
                int hb = res.optInt("heartbeat_seconds", 0);
                if (hb > 0) session.prefs().saveServerInfo(null, hb);
                session.markOnline();
                kind = 0;
            } catch (ApiException e) {
                if (e.code == 401) {
                    try {
                        session.reloginBlocking();
                        session.markOnline();
                        kind = 0;
                    } catch (ApiException e2) {
                        kind = e2.code == 401 ? 2 : 1;
                        message = e2.getMessage();
                    }
                } else {
                    kind = 1;
                    message = e.getMessage();
                }
            }
            final int k = kind;
            final String msg = message;
            main.post(() -> {
                busy = false;
                if (k == 2) {
                    running = false; // Session.lose 已经通知界面了
                    return;
                }
                if (k == 1) {
                    failures++;
                    session.markOffline(msg);
                    schedule(BACKOFF_MS[Math.min(failures, BACKOFF_MS.length) - 1]);
                    return;
                }
                failures = 0;
                schedule(session.prefs().heartbeatSeconds() * 1000L);
            });
        });
    }
}
