package cn.wfxxkj.teacher.exam;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Collection;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;
import cn.wfxxkj.teacher.core.session.Session;

/**
 * 考试模块要用的接口（对应网页 api.js 里 exams / submissions / examStats / examPaper /
 * examAnalysis / exportScores / exportDeskPack 那几个）。全部同步，只能在 Screen.run 的后台任务里调。
 */
final class ExamApi {
    private ExamApi() {}

    // ---------- 服务器配置（及格线、发布默认值、学生链接前缀） ----------

    /** 及格线（百分比），取不到配置时按 60 */
    static volatile int passScore = 60;
    /** 发布考试时四个开关的默认值：开放、交卷看分、交卷看答案、可重考 */
    static volatile boolean defOpen = true, defShowScore = true, defShowAnswer = false, defRetake = false;
    /** 配置里指定的学生访问地址（PUBLIC_BASE_URL），空 = 用 APP 登录时填的服务器地址 */
    static volatile String publicBase = "";
    private static volatile boolean configLoaded;

    /** 读一次 /config（公开接口）。失败不要紧，用默认值 */
    static void ensureConfig() {
        if (configLoaded) return;
        try {
            JSONObject c = Http.getObj("/config", null);
            publicBase = Json.str(c, "public_base_url").replaceAll("/+$", "");
            JSONObject exam = Json.obj(c, "exam");
            passScore = exam.optInt("pass_score", 60);
            JSONObject d = Json.obj(exam, "defaults");
            defOpen = d.optBoolean("is_open", true);
            defShowScore = d.optBoolean("show_score", true);
            defShowAnswer = d.optBoolean("show_answer", false);
            defRetake = d.optBoolean("allow_retake", false);
            configLoaded = true;
        } catch (ApiException ignored) {
            // 取不到就用默认值，不影响使用
        }
    }

    /** 学生答题链接：/take/{token}。和网页 studentLink 同一个规则 */
    static String linkOf(JSONObject exam) {
        String base = publicBase.isEmpty() ? Session.get().server() : publicBase;
        return base.replaceAll("/+$", "") + "/take/" + Json.str(exam, "token");
    }

    // ---------- 考试 ----------

    static List<JSONObject> exams() throws ApiException {
        ensureConfig();
        return Json.list(Http.getArr("/exams", null));
    }

    /** 列表接口才带 owner_name / can_edit，所以单场也从列表里找 */
    static JSONObject exam(long id) throws ApiException {
        for (JSONObject e : exams()) if (e.optLong("id") == id) return e;
        throw new ApiException(404, "这场考试已经不在了，可能被删除了");
    }

    static JSONObject createExam(JSONObject body) throws ApiException {
        return Http.postObj("/exams", body);
    }

    static JSONObject updateExam(long id, JSONObject body) throws ApiException {
        return Http.asObj(Http.patch("/exams/" + id, body));
    }

    static void deleteExam(long id) throws ApiException {
        Http.delete("/exams/" + id, null);
    }

    /** 存档的试卷（发布时选） */
    static List<JSONObject> papers() throws ApiException {
        return Json.list(Http.getArr("/papers", null));
    }

    /** 能发给哪些班：老师只列自己名下的，管理员列全校 */
    static List<JSONObject> classes() throws ApiException {
        Params p = Session.get().isAdmin() ? null : Params.of("mine", "true");
        return Json.list(Http.getArr("/classes", p));
    }

    static JSONObject stats(long id) throws ApiException {
        return Http.getObj("/exams/" + id + "/stats", null);
    }

    static JSONObject paper(long id) throws ApiException {
        return Http.getObj("/exams/" + id + "/paper", null);
    }

    /** 成绩分析。classes：班级名；students：答卷 id。都空 = 全体 */
    static JSONObject analysis(long id, Collection<?> classes, Collection<?> students) throws ApiException {
        Params p = Params.of();
        if (students != null && !students.isEmpty()) p.add("students", join(students));
        else if (classes != null && !classes.isEmpty()) p.add("classes", join(classes));
        return Http.getObj("/exams/" + id + "/analysis", p);
    }

    static Http.Download exportScores(long id) throws ApiException {
        return Http.download("GET", "/exams/" + id + "/export.xlsx", null, null);
    }

    /** 桌面考试包（.ekb）：交卷地址填 APP 连的这台服务器，和网页传 location.origin 一样 */
    static Http.Download exportDeskPack(long id) throws ApiException {
        return Http.download("GET", "/desk/export/" + id, Params.of("server", Session.get().server()), null);
    }

    // ---------- 答卷 ----------

    static List<JSONObject> submissions(long examId) throws ApiException {
        return Json.list(Http.getArr("/exams/" + examId + "/submissions", null));
    }

    static JSONObject submission(long examId, long subId) throws ApiException {
        return Http.getObj("/exams/" + examId + "/submissions/" + subId, null);
    }

    /** 人工给分：scores 是 {题目id: 得分} */
    static JSONObject gradeManual(long examId, long subId, Map<String, Integer> scores) throws ApiException {
        JSONObject s = new JSONObject();
        Iterator<Map.Entry<String, Integer>> it = scores.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<String, Integer> e = it.next();
            Json.put(s, e.getKey(), e.getValue());
        }
        return Http.asObj(Http.patch("/exams/" + examId + "/submissions/" + subId + "/manual", Json.of("scores", s)));
    }

    static void deleteSubmission(long examId, long subId) throws ApiException {
        Http.delete("/exams/" + examId + "/submissions/" + subId, null);
    }

    /** 批量删答卷，返回实际删掉几份 */
    static int deleteSubmissions(long examId, Collection<?> ids) throws ApiException {
        JSONObject r = Http.postObj("/exams/" + examId + "/submissions/delete", Json.of("ids", new JSONArray(ids)));
        return r.optInt("deleted", ids.size());
    }

    private static String join(Collection<?> items) {
        StringBuilder sb = new StringBuilder();
        for (Object o : items) {
            if (sb.length() > 0) sb.append(',');
            sb.append(o instanceof Double && (Double) o == Math.rint((Double) o)
                    ? String.valueOf(((Double) o).longValue()) : String.valueOf(o));
        }
        return sb.toString();
    }
}
