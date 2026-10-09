package cn.wfxxkj.teacher.core.io;

import android.content.ActivityNotFoundException;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.TextUtils;
import android.webkit.MimeTypeMap;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Locale;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Http;

/**
 * 导出的文件（成绩 Excel、试卷、考试包……）存进手机的「下载/教学平台」。
 *
 * <p>走系统的 MediaStore，安卓 10 起不用申请任何存储权限。写完之前文件标着「待定」，
 * 别的应用看不到半截文件；中途失败就删掉。同名文件系统会自动加 (1)、(2)。
 *
 * <p>页面里最常用的是 {@link #export}：
 * <pre>Files.export(this, "正在导出…", () -&gt; QuestionApi.exportXlsx(filter), "题库.xlsx");</pre>
 * 下载 → 保存 → 底部提示「已保存到 下载/教学平台」并给一个「打开」按钮。
 */
public final class Files {
    public static final String FOLDER = Environment.DIRECTORY_DOWNLOADS + "/教学平台";

    public static final String XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    public static final String XLS = "application/vnd.ms-excel";
    public static final String[] EXCEL = {XLSX, XLS, "application/octet-stream"};

    private Files() {}

    /** 下载并保存，完了提示可以打开 */
    public static void export(final Screen s, CharSequence busy, final Screen.Task<Http.Download> download,
                              final String fileName) {
        s.runBusy(busy, () -> {
            Http.Download d = download.call();
            String name = !TextUtils.isEmpty(fileName) ? fileName
                    : (d.serverName != null ? d.serverName : "下载文件");
            Uri uri = save(s.ctx(), d.file, name, d.mime);
            return new Object[]{uri, displayName(s.ctx(), uri, name)};
        }, r -> {
            final Uri uri = (Uri) ((Object[]) r)[0];
            String name = (String) ((Object[]) r)[1];
            s.snack("已保存到「下载/教学平台/" + name + "」", "打开", () -> open(s.ctx(), uri, name));
        });
    }

    /** 把一个本地文件存进下载目录（后台线程调），返回文件地址 */
    public static Uri save(Context c, File src, String name, String mime) throws IOException {
        ContentResolver cr = c.getContentResolver();
        String safe = safeName(name);
        String type = guessMime(safe, mime);
        ContentValues v = new ContentValues();
        v.put(MediaStore.MediaColumns.DISPLAY_NAME, safe);
        v.put(MediaStore.MediaColumns.MIME_TYPE, type);
        v.put(MediaStore.MediaColumns.RELATIVE_PATH, FOLDER);
        v.put(MediaStore.MediaColumns.IS_PENDING, 1);
        Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
        if (uri == null) throw new IOException("手机存储不可用，存不了文件");
        try {
            OutputStream out = cr.openOutputStream(uri);
            if (out == null) throw new IOException("手机存储不可用，存不了文件");
            InputStream in = new FileInputStream(src);
            byte[] buf = new byte[32 * 1024];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            in.close();
            out.close();
            ContentValues done = new ContentValues();
            done.put(MediaStore.MediaColumns.IS_PENDING, 0);
            cr.update(uri, done, null, null);
            return uri;
        } catch (IOException e) {
            cr.delete(uri, null, null);
            throw new IOException("保存失败，请检查手机存储空间");
        } finally {
            //noinspection ResultOfMethodCallIgnored
            src.delete();
        }
    }

    /** 用别的应用（WPS、浏览器……）打开 */
    public static void open(Context c, Uri uri, String name) {
        Intent i = new Intent(Intent.ACTION_VIEW);
        i.setDataAndType(uri, guessMime(name, null));
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            c.startActivity(Intent.createChooser(i, "用什么打开").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (ActivityNotFoundException e) {
            android.widget.Toast.makeText(c, "手机上没有能打开这个文件的应用（可以装个 WPS）",
                    android.widget.Toast.LENGTH_LONG).show();
        }
    }

    /** 系统可能给文件名加了 (1)，取实际的名字 */
    public static String displayName(Context c, Uri uri, String fallback) {
        Cursor cur = null;
        try {
            cur = c.getContentResolver().query(uri, new String[]{MediaStore.MediaColumns.DISPLAY_NAME},
                    null, null, null);
            if (cur != null && cur.moveToFirst() && cur.getString(0) != null) return cur.getString(0);
        } catch (Exception ignored) {
            // 查不到就用原名
        } finally {
            if (cur != null) cur.close();
        }
        return fallback;
    }

    /** 去掉文件名里不允许的字符（和网页版 safeName 一致） */
    public static String safeName(String name) {
        String n = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|\\n\\r]", "").trim();
        return n.isEmpty() ? "下载文件" : n;
    }

    public static String guessMime(String name, String fallback) {
        String ext = "";
        int dot = name == null ? -1 : name.lastIndexOf('.');
        if (dot >= 0) ext = name.substring(dot + 1).toLowerCase(Locale.ROOT);
        switch (ext) {
            case "xlsx":
                return XLSX;
            case "xls":
                return XLS;
            case "html":
            case "htm":
                return "text/html";
            case "zip":
                return "application/zip";
            case "pdf":
                return "application/pdf";
            default:
                String m = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext);
                if (m != null) return m;
                if (fallback != null && !fallback.isEmpty()) {
                    int semi = fallback.indexOf(';');
                    return semi > 0 ? fallback.substring(0, semi).trim() : fallback;
                }
                return "application/octet-stream";
        }
    }
}
