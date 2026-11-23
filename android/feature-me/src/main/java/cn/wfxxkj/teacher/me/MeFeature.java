package cn.wfxxkj.teacher.me;

import cn.wfxxkj.teacher.core.nav.Screen;

/**
 * 模块入口：我的（账号资料、账号管理、需求反馈、更新日志、设置、关于）
 * 主界面（app 模块的 Features）从这里取页面，拼成底部标签。
 */
public final class MeFeature {
    private MeFeature() {}

    /** 我的 */
    public static Screen home() {
        return new MeHomeScreen();
    }

    /** 需求反馈（点顶上的置顶提醒进来） */
    public static Screen feedback() {
        return new FeedbackScreen();
    }

    /** 每个页面顶上的置顶提醒（服务端 2.24.0），主界面放在顶栏下面 */
    public static PinnedNews pinnedNews(android.content.Context c, Runnable openFeedback) {
        return new PinnedNews(c, openFeedback);
    }
}
