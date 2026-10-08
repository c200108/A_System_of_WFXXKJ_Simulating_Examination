package cn.wfxxkj.teacher;

import android.text.TextUtils;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.URLEncoder;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import javax.net.ssl.SSLException;

/**
 * 和服务器说话的几个请求。只用系统自带的 HttpURLConnection，不引第三方网络库 ——
 * 安装包能小几百 KB，而这里统共就三四个请求。
 *
 * 所有方法都是同步的，必须在后台线程调。
 */
final class Api {
    private static final int CONNECT_TIMEOUT = 8000;
    private static final int READ_TIMEOUT = 15000;

    /** 请求失败。code 是 HTTP 状态码，连不上服务器时为 0；message 是给老师看的中文 */
    static final class ApiException extends Exception {
        final int code;

        ApiException(int code, String message) {
            super(message);
            this.code = code;
        }
    }

    private Api() {}

    /**
     * 把老师随手填的地址整理成 http(s)://主机[:端口]。
     * 「192.168.1.10:8080」「exam.school.cn/js/paper」「http://x.cn/」都能认。
     */
    static String normalizeServer(String input) {
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

    /** 认服务器。旧服务器（5.0 以前）没有这个接口，退回去读 /api/config 认一下 */
    static JSONObject info(String server) throws ApiException {
        try {
            JSONObject info = new JSONObject(request("GET", server + "/api/app/info", null, null, null));
            if (!"wfxxkj-exam".equals(info.optString("app"))) {
                throw new ApiException(0, "这个地址不是教学平台的服务器，请检查地址");
            }
            return info;
        } catch (ApiException e) {
            if (e.code != 404) throw e;
        } catch (Exception e) {
            throw new ApiException(0, "这个地址不是教学平台的服务器，请检查地址");
        }
        try {
            JSONObject cfg = new JSONObject(request("GET", server + "/api/config", null, null, null));
            JSONObject site = cfg.optJSONObject("site");
            if (site == null) throw new ApiException(0, "这个地址不是教学平台的服务器，请检查地址");
            JSONObject info = new JSONObject();
            info.put("app", "wfxxkj-exam");
            info.put("protocol", 0); // 旧服务器：能用，但没有心跳续期
            info.put("brand", site.optString("brand"));
            info.put("title", site.optString("title"));
            return info;
        } catch (ApiException e) {
            if (e.code == 404) throw new ApiException(404, "这个地址不是教学平台的服务器，请检查地址和端口");
            throw e;
        } catch (Exception e) {
            throw new ApiException(0, "这个地址不是教学平台的服务器，请检查地址");
        }
    }

    /** 教师登录，返回 {access_token, user} */
    static JSONObject login(String server, String username, String password) throws ApiException {
        try {
            String form = "username=" + URLEncoder.encode(username, "UTF-8")
                    + "&password=" + URLEncoder.encode(password, "UTF-8");
            return new JSONObject(request("POST", server + "/api/auth/login", null,
                    "application/x-www-form-urlencoded", form));
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException(0, "服务器返回的内容看不懂，请确认服务器版本");
        }
    }

    /**
     * 心跳：保持登录、需要时换新令牌。返回 {token|null, user, heartbeat_seconds}。
     * 旧服务器没有这个接口（404），退回去调 /api/auth/me，只确认令牌还有效。
     */
    static JSONObject session(String server, String token) throws ApiException {
        try {
            return new JSONObject(request("POST", server + "/api/app/session", token,
                    "application/json", "{}"));
        } catch (ApiException e) {
            if (e.code != 404) throw e;
        } catch (Exception e) {
            throw new ApiException(0, "服务器返回的内容看不懂");
        }
        try {
            JSONObject me = new JSONObject(request("GET", server + "/api/auth/me", token, null, null));
            JSONObject out = new JSONObject();
            out.put("ok", true);
            out.put("token", JSONObject.NULL);
            out.put("user", me);
            return out;
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException(0, "服务器返回的内容看不懂");
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
            conn.setRequestProperty("User-Agent", "WfxxTeacherApp/" + BuildConfig.VERSION_NAME);
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
            if (code >= 400) throw new ApiException(code, explain(code, text));
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

    /** 把后端的报错翻成一句话。后端的 detail 本来就是中文，有就直接用 */
    private static String explain(int code, String text) {
        try {
            Object detail = new JSONObject(text).opt("detail");
            if (detail instanceof String && !((String) detail).isEmpty()) return (String) detail;
            if (detail instanceof JSONArray && ((JSONArray) detail).length() > 0) {
                return "填写的内容不符合要求";
            }
        } catch (Exception ignored) {
            // 不是 JSON（比如 nginx 的错误页），按状态码说
        }
        if (code == 401) return "登录已过期，请重新登录";
        if (code == 403) return "没有权限";
        if (code == 404) return "服务器上找不到这个接口";
        if (code == 502 || code == 503 || code == 504) return "服务器正在重启或负载过高，请稍后再试";
        if (code >= 500) return "服务器出错了（" + code + "），请联系管理员";
        return "请求失败（" + code + "）";
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
