package cn.wfxxkj.teacher.paper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;

/**
 * 组卷相关的接口（后端 backend/app/routers/papers.py）。全部同步，只能在 Screen.run(...) 的后台任务里调。
 */
final class PaperApi {
    private PaperApi() {}

    /** 站点配置（/api/config），组卷要用其中的 school 和 paper 两段 */
    static JSONObject config() throws ApiException {
        return Http.getObj("/config", null);
    }

    /** 字典：知识范围（scope）、题型（qtype） */
    static List<JSONObject> dicts() throws ApiException {
        return Json.list(Http.getArr("/dicts", null));
    }

    /** 只算名额分布，不真的抽题 */
    static JSONObject previewPlan(JSONObject payload) throws ApiException {
        return Http.postObj("/papers/preview-plan", payload);
    }

    /** 抽题组卷（payload.save = true 时顺便存档，返回的 paper_id 不为空） */
    static JSONObject generate(JSONObject payload) throws ApiException {
        return Http.postObj("/papers/generate", payload);
    }

    /** 历史试卷（新的在前） */
    static List<JSONObject> papers() throws ApiException {
        JSONArray a = Http.getArr("/papers", Params.of("limit", 200));
        return Json.list(a);
    }

    /** 打开一份历史试卷，结构和 generate 的返回一样 */
    static JSONObject paper(long id) throws ApiException {
        return Http.getObj("/papers/" + id, null);
    }

    static void delete(long id) throws ApiException {
        Http.delete("/papers/" + id, null);
    }

    /** 把整份卷子（generate / paper 的返回）导成 Excel */
    static Http.Download exportXlsx(JSONObject paper) throws ApiException {
        return Http.download("POST", "/papers/export/xlsx", null, paper);
    }

    /** 导出学生答题网页（单个 html 文件，可以直接发给学生） */
    static Http.Download exportStudentHtml(JSONObject paper) throws ApiException {
        return Http.download("POST", "/papers/export/student-html", null, paper);
    }
}
