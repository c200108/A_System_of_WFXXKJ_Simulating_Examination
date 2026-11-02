package cn.wfxxkj.teacher.core.nav;

import android.app.Activity;
import android.net.Uri;

import java.util.List;

/**
 * 装页面的容器（主界面 MainActivity 实现它）。页面通过 {@link Screen} 上的同名方法间接调用，
 * 一般不用直接碰这个接口。
 */
public interface Host {

    interface FilesPicked {
        void onPicked(List<Uri> files);
    }

    Activity activity();

    /** 在当前标签页上压一个新页面 */
    void push(Screen screen);

    /** 关掉一个页面（一般是栈顶的那个） */
    void pop(Screen screen);

    /** 页面的标题、顶栏按钮、浮动按钮变了，重画顶栏 */
    void invalidateChrome(Screen screen);

    /** 切到某个底部标签（key 见各模块的 Tab 定义），并回到那个标签的首页 */
    void switchTab(String key);

    /**
     * 让老师选文件。mimeTypes 例如 {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}，
     * 传 {"image/*"} 选图片。取消选择时不回调。
     */
    void pickFiles(String[] mimeTypes, boolean multiple, FilesPicked callback);

    void toast(CharSequence message);

    /** 底部提示条，带一个操作按钮（例如「打开」「撤销」）；action 为 null 时就是普通提示 */
    void snack(CharSequence message, String action, Runnable onAction);

    /** 盖住全屏的「正在处理…」，期间点不了别的 */
    void showBusy(CharSequence message);

    void hideBusy();

    /** 退出登录回到登录页 */
    void logout(String message);

    /**
     * 页面出错了（建界面、数据回来画页面时抛了异常）：弹出错误详情、把这个页面关掉，APP 不退出。
     * 以前这里没人接，异常一路抛到系统，老师看到的就是「点开回到桌面」，什么信息都没有。
     */
    void screenFailed(Screen screen, Throwable error, String where);
}
