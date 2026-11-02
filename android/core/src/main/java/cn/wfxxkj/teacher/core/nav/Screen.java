package cn.wfxxkj.teacher.core.nav;

import android.app.Activity;
import android.content.Context;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.view.View;

import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.ui.Ui;

/**
 * 一个页面。APP 是单个 Activity，页面是轻量的 Screen 对象，由主界面按标签页各自维护一个栈。
 *
 * <p>写一个页面：
 * <pre>
 * public class ExamListScreen extends Screen {
 *     public String title() { return "考试管理"; }
 *
 *     protected View onCreateView(Context ctx) {
 *         list = new ItemList&lt;&gt;(ctx, binder);
 *         return list;
 *     }
 *
 *     protected void onFirstShow() { load(); }
 *
 *     void load() {
 *         run(() -&gt; ExamApi.list(), items -&gt; list.setItems(items));
 *     }
 * }
 * </pre>
 *
 * <p>生命周期：{@link #onCreateView} → {@link #onFirstShow}（只一次，适合首次加载数据）→
 * {@link #onShow}（每次回到栈顶，例如从编辑页返回）→ {@link #onDestroy}。
 * 转屏、分屏改变窗口大小时页面不会重建，界面用 GridBox / ItemList 这类按宽度自动排版的组件即可。
 */
public abstract class Screen {

    /** 后台任务，在后台线程里跑，可以抛异常 */
    public interface Task<T> {
        T call() throws Exception;
    }

    /** 成功回调（主线程） */
    public interface Ok<T> {
        void done(T result);
    }

    /** 失败回调（主线程）。返回 true 表示自己处理了，不再弹默认的错误提示 */
    public interface Err {
        boolean failed(Exception e);
    }

    /** 被打开的页面关掉时带回来的结果 */
    public interface ResultListener {
        void onResult(Object result);
    }

    private static final ExecutorService IO = Executors.newFixedThreadPool(4, new ThreadFactory() {
        private int n;

        @Override
        public synchronized Thread newThread(Runnable r) {
            Thread t = new Thread(r, "wfxx-io-" + (++n));
            t.setDaemon(true);
            return t;
        }
    });
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private Host host;
    private Context ctx;
    private View view;
    private boolean destroyed;
    private boolean shownOnce;
    private ResultListener resultListener;
    private Object pendingResult;
    private boolean hasResult;
    /** 嵌在别的页面里（例如工作台的分页）时，顶栏由外层页面管 */
    private Screen parent;

    // ---------- 给子类重写 ----------

    /** 顶栏标题 */
    public abstract String title();

    /** 顶栏副标题（可选） */
    public String subtitle() {
        return null;
    }

    /** 建界面。只调一次 */
    protected abstract View onCreateView(Context ctx);

    /** 第一次显示（界面已建好），适合加载数据 */
    protected void onFirstShow() {}

    /** 每次回到栈顶（包括第一次） */
    protected void onShow() {}

    /** 被别的页面盖住 */
    protected void onHide() {}

    protected void onDestroy() {}

    /** 顶栏右侧的操作。内容变了调 {@link #invalidateChrome()} */
    public List<Action> actions() {
        return Collections.emptyList();
    }

    /** 右下角的浮动按钮（新建之类的主操作），没有返回 null */
    public Action fab() {
        return null;
    }

    /** 返回键：返回 true 表示自己处理了（例如先退出多选） */
    public boolean onBack() {
        return false;
    }

    /** 这个页面是否显示顶栏的返回箭头（栈底的页面由外面决定，不用管） */
    public boolean showBack() {
        return true;
    }

    // ---------- 主界面调用 ----------

    public final View attach(Host host, Context ctx) {
        if (view == null) {
            this.host = host;
            this.ctx = ctx;
            view = onCreateView(ctx);
        }
        return view;
    }

    public final void dispatchShow() {
        if (destroyed) return;
        if (!shownOnce) {
            shownOnce = true;
            onFirstShow();
        }
        onShow();
    }

    public final void dispatchHide() {
        if (!destroyed) onHide();
    }

    public final void dispatchDestroy() {
        if (destroyed) return;
        destroyed = true;
        onDestroy();
        if (hasResult && resultListener != null) {
            final ResultListener l = resultListener;
            final Object r = pendingResult;
            MAIN.post(() -> l.onResult(r));
        }
    }

    /** 嵌入另一个页面时由外层调用 */
    public final void setParent(Screen parent) {
        this.parent = parent;
    }

    public final View view() {
        return view;
    }

    // ---------- 子类可用 ----------

    public final Context ctx() {
        return ctx;
    }

    public final Activity activity() {
        return host.activity();
    }

