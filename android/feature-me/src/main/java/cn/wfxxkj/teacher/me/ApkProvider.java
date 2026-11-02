package cn.wfxxkj.teacher.me;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * 把下载好的新版 apk <b>只读</b>地交给系统安装器（「检查更新」用，见 {@link AppUpdate}）。
 *
 * 安卓 7 起不能把 file:// 地址交给别的应用，得用 content://。一般用 AndroidX 的 FileProvider，
 * 这个 APP 不依赖任何第三方库，就自己写这一小段：只认缓存目录 updates/ 下的 .apk，
 * 不能写、不能删、不能列目录。不对外导出，安装器靠 Intent 上临时授予的读权限来读。
 */
public class ApkProvider extends ContentProvider {

    static final String DIR = "updates";
    static final String MIME = "application/vnd.android.package-archive";

    static String authority(Context c) {
        return c.getPackageName() + ".apkprovider";
    }

    static Uri uriFor(Context c, File apk) {
        return new Uri.Builder().scheme("content").authority(authority(c))
                .appendPath(apk.getName()).build();
    }

    /** content://…/文件名 → 缓存目录 updates/ 下那个文件；别的一律不认 */
    private File fileFor(Uri uri) throws FileNotFoundException {
        String name = uri.getLastPathSegment();
        if (name == null || !name.matches("[A-Za-z0-9._-]+\\.apk") || uri.getPathSegments().size() != 1) {
            throw new FileNotFoundException(String.valueOf(uri));
        }
        File f = new File(new File(getContext().getCacheDir(), DIR), name);
        if (!f.isFile()) throw new FileNotFoundException(f.getName());
        return f;
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("只读");
        return ParcelFileDescriptor.open(fileFor(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public String getType(Uri uri) {
        return MIME;
    }

    /** 安装器会问文件名和大小（显示在确认页上） */
    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        File f;
        try {
            f = fileFor(uri);
        } catch (FileNotFoundException e) {
            return null;
        }
        String[] cols = projection != null ? projection
                : new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
        MatrixCursor c = new MatrixCursor(cols, 1);
        Object[] row = new Object[cols.length];
        for (int i = 0; i < cols.length; i++) {
            if (OpenableColumns.DISPLAY_NAME.equals(cols[i])) row[i] = f.getName();
            else if (OpenableColumns.SIZE.equals(cols[i])) row[i] = f.length();
        }
        c.addRow(row);
        return c;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("只读");
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        throw new UnsupportedOperationException("只读");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        throw new UnsupportedOperationException("只读");
    }
}
