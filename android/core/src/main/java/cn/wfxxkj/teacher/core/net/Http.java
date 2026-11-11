package cn.wfxxkj.teacher.core.net;

import android.content.ContentResolver;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.text.TextUtils;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.ConnectException;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.URLDecoder;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import javax.net.ssl.SSLException;

import cn.wfxxkj.teacher.core.session.Session;

/**
 * 和服务器说话。只用系统自带的 HttpURLConnection，不引第三方网络库。
 *
 * <p>所有方法都是同步的，必须在后台线程调（页面里用 {@code Screen.run(...)}，它会替你切线程）。
 * 路径从 /api 后面写起：{@code Http.getObj("/questions", Params.of("page", 1))}。
 *
 * <p>令牌过期（401）时自动用保存的密码重新登录一次再重试，老师感觉不到；
 * 重登也失败（密码被改了）才抛出 401，并通知界面回登录页。
 */
public final class Http {
    private static final int CONNECT_TIMEOUT = 10_000;
    private static final int READ_TIMEOUT = 60_000;

    private Http() {}

    // ---------- JSON 请求 ----------

    public static Object get(String path, Params query) throws ApiException {
        return json("GET", path, query, null);
    }

    public static JSONObject getObj(String path, Params query) throws ApiException {
        return asObj(get(path, query));
    }

    public static JSONArray getArr(String path, Params query) throws ApiException {
        return asArr(get(path, query));
    }

    /** body：JSONObject / JSONArray 发 JSON；Params 发表单；null 不带正文 */
    public static Object post(String path, Object body) throws ApiException {
        return json("POST", path, null, body);
    }

    public static Object post(String path, Params query, Object body) throws ApiException {
        return json("POST", path, query, body);
    }

    public static JSONObject postObj(String path, Object body) throws ApiException {
        return asObj(post(path, body));
    }

    public static Object put(String path, Object body) throws ApiException {
        return json("PUT", path, null, body);
    }

    public static Object patch(String path, Object body) throws ApiException {
        return json("PATCH", path, null, body);
    }

    public static Object delete(String path, Params query) throws ApiException {
        return json("DELETE", path, query, null);
    }

    public static JSONObject asObj(Object o) throws ApiException {
        if (o instanceof JSONObject) return (JSONObject) o;
        throw new ApiException(0, "服务器返回的内容看不懂，请确认服务器版本");
    }

    public static JSONArray asArr(Object o) throws ApiException {
        if (o instanceof JSONArray) return (JSONArray) o;
        // 有的列表接口返回 {items: [...]}，统一拆出来
        if (o instanceof JSONObject && ((JSONObject) o).optJSONArray("items") != null) {
            return ((JSONObject) o).optJSONArray("items");
        }
        throw new ApiException(0, "服务器返回的内容看不懂，请确认服务器版本");
    }

    /** 通用请求，返回解析好的 JSON（JSONObject / JSONArray / String / Number / Boolean / null） */
    public static Object json(String method, String path, Params query, Object body) throws ApiException {
        Response r = send(method, path, query, body, null, true);
        String text = new String(r.bytes, StandardCharsets.UTF_8).trim();
        if (text.isEmpty()) return null;
        try {
            return new JSONTokener(text).nextValue();
        } catch (Exception e) {
            return text;
        }
    }

    // ---------- 上传 ----------

    /**
     * multipart 上传一个文件（题目导入、学生导入、反馈配图）。
     * field 是表单字段名（后端都叫 file）。
     */
    public static Object upload(String path, Params query, String field, Uri file) throws ApiException {
        return upload(path, query, field, file, null);
    }

    /** 同上，再带几个普通表单字段（如系统管理员导入数据要带的 password） */
    public static Object upload(String path, Params query, String field, Uri file,
                                java.util.Map<String, String> fields) throws ApiException {
        Multipart mp = new Multipart(field, file);
        if (fields != null) mp.fields.putAll(fields);
        Response r = send("POST", path, query, null, mp, true);
        String text = new String(r.bytes, StandardCharsets.UTF_8).trim();
        if (text.isEmpty()) return null;
        try {
            return new JSONTokener(text).nextValue();
        } catch (Exception e) {
            return text;
        }
    }

    // ---------- 下载 ----------

    /** 下载结果：内容先落在 APP 的缓存目录，再由 Files.save 存进「下载」 */
    public static final class Download {
        public File file;
        /** 服务器给的文件名（Content-Disposition），没有就是 null */
        public String serverName;
        public String mime;
    }