    public final Host host() {
        return host;
    }

    public final Session session() {
        return Session.get();
    }

    public final boolean isDestroyed() {
        return destroyed;
    }

    /** 宽屏（≥600dp，平板、横屏大手机） */
    public final boolean wide() {
        return Ui.wide(ctx);
    }

    public final int dp(float v) {
        return Ui.dp(ctx, v);
    }

    public final void push(Screen s) {
        host.push(s);
    }

    /** 打开一个页面，它用 {@link #finish(Object)} 关掉时把结果带回来 */
    public final void push(Screen s, ResultListener onResult) {
        s.resultListener = onResult;
        host.push(s);
    }

    /** 关掉自己 */
    public final void finish() {
        if (parent != null) {
            parent.finish();
            return;
        }
        host.pop(this);
    }

    /** 关掉自己并把结果交给打开者 */
    public final void finish(Object result) {
        pendingResult = result;
        hasResult = true;
        finish();
    }

    public final void invalidateChrome() {
        if (parent != null) parent.invalidateChrome();
        else if (host != null) host.invalidateChrome(this);
    }

    public final void toast(CharSequence msg) {
        host.toast(msg);
    }

    public final void snack(CharSequence msg, String action, Runnable onAction) {
        host.snack(msg, action, onAction);
    }

    public final void pickFiles(String[] mimeTypes, boolean multiple, Host.FilesPicked cb) {
        host.pickFiles(mimeTypes, multiple, files -> {
            if (!destroyed) cb.onPicked(files);
        });
    }

    public final void pickFile(String[] mimeTypes, final FilePicked cb) {
        pickFiles(mimeTypes, false, files -> {
            if (!files.isEmpty()) cb.onPicked(files.get(0));
        });
    }

    public interface FilePicked {
        void onPicked(Uri file);
    }

    /** 主线程上稍后执行（页面已关闭就不执行） */
    public final void post(Runnable r, long delayMs) {
        MAIN.postDelayed(() -> {
            if (!destroyed) guard("定时任务", r);
        }, delayMs);
    }

    /**
     * 在主线程上跑一段改界面的代码；出错交给主界面（弹错误详情、关掉这个页面），不让整个 APP 退出。
     */
    public final void guard(String where, Runnable r) {
        try {
            r.run();
        } catch (Throwable t) {
            if (host != null) host.screenFailed(this, t, title() + " · " + where);
            else throw t;
        }
    }

    // ---------- 后台任务 ----------

    /** 后台跑 task，成功了在主线程回调 ok；失败弹出错误提示。页面关了就不再回调 */
    public final <T> void run(Task<T> task, Ok<T> ok) {
        run(task, ok, null);
    }

    public final <T> void run(final Task<T> task, final Ok<T> ok, final Err err) {
        IO.execute(() -> {
            final T r;
            try {
                r = task.call();
            } catch (final Exception e) {
                MAIN.post(() -> {
                    if (destroyed) return;
                    guard("处理出错", () -> {
                        if (err != null && err.failed(e)) return;
                        showError(e);
                    });
                });
                return;
            } catch (final Throwable t) {
                // 内存不够、手机上缺某个系统方法这类 Error：以前没接，后台线程直接把 APP 带走
                MAIN.post(() -> {
                    if (!destroyed && host != null) host.screenFailed(this, t, title() + " · 加载数据");
                });
                return;
            }
            MAIN.post(() -> {
                // 数据回来画页面这一步最容易因为数据和预想的不一样而出错
                if (!destroyed && ok != null) guard("显示数据", () -> ok.done(r));
            });
        });
    }

    /** 同 run，期间盖一层「正在…」挡住操作（保存、删除、导出这类不能重复点的事） */
    public final <T> void runBusy(CharSequence message, final Task<T> task, final Ok<T> ok) {
        runBusy(message, task, ok, null);
    }

    public final <T> void runBusy(CharSequence message, final Task<T> task, final Ok<T> ok, final Err err) {
        host.showBusy(message);
        run(task, r -> {
            host.hideBusy();
            if (ok != null) ok.done(r);
        }, e -> {
            host.hideBusy();
            return err != null && err.failed(e);
        });
    }

    /** 默认的报错方式：一句话提示。登录失效的不用提示（会自动回登录页） */
    public final void showError(Exception e) {
        if (e instanceof ApiException) {
            ApiException ae = (ApiException) e;
            if (ae.code == 401) return;
            toast(ae.getMessage());
            return;
        }
        toast("出错了：" + e.getMessage());
    }

    /** 后台线程池（少数需要自己管线程的地方用） */
    public static ExecutorService io() {
        return IO;
    }

    public static Handler main() {
        return MAIN;
    }
}
