package cn.wfxxkj.teacher.exam;

import android.content.Context;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.util.Fmt;

/**
 * 发布新考试 / 修改考试设置的弹层（网页「发布新考试」对话框）。
 * 发布：选试卷、起名、选班、四个开关，发完自动复制学生链接。
 * 修改：改名、改发给哪些班、四个开关（网页上只有列表里的开关，名字和班级改不了；后端支持，APP 补上）。
 */
final class PublishSheet {
    private PublishSheet() {}

    interface Done {
        void done(JSONObject exam);
    }

    /** 发布新考试：先取试卷和班级，再弹表单 */
    static void create(Screen s, Done done) {
        s.runBusy("正在准备…", () -> {
            ExamApi.ensureConfig();
            return new Object[]{ExamApi.papers(), ExamApi.classes()};
        }, r -> {
            @SuppressWarnings("unchecked") List<JSONObject> papers = (List<JSONObject>) r[0];
            @SuppressWarnings("unchecked") List<JSONObject> classes = (List<JSONObject>) r[1];
            if (papers.isEmpty()) {
                Dialogs.alert(s.ctx(), "还没有存档的试卷",
                        "先去「组卷」页生成一份试卷，并勾上「把这套卷子存档」，存档的试卷才能发布成考试。");
                return;
            }
            open(s, null, papers, classes, done);
        });
    }

    /** 修改已有考试的设置 */
    static void edit(Screen s, JSONObject exam, Done done) {
        s.runBusy("正在准备…", ExamApi::classes, classes -> open(s, exam, null, classes, done));
    }

    private static void open(Screen s, JSONObject exam, List<JSONObject> papers, List<JSONObject> classes, Done done) {
        Context c = s.ctx();
        boolean admin = s.session().isAdmin();
        boolean creating = exam == null;
        Sheet sheet = new Sheet(c, creating ? "发布新考试" : "修改考试设置");
        Form f = new Form(c);

        Form.Select paper = null;
        if (creating) {
            List<Option> opts = new ArrayList<>();
            for (JSONObject p : papers) {
                opts.add(new Option(p.optLong("id"), Json.str(p, "title"),
                        ExamUi.dot(Json.str(p, "code"), Json.num(p, "question_count") + " 题",
                                Fmt.date(Json.str(p, "created_at")))));
            }
            paper = f.select("选一份试卷", opts, papers.get(0).optLong("id")).required();
        }
        Form.Text title = f.text("考试名称", creating ? "" : Json.str(exam, "title"),
                creating ? "留空就用试卷标题" : null);
        if (!creating) title.required();

        List<Option> clsOpts = new ArrayList<>();
        for (JSONObject k : classes) {
            clsOpts.add(new Option(k.optLong("id"), Json.str(k, "display"),
                    k.has("student_count") ? Json.num(k, "student_count") + " 名学生" : null));
        }
        List<Object> picked = new ArrayList<>();
        if (!creating) for (Integer id : Json.ints(Json.arr(exam, "target_class_ids"))) picked.add((long) id);
        Form.Multi targets = f.multi("发给哪些班", clsOpts, picked)
                .placeholder(admin ? "不选 = 全体学生" : "不选 = 我带的全部班");
        targets.help((admin ? "不选就是全体学生；选了就只发给这几个班。"
                : "只能选自己带的班，不选就是我带的全部班。")
                + "学生在平台上只看得到发给自己班的考试；凭链接答题不受影响。");

        f.section("考试设置");
        Form.Toggle open = f.toggle("立即开放", "关掉后学生打不开，考试当天再开",
                creating ? ExamApi.defOpen : Json.bool(exam, "is_open"));
        Form.Toggle showScore = f.toggle("交卷看分数", "关掉则只提示交卷成功，成绩由老师公布",
                creating ? ExamApi.defShowScore : Json.bool(exam, "show_score"));
        Form.Toggle showAnswer = f.toggle("交卷看答案", "正式考试建议关，否则先考的学生能把答案带出去",
                creating ? ExamApi.defShowAnswer : Json.bool(exam, "show_answer"));
        Form.Toggle early = f.toggle("允许提前交卷", "默认要考试时间过一半、并且答完一半的题才能交卷；打开后全程随时能交",
                !creating && Json.bool(exam, "early_submit"));
        Form.Toggle retake = f.toggle("允许重考", "默认同一学号只能交一次",
                creating ? ExamApi.defRetake : Json.bool(exam, "allow_retake"));

        sheet.content(f.view());
        final Form.Select paperF = paper;
        final List<Object> before = new ArrayList<>(picked);
        sheet.buttons("取消", null, creating ? "发布并复制链接" : "保存", () -> {
            if (!f.validate()) return;
            JSONObject body = Json.of(
                    "title", title.value().isEmpty() ? null : title.value(),
                    "is_open", open.value(),
                    "show_score", showScore.value(),
                    "show_answer", showAnswer.value(),
                    "early_submit", early.value(),
                    "allow_retake", retake.value());
            List<Object> ids = targets.values();
            // 修改时班级没动就不发，免得把已删班级的旧记录冲掉
            if (creating || !sameSet(before, ids)) Json.put(body, "target_class_ids", ids);
            if (creating) Json.put(body, "paper_id", paperF.value());
            s.runBusy(creating ? "正在发布…" : "正在保存…",
                    () -> creating ? ExamApi.createExam(body) : ExamApi.updateExam(exam.optLong("id"), body),
                    saved -> {
                        sheet.dismiss();
                        if (creating) {
                            Sys.copy(c, "考试链接", ExamApi.linkOf(saved));
                            s.toast("已发布，学生链接已复制，发给学生就行");
                        } else {
                            s.toast("已保存");
                        }
                        done.done(saved);
                    });
        });
        sheet.show();
    }

    private static boolean sameSet(List<Object> a, List<Object> b) {
        if (a.size() != b.size()) return false;
        for (Object x : a) {
            boolean hit = false;
            for (Object y : b) if (Option.same(x, y)) hit = true;
            if (!hit) return false;
        }
        return true;
    }
}
