package cn.wfxxkj.teacher;

import android.webkit.JavascriptInterface;

/**
 * 页面里的 window.WfxxApp。网页那一侧见 frontend/src/appBridge.js。
 *
 * 这些方法在 WebView 的后台线程上被调用：读数据、写文件直接做，
 * 碰界面的事一律交给 {@link MainActivity} 切回主线程。
 *
 * 令牌只交给本服务器的页面：页面里万一嵌了别的网站（比如反馈里贴的外链图片所在页），
 * 那边调 getToken 拿到的是空串。
 */
final class AppBridge {
    private final MainActivity host;
    private final Prefs prefs;
    private final FileSaver saver;

    AppBridge(MainActivity host, Prefs prefs, FileSaver saver) {
        this.host = host;
        this.prefs = prefs;
        this.saver = saver;
    }

    @JavascriptInterface
    public String getToken() {
        return host.isOnOwnServer() ? prefs.token() : "";
    }

    @JavascriptInterface
    public String getUser() {
        return host.isOnOwnServer() ? prefs.userJson() : "";
    }

    @JavascriptInterface
    public String getAppVersion() {
        return BuildConfig.VERSION_NAME;
    }

    @JavascriptInterface
    public void logout() {
        host.logout(null);
    }

    @JavascriptInterface
    public void onAuthExpired() {
        host.onAuthExpired();
    }

    @JavascriptInterface
    public void onPasswordChanged(String password) {
        if (host.isOnOwnServer()) prefs.updatePassword(password);
    }

    @JavascriptInterface
    public void copyText(String text) {
        host.copyText(text);
    }

    @JavascriptInterface
    public void print(String title) {
        host.printPage(title);
    }

    @JavascriptInterface
    public void setDarkMode(boolean dark) {
        host.setDarkMode(dark);
    }

    // ------------------------------------------------------------ 分块存文件

    @JavascriptInterface
    public String fileBegin(String name, String mime) {
        return saver.begin(name, mime);
    }

    @JavascriptInterface
    public boolean fileChunk(String id, String base64) {
        return saver.chunk(id, base64);
    }

    @JavascriptInterface
    public void fileEnd(String id) {
        host.onFileSaved(saver.end(id));
    }

    @JavascriptInterface
    public void fileAbort(String id) {
        saver.abort(id);
    }
}
