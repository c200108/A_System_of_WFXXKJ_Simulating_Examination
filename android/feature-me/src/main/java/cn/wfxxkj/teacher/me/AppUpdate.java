package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.SystemClock;
import android.provider.Settings;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.security.MessageDigest;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import cn.wfxxkj.teacher.core.net.Json;

/**
 * 「我的 → 检查更新」背后的事：去联网版公开仓库的 GitHub Releases 查教师端 APP 的新版，
 * 下载 apk，交给系统安装器。
 *
 * <h3>查哪儿</h3>
 * 学生端 exe 和教师端 APP 发在同一个公开仓库里：学生端的 tag 是 {@code v4.12.0}，
 * APP 的 tag 是 {@code teacher-v5.1.0}。所以这里查的是 <b>Release 列表</b>（不是 latest ——
 * latest 多半是学生端那个），只挑 tag 以 {@code teacher-v} 开头、不是草稿也不是预发布的最新一个，
 * 附件取 .apk。不经过学校服务器，几十个老师一起升级也不占学校带宽。
 *
 * <h3>规矩</h3>
 * 只在点按钮时查；两次至少隔 60 秒；整次查询 5 秒封顶（超时就提示「无法获取更新」，不重试）。
 * 下载另算。下载完校验大小（和 sha256），再调系统安装器；新版必须用同一把正式签名，系统才让覆盖安装。
 *
 * <h3>为什么自己写 ApkProvider</h3>
 * 交给安装器的必须是 content:// 地址。通常用 AndroidX 的 FileProvider，可这个 APP 不依赖任何
 * 第三方库（安装包几百 KB），所以 {@link ApkProvider} 只做 FileProvider 用得上的那一点：
 * 把下载目录里的 apk 只读地交给安装器。
 */
final class AppUpdate {
    private AppUpdate() {}

    static final String REPO = "c200108/A_System_of_WFXXKJ_Simulating_Examination";
    static final String TAG_PREFIX = "teacher-v";
    static final long INTERVAL_MS = 60_000;      // 两次检查至少隔这么久
    static final int QUERY_MS = 5_000;           // 整次查询封顶
    static final int DOWNLOAD_TIMEOUT_MS = 30_000;
    private static final String API = "https://api.github.com/repos/" + REPO + "/releases?per_page=30";
    private static final Pattern VERSION = Pattern.compile("\\d+(?:\\.\\d+)*");

    /** 上次点检查的时刻（开机以来的毫秒）。只记在内存里：防连点，不是防作弊 */
    private static long lastCheck = -1;

    /** 查到的新版 */
    static final class Release {
        String version = "", notes = "", page = "", apkUrl = "", apkName = "", sha256 = "";
        long size;
    }

    static final class UpdateException extends Exception {
        UpdateException(String msg) {
            super(msg);
        }
    }

    // ---------------------------------------------------------------- 限流

    /** 还要等几秒才能再查；0 表示现在就能查 */
    static int waitLeft() {
        if (lastCheck < 0) return 0;
        long left = INTERVAL_MS - (SystemClock.elapsedRealtime() - lastCheck);
        return left <= 0 ? 0 : (int) ((left + 999) / 1000);
    }

    static void markChecked() {
        lastCheck = SystemClock.elapsedRealtime();
    }

    // ---------------------------------------------------------------- 版本号

    /** 5.1.0 和 5.1 算一样；认不出的算 0 */
    static int compare(String a, String b) {
        int[] x = parts(a), y = parts(b);
        for (int i = 0; i < Math.max(x.length, y.length); i++) {
            int p = i < x.length ? x[i] : 0, q = i < y.length ? y[i] : 0;
            if (p != q) return p < q ? -1 : 1;
        }
        return 0;
    }

    private static int[] parts(String s) {
        Matcher m = VERSION.matcher(s == null ? "" : s);
        if (!m.find()) return new int[0];
        String[] seg = m.group().split("\\.");
        int[] out = new int[seg.length];
        for (int i = 0; i < seg.length; i++) {
            try {
                out[i] = Integer.parseInt(seg[i]);
            } catch (NumberFormatException e) {
                out[i] = 0;
            }
        }
        return out;
    }

    // ---------------------------------------------------------------- 查

    /** 去 GitHub 查教师端最新的正式版。没有发布过返回 null。在后台线程调 */
    static Release latest() throws UpdateException {
        String body;
        try {
            body = get(API, QUERY_MS);
        } catch (SocketTimeoutException e) {
            throw new UpdateException("无法获取更新：网络太慢，5 秒内没有拿到更新信息");
        } catch (IOException e) {
            throw new UpdateException("无法获取更新：连不上 GitHub，请检查网络");
        }
        try {
            return pick(new JSONArray(body));
        } catch (Exception e) {
            throw new UpdateException("无法获取更新：返回的内容看不懂");
        }
    }

