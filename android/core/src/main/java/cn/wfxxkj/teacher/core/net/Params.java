package cn.wfxxkj.teacher.core.net;

import java.io.UnsupportedEncodingException;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * 查询参数（也用作表单）。按添加顺序拼，同名参数可以加多次（后端认 classes=a&amp;classes=b）。
 * 值为 null 或空字符串的自动跳过，调用处不用每个都判断。
 *
 * <pre>Params.of("page", 1).add("q", keyword).addAll("classes", picked)</pre>
 */
public final class Params {
    private final List<String[]> pairs = new ArrayList<>();

    public static Params of() {
        return new Params();
    }

    public static Params of(String key, Object value) {
        return new Params().add(key, value);
    }

    public Params add(String key, Object value) {
        if (value == null) return this;
        String s = String.valueOf(value);
        if (s.isEmpty()) return this;
        pairs.add(new String[]{key, s});
        return this;
    }

    public Params addAll(String key, Collection<?> values) {
        if (values != null) for (Object v : values) add(key, v);
        return this;
    }

    public boolean isEmpty() {
        return pairs.isEmpty();
    }

    public String encode() {
        StringBuilder sb = new StringBuilder();
        for (String[] p : pairs) {
            if (sb.length() > 0) sb.append('&');
            sb.append(enc(p[0])).append('=').append(enc(p[1]));
        }
        return sb.toString();
    }

    private static String enc(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8").replace("+", "%20");
        } catch (UnsupportedEncodingException e) {
            return s;
        }
    }
}
