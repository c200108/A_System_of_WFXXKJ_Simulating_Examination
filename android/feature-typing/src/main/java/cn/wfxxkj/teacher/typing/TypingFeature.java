package cn.wfxxkj.teacher.typing;

import cn.wfxxkj.teacher.core.nav.Screen;

/**
 * 模块入口：打字训练（打字成绩与学情分析、练习文本库）
 * 主界面（app 模块的 Features）从这里取页面，拼成底部标签。
 */
public final class TypingFeature {
    private TypingFeature() {}

    /** 打字学情：成绩列表、概况，从这里进学情分析 */
    public static Screen records() {
        return new RecordListScreen();
    }

    /** 练习文本 */
    public static Screen texts() {
        return new TextListScreen();
    }
}
