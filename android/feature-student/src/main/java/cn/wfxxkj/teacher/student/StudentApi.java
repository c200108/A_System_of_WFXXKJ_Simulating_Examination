package cn.wfxxkj.teacher.student;

import android.net.Uri;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;

/**
 * 学生账号、班级相关的接口（后端 routers/students.py、routers/classes.py）。
 * 全是同步方法，只能在 Screen.run(...) 的后台任务里调。
 */
final class StudentApi {
    private StudentApi() {}

    // ---------- 学生账号 ----------

    /** 学生列表。classId 为 null = 全部；老师只拿得到自己班的（后端按班隔离） */
    static List<JSONObject> students(Integer classId, String keyword) throws ApiException {
        return Json.list(Http.getArr("/students", Params.of("class_id", classId).add("keyword", keyword)));
    }

    static JSONObject createStudent(JSONObject body) throws ApiException {
        return Http.asObj(Http.post("/students", body));
    }

    static JSONObject updateStudent(int id, JSONObject body) throws ApiException {
        return Http.asObj(Http.patch("/students/" + id, body));
    }

    /** 批量操作：delete / disable / enable / reset_password，返回受影响人数 */
    static int bulk(List<Integer> ids, String action) throws ApiException {
        JSONObject r = Http.asObj(Http.post("/students/bulk", Json.of("ids", ids, "action", action)));
        return Json.num(r, "affected");
    }

    /** 粘贴名单批量建号 */
    static JSONObject batch(Integer classId, String text) throws ApiException {
        return Http.asObj(Http.post("/students/batch", Json.of("class_id", classId, "text", text)));
    }

    /** 上传 Excel / CSV 导入 */
    static JSONObject importFile(Uri file, Integer classId) throws ApiException {
        return Http.asObj(Http.upload("/students/import", Params.of("class_id", classId), "file", file));
    }

    static Http.Download template() throws ApiException {
        return Http.download("GET", "/students/template.xlsx", null, null);
    }

    static Http.Download export(Integer classId, String keyword) throws ApiException {
        return Http.download("GET", "/students/export.xlsx",
                Params.of("class_id", classId).add("keyword", keyword), null);
    }

    // ---------- 班级 ----------

    /** 班级列表。mine = 只要自己名下的；includeInactive = 连停用的也要 */
    static List<JSONObject> classes(boolean mine, boolean includeInactive) throws ApiException {
        Params p = Params.of();
        if (mine) p.add("mine", "true");
        if (includeInactive) p.add("include_inactive", "true");
        return Json.list(Http.getArr("/classes", p));
    }

    /** 学生页下拉用：管理员看全校，老师只看自己带的班 */
    static List<JSONObject> pickableClasses(boolean admin) throws ApiException {
        return classes(!admin, false);
    }

    static JSONObject createClass(String grade, String name, Integer ownerId) throws ApiException {
        return Http.asObj(Http.post("/classes", Json.of("grade", grade, "name", name, "owner_id", ownerId)));
    }

    static JSONObject updateClass(int id, JSONObject body) throws ApiException {
        return Http.asObj(Http.patch("/classes/" + id, body));
    }

    /** 删除班级。force = 班里有人也删（学生变未分班），返回变成未分班的人数 */
    static int deleteClass(int id, boolean force) throws ApiException {
        JSONObject r = Http.asObj(Http.delete("/classes/" + id, Params.of("force", force ? "true" : null)));
        return Json.num(r, "detached");
    }

    static JSONObject batchClasses(String grade, int start, int end, String suffix) throws ApiException {
        return Http.asObj(Http.post("/classes/batch",
                Json.of("grade", grade, "start", start, "end", end, "suffix", suffix)));
    }

    static JSONObject bulkDeleteClasses(List<Integer> ids, boolean force) throws ApiException {
        return Http.asObj(Http.post("/classes/bulk", Json.of("ids", ids, "force", force)));
    }

