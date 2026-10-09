package cn.wfxxkj.teacher.bank;

import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;

/**
 * 题库模块用到的全部接口（对应网页 api.js 里 questions / imports / sims / dicts 那几组）。
 * 都是同步方法，只能在 Screen.run(...) 的后台任务里调。
 */
final class BankApi {
    private BankApi() {}

    // ---------- 字典 ----------

    /** 题型和知识范围清单（网页 onMounted 里取的 dicts） */
    static final class Dicts {
        final List<String> types = new ArrayList<>();
        final List<String> scopes = new ArrayList<>();
    }

    static Dicts dicts() throws ApiException {
        Dicts d = new Dicts();
        for (JSONObject o : Json.list(Http.getArr("/dicts", null))) {
            String cat = Json.str(o, "category");
            if ("qtype".equals(cat)) d.types.add(Json.str(o, "name"));
            else if ("scope".equals(cat)) d.scopes.add(Json.str(o, "name"));
        }
        return d;
    }

    // ---------- 题目 ----------

    /** 筛选条件，列表、导出共用（和后端 _filtered 一致） */
    static final class Filter {
        String keyword = "";
        String type = "";
        String scope = "";
        String source = "";
        int difficulty;          // 0 = 不限
        boolean onlyPinned;

        Params params() {
            Params p = Params.of("keyword", keyword).add("type", type).add("scope", scope)
                    .add("source", source);
            if (difficulty > 0) p.add("difficulty", difficulty);
            if (onlyPinned) p.add("pinned", "true");
            return p;
        }

        /** 除了题型以外设了几个条件（筛选按钮上的角标） */
        int extraCount() {
            int n = 0;
            if (!scope.isEmpty()) n++;
            if (!source.isEmpty()) n++;
            if (difficulty > 0) n++;
            if (onlyPinned) n++;
            return n;
        }

        boolean isEmpty() {
            return keyword.isEmpty() && type.isEmpty() && extraCount() == 0;
        }

        Filter copy() {
            Filter f = new Filter();
            f.keyword = keyword;
            f.type = type;
            f.scope = scope;
            f.source = source;
            f.difficulty = difficulty;
            f.onlyPinned = onlyPinned;
            return f;
        }
    }

    /** 一页题目：{total, items} */
    static JSONObject questions(Filter f, int page, int pageSize) throws ApiException {
        return Http.getObj("/questions", f.params().add("page", page).add("page_size", pageSize));
    }

    static JSONObject question(long id) throws ApiException {
        return Http.getObj("/questions/" + id, null);
    }

    static JSONObject stats() throws ApiException {
        return Http.getObj("/questions/stats", null);
    }

    static JSONObject create(JSONObject body) throws ApiException {
        return Http.asObj(Http.post("/questions", body));
    }

    static JSONObject update(long id, JSONObject body) throws ApiException {
        return Http.asObj(Http.put("/questions/" + id, body));
    }

    static void delete(long id) throws ApiException {
        Http.delete("/questions/" + id, null);
    }

    /** 恢复刚删掉的题（后端是软删除，删完给「撤销」用） */
    static void restore(long id) throws ApiException {
        Http.post("/questions/" + id + "/restore", null);
    }

    /** 上传配图，返回 /uploads/images/xx.png */
    static String uploadImage(Uri file) throws ApiException {
        Object r = Http.upload("/questions/upload-image", null, "file", file);
        String url = r instanceof JSONObject ? Json.str((JSONObject) r, "image_url") : "";
        if (url.isEmpty()) throw new ApiException(0, "图片上传失败");
        return url;
    }

    static Http.Download exportBank(Params filter, String name) throws ApiException {
        return Http.download("GET", "/questions/export.xlsx", filter.add("filename", name), null);
    }

    // ---------- 导入 ----------

    static Http.Download template() throws ApiException {
        return Http.download("GET", "/imports/template", null, null);
    }

    static JSONObject importFile(Uri file) throws ApiException {
        return Http.asObj(Http.upload("/imports/questions", null, "file", file));
    }

    static List<JSONObject> importLogs() throws ApiException {
        return Json.list(Http.getArr("/imports/logs", null));
    }

    // ---------- 仿真任务 ----------

    static List<JSONObject> sims(String kind) throws ApiException {
        return Json.list(Http.getArr("/sims", Params.of("kind", kind)));
    }

    static JSONObject sim(long id) throws ApiException {
        return Http.getObj("/sims/" + id, null);
    }

    static JSONObject simBlank(String kind) throws ApiException {
        return Json.obj(Http.getObj("/sims/blank", Params.of("kind", kind)), "env");
    }

    static JSONObject simCreate(String kind, String title, JSONObject env, JSONArray checks) throws ApiException {
        return Http.asObj(Http.post("/sims", Json.of("kind", kind, "title", title, "env", env,
                "checks", checks == null ? new JSONArray() : checks)));
    }

    static JSONObject simUpdate(long id, JSONObject body) throws ApiException {
        return Http.asObj(Http.patch("/sims/" + id, body));
    }

    static JSONObject simDelete(long id) throws ApiException {
        Object r = Http.delete("/sims/" + id, null);
        return r instanceof JSONObject ? (JSONObject) r : new JSONObject();
    }

    /** 拿初始环境和终态的差异生成检查点草稿：{checks, count} */
    static JSONObject simPropose(String kind, JSONObject env, JSONObject state) throws ApiException {
        return Http.asObj(Http.post("/sims/propose", Json.of("kind", kind, "env", env, "state", state)));
    }

    /** 试判：{score, full, results:[{no, ok, desc, why}]} */
    static JSONObject simTry(long id, JSONObject state, JSONArray checks) throws ApiException {
        return Http.asObj(Http.post("/sims/" + id + "/try", Json.of("state", state, "checks", checks)));
    }
}
