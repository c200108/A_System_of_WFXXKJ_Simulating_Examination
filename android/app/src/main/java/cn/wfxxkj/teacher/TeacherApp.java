package cn.wfxxkj.teacher;

import android.app.Application;

import cn.wfxxkj.teacher.core.session.Session;

/** 进程启动时初始化登录状态 */
public class TeacherApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        Session.init(this);
    }
}
