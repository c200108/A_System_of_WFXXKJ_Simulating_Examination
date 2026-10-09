package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.util.LruCache;
import android.widget.ImageView;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

import cn.wfxxkj.teacher.core.io.Images;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.session.Session;

/**
 * 反馈配图的加载。本站上传的图（/uploads/...）交给 core 的 Images；
 * 老师粘贴的外部网络图片自己下载 —— core 的 Http.bytes 下载失败时会把整个 APP 标成「连接已断开」，
 * 一张外链图打不开不该让顶上冒出断网提示。
 */
final class MeImages {
    private MeImages() {}

    private static final LruCache<String, Bitmap> CACHE = new LruCache<String, Bitmap>(8 * 1024 * 1024) {
        @Override
        protected int sizeOf(String key, Bitmap value) {
            return value.getByteCount();
        }
    };

    static void load(final ImageView iv, final String url, final int maxWidthPx) {
        String server = Session.get().server();
        boolean local = url.startsWith("/") || (!server.isEmpty() && url.startsWith(server + "/"));
        if (local) {
            Images.load(iv, url, maxWidthPx);
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
            HttpURLConnection conn = null;
            try {
                conn = (HttpURLConnection) new URL(url).openConnection();
                conn.setConnectTimeout(8000);
                conn.setReadTimeout(15000);
                conn.setInstanceFollowRedirects(true);
                InputStream in = conn.getInputStream();
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[16 * 1024];
                int n;
                while ((n = in.read(buf)) > 0 && out.size() < 10 * 1024 * 1024) out.write(buf, 0, n);
                in.close();
                byte[] data = out.toByteArray();
                BitmapFactory.Options o = new BitmapFactory.Options();
                o.inJustDecodeBounds = true;
                BitmapFactory.decodeByteArray(data, 0, data.length, o);
                int sample = 1;
                while (maxWidthPx > 0 && o.outWidth / (sample * 2) >= maxWidthPx) sample *= 2;
                o = new BitmapFactory.Options();
                o.inSampleSize = sample;
                bm = BitmapFactory.decodeByteArray(data, 0, data.length, o);
            } catch (Exception ignored) {
                // 外链图打不开：留着占位底色
            } finally {
                if (conn != null) conn.disconnect();
            }
            final Bitmap result = bm;
            if (result != null) CACHE.put(key, result);
            Screen.main().post(() -> {
                if (key.equals(iv.getTag()) && result != null) iv.setImageBitmap(result);
            });
        });
    }

    /** 固定大小的图片框：FlowBox 量子视图时不看 LayoutParams，空图会被量成 0×0 */
    static final class Box extends ImageView {
        private final int w, h;

        Box(Context c, int wPx, int hPx) {
            super(c);
            w = wPx;
            h = hPx;
        }

        @Override
        protected void onMeasure(int ws, int hs) {
            setMeasuredDimension(w, h);
        }
    }
}
