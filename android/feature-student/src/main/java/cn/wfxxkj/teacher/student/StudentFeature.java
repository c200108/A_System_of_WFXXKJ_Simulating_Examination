package cn.wfxxkj.teacher.student;

import cn.wfxxkj.teacher.core.nav.Screen;

/**
 * 模块入口：学生（学生账号、班级）
 * 主界面（app 模块的 Features）从这里取页面，拼成底部标签。
 */
public final class StudentFeature {
    private StudentFeature() {}

    /** 学生账号：增删改查、按班筛选搜索、导入导出、批量重置密码/调班/启停用/删除 */
    public static Screen students() {
        return new StudentListScreen();
    }

    /** 班级：按年级看班、建班改班删班、分配老师、班级详情和名单 */
    public static Screen classes() {
        return new ClassListScreen();
    }
}
