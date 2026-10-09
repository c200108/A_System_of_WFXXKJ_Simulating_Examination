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
}
