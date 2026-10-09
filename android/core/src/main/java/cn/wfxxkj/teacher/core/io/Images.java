package cn.wfxxkj.teacher.core.io;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.LruCache;
import android.widget.ImageView;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Http;

/**
 * 加载服务器上的图片（题目配图、反馈截图）到 ImageView。带内存缓存，列表滚动不重复下载；
 * 大图按控件宽度缩小解码，省内存。
 */
public final class Images {
    private static final LruCache<String, Bitmap> CACHE =
            new LruCache<String, Bitmap>((int) Math.min(Runtime.getRuntime().maxMemory() / 8, 32L * 1024 * 1024)) {
                @Override
                protected int sizeOf(String key, Bitmap value) {
                    return value.getByteCount();
                }
            };

    private Images() {}

    /** url 可以是 "/uploads/xx.png" 这样的站内路径 */
    public static void load(final ImageView iv, final String url, final int maxWidthPx) {
        if (url == null || url.isEmpty()) {
            iv.setImageDrawable(null);
            return;
        }
        final String key = url + "@" + maxWidthPx;
        iv.setTag(key);
        Bitmap hit = CACHE.get(key);
        if (hit != null) {
            iv.setImageBitmap(hit);
            return;
        }
        iv.setImageDrawable(null);
        Screen.io().execute(() -> {
            Bitmap bm = null;
            try {
                byte[] data = Http.bytes(url);
                BitmapFactory.Options o = new BitmapFactory.Options();
                o.inJustDecodeBounds = true;
                BitmapFactory.decodeByteArray(data, 0, data.length, o);
                int sample = 1;
                while (maxWidthPx > 0 && o.outWidth / (sample * 2) >= maxWidthPx) sample *= 2;
                o = new BitmapFactory.Options();
                o.inSampleSize = sample;
                bm = BitmapFactory.decodeByteArray(data, 0, data.length, o);
            } catch (Exception ignored) {
                // 图片坏了或下载失败：留空
            }
            final Bitmap result = bm;
            if (result != null) CACHE.put(key, result);
            Screen.main().post(() -> {
                if (key.equals(iv.getTag()) && result != null) iv.setImageBitmap(result);
            });
        });
    }
}
