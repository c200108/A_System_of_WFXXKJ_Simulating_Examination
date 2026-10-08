package cn.wfxxkj.teacher;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;

import java.io.OutputStream;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * 把网页导出的文件（成绩 Excel、试卷、考试包……）存进手机的「下载/教学平台」。
 *
 * 走系统的 MediaStore，安卓 10 起不用申请任何存储权限。文件写完之前标着「待定」，
 * 别的应用看不到半截文件；中途失败就删掉。同名文件系统会自动加 (1)、(2)。
 */
final class FileSaver {
    static final String FOLDER = Environment.DIRECTORY_DOWNLOADS + "/教学平台";

    private static final class Pending {
        Uri uri;
        String name;
        String mime;
        OutputStream out;
    }

    private final ContentResolver resolver;
    private final Map<String, Pending> pending = new HashMap<>();

    FileSaver(Context context) {
        resolver = context.getApplicationContext().getContentResolver();
    }

    /** 开一个新文件，返回句柄；失败返回 null */
    synchronized String begin(String name, String mime) {
        try {
            ContentValues v = new ContentValues();
            v.put(MediaStore.MediaColumns.DISPLAY_NAME, safeName(name));
            v.put(MediaStore.MediaColumns.MIME_TYPE, mime == null || mime.isEmpty()
                    ? "application/octet-stream" : mime);
            v.put(MediaStore.MediaColumns.RELATIVE_PATH, FOLDER);
            v.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
            if (uri == null) return null;
            Pending p = new Pending();
            p.uri = uri;
            p.name = safeName(name);
            p.mime = mime;
            p.out = resolver.openOutputStream(uri);
            if (p.out == null) {
                resolver.delete(uri, null, null);
                return null;
            }
            String id = UUID.randomUUID().toString();
            pending.put(id, p);
            return id;
        } catch (Exception e) {
            return null;
        }
    }

    synchronized boolean chunk(String id, String base64) {
        Pending p = pending.get(id);
        if (p == null) return false;
        try {
            p.out.write(Base64.decode(base64, Base64.DEFAULT));
            return true;
        } catch (Exception e) {
            abort(id);
            return false;
        }
    }

    /** 写完了：去掉「待定」标记，返回文件，失败返回 null */
    synchronized Uri end(String id) {
        Pending p = pending.remove(id);
        if (p == null) return null;
        try {
            p.out.close();
            ContentValues v = new ContentValues();
            v.put(MediaStore.MediaColumns.IS_PENDING, 0);
            resolver.update(p.uri, v, null, null);
            return p.uri;
        } catch (Exception e) {
            resolver.delete(p.uri, null, null);
            return null;
        }
    }

    synchronized void abort(String id) {
        Pending p = pending.remove(id);
        if (p == null) return;
        try {
            p.out.close();
        } catch (Exception ignored) {
            // 关不上也要删
        }
        resolver.delete(p.uri, null, null);
    }

    /** 文件实际叫什么（系统可能加了 (1)） */
    String displayName(Uri uri, String fallback) {
        android.database.Cursor c = null;
        try {
            c = resolver.query(uri, new String[]{MediaStore.MediaColumns.DISPLAY_NAME},
                    null, null, null);
            if (c != null && c.moveToFirst()) return c.getString(0);
        } catch (Exception ignored) {
            // 查不到就用原名
        } finally {
            if (c != null) c.close();
        }
        return fallback;
    }

    private static String safeName(String name) {
        String n = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|\\n\\r]", "").trim();
        return n.isEmpty() ? "下载文件" : n;
    }
}
