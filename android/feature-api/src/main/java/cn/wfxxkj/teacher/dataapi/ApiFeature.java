package cn.wfxxkj.teacher.dataapi;

import cn.wfxxkj.teacher.core.nav.Screen;

/**
 * 模块入口：API（5.1.2）。老师建接口，第三方教学网页往里送学生答题、自评互评等数据，
 * 这里看数据列表、来源网页、图表，复制接收地址和密钥。和网页版教师端「API」菜单一一对应。
 * 各老师的 API 互不相通，管理员看全部（后端 routers/data_apis.py 拦）。
 */
public final class ApiFeature {
    private ApiFeature() {}

    public static Screen home() {
        return new ApiListScreen();
    }
}