    /** 下载二进制（导出 Excel、考试包等）。body 规则同 {@link #post} */
    public static Download download(String method, String path, Params query, Object body) throws ApiException {
        Download d = new Download();
        File dir = new File(Session.get().context().getCacheDir(), "dl");
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        d.file = new File(dir, UUID.randomUUID().toString());
        Response r = send(method, path, query, body, null, true, d.file);
        d.serverName = r.filename;
        d.mime = r.mime;
        return d;
    }

    /** 读一个地址的原始字节（题目配图等）。同一台服务器的地址会带上令牌 */
    public static byte[] bytes(String urlOrPath) throws ApiException {
        String url = absolute(urlOrPath);
        return sendRaw("GET", url, null, null, true, null).bytes;
    }

    /** "/uploads/a.png" → "http://服务器/uploads/a.png"；已是完整地址的原样返回 */
    public static String absolute(String urlOrPath) {
        if (urlOrPath == null) return "";
        if (urlOrPath.startsWith("http://") || urlOrPath.startsWith("https://")) return urlOrPath;
        String server = Session.get().server();
        return server + (urlOrPath.startsWith("/") ? "" : "/") + urlOrPath;
    }

    // ---------- 内部 ----------

    private static final class Response {
        byte[] bytes = new byte[0];
        String filename;
        String mime;
    }

    private static final class Multipart {
        final String field;
        final Uri uri;
        final String boundary = "----wfxx" + UUID.randomUUID().toString().replace("-", "");
        final java.util.Map<String, String> fields = new java.util.LinkedHashMap<>();

        Multipart(String field, Uri uri) {
            this.field = field;
            this.uri = uri;
        }
    }

    private static Response send(String method, String path, Params query, Object body, Multipart mp,
                                 boolean retry) throws ApiException {
        return send(method, path, query, body, mp, retry, null);
    }

    private static Response send(String method, String path, Params query, Object body, Multipart mp,
                                 boolean retry, File sink) throws ApiException {
        Session s = Session.get();
        String url = s.server() + "/api" + path;
        if (query != null && !query.isEmpty()) url += (url.contains("?") ? "&" : "?") + query.encode();
        try {
            return sendRaw(method, url, body, mp, false, sink);
        } catch (ApiException e) {
            // 令牌过期：用保存的密码悄悄重新登录一次，成功了再发一遍
            if (e.code == 401 && retry && !path.startsWith("/auth/login")) {
                s.reloginBlocking();
                return send(method, path, query, body, mp, false, sink);
            }
            throw e;
        }
    }

