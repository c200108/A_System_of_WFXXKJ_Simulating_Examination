package cn.wfxxkj.teacher.core.net;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/**
 * 把后端的报错翻成一句能读的中文。规则和网页版 api.js 的 explainError 一致：
 * detail 是字符串就直接用（后端本来就写的中文）；是数组（FastAPI 的 422 校验错误）就逐条翻译，
 * 最多说三条。
 */
public final class Errors {
    private Errors() {}

    private static final Map<String, String> FIELD_CN = new HashMap<>();

    static {
        String[][] f = {
                {"username", "用户名"}, {"password", "密码"}, {"new_password", "新密码"},
                {"old_password", "原密码"}, {"name", "姓名"}, {"role", "角色"},
                {"grade_class", "任教年级班级"}, {"contact", "联系方式"}, {"content", "内容"},
                {"author", "称呼"}, {"category", "类型"}, {"reply", "回复"}, {"version", "版本号"},
                {"released_on", "发布日期"}, {"change_type", "变动类型"}, {"title", "标题"},
                {"difficulty", "难度"}, {"mode", "语言"}, {"ids", "选中项"}, {"action", "操作"},
                {"stem", "题干"}, {"answer", "答案"}, {"score", "分值"}, {"options", "选项"},
                {"student_no", "学号"}, {"class_id", "班级"}, {"grade", "年级"},
                {"duration_minutes", "考试时长"}, {"start_at", "开始时间"}, {"end_at", "结束时间"},
        };
        for (String[] p : f) FIELD_CN.put(p[0], p[1]);
    }

    /** 状态码 + 响应正文 → 一句中文 */
    public static String explain(int code, String body) {
        Object detail = null;
        try {
            detail = new JSONObject(body).opt("detail");
        } catch (Exception ignored) {
            // 不是 JSON（比如 nginx 的错误页），按状态码说
        }
        String fromDetail = explainDetail(detail);
        if (fromDetail != null) return fromDetail;
        if (code == 401) return "登录已过期，请重新登录";
        if (code == 403) return "没有权限做这件事";
        if (code == 404) return "要找的内容不存在，可能已被删除";
        if (code == 413) return "文件太大了，服务器不收";
        if (code == 502 || code == 503 || code == 504) return "服务器正在重启或负载过高，请稍后再试";
        if (code >= 500) return "服务器出错了（" + code + "），请联系管理员";
        return "请求失败（" + code + "）";
    }

    static Object parseDetail(String body) {
        try {
            return new JSONObject(body).opt("detail");
        } catch (Exception e) {
            return null;
        }
    }

    private static String explainDetail(Object detail) {
        if (detail instanceof String && !((String) detail).isEmpty()) return (String) detail;
        if (detail instanceof JSONArray && ((JSONArray) detail).length() > 0) {
            JSONArray arr = (JSONArray) detail;
            Set<String> msgs = new LinkedHashSet<>();
            for (int i = 0; i < arr.length(); i++) {
                JSONObject e = arr.optJSONObject(i);
                if (e != null) msgs.add(explainOne(e));
            }
            StringBuilder sb = new StringBuilder();
            int n = 0;
            for (String m : msgs) {
                if (n == 3) break;
                if (n > 0) sb.append('；');
                sb.append(m);
                n++;
            }
            if (msgs.size() > 3) sb.append(" 等 ").append(msgs.size()).append(" 处");
            return sb.toString();
        }
        if (detail instanceof JSONObject) {
            // 少数接口 detail 是对象，里面带 message
            String m = ((JSONObject) detail).optString("message", "");
            if (!m.isEmpty()) return m;
        }
        return null;
    }

    private static String explainOne(JSONObject e) {
        JSONArray loc = e.optJSONArray("loc");
        String last = loc != null && loc.length() > 0 ? String.valueOf(loc.opt(loc.length() - 1)) : "";
        String field = FIELD_CN.containsKey(last) ? FIELD_CN.get(last) : (last.isEmpty() ? "有个字段" : last);
        JSONObject ctx = e.optJSONObject("ctx");
        String n = ctx == null ? "" : ctx.has("min_length") ? ctx.optString("min_length")
                : ctx.optString("max_length", "");
        String type = e.optString("type");
        switch (type) {
            case "missing":
                return field + "不能为空";
            case "string_too_short":
                return field + "太短，至少 " + n + " 个字符";
            case "string_too_long":
                return field + "太长，最多 " + n + " 个字符";
            case "string_pattern_mismatch":
                return field + "格式不对";
            case "int_parsing":
            case "float_parsing":
                return field + "要填数字";
            case "literal_error":
            case "enum":
                return field + "只能是 " + (ctx == null ? "" : ctx.optString("expected").replace("'", ""));
            default:
                String msg = e.optString("msg", "");
                return field + "填得不对：" + (msg.isEmpty() ? "格式不符合要求" : msg);
        }
    }
}
