package cn.wfxxkj.teacher.core.net;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * 读写 JSON 的小工具，省掉到处 try/catch 和判 null。
 *
 * <p>注意 org.json 的坑：{@code optString} 遇到 JSON 里的 null 会返回字符串 "null"，
 * 这里的 {@link #str} 会把它当成空。
 */
public final class Json {
    private Json() {}

    /** 字段的字符串值；缺失或 null 返回 "" */
    public static String str(JSONObject o, String key) {
        return str(o, key, "");
    }

    public static String str(JSONObject o, String key, String def) {
        if (o == null || !o.has(key) || o.isNull(key)) return def;
        Object v = o.opt(key);
        if (v instanceof Double) {
            double d = (Double) v;
            if (d == Math.rint(d) && !Double.isInfinite(d)) return String.valueOf((long) d);
        }
        return String.valueOf(v);
    }

    public static int num(JSONObject o, String key) {
        return o == null ? 0 : o.optInt(key, 0);
    }

    public static double dbl(JSONObject o, String key) {
        return o == null ? 0 : o.optDouble(key, 0);
    }

    /** 数字字段：缺失或 null 返回 null（区分「0 分」和「没有分」） */
    public static Double dblOrNull(JSONObject o, String key) {
        if (o == null || !o.has(key) || o.isNull(key)) return null;
        double d = o.optDouble(key, Double.NaN);
        return Double.isNaN(d) ? null : d;
    }

    public static Long longOrNull(JSONObject o, String key) {
        Double d = dblOrNull(o, key);
        return d == null ? null : Math.round(d);
    }

    public static boolean bool(JSONObject o, String key) {
        return o != null && o.optBoolean(key, false);
    }

    public static boolean isNull(JSONObject o, String key) {
        return o == null || !o.has(key) || o.isNull(key);
    }

    public static JSONArray arr(JSONObject o, String key) {
        JSONArray a = o == null ? null : o.optJSONArray(key);
        return a == null ? new JSONArray() : a;
    }

    public static JSONObject obj(JSONObject o, String key) {
        JSONObject v = o == null ? null : o.optJSONObject(key);
        return v == null ? new JSONObject() : v;
    }

    /** 数组里的对象 → List，非对象元素跳过 */
    public static List<JSONObject> list(JSONArray a) {
        List<JSONObject> out = new ArrayList<>();
        if (a == null) return out;
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null) out.add(o);
        }
        return out;
    }

    public static List<String> strings(JSONArray a) {
        List<String> out = new ArrayList<>();
        if (a == null) return out;
        for (int i = 0; i < a.length(); i++) {
            if (!a.isNull(i)) out.add(String.valueOf(a.opt(i)));
        }
        return out;
    }

    public static List<Integer> ints(JSONArray a) {
        List<Integer> out = new ArrayList<>();
        if (a == null) return out;
        for (int i = 0; i < a.length(); i++) out.add(a.optInt(i));
        return out;
    }

    public static JSONArray array(Collection<?> items) {
        JSONArray a = new JSONArray();
        if (items != null) for (Object o : items) a.put(o);
        return a;
    }

    /**
     * 拼对象：{@code Json.of("ids", ids, "action", "delete")}。值为 null 的写成 JSON null。
     */
    public static JSONObject of(Object... kv) {
        JSONObject o = new JSONObject();
        try {
            for (int i = 0; i + 1 < kv.length; i += 2) {
                Object v = kv[i + 1];
                if (v instanceof Collection) v = array((Collection<?>) v);
                o.put(String.valueOf(kv[i]), v == null ? JSONObject.NULL : v);
            }
        } catch (JSONException e) {
            throw new IllegalArgumentException(e);
        }
        return o;
    }

    /** put 不抛受检异常 */
    public static JSONObject put(JSONObject o, String key, Object value) {
        try {
            if (value instanceof Collection) value = array((Collection<?>) value);
            o.put(key, value == null ? JSONObject.NULL : value);
        } catch (JSONException e) {
            throw new IllegalArgumentException(e);
        }
        return o;
    }

    /** 深拷贝 */
    public static JSONObject copy(JSONObject o) {
        try {
            return o == null ? new JSONObject() : new JSONObject(o.toString());
        } catch (JSONException e) {
            return new JSONObject();
        }
    }

    public static JSONObject parse(String s) {
        try {
            return s == null || s.isEmpty() ? new JSONObject() : new JSONObject(s);
        } catch (JSONException e) {
            return new JSONObject();
        }
    }
}
