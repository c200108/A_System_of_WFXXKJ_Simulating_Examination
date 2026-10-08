package cn.wfxxkj.teacher;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.text.TextUtils;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

/**
 * 登录以后的主界面：一个铺满屏幕的 WebView，打开服务器上的教师端网页。
 *
 * 网页有的功能这里全都有，而且网页以后加了功能，APP 不用重新发版。
 * 外壳只补网页在 WebView 里做不到、或者做得不好的事：
 * 保持登录（{@link SessionKeeper}）、断网提示和自动重连、存文件、复制、打印、
 * 选文件上传、返回键、系统栏配色。
 */
public class MainActivity extends Activity implements SessionKeeper.Listener {
    private static final int REQ_FILE = 11;

    private Prefs prefs;
    private SessionKeeper keeper;
    private FileSaver saver;
    private WebView web;
    private View root;
    private ProgressBar progress;
    private TextView offlineBar;
    private View errorView;
    private TextView errorText;
    private View splash;
    private View saved;
    private TextView savedText;

    private final Handler main = new Handler(Looper.getMainLooper());
    private ConnectivityManager.NetworkCallback netCallback;
    private ValueCallback<Uri[]> fileCallback;
    private String server;
    private volatile String currentHost = "";
    private boolean reloadAfterRelogin;
    private boolean pageFailed;
    private long lastBack;
    private Uri savedUri;
    private String savedMime;

