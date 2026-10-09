package cn.wfxxkj.teacher.paper;

import cn.wfxxkj.teacher.core.nav.Screen;

/**
 * 模块入口：组卷（按卷面结构或按题型抽题、抽题预览、试卷预览/答案卷/在线自测、导出、组卷历史）
 * 主界面（app 模块的 Features）从这里取页面，拼成底部标签。
 */
public final class PaperFeature {
    private PaperFeature() {}

    /** 组卷 */
    public static Screen home() {
        return new ComposeScreen();
    }
}