    /** Release 列表里挑教师端最新的正式版（tag teacher-v…，有 apk 附件） */
    static Release pick(JSONArray items) {
        Release best = null;
        for (JSONObject r : Json.list(items)) {
            String tag = Json.str(r, "tag_name");
            if (!tag.startsWith(TAG_PREFIX) || Json.bool(r, "draft") || Json.bool(r, "prerelease")) continue;
            String v = tag.substring(TAG_PREFIX.length());
            if (parts(v).length == 0 || (best != null && compare(v, best.version) <= 0)) continue;
            for (JSONObject a : Json.list(Json.arr(r, "assets"))) {
                String name = Json.str(a, "name");
                if (!name.toLowerCase().endsWith(".apk")) continue;
                Release rel = new Release();
                rel.version = v;
                rel.notes = Json.str(r, "body");
                rel.page = Json.str(r, "html_url");
                rel.apkUrl = Json.str(a, "browser_download_url");
                rel.apkName = name;
                Long size = Json.longOrNull(a, "size");
                rel.size = size == null ? 0 : size;
                String digest = Json.str(a, "digest");
                rel.sha256 = digest.startsWith("sha256:") ? digest.substring(7).toLowerCase() : "";
                best = rel;
                break;
            }
        }
        return best;
    }

    private static String get(String url, int timeoutMs) throws IOException {
        HttpURLConnection c = open(url, timeoutMs);
        try (InputStream in = c.getInputStream()) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[16 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toString("UTF-8");
        } finally {
            c.disconnect();
        }
    }

    private static HttpURLConnection open(String url, int timeoutMs) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(timeoutMs);
        c.setReadTimeout(timeoutMs);
        c.setInstanceFollowRedirects(true);          // GitHub 的下载地址会跳到存储域名
        c.setRequestProperty("User-Agent", "wfxxkj-teacher-app");
        c.setRequestProperty("Accept", "application/vnd.github+json");
        int code = c.getResponseCode();
        if (code != 200) {
            c.disconnect();
            throw new IOException("HTTP " + code);
        }
        return c;
    }

    // ---------------------------------------------------------------- 下载

    interface Progress {
        void on(long got, long total);
    }

    /** 下载好的 apk 放哪：APP 自己的缓存目录，不用存储权限，卸载时一起清掉 */
    static File apkFile(Context c, Release r) {
        File dir = new File(c.getCacheDir(), ApkProvider.DIR);
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
        return new File(dir, "wfxx-teacher-" + r.version.replaceAll("[^0-9.]", "") + ".apk");
    }

    /** 已经下好、而且校验得过的就不再下（老师去设置里开完「安装未知应用」回来，直接装） */
    static boolean ready(File f, Release r) {
        return f.isFile() && (r.size <= 0 || f.length() == r.size)
                && (r.sha256.isEmpty() || r.sha256.equals(sha256(f)));
    }

    /** 在后台线程调。校验不过就删掉并抛异常 */
    static File download(Context c, Release r, Progress p, java.util.concurrent.atomic.AtomicBoolean cancel)
            throws UpdateException {
        File out = apkFile(c, r);
        File part = new File(out.getPath() + ".part");
        long got = 0;
        try {
            HttpURLConnection conn = open(r.apkUrl, DOWNLOAD_TIMEOUT_MS);
            long total = conn.getContentLengthLong() > 0 ? conn.getContentLengthLong() : r.size;
            try (InputStream in = conn.getInputStream(); OutputStream os = new FileOutputStream(part)) {
                byte[] buf = new byte[64 * 1024];
                int n;
                while ((n = in.read(buf)) > 0) {
                    if (cancel.get()) throw new UpdateException("已取消下载");
                    os.write(buf, 0, n);
                    got += n;
                    p.on(got, total);
                }
            } finally {
                conn.disconnect();
            }
        } catch (IOException e) {
            //noinspection ResultOfMethodCallIgnored
            part.delete();
            throw new UpdateException("下载中断了，请稍后再试");
        } catch (UpdateException e) {
            //noinspection ResultOfMethodCallIgnored
            part.delete();
            throw e;
        }
        String why = "";
        if (r.size > 0 && got != r.size) why = "大小不对";
        else if (!r.sha256.isEmpty() && !r.sha256.equals(sha256(part))) why = "校验码不对";
        if (!why.isEmpty()) {
            //noinspection ResultOfMethodCallIgnored
            part.delete();
            throw new UpdateException("下载的安装包" + why + "，已丢弃，请重试");
        }
        //noinspection ResultOfMethodCallIgnored
        out.delete();
        if (!part.renameTo(out)) throw new UpdateException("安装包保存不了，请重试");
        return out;
    }

    static String sha256(File f) {
        try (InputStream in = new FileInputStream(f)) {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            StringBuilder sb = new StringBuilder();
            for (byte b : md.digest()) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }

    // ---------------------------------------------------------------- 安装

    /** 这台手机允不允许本 APP 装应用（安卓 8 起要老师在设置里点一次「允许」） */
    static boolean canInstall(Context c) {
        return c.getPackageManager().canRequestPackageInstalls();
    }

    /** 打开「安装未知应用」设置页，直接定位到本 APP */
    static Intent allowInstallIntent(Context c) {
        return new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + c.getPackageName())).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    /** 交给系统安装器 */
    static Intent installIntent(Context c, File apk) {
        Uri uri = ApkProvider.uriFor(c, apk);
        Intent i = new Intent(Intent.ACTION_VIEW);
        i.setDataAndType(uri, ApkProvider.MIME);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        return i;
    }
}
