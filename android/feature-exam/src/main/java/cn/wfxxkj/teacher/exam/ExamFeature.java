package cn.wfxxkj.teacher.exam;

import cn.wfxxkj.teacher.core.nav.Screen;

/**
 * 模块入口：考试（发布考试、成绩、阅卷、成绩分析、导出）
 * 主界面（app 模块的 Features）从这里取页面，拼成底部标签。
 *
 * <p>页面关系：考试列表 {@link ExamListScreen} → 考试详情 {@link ExamDetailScreen}
 * → 提交记录 {@link SubmissionListScreen} → 单份答卷 / 阅卷 {@link SubmissionScreen}；
 * 详情页还能进成绩分析 {@link AnalysisScreen}、样卷 {@link SamplePaperScreen}。
 */
public final class ExamFeature {
    private ExamFeature() {}

    /** 考试管理 */
    public static Screen exams() {
        return new ExamListScreen();
    }
}
