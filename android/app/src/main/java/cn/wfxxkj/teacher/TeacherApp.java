package cn.wfxxkj.teacher;

import android.app.Application;

import cn.wfxxkj.teacher.core.session.Session;

/** 进程启动时初始化登录状态 */
public class TeacherApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        Session.init(this);
        // 漏网的异常（主界面没接住的）让 APP 退出前先记下来，下次打开时弹给老师看（见 core/util/Crash）
        final Thread.UncaughtExceptionHandler system = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            cn.wfxxkj.teacher.core.util.Crash.save(this, error);
            if (system != null) system.uncaughtException(thread, error);
        });
    }
}
