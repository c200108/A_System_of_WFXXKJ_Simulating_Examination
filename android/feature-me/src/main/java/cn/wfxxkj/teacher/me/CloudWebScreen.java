package cn.wfxxkj.teacher.me;

import android.app.DownloadManager;
import android.content.Context;
import android.net.Uri;
import android.os.Environment;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import org.json.JSONObject;

import java.util.Arrays;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.StateView;

/**
 * 在 APP 里打开个人云盘（服务端 2.25.0，网页 cloud.js 的 openCloud）。
 *
 * <p>云盘是服务器上的 OpenList，文件管理界面是它自己的网页，所以这一页是个内嵌浏览器。免登录的做法和网页端一样：
 * 先问教学平台要一个云盘令牌（POST /api/cloud/open），放进云盘网页的 localStorage（键 wfxxcloud:token），再打开 /cloud/。
 * 放令牌这一步用 loadDataWithBaseURL 以服务器地址为源跑一小段脚本，所以不经过 OpenList 页面头上那段改键名的脚本。
 *
 * <p>上传走系统文件选择器，下载交给系统「下载管理」存进「下载」。离开这一页时清掉内嵌浏览器存的数据，
 * 换个老师登录这台手机打不开上一位的云盘。
 */
final class CloudWebScreen extends Screen {
    private WebView web;
    private StateView state;
    private ValueCallback<Uri[]> pendingUpload;

    @Override
    public String title() {
        return "个人云盘";
    }

    @Override
    public String subtitle() {
        return CloudUi.url().replaceFirst("^https?://", "");
    }

    @Override
    protected View onCreateView(Context c) {
        FrameLayout root = new FrameLayout(c);
        web = new WebView(c);
        WebSettings ws = web.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setDatabaseEnabled(true);
        ws.setAllowFileAccess(false);
        ws.setLoadWithOverviewMode(true);
        ws.setUseWideViewPort(true);
        ws.setBuiltInZoomControls(true);
        ws.setDisplayZoomControls(false);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, android.webkit.WebResourceRequest req) {
                // 本服务器的页面留在这里，别的网址（OpenList 里的外链）交给系统浏览器
                String u = req.getUrl().toString();
                if (sameServer(u)) return false;
                Sys.openUrl(ctx(), u);
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> cb, FileChooserParams params) {
                if (pendingUpload != null) pendingUpload.onReceiveValue(null);
                pendingUpload = cb;
                boolean multiple = params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE;
                pickFilesOrCancel(new String[]{"*/*"}, multiple, files -> {
                    ValueCallback<Uri[]> p = pendingUpload;
                    pendingUpload = null;
                    if (p != null) p.onReceiveValue(files.isEmpty() ? null : files.toArray(new Uri[0]));
                });
                return true;
            }
        });
        web.setDownloadListener((url, userAgent, disposition, mime, length) -> download(url, userAgent, disposition, mime));
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        state = new StateView(c);
        root.addView(state, new FrameLayout.LayoutParams(-1, -1));
        return root;
    }

    private static String origin() {
        Uri u = Uri.parse(CloudUi.url());
        return u.getScheme() + "://" + u.getEncodedAuthority();
    }

    private static boolean sameServer(String url) {
        return url.startsWith(origin() + "/") || url.equals(origin());
    }

    @Override
    protected void onFirstShow() {
        open();
    }

    private void open() {
        state.loading();
        run(MeApi::cloudOpen, r -> {
            state.hide();
            String key = Json.str(r, "storage_key", "wfxxcloud:token");
            String path = Json.str(r, "url", "/cloud/");
            String target = origin() + (path.startsWith("/") ? path : "/" + path);
            String js = "<!doctype html><meta charset=utf-8><script>try{localStorage.setItem("
                    + JSONObject.quote(key) + "," + JSONObject.quote(Json.str(r, "token")) + ")}catch(e){}"
                    + "location.replace(" + JSONObject.quote(target) + ")</script>";
            web.loadDataWithBaseURL(origin() + "/cloud/__app_login", js, "text/html", "utf-8",
                    origin() + "/cloud/__app_login");
        }, e -> {
            int code = e instanceof ApiException ? ((ApiException) e).code : 0;
            String title = code == 403 ? "无法访问个人云盘" : "个人云盘暂时打不开";
            String msg = code == 401 ? "登录已过期，请重新登录后再打开" : e.getMessage();
            state.error(title + "：" + msg, this::open);
            return true;
        });
    }

    @Override
    public List<Action> actions() {
        return Arrays.asList(
                Action.icon(R.drawable.ic_refresh, "刷新", () -> web.reload()),
                Action.menu(R.drawable.ic_open_in_new, "用浏览器打开", () -> {
                    if (!Sys.openUrl(ctx(), CloudUi.url())) toast("这台手机没有浏览器");
                }),
                Action.menu(R.drawable.ic_content_copy, "复制云盘网址", () -> {
                    Sys.copy(ctx(), "云盘网址", CloudUi.url());
                    toast("云盘网址已复制");
                }),
                Action.menu(R.drawable.ic_restart_alt, "重新登录云盘", this::open));
    }

    @Override
    public boolean onBack() {
        if (web != null && web.canGoBack()) {
            String back = web.copyBackForwardList().getCurrentIndex() > 0
                    ? web.copyBackForwardList().getItemAtIndex(web.copyBackForwardList().getCurrentIndex() - 1).getUrl()
                    : "";
            // 退到放令牌的那一页就是到头了，直接关
            if (!back.contains("__app_login") && !back.startsWith("data:") && !back.startsWith("about:")) {
                web.goBack();
                return true;
            }
        }
        return false;
    }

    /** 下载交给系统「下载管理」：通知栏有进度，存进「下载」 */
    private void download(String url, String userAgent, String disposition, String mime) {
        if (!url.startsWith("http")) {
            toast("这个文件请用浏览器打开云盘下载");
            return;
        }
        String name = URLUtil.guessFileName(url, disposition, mime);
        try {
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
            req.setTitle(name);
            req.setMimeType(mime);
            req.addRequestHeader("User-Agent", userAgent);
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) req.addRequestHeader("Cookie", cookie);
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            DownloadManager dm = ctx().getSystemService(DownloadManager.class);
            dm.enqueue(req);
            toast("开始下载「" + name + "」，完成后在「下载」里");
        } catch (Exception e) {
            Dialogs.alert(ctx(), "下载不了", "系统下载器没接下这个文件（" + e.getMessage() + "）。可以「用浏览器打开」云盘再下载。");
        }
    }

    @Override
    protected void onDestroy() {
        if (pendingUpload != null) {
            pendingUpload.onReceiveValue(null);
            pendingUpload = null;
        }
        if (web != null) {
            web.stopLoading();
            web.destroy();
        }
        // 云盘令牌不留在手机上：下次进来重新换一个
        WebStorage.getInstance().deleteAllData();
    }
}
