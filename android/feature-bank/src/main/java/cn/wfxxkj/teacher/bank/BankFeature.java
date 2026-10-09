package cn.wfxxkj.teacher.bank;

import cn.wfxxkj.teacher.core.nav.Screen;

/**
 * 模块入口：题库（题目管理、批量导入、仿真操作题）
 * 主界面（app 模块的 Features）从这里取页面，拼成「题库」标签顶部的三个分页。
 */
public final class BankFeature {
    private BankFeature() {}

    /** 题库管理 */
    public static Screen questions() {
        return new QuestionListScreen();
    }

    /** 批量导入 */
    public static Screen imports() {
        return new ImportScreen();
    }

    /** 仿真操作题 */
    public static Screen sims() {
        return new SimListScreen();
    }
}
