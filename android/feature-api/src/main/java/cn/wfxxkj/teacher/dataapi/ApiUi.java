package cn.wfxxkj.teacher.dataapi;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.util.Fmt;

/** 几个显示用的小工具 */
final class ApiUi {
    private ApiUi() {}

    static String templateName(String k) {
        switch (k) {
            case "answer": return "答题回收";
            case "self_eval": return "自我评价";
            case "peer_eval": return "同伴互评";
            case "survey": return "问卷调查";
            default: return "自定义";
        }
    }

    static String typeName(String t) {
        switch (t) {
            case "answer": return "答题";
            case "self_eval": return "自评";
            case "peer_eval": return "互评";
            case "survey": return "问卷";
            case "event": return "操作记录";
            case "data": return "数据";
            default: return t.isEmpty() ? "—" : t;
        }
    }

    /** 8 / 10、8 或空 */
    static String score(JSONObject r) {
        Double s = Json.dblOrNull(r, "score");
        if (s == null) return "";
        Double m = Json.dblOrNull(r, "max_score");
        return m == null ? Fmt.num(s) : Fmt.num(s) + " / " + Fmt.num(m);
    }

    static String pretty(Object json) {
        try {
            if (json instanceof JSONObject) return ((JSONObject) json).toString(2);
            if (json instanceof org.json.JSONArray) return ((org.json.JSONArray) json).toString(2);
        } catch (Exception ignored) {
            // 落到下面
        }
        return String.valueOf(json);
    }
}
