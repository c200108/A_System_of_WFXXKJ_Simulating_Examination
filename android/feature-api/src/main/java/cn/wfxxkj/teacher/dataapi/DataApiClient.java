package cn.wfxxkj.teacher.dataapi;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;

/** API 板块的接口（后端 routers/data_apis.py）。同步方法，只在 Screen.run 的后台任务里调。 */
final class DataApiClient {
    private DataApiClient() {}

    /** 列表：{items, templates, teachers?} */
    static JSONObject list(Integer ownerId) throws ApiException {
        return Http.getObj("/data-apis", Params.of("owner_id", ownerId));
    }

    static JSONObject create(String name, String desc, String template) throws ApiException {
        return Http.postObj("/data-apis", Json.of("name", name, "description", desc, "template", template));
    }

    static JSONObject get(int id) throws ApiException {
        return Http.getObj("/data-apis/" + id, null);
    }

    static JSONObject update(int id, JSONObject body) throws ApiException {
        return Http.asObj(Http.put("/data-apis/" + id, body));
    }

    static void delete(int id) throws ApiException {
        Http.delete("/data-apis/" + id, null);
    }

    static JSONObject rotate(int id, String which, boolean enable) throws ApiException {
        return Http.postObj("/data-apis/" + id + "/rotate-token", Json.of("which", which, "enable", enable));
    }

    /** 数据表单一页：{total, items, columns, options, type_names} */
    static JSONObject records(int id, int page, Params filters) throws ApiException {
        Params p = filters == null ? Params.of() : filters;
        return Http.getObj("/data-apis/" + id + "/records", p.add("page", page).add("size", 30));
    }

    static void flag(int id, List<Integer> ids, String flag) throws ApiException {
        Http.patch("/data-apis/" + id + "/records", Json.of("ids", ids, "flag", flag));
    }

    static void deleteRecords(int id, List<Integer> ids) throws ApiException {
        Http.post("/data-apis/" + id + "/records/delete", Json.of("ids", ids));
    }

    static List<JSONObject> sources(int id) throws ApiException {
        return Json.list(Json.arr(Http.getObj("/data-apis/" + id + "/sources", null), "items"));
    }

    static JSONObject stats(int id, Params filters) throws ApiException {
        return Http.getObj("/data-apis/" + id + "/stats", filters);
    }

    static JSONObject test(int id) throws ApiException {
        return Http.postObj("/data-apis/" + id + "/test", null);
    }

    static Http.Download export(int id) throws ApiException {
        return Http.download("GET", "/data-apis/" + id + "/export", Params.of("format", "xlsx"), null);
    }

    /** 接收地址按 APP 连的服务器地址拼（后端在 nginx 后面看到的 Host 不带端口） */
    static String endpoint(JSONObject api) {
        return Http.absolute("/api/hook/" + Json.str(api, "key"));
    }

    static String sdk() {
        return Http.absolute("/api/hook/sdk.js");
    }
}
