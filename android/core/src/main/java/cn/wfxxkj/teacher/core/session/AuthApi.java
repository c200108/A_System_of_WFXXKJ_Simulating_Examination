package cn.wfxxkj.teacher.core.session;

import android.text.TextUtils;

import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import javax.net.ssl.SSLException;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Errors;
import cn.wfxxkj.teacher.core.net.Params;

/**
 * 登录相关的三个请求：认服务器、登录、心跳。
 *
 * 和 {@link cn.wfxxkj.teacher.core.net.Http} 分开写，因为这几个请求发生在「还没登录」或
 * 「正在换令牌」的时候，不能走 Http 那套 401 自动重登（会自己调自己）。都是同步方法，后台线程调。
 */
public final class AuthApi {
    private static final int CONNECT_TIMEOUT = 8000;
    private static final int READ_TIMEOUT = 15000;

    private AuthApi() {}

    /**
     * 把老师随手填的地址整理成 http(s)://主机[:端口]。
     * 「192.168.1.10:8080」「exam.school.cn/js/paper」「http://x.cn/」都能认。
     */
    public static String normalizeServer(String input) {
        String s = input == null ? "" : input.trim();
        if (s.isEmpty()) return "";
        s = s.replace('：', ':').replace('。', '.').replace(" ", "");
        String lower = s.toLowerCase(Locale.ROOT);
        if (lower.startsWith("https://")) s = "https://" + s.substring(8);
        else if (lower.startsWith("http://")) s = "http://" + s.substring(7);
        else s = "http://" + s;
        int slash = s.indexOf('/', s.indexOf("//") + 2);
        if (slash > 0) s = s.substring(0, slash); // 去掉 /js/paper 之类的路径
        return s;
    }

    /** 认服务器。5.0 以前的服务器没有 /api/app/info，退回去读 /api/config 认一下 */
    public static JSONObject info(String server) throws ApiException {
        try {
            JSONObject info = (JSONObject) parse(request("GET", server + "/api/app/info", null, null, null));
            if (!"wfxxkj-exam".equals(info.optString("app"))) throw notOurs();
            return info;
        } catch (ApiException e) {
            if (e.code != 404) throw e;
        } catch (Exception e) {
            throw notOurs();
        }
        try {
            JSONObject cfg = (JSONObject) parse(request("GET", server + "/api/config", null, null, null));
            JSONObject site = cfg.optJSONObject("site");
            if (site == null) throw notOurs();
            JSONObject info = new JSONObject();
            info.put("app", "wfxxkj-exam");
            info.put("protocol", 0);
            info.put("brand", site.optString("brand"));
            info.put("title", site.optString("title"));
            return info;
        } catch (ApiException e) {
            if (e.code == 404) throw new ApiException(404, "这个地址不是教学平台的服务器，请检查地址和端口");
            throw e;
        } catch (Exception e) {
            throw notOurs();
        }
    }

    private static ApiException notOurs() {
        return new ApiException(0, "这个地址不是教学平台的服务器，请检查地址");
    }

    /** 教师登录，返回 {access_token, user} */
    public static JSONObject login(String server, String username, String password) throws ApiException {
        String form = Params.of("username", username).add("password", password).encode();
        Object o = parse(request("POST", server + "/api/auth/login", null,
                "application/x-www-form-urlencoded", form));
        if (!(o instanceof JSONObject) || TextUtils.isEmpty(((JSONObject) o).optString("access_token"))) {
            throw new ApiException(0, "服务器返回的内容看不懂，请确认服务器版本");
        }
        JSONObject res = (JSONObject) o;
        JSONObject user = res.optJSONObject("user");
        if (user != null && "student".equals(user.optString("role"))) {
            throw new ApiException(403, "这是学生账号，教师端 APP 只能用老师的账号登录");
        }
        return res;
    }

    /**
     * 心跳：保持登录、需要时换新令牌。返回 {token|null, user, heartbeat_seconds}。
     * 旧服务器没有这个接口（404），退回去调 /api/auth/me，只确认令牌还有效。
     */
    public static JSONObject session(String server, String token) throws ApiException {
        try {
            Object o = parse(request("POST", server + "/api/app/session", token, "application/json", "{}"));
            if (o instanceof JSONObject) return (JSONObject) o;
            throw new ApiException(0, "服务器返回的内容看不懂");
        } catch (ApiException e) {
            if (e.code != 404) throw e;
        }
        Object me = parse(request("GET", server + "/api/auth/me", token, null, null));
        JSONObject out = new JSONObject();
        try {
            out.put("ok", true);
            out.put("token", JSONObject.NULL);
            out.put("user", me);
        } catch (Exception ignored) {
            // put 不会失败
        }
        return out;
    }

    private static Object parse(String text) throws ApiException {
        try {
            return new JSONTokener(text).nextValue();
        } catch (Exception e) {
            throw new ApiException(0, "服务器返回的内容看不懂，请确认服务器版本");
        }
    }

    private static String request(String method, String url, String token, String contentType,
                                  String body) throws ApiException {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setRequestMethod(method);
            conn.setConnectTimeout(CONNECT_TIMEOUT);
            conn.setReadTimeout(READ_TIMEOUT);
            conn.setUseCaches(false);
            conn.setRequestProperty("Accept", "application/json");
            conn.setRequestProperty("User-Agent", Session.userAgentStatic());
            if (!TextUtils.isEmpty(token)) conn.setRequestProperty("Authorization", "Bearer " + token);
            if (body != null) {
                byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", contentType);
                conn.setFixedLengthStreamingMode(bytes.length);
                OutputStream os = conn.getOutputStream();
                os.write(bytes);
                os.close();
            }
            int code = conn.getResponseCode();
            InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String text = in == null ? "" : readAll(in);
            if (code >= 400) {
                String msg = Errors.explain(code, text);
                if (code == 401 && url.endsWith("/auth/login")) msg = "用户名或密码不正确";
                throw new ApiException(code, msg);
            }
            return text;
        } catch (ApiException e) {
            throw e;
        } catch (UnknownHostException e) {
            throw new ApiException(0, "找不到这个服务器，请检查地址是否填对");
        } catch (SocketTimeoutException e) {
            throw new ApiException(0, "连接服务器超时，请检查网络，或确认手机和服务器在同一网络里");
        } catch (ConnectException e) {
            throw new ApiException(0, "连不上服务器，请检查地址和端口，或确认服务器已开机");
        } catch (SSLException e) {
            throw new ApiException(0, "HTTPS 证书有问题，连接被拒绝。可改用 http:// 地址，或请管理员换有效证书");
        } catch (IOException e) {
            throw new ApiException(0, "网络出错：" + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static String readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        in.close();
        return out.toString("UTF-8");
    }
}