    private static Response sendRaw(String method, String url, Object body, Multipart mp,
                                    boolean authOnlySameServer, File sink) throws ApiException {
        Session s = Session.get();
        HttpURLConnection conn = null;
        // 别的网站（反馈里贴的外链图片）连不上不算「和服务器断开」
        final boolean own = url.startsWith(s.server() + "/");
        try {
            conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setRequestMethod(method);
            conn.setConnectTimeout(CONNECT_TIMEOUT);
            // 系统管理员导出 / 导入整库数据、上传升级包：服务器要打包 / 体检，比普通请求慢得多
            conn.setReadTimeout(url.contains("/api/system/") ? 600_000 : READ_TIMEOUT);
            conn.setUseCaches(false);
            conn.setRequestProperty("Accept", "application/json, */*");
            conn.setRequestProperty("User-Agent", s.userAgent());
            String token = s.token();
            boolean sameServer = !authOnlySameServer || own;
            if (!TextUtils.isEmpty(token) && sameServer) {
                conn.setRequestProperty("Authorization", "Bearer " + token);
            }
            if (mp != null) {
                writeMultipart(conn, mp);
            } else if (body != null) {
                byte[] bytes;
                String type;
                if (body instanceof Params) {
                    bytes = ((Params) body).encode().getBytes(StandardCharsets.UTF_8);
                    type = "application/x-www-form-urlencoded";
                } else {
                    bytes = String.valueOf(body).getBytes(StandardCharsets.UTF_8);
                    type = "application/json; charset=utf-8";
                }
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", type);
                conn.setFixedLengthStreamingMode(bytes.length);
                OutputStream os = conn.getOutputStream();
                os.write(bytes);
                os.close();
            } else if ("POST".equals(method) || "PUT".equals(method) || "PATCH".equals(method)) {
                conn.setDoOutput(true);
                conn.setFixedLengthStreamingMode(0);
                conn.getOutputStream().close();
            }
            int code = conn.getResponseCode();
            Response r = new Response();
            if (code >= 400) {
                InputStream es = conn.getErrorStream();
                String text = es == null ? "" : new String(readAll(es), StandardCharsets.UTF_8);
                throw new ApiException(code, Errors.explain(code, text), Errors.parseDetail(text));
            }
            r.mime = conn.getContentType();
            r.filename = filenameOf(conn.getHeaderField("Content-Disposition"));
            InputStream in = conn.getInputStream();
            if (sink != null) {
                OutputStream out = new FileOutputStream(sink);
                copy(in, out);
                out.close();
            } else {
                r.bytes = readAll(in);
            }
            if (own) s.markOnline();
            return r;
        } catch (ApiException e) {
            throw e;
        } catch (UnknownHostException e) {
            throw offline(s, own, "找不到服务器，请检查网络或服务器地址");
        } catch (SocketTimeoutException e) {
            throw offline(s, own, "连接服务器超时，请检查网络");
        } catch (ConnectException e) {
            throw offline(s, own, "连不上服务器，请检查网络，或确认服务器已开机");
        } catch (SSLException e) {
            throw new ApiException(0, "HTTPS 证书有问题，连接被拒绝");
        } catch (IOException e) {
            throw offline(s, own, "网络出错：" + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static ApiException offline(Session s, boolean own, String msg) {
        if (own) s.markOffline(msg);
        return new ApiException(0, msg);
    }

    private static void writeMultipart(HttpURLConnection conn, Multipart mp) throws IOException {
        ContentResolver cr = Session.get().context().getContentResolver();
        String name = displayName(cr, mp.uri);
        String type = cr.getType(mp.uri);
        if (type == null) type = "application/octet-stream";
        conn.setDoOutput(true);
        conn.setChunkedStreamingMode(64 * 1024);
        conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + mp.boundary);
        OutputStream os = conn.getOutputStream();
        for (java.util.Map.Entry<String, String> f : mp.fields.entrySet()) {
            os.write(("--" + mp.boundary + "\r\nContent-Disposition: form-data; name=\"" + f.getKey() + "\"\r\n\r\n"
                    + f.getValue() + "\r\n").getBytes(StandardCharsets.UTF_8));
        }
        String head = "--" + mp.boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"" + mp.field + "\"; filename=\""
                + name.replace("\"", "") + "\"\r\n"
                + "Content-Type: " + type + "\r\n\r\n";
        os.write(head.getBytes(StandardCharsets.UTF_8));
        InputStream in = cr.openInputStream(mp.uri);
        if (in == null) throw new IOException("读不到选中的文件");
        copy(in, os);
        os.write(("\r\n--" + mp.boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        os.close();
    }

    /** 选中文件的文件名（系统文件选择器给的是 content:// 地址，名字要另外查） */
    public static String displayName(ContentResolver cr, Uri uri) {
        Cursor c = null;
        try {
            c = cr.query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null);
            if (c != null && c.moveToFirst() && c.getString(0) != null) return c.getString(0);
        } catch (Exception ignored) {
            // 查不到用路径最后一段
        } finally {
            if (c != null) c.close();
        }
        String last = uri.getLastPathSegment();
        return last == null ? "file" : last;
    }

    private static String filenameOf(String disposition) {
        if (disposition == null) return null;
        try {
            int i = disposition.indexOf("filename*=");
            if (i >= 0) {
                String v = disposition.substring(i + 10).split(";")[0].trim();
                int q = v.indexOf("''");
                if (q >= 0) v = v.substring(q + 2);
                return URLDecoder.decode(v.replace("\"", ""), "UTF-8");
            }
            i = disposition.indexOf("filename=");
            if (i >= 0) {
                String v = disposition.substring(i + 9).split(";")[0].trim().replace("\"", "");
                return v.isEmpty() ? null : v;
            }
        } catch (Exception ignored) {
            // 解析不了就不用服务器的名字
        }
        return null;
    }

    private static void copy(InputStream in, OutputStream out) throws IOException {
        byte[] buf = new byte[16 * 1024];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        in.close();
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        copy(in, out);
        return out.toByteArray();
    }
}
