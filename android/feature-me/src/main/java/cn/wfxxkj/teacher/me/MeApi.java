package cn.wfxxkj.teacher.me;

import android.net.Uri;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;

/**
 * 「我的」用到的接口（对应网页 api.js 里的账号、反馈、更新日志几组）。
 * 全是同步方法，只能在 Screen.run(...) 的后台任务里调。
 */
final class MeApi {
    private MeApi() {}

    // ---------- 自己的账号 ----------

    static JSONObject me() throws ApiException {
        return Http.getObj("/auth/me", null);
    }

    /** 只能改 name / grade_class / contact 三项 */
    static JSONObject updateMe(String name, String gradeClass, String contact) throws ApiException {
        return Http.asObj(Http.patch("/auth/me", Json.of("name", name, "grade_class", gradeClass,
                "contact", contact)));
    }

    static void changePassword(String oldPwd, String newPwd) throws ApiException {
        Http.post("/auth/password", Json.of("old_password", oldPwd, "new_password", newPwd));
    }

    // ---------- 账号管理（管理员） ----------

    static List<JSONObject> users() throws ApiException {
        return Json.list(Http.getArr("/auth/users", null));
    }

    static JSONObject createUser(String username, String password, String name, String role) throws ApiException {
        return Http.postObj("/auth/users", Json.of("username", username, "password", password,
                "name", name, "role", role));
    }

    /** 只传要改的字段 */
    static JSONObject updateUser(long id, JSONObject data) throws ApiException {
        return Http.asObj(Http.patch("/auth/users/" + id, data));
    }

    static void disableUser(long id) throws ApiException {
        Http.delete("/auth/users/" + id, null);
    }

    /** action：enable / disable / delete。返回 {affected} */
    static JSONObject bulkUsers(List<Object> ids, String action) throws ApiException {
        return Http.postObj("/auth/users/bulk", Json.of("ids", ids, "action", action));
    }

    /** 全部班级（含停用的），给老师分班用 */
    static List<JSONObject> classes() throws ApiException {
        return Json.list(Http.getArr("/classes", Params.of("include_inactive", "true")));
    }

    // ---------- 需求反馈 ----------

    /** 公开区（只有审核通过的） */
    static List<JSONObject> feedbackList(String category) throws ApiException {
        return Json.list(Http.getArr("/feedback", Params.of("category", category)));
    }

    /** 管理员：全部（含待审核、已拒绝、联系方式） */
    static List<JSONObject> feedbackAll() throws ApiException {
        return Json.list(Http.getArr("/feedback/all", null));
    }

    static int feedbackPending() throws ApiException {
        return Http.getObj("/feedback/pending-count", null).optInt("pending", 0);
    }

    static JSONObject feedbackCreate(String author, String contact, String category, String content,
                                     List<String> images) throws ApiException {
        return Http.postObj("/feedback", Json.of("author", author, "contact", contact, "category", category,
                "content", content, "images", images));
    }

    /** 上传一张配图，返回 /uploads/feedback/xxx.png */
    static String feedbackUploadImage(Uri file) throws ApiException {
        Object r = Http.upload("/feedback/images", null, "file", file);
        return Json.str(Http.asObj(r), "image_url");
    }

    static JSONObject feedbackReply(long id, String text) throws ApiException {
        return Http.postObj("/feedback/" + id + "/reply", Json.of("reply", text));
    }

    static void feedbackReplyDelete(long rid) throws ApiException {
        Http.delete("/feedback/replies/" + rid, null);
    }

    static JSONObject feedbackLike(long id) throws ApiException {
        return Http.postObj("/feedback/" + id + "/like", null);
    }

    /** status：approved / rejected / pending */
    static void feedbackReview(long id, String status, String note) throws ApiException {
        Http.patch("/feedback/" + id + "/review", Json.of("status", status, "note", note == null ? "" : note));
    }

    static JSONObject feedbackReviewBulk(List<Object> ids, String status) throws ApiException {
        return Http.postObj("/feedback/review-bulk", Json.of("ids", ids, "status", status));
    }

    static void feedbackDelete(long id) throws ApiException {
        Http.delete("/feedback/" + id, null);
    }

    // ---------- 更新日志（管理员） ----------

    static List<JSONObject> changelog() throws ApiException {
        return Json.list(Http.getArr("/changelog", null));
    }

    static List<JSONObject> changelogTypes() throws ApiException {
        return Json.list(Http.getArr("/changelog/types", null));
    }

    /** 公开：{version, released_on} */
    static JSONObject changelogLatest() throws ApiException {
        return Http.getObj("/changelog/latest", null);
    }

    static void changelogCreate(String version, String releasedOn, String type, String content) throws ApiException {
        Http.post("/changelog", Json.of("version", version, "released_on", releasedOn,
                "change_type", type, "content", content));
    }

    static void changelogDelete(long id) throws ApiException {
        Http.delete("/changelog/" + id, null);
    }

    // ---------- 站点 ----------

    /** 公开的站点配置（学校名、平台名、页脚） */
    static JSONObject siteConfig() throws ApiException {
        return Http.getObj("/config", null);
    }

    // ---------- 回收站（每位老师都有；老师只看自己删的，管理员看所有人删的） ----------

    /** {items: [{id, kind, kind_name, title, detail, deleted_by_name, deleted_at, days_left}], kinds, keep_days} */
    static JSONObject recycle() throws ApiException {
        return Http.getObj("/recycle", null);
    }

    static JSONObject recycleRestore(List<Integer> ids) throws ApiException {
        return Http.postObj("/recycle/restore", Json.of("ids", ids));
    }

    static JSONObject recycleDestroy(List<Integer> ids) throws ApiException {
        return Http.postObj("/recycle/destroy", Json.of("ids", ids));
    }

    /** 清空（管理员） */
    static void recycleClear() throws ApiException {
        Http.delete("/recycle", null);
    }

    // ---------- 数据备份与系统更新（只有部署时建的系统管理员） ----------

    /** {agent: {installed…}, busy: 任务或 null, recent: [任务…]} */
    static JSONObject systemStatus() throws ApiException {
        return Http.getObj("/system/status", null);
    }

    /** {id, action, label, status: queued/running/ok/failed/lost, message, log} */
    static JSONObject systemJob(String id) throws ApiException {
        return Http.getObj("/system/jobs/" + id, null);
    }

    static Http.Download exportBackup() throws ApiException {
        return Http.download("GET", "/system/backup/export", null, null);
    }

    static JSONObject importBackup(Uri file, String password) throws ApiException {
        java.util.Map<String, String> f = new java.util.HashMap<>();
        f.put("password", password);
        return Http.asObj(Http.upload("/system/backup/import", null, "file", file, f));
    }

    static JSONObject updateFromGithub(String password) throws ApiException {
        return Http.asObj(Http.post("/system/update/github", Params.of("password", password)));
    }

    static JSONObject updateFromZip(Uri file, String password) throws ApiException {
        java.util.Map<String, String> f = new java.util.HashMap<>();
        f.put("password", password);
        return Http.asObj(Http.upload("/system/update/upload", null, "file", file, f));
    }
}