    private final Runnable hideSaved = new Runnable() {
        @Override
        public void run() {
            saved.setVisibility(View.GONE);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new Prefs(this);
        server = prefs.server();
        if (!prefs.loggedIn()) {
            toLogin(null);
            return;
        }
        setContentView(R.layout.activity_main);
        Ui.edgeToEdge(this, true);

        root = findViewById(R.id.root);
        web = findViewById(R.id.web);
        progress = findViewById(R.id.progress);
        offlineBar = findViewById(R.id.offline);
        errorView = findViewById(R.id.error);
        errorText = findViewById(R.id.error_text);
        splash = findViewById(R.id.splash);
        saved = findViewById(R.id.saved);
        savedText = findViewById(R.id.saved_text);
        ((TextView) findViewById(R.id.splash_title)).setText(
                TextUtils.isEmpty(prefs.brand()) ? getString(R.string.app_name) : prefs.brand());

        final View content = findViewById(R.id.content);
        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                int[] in = Ui.insets(insets);
                content.setPadding(in[2], in[0], in[3], in[1]);
                return insets;
            }
        });

        findViewById(R.id.retry).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                errorView.setVisibility(View.GONE);
                pageFailed = false;
                web.reload();
                keeper.kick();
            }
        });
        findViewById(R.id.switch_server).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                startActivity(new Intent(MainActivity.this, LoginActivity.class)
                        .putExtra(LoginActivity.EXTRA_EDIT, true));
            }
        });
        findViewById(R.id.saved_open).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                openSaved();
            }
        });

        saver = new FileSaver(this);
        keeper = new SessionKeeper(prefs, this);
        setupWebView();
        watchNetwork();

        if (state != null) web.restoreState(state);
        else web.loadUrl(server + "/js");
    }

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    private void setupWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100); // 系统字体调大时页面不变形；页面自己的字号已经按手机排过
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setUserAgentString(s.getUserAgentString() + " WfxxTeacherApp/" + BuildConfig.VERSION_NAME);
        CookieManager.getInstance().setAcceptCookie(true);

        web.addJavascriptInterface(new AppBridge(this, prefs, saver), "WfxxApp");
        web.setWebViewClient(new Client());
        web.setWebChromeClient(new Chrome());
        web.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String ua, String disposition, String mime, long len) {
                downloadUrl(url, disposition, mime);
            }
        });
    }

    // ------------------------------------------------------------ 生命周期

    @Override
    protected void onResume() {
        super.onResume();
        if (keeper != null) keeper.start();
        if (web != null) web.onResume();
    }

    @Override
    protected void onPause() {
        // 退到后台：心跳停掉，页面里的定时器（成绩页自动刷新这些）也停，不耗电不耗流量
        if (keeper != null) keeper.stop();
        if (web != null) web.onPause();
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (web != null) web.saveState(out);
    }

    @Override
    protected void onDestroy() {
        if (netCallback != null) {
            try {
                ((ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE))
                        .unregisterNetworkCallback(netCallback);
            } catch (Exception ignored) {
                // 没注册上就算了
            }
        }
        if (keeper != null) keeper.shutdown();
        if (web != null) {
            web.removeJavascriptInterface("WfxxApp");
            web.destroy();
        }
        super.onDestroy();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (errorView.getVisibility() == View.VISIBLE) {
            super.onBackPressed();
            return;
        }
        if (web.canGoBack()) {
            web.goBack();
            return;
        }
        long now = System.currentTimeMillis();
        if (now - lastBack < 2000) {
            super.onBackPressed();
        } else {
            lastBack = now;
            Toast.makeText(this, "再按一次退出", Toast.LENGTH_SHORT).show();
        }
    }

    // ------------------------------------------------------------ 网络

    private void watchNetwork() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        netCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network network) {
                main.post(new Runnable() {
                    @Override
                    public void run() {
                        keeper.kick();
                        if (pageFailed) {
                            pageFailed = false;
                            errorView.setVisibility(View.GONE);
                            web.reload();
                        }
                    }
                });
            }
        };
        try {
            cm.registerDefaultNetworkCallback(netCallback);
        } catch (Exception e) {
            netCallback = null;
        }
    }

    @Override
    public void onOnlineChanged(boolean online, String message) {
        if (online) {
            offlineBar.setVisibility(View.GONE);
        } else {
            offlineBar.setText("连接已断开，正在自动重连…  " + (message == null ? "" : message));
            offlineBar.setVisibility(View.VISIBLE);
        }
    }

    @Override
    public void onTokenRefreshed(String token, String userJson) {
        String js = "window.__wfxxSetToken && window.__wfxxSetToken("
                + JSONObject.quote(token) + "," + JSONObject.quote(userJson == null ? "" : userJson) + ")";
        web.evaluateJavascript(js, null);
        if (reloadAfterRelogin) {
            reloadAfterRelogin = false;
            web.reload();
        }
    }

    @Override
    public void onSessionLost(String message) {
        logout(message);
    }

    // ------------------------------------------------------------ 给 AppBridge 用（后台线程调进来）

    boolean isOnOwnServer() {
        return !TextUtils.isEmpty(currentHost) && currentHost.equalsIgnoreCase(hostOf(server));
    }

    void onAuthExpired() {
        main.post(new Runnable() {
            @Override
            public void run() {
                reloadAfterRelogin = true;
                keeper.forceRelogin();
            }
        });
    }

    void logout(final String message) {
        main.post(new Runnable() {
            @Override
            public void run() {
                prefs.logout();
                CookieManager.getInstance().removeAllCookies(null);
                // 网页那边的 localStorage 里也有令牌，一起清掉
                web.evaluateJavascript("try{localStorage.removeItem('token');localStorage.removeItem('user')}catch(e){}", null);
                toLogin(message);
            }
        });
    }

    void copyText(final String text) {
        main.post(new Runnable() {
            @Override
            public void run() {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                cm.setPrimaryClip(ClipData.newPlainText("链接", text));
                // 安卓 13 起系统自己会弹「已复制」，再弹一个就重复了
                if (Build.VERSION.SDK_INT < 33) {
                    Toast.makeText(MainActivity.this, "已复制", Toast.LENGTH_SHORT).show();
                }
            }
        });
    }

    void printPage(final String title) {
        main.post(new Runnable() {
            @Override
            public void run() {
                PrintManager pm = (PrintManager) getSystemService(Context.PRINT_SERVICE);
                String name = TextUtils.isEmpty(title) ? getString(R.string.app_name) : title;
                pm.print(name, web.createPrintDocumentAdapter(name),
                        new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());
            }
        });
    }

    void setDarkMode(final boolean value) {
        main.post(new Runnable() {
            @Override
            public void run() {
                // 系统栏底色跟网页的顶栏、底部标签栏一个颜色（Element Plus 的 --el-bg-color）
                root.setBackgroundColor(value ? Color.parseColor("#141414") : Color.WHITE);
                Ui.setLightBars(MainActivity.this, !value);
            }
        });
    }

    void onFileSaved(final Uri uri) {
        main.post(new Runnable() {
            @Override
            public void run() {
                if (uri == null) {
                    Toast.makeText(MainActivity.this, "保存失败，请检查手机存储空间", Toast.LENGTH_LONG).show();
                    return;
                }
                savedUri = uri;
                savedMime = getContentResolver().getType(uri);
                String name = saver.displayName(uri, "文件");
                savedText.setText("已保存到「下载/教学平台」\n" + name);
                saved.setVisibility(View.VISIBLE);
                main.removeCallbacks(hideSaved);
                main.postDelayed(hideSaved, 6000);
            }
        });
    }

    // ------------------------------------------------------------ 文件

    private void openSaved() {
        if (savedUri == null) return;
        saved.setVisibility(View.GONE);
        Intent i = new Intent(Intent.ACTION_VIEW)
                .setDataAndType(savedUri, TextUtils.isEmpty(savedMime) ? "*/*" : savedMime)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            startActivity(Intent.createChooser(i, "用什么打开"));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "手机上没有能打开这种文件的应用", Toast.LENGTH_LONG).show();
        }
    }

    /** 网页里普通的下载链接（题目配图之类）：交给系统下载管理器，带上登录令牌 */
    private void downloadUrl(String url, String disposition, String mime) {
        try {
            android.app.DownloadManager.Request r = new android.app.DownloadManager.Request(Uri.parse(url));
            String name = URLUtil.guessFileName(url, disposition, mime);
            r.setMimeType(mime);
            if (sameHost(url)) r.addRequestHeader("Authorization", "Bearer " + prefs.token());
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) r.addRequestHeader("Cookie", cookie);
            r.setNotificationVisibility(android.app.DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(android.os.Environment.DIRECTORY_DOWNLOADS, "教学平台/" + name);
            ((android.app.DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(r);
            Toast.makeText(this, "开始下载：" + name, Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            openExternal(url);
        }
    }

    private void openExternal(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "没有可以打开这个链接的浏览器", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE && fileCallback != null) {
            Uri[] picked = null;
            if (resultCode == RESULT_OK && data != null) {
                ClipData clip = data.getClipData(); // 一次选了多个
                if (clip != null && clip.getItemCount() > 0) {
                    picked = new Uri[clip.getItemCount()];
                    for (int k = 0; k < picked.length; k++) picked[k] = clip.getItemAt(k).getUri();
                } else if (data.getData() != null) {
                    picked = new Uri[]{data.getData()};
                }
            }
            fileCallback.onReceiveValue(picked);
            fileCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    // ------------------------------------------------------------ 杂项

    private void toLogin(String message) {
        Intent i = new Intent(this, LoginActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK);
        if (message != null) i.putExtra(LoginActivity.EXTRA_MESSAGE, message);
        startActivity(i);
        finish();
    }

    private static String hostOf(String url) {
        try {
            Uri u = Uri.parse(url);
            return u.getHost() + ":" + u.getPort();
        } catch (Exception e) {
            return "";
        }
    }

    private boolean sameHost(String url) {
        return hostOf(url).equalsIgnoreCase(hostOf(server));
    }

    /**
     * 选文件的 Intent。不用 params.createIntent()：网页写的 accept 是扩展名（.xlsx,.csv），
     * 它直接当 MIME 类型用，很多手机上就弹「没有应用可以执行此操作」。这里把扩展名换成 MIME。
     */
    private static Intent chooserIntent(WebChromeClient.FileChooserParams params) {
        java.util.LinkedHashSet<String> mimes = new java.util.LinkedHashSet<>();
        android.webkit.MimeTypeMap map = android.webkit.MimeTypeMap.getSingleton();
        for (String raw : params.getAcceptTypes()) {
            for (String part : raw.split(",")) {
                String a = part.trim().toLowerCase(java.util.Locale.ROOT);
                if (a.isEmpty()) continue;
                if (a.contains("/")) {
                    mimes.add(a);
                } else {
                    String ext = a.startsWith(".") ? a.substring(1) : a;
                    String m = map.getMimeTypeFromExtension(ext);
                    if (m != null) mimes.add(m);
                    if (ext.equals("csv")) mimes.add("text/comma-separated-values");
                    if (ext.equals("xls") || ext.equals("xlsx")) mimes.add("application/vnd.ms-excel");
                }
            }
        }
        Intent i = new Intent(Intent.ACTION_GET_CONTENT).addCategory(Intent.CATEGORY_OPENABLE);
        if (mimes.size() == 1) {
            i.setType(mimes.iterator().next());
        } else {
            i.setType("*/*");
            if (!mimes.isEmpty()) i.putExtra(Intent.EXTRA_MIME_TYPES, mimes.toArray(new String[0]));
        }
        if (params.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
            i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        }
        return Intent.createChooser(i, "选择文件");
    }

    private final class Client extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri u = request.getUrl();
            String scheme = u.getScheme() == null ? "" : u.getScheme();
            if ((scheme.equals("http") || scheme.equals("https")) && sameHost(u.toString())) {
                return false; // 本服务器的页面就在 APP 里开
            }
            // 外链（更新日志里的参考网址这类）、mailto、tel 交给系统
            openExternal(u.toString());
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            currentHost = hostOf(url);
            progress.setVisibility(View.VISIBLE);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            currentHost = hostOf(url);
            progress.setVisibility(View.GONE);
            if (splash.getVisibility() == View.VISIBLE && !pageFailed) {
                splash.animate().alpha(0f).setDuration(200).withEndAction(new Runnable() {
                    @Override
                    public void run() {
                        splash.setVisibility(View.GONE);
                    }
                });
            }
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (!request.isForMainFrame()) return;
            pageFailed = true;
            splash.setVisibility(View.GONE);
            errorText.setText("打开 " + server + " 失败：" + error.getDescription()
                    + "\n\n请检查网络，或确认服务器已开机。网络恢复后会自动重新加载。");
            errorView.setVisibility(View.VISIBLE);
        }
    }

    private final class Chrome extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            progress.setProgress(newProgress);
            progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
        }

        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                         FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = callback;
            try {
                startActivityForResult(chooserIntent(params), REQ_FILE);
                return true;
            } catch (ActivityNotFoundException e) {
                fileCallback = null;
                Toast.makeText(MainActivity.this, "找不到可以选文件的应用", Toast.LENGTH_SHORT).show();
                return false;
            }
        }
    }
}