    static int bulkOwner(List<Integer> ids, Integer ownerId) throws ApiException {
        JSONObject r = Http.asObj(Http.post("/classes/bulk-owner", Json.of("ids", ids, "owner_id", ownerId)));
        return Json.num(r, "updated");
    }

    /** 改学生的个别字段（班干部 class_role 等） */
    static JSONObject patchStudent(int id, JSONObject body) throws ApiException {
        return Http.asObj(Http.patch("/students/" + id, body));
    }

    /** 出现过的年级（新建班级时下拉用） */
    static List<String> grades() throws ApiException {
        return Json.strings(Http.getArr("/classes/grades", null));
    }

    // ---------- 在线座次（网页端 SeatSheet.vue 同一套接口） ----------

    /** {class_id, display, can_edit, sheet(可能为 null), students[]}；学生名单只在 can_edit 时给 */
    static JSONObject seatSheet(int cid) throws ApiException {
        return Http.getObj("/classes/" + cid + "/seat-sheet", null);
    }

    static JSONObject saveSeatSheet(int cid, JSONObject sheet) throws ApiException {
        return Http.asObj(Http.put("/classes/" + cid + "/seat-sheet", Json.of("sheet", sheet)));
    }

    static void deleteSeatSheet(int cid) throws ApiException {
        Http.delete("/classes/" + cid + "/seat-sheet", null);
    }

    /** 一键排座：只算不存，返回 {assignments:[{cell,text,…}], seats, warnings[]} */
    static JSONObject seatPlan(int cid, JSONObject body) throws ApiException {
        return Http.asObj(Http.post("/classes/" + cid + "/seat-plan", body));
    }

    /** {totals: {学生 id: 总分}, recent: [{id, student_id, delta, reason, author_name, created_at}]} */
    static JSONObject points(int cid) throws ApiException {
        return Http.getObj("/classes/" + cid + "/points", null);
    }

    static JSONObject addPoint(int cid, int studentId, int delta, String reason) throws ApiException {
        return Http.asObj(Http.post("/classes/" + cid + "/points",
                Json.of("student_id", studentId, "delta", delta, "reason", reason)));
    }

    static JSONObject addPoints(int cid, List<Integer> ids, int delta, String reason) throws ApiException {
        return Http.asObj(Http.post("/classes/" + cid + "/points/bulk",
                Json.of("student_ids", ids, "delta", delta, "reason", reason)));
    }

    static JSONObject undoPoint(int cid, int pid) throws ApiException {
        return Http.asObj(Http.delete("/classes/" + cid + "/points/" + pid, null));
    }

    // ---------- 课堂情况日志 ----------

    static List<JSONObject> logs(int cid) throws ApiException {
        return Json.list(Http.getArr("/classes/" + cid + "/logs", null));
    }

    static JSONObject saveLog(int cid, Integer lid, String date, String title, String content) throws ApiException {
        JSONObject body = Json.of("lesson_date", date, "title", title, "content", content);
        return Http.asObj(lid == null ? Http.post("/classes/" + cid + "/logs", body)
                : Http.put("/classes/" + cid + "/logs/" + lid, body));
    }

    static void deleteLog(int cid, int lid) throws ApiException {
        Http.delete("/classes/" + cid + "/logs/" + lid, null);
    }

    // ---------- 上机座次表文件（图片或 Excel） ----------

    static JSONObject uploadSeatFile(int cid, Uri file) throws ApiException {
        return Http.asObj(Http.upload("/classes/" + cid + "/seat", null, "file", file));
    }

    static JSONObject deleteSeatFile(int cid) throws ApiException {
        return Http.asObj(Http.delete("/classes/" + cid + "/seat", null));
    }

    static Http.Download seatFile(int cid) throws ApiException {
        return Http.download("GET", "/classes/" + cid + "/seat/file", null, null);
    }

    /** 教师账号列表（管理员），分配班主任用 */
    static List<JSONObject> teachers() throws ApiException {
        return Json.list(Http.getArr("/auth/users", null));
    }
}
