package cn.wfxxkj.teacher;

import java.util.Arrays;
import java.util.List;

import cn.wfxxkj.teacher.bank.BankFeature;
import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.HubScreen;
import cn.wfxxkj.teacher.core.nav.TabSpec;
import cn.wfxxkj.teacher.exam.ExamFeature;
import cn.wfxxkj.teacher.me.MeFeature;
import cn.wfxxkj.teacher.paper.PaperFeature;
import cn.wfxxkj.teacher.student.StudentFeature;
import cn.wfxxkj.teacher.typing.TypingFeature;

/**
 * 底部标签栏上的五个标签，和网页版教师端的顶部菜单一一对应：
 * 组卷 / 题库（题库管理、批量导入、仿真操作题）/ 考试（考试管理、打字学情、练习文本）/
 * 学生（学生账号、班级）/ 我的。
 *
 * 各功能模块互不依赖，标签怎么拼在这里决定。加一个模块：新建 feature-xxx，
 * 在 settings.gradle 和 app/build.gradle 里登记，再在这里放到某个标签下。
 */
final class Features {
    private Features() {}

    static List<TabSpec> tabs() {
        return Arrays.asList(
                new TabSpec("paper", "组卷", R.drawable.ic_edit_note_outlined, R.drawable.ic_edit_note,
                        PaperFeature::home),
                new TabSpec("bank", "题库", R.drawable.ic_library_books_outlined, R.drawable.ic_library_books,
                        () -> new HubScreen("题库", "bank", Arrays.asList(
                                HubScreen.page("题库管理", BankFeature::questions),
                                HubScreen.page("批量导入", BankFeature::imports),
                                HubScreen.page("仿真操作题", BankFeature::sims)))),
                new TabSpec("exams", "考试", R.drawable.ic_assignment_outlined, R.drawable.ic_assignment,
                        () -> new HubScreen("考试", "exams", Arrays.asList(
                                HubScreen.page("考试管理", ExamFeature::exams),
                                HubScreen.page("打字学情", TypingFeature::records),
                                HubScreen.page("练习文本", TypingFeature::texts)))),
                new TabSpec("students", "学生", R.drawable.ic_groups_outlined, R.drawable.ic_groups,
                        () -> new HubScreen("学生", "students", Arrays.asList(
                                HubScreen.page("学生账号", StudentFeature::students),
                                HubScreen.page("班级", StudentFeature::classes)))),
                new TabSpec("me", "我的", R.drawable.ic_person_outlined, R.drawable.ic_person,
                        MeFeature::home));
    }
}
