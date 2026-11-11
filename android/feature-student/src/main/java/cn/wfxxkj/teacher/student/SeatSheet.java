package cn.wfxxkj.teacher.student;

import android.graphics.Color;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 在线座次表的数据（和网页端 SeatSheet.vue 存的是同一份 JSON，两边改的互通）。
 *
 * <pre>
 * { version, data: [[格子文字…]…], mergeCells: {"A1": [宽, 高]}, style: {"A1": "background-color:#fff;…"},
 *   colWidths: [px…], rowHeights: {"行号": px}, seatRanges, zoneRanges,
 *   groups: [{id, name, color}], groupOf: {学生 id: 组 id}, broken: {"B3": "说明"} }
 * </pre>
 *
 * APP 只改 data（换座、排座、改字）、groups / groupOf、broken、seatRanges 这几项；
 * 其余字段（样式、合并、列宽行高、以后网页新加的字段）原样带回去，网页端的排版不会被 APP 弄乱。
 */
final class SeatSheet {

    /** 一格的显示样式：从网页存的 CSS 文字里解析出来的几项 */
    static final class Style {
        int bg = 0;              // 0 = 没设
        int color = 0;
        boolean bold, italic, underline;
        float fontPx = 0;        // 0 = 默认
        int hAlign = -1;         // -1 默认（文字靠左、数字靠右）/ 0 左 / 1 中 / 2 右
        int vAlign = 1;          // 0 上 / 1 中 / 2 下
        /** 上右下左四条边：宽度（px，0 = 没有）和颜色 */
        final float[] borderW = new float[4];
        final int[] borderC = new int[4];
    }

    private final JSONObject raw;
    final List<List<String>> data = new ArrayList<>();
    int cols;
    final int[] colWidths;
    final Map<Integer, Integer> rowHeights = new HashMap<>();
    /** 合并：左上角格子 → {宽, 高} */
    final Map<String, int[]> merges = new LinkedHashMap<>();
    /** 被合并盖住的格子（不是左上角的那些） */
    final Set<String> covered = new HashSet<>();
    final Map<String, Style> styles = new HashMap<>();
    final List<JSONObject> groups = new ArrayList<>();
    /** 学生 id → 组 id */
    final Map<String, String> groupOf = new LinkedHashMap<>();
    /** 设备故障：格子 → 说明（可以是空串） */
    final Map<String, String> broken = new LinkedHashMap<>();
    String seatRanges, zoneRanges;

    static final int DEFAULT_COL = 90;
    static final int DEFAULT_ROW = 25;

    /** 淡色系小组底色，和网页端 seatBoard.js 的 GROUP_COLORS 一样 */
    static final String[] GROUP_COLORS = {
            "#DCEBFF", "#DDF5E3", "#FFE9D2", "#EFE1FA", "#D6F3F5", "#FFDDE8", "#F6F3C9", "#E6E9EE"};

    SeatSheet(JSONObject raw) {
        this.raw = raw == null ? new JSONObject() : raw;
        JSONArray rows = this.raw.optJSONArray("data");
        int maxCols = 0;
        if (rows != null) {
            for (int y = 0; y < rows.length(); y++) {
                JSONArray r = rows.optJSONArray(y);
                List<String> line = new ArrayList<>();
                if (r != null) {
                    for (int x = 0; x < r.length(); x++) {
                        Object v = r.opt(x);
                        line.add(v == null || v == JSONObject.NULL ? "" : String.valueOf(v));
                    }
                }
                maxCols = Math.max(maxCols, line.size());
                data.add(line);
            }
        }
        JSONArray w = this.raw.optJSONArray("colWidths");
        if (w != null) maxCols = Math.max(maxCols, w.length());
        cols = maxCols;
        colWidths = new int[cols];
        for (int x = 0; x < cols; x++) {
            int v = w == null ? 0 : w.optInt(x, 0);
            colWidths[x] = v > 0 ? v : DEFAULT_COL;
        }
        for (List<String> line : data) while (line.size() < cols) line.add("");

        JSONObject rh = this.raw.optJSONObject("rowHeights");
        if (rh != null) {
            for (Iterator<String> it = rh.keys(); it.hasNext(); ) {
                String k = it.next();
                try {
                    int h = rh.optInt(k, 0);
                    if (h > 0) rowHeights.put(Integer.parseInt(k), h);
                } catch (NumberFormatException ignored) {
                    // 不是行号，跳过
                }
            }
        }
        JSONObject mc = this.raw.optJSONObject("mergeCells");
        if (mc != null) {
            for (Iterator<String> it = mc.keys(); it.hasNext(); ) {
                String k = it.next();
                JSONArray span = mc.optJSONArray(k);
                int[] p = parse(k);
                if (span == null || p == null) continue;
                int sw = Math.max(1, span.optInt(0, 1)), sh = Math.max(1, span.optInt(1, 1));
                merges.put(k.toUpperCase(Locale.ROOT), new int[]{sw, sh});
                for (int dy = 0; dy < sh; dy++) {
                    for (int dx = 0; dx < sw; dx++) if (dx > 0 || dy > 0) covered.add(name(p[0] + dx, p[1] + dy));
                }
            }
        }
        JSONObject st = this.raw.optJSONObject("style");
        if (st != null) {
            for (Iterator<String> it = st.keys(); it.hasNext(); ) {
                String k = it.next();
                styles.put(k.toUpperCase(Locale.ROOT), parseCss(st.optString(k)));
            }
        }
        JSONArray gs = this.raw.optJSONArray("groups");
        if (gs != null) for (int i = 0; i < gs.length(); i++) {
            JSONObject g = gs.optJSONObject(i);
            if (g != null) groups.add(g);
        }
        JSONObject go = this.raw.optJSONObject("groupOf");
        if (go != null) for (Iterator<String> it = go.keys(); it.hasNext(); ) {
            String k = it.next();
            groupOf.put(k, String.valueOf(go.opt(k)));
        }
        JSONObject bk = this.raw.optJSONObject("broken");
        if (bk != null) for (Iterator<String> it = bk.keys(); it.hasNext(); ) {
            String k = it.next();
            broken.put(k.toUpperCase(Locale.ROOT), bk.optString(k, ""));
        }
        seatRanges = this.raw.optString("seatRanges", "");
        zoneRanges = this.raw.optString("zoneRanges", "");
    }

    int rows() {
        return data.size();
    }

    int rowHeight(int y) {
        Integer h = rowHeights.get(y);
        return h == null ? DEFAULT_ROW : h;
    }

    String get(int x, int y) {
        if (y < 0 || y >= data.size()) return "";
        List<String> r = data.get(y);
        return x < 0 || x >= r.size() ? "" : r.get(x);
    }

    void set(int x, int y, String v) {
        if (y < 0 || y >= data.size() || x < 0 || x >= cols) return;
        data.get(y).set(x, v == null ? "" : v);
    }

    boolean isEmpty() {
        return data.isEmpty() || cols == 0;
    }

    // ---------- 格子名 ----------

    /** (0,0) → A1，(26,4) → AA5 */
    static String name(int x, int y) {
        StringBuilder s = new StringBuilder();
        int n = x + 1;
        while (n > 0) {
            int r = (n - 1) % 26;
            s.insert(0, (char) ('A' + r));
            n = (n - 1) / 26;
        }
        return s.append(y + 1).toString();
    }

    private static final Pattern CELL = Pattern.compile("^\\s*([A-Za-z]{1,3})\\s*(\\d{1,5})\\s*$");

    /** A1 → {0,0}；认不出返回 null */
    static int[] parse(String n) {
        if (n == null) return null;
        Matcher m = CELL.matcher(n);
        if (!m.matches()) return null;
        int x = 0;
        for (char ch : m.group(1).toUpperCase(Locale.ROOT).toCharArray()) x = x * 26 + (ch - 'A' + 1);
        int y = Integer.parseInt(m.group(2));
        return y < 1 ? null : new int[]{x - 1, y - 1};
    }

    /** 「B2:B15, A4:H4」→ 一个个格子名，和网页端 expandRanges 一样 */
    static List<String> expand(String text) {
        List<String> out = new ArrayList<>();
        if (text == null) return out;
        for (String part : text.split("[\\s,，;；、]+")) {
            if (part.isEmpty()) continue;
            String[] ab = part.replace('：', ':').split(":");
            int[] p1 = parse(ab[0]);
            int[] p2 = parse(ab.length > 1 ? ab[1] : ab[0]);
            if (p1 == null || p2 == null) continue;
            for (int y = Math.min(p1[1], p2[1]); y <= Math.max(p1[1], p2[1]); y++) {
                for (int x = Math.min(p1[0], p2[0]); x <= Math.max(p1[0], p2[0]); x++) out.add(name(x, y));
            }
        }
        return out;
    }

    // ---------- 自动认座位（同网页端 detectSeats） ----------

    private static final Pattern SEAT_LABEL = Pattern.compile("^([A-Za-z]{1,2})\\s*-?\\s*(\\d{1,3})$");

    /** 写着座位号（A1、B12）的格子，右边那格就是座位。返回按座位号排好的格子名 */
    List<String> detectSeats(Roster roster) {
        List<Object[]> found = new ArrayList<>();
        for (int y = 0; y < data.size(); y++) {
            for (int x = 0; x + 1 < cols; x++) {
                Matcher m = SEAT_LABEL.matcher(get(x, y).trim());
                if (!m.matches()) continue;
                String seat = name(x + 1, y);
                if (covered.contains(seat)) continue;
                String right = get(x + 1, y).trim();
                if (!right.isEmpty() && (SEAT_LABEL.matcher(right).matches() || roster.find(right) == null)) continue;
                found.add(new Object[]{seat, x + 1, y, m.group(1).toUpperCase(Locale.ROOT), Integer.parseInt(m.group(2))});
            }
        }
        java.util.Collections.sort(found, (a, b) -> {
            int c = ((String) a[3]).compareTo((String) b[3]);
            return c != 0 ? c : Integer.compare((Integer) a[4], (Integer) b[4]);
        });
        List<String> out = new ArrayList<>();
        for (Object[] f : found) out.add((String) f[0]);
        return out;
    }

    /** 座位 → 区域文字：同一列连着往下的并成 B3:B18 */
    static String toRanges(List<String> seats) {
        StringBuilder sb = new StringBuilder();
        int rx = -1, y1 = -1, y2 = -1;
        for (String s : seats) {
            int[] p = parse(s);
            if (p == null) continue;
            if (rx == p[0] && p[1] == y2 + 1) {
                y2 = p[1];
                continue;
            }
            if (rx >= 0) append(sb, rx, y1, y2);
            rx = p[0];
            y1 = y2 = p[1];
        }
        if (rx >= 0) append(sb, rx, y1, y2);
        return sb.toString();
    }

    private static void append(StringBuilder sb, int x, int y1, int y2) {
        if (sb.length() > 0) sb.append(", ");
        sb.append(name(x, y1));
        if (y2 != y1) sb.append(':').append(name(x, y2));
    }

    // ---------- 小组 ----------

    JSONObject group(String id) {
        if (id == null) return null;
        for (JSONObject g : groups) if (id.equals(String.valueOf(g.opt("id")))) return g;
        return null;
    }

    String nextGroupId() {
        int max = 0;
        for (JSONObject g : groups) {
            try {
                max = Math.max(max, Integer.parseInt(String.valueOf(g.opt("id"))));
            } catch (NumberFormatException ignored) {
                // 网页端生成的都是数字，别的就跳过
            }
        }
        return String.valueOf(max + 1);
    }

    JSONObject addGroup() {
        int i = groups.size();
        JSONObject g = new JSONObject();
        try {
            g.put("id", nextGroupId());
            g.put("name", "第" + (i + 1) + "组");
            g.put("color", GROUP_COLORS[i % GROUP_COLORS.length]);
        } catch (JSONException ignored) {
            // 不会发生
        }
        groups.add(g);
        return g;
    }

    void removeGroup(JSONObject g) {
        String id = String.valueOf(g.opt("id"));
        groups.remove(g);
        for (Iterator<Map.Entry<String, String>> it = groupOf.entrySet().iterator(); it.hasNext(); ) {
            if (id.equals(it.next().getValue())) it.remove();
        }
    }

    /** 这位学生所在小组的底色（没分组 / 组被删了返回 0） */
    int groupColor(int studentId) {
        JSONObject g = group(groupOf.get(String.valueOf(studentId)));
        return g == null ? 0 : color(g.optString("color"), 0);
    }

    // ---------- 存回去 ----------

    JSONObject toJson() {
        try {
            JSONObject o = new JSONObject(raw.toString());
            JSONArray rows = new JSONArray();
            for (List<String> line : data) {
                JSONArray r = new JSONArray();
                for (String v : line) r.put(v);
                rows.put(r);
            }
            o.put("data", rows);
            if (!o.has("version")) o.put("version", 1);
            if (!o.has("colWidths")) {
                JSONArray w = new JSONArray();
                for (int cw : colWidths) w.put(cw);
                o.put("colWidths", w);
            }
            JSONArray gs = new JSONArray();
            for (JSONObject g : groups) gs.put(g);
            o.put("groups", gs);
            JSONObject go = new JSONObject();
            for (Map.Entry<String, String> e : groupOf.entrySet()) go.put(e.getKey(), e.getValue());
            o.put("groupOf", go);
            JSONObject bk = new JSONObject();
            for (Map.Entry<String, String> e : broken.entrySet()) bk.put(e.getKey(), e.getValue());
            o.put("broken", bk);
            o.put("seatRanges", seatRanges == null ? "" : seatRanges);
            o.put("zoneRanges", zoneRanges == null ? "" : zoneRanges);
            return o;
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
    }

    // ---------- 样式 ----------

    static Style parseCss(String css) {
        Style s = new Style();
        if (css == null) return s;
        for (String decl : css.split(";")) {
            int i = decl.indexOf(':');
            if (i <= 0) continue;
            String k = decl.substring(0, i).trim().toLowerCase(Locale.ROOT);
            String v = decl.substring(i + 1).trim();
            String lv = v.toLowerCase(Locale.ROOT);
            switch (k) {
                case "background-color":
                case "background":
                    s.bg = color(v, 0);
                    break;
                case "color":
                    s.color = color(v, 0);
                    break;
                case "font-weight":
                    s.bold = lv.startsWith("bold") || lv.matches("[6-9]00");
                    break;
                case "font-style":
                    s.italic = lv.contains("italic");
                    break;
                case "text-decoration":
                    s.underline = lv.contains("underline");
                    break;
                case "font-size":
                    s.fontPx = px(lv);
                    break;
                case "text-align":
                    s.hAlign = lv.startsWith("center") ? 1 : lv.startsWith("right") ? 2 : lv.startsWith("left") ? 0 : -1;
                    break;
                case "vertical-align":
                    s.vAlign = lv.startsWith("top") ? 0 : lv.startsWith("bottom") ? 2 : 1;
                    break;
                case "border-top":
                    border(s, 0, lv);
                    break;
                case "border-right":
                    border(s, 1, lv);
                    break;
                case "border-bottom":
                    border(s, 2, lv);
                    break;
                case "border-left":
                    border(s, 3, lv);
                    break;
                case "border":
                    for (int side = 0; side < 4; side++) border(s, side, lv);
                    break;
                default:
                    break;
            }
        }
        return s;
    }

    private static void border(Style s, int side, String v) {
        if (v.startsWith("none") || v.startsWith("0")) {
            s.borderW[side] = 0;
            return;
        }
        float w = 1;
        int c = Color.BLACK;
        for (String t : v.split("\\s+")) {
            if (t.endsWith("px")) w = Math.max(0.5f, px(t));
            else if (t.equals("thin")) w = 1;
            else if (t.equals("medium")) w = 2;
            else if (t.equals("thick")) w = 3;
            else if (t.startsWith("#") || t.startsWith("rgb")) c = color(t, Color.BLACK);
        }
        // rgb(…) 里带空格会被拆开：整串再找一次
        int r = v.indexOf("rgb");
        if (r >= 0) c = color(v.substring(r), c);
        s.borderW[side] = w;
        s.borderC[side] = c;
    }

    private static float px(String v) {
        try {
            String n = v.replaceAll("[^0-9.]", "");
            float f = n.isEmpty() ? 0 : Float.parseFloat(n);
            if (v.endsWith("pt")) f = f * 4 / 3;
            return f;
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    /** #RGB / #RRGGBB / #AARRGGBB / rgb(r,g,b) / rgba(r,g,b,a)；认不出返回 def */
    static int color(String v, int def) {
        if (v == null) return def;
        v = v.trim();
        try {
            if (v.startsWith("#")) {
                String h = v.substring(1);
                if (h.length() == 3) {
                    h = "" + h.charAt(0) + h.charAt(0) + h.charAt(1) + h.charAt(1) + h.charAt(2) + h.charAt(2);
                }
                if (h.length() == 6) return 0xFF000000 | Integer.parseInt(h, 16);
                if (h.length() == 8) {
                    // CSS 的 8 位写法是 #RRGGBBAA，安卓要 AARRGGBB
                    long hv = Long.parseLong(h, 16);
                    return (int) (((hv & 0xFF) << 24) | (hv >>> 8));
                }
                return def;
            }
            Matcher m = Pattern.compile("rgba?\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)\\s*(?:,\\s*([0-9.]+)\\s*)?\\)")
                    .matcher(v);
            if (m.find()) {
                int a = m.group(4) == null ? 255 : Math.round(Float.parseFloat(m.group(4)) * 255);
                return Color.argb(a, Integer.parseInt(m.group(1)), Integer.parseInt(m.group(2)),
                        Integer.parseInt(m.group(3)));
            }
            switch (v.toLowerCase(Locale.ROOT)) {
                case "white":
                    return Color.WHITE;
                case "black":
                    return Color.BLACK;
                case "red":
                    return Color.RED;
                case "transparent":
                    return 0;
                default:
                    return def;
            }
        } catch (RuntimeException e) {
            return def;
        }
    }

    // ---------- 学生名单：格子里的字是谁 ----------

    /** 和网页端 studentIndex 一样：格子里写「姓名」或「学号 姓名」；重名的只认「学号 姓名」 */
    static final class Roster {
        final List<JSONObject> students;
        private final Map<String, JSONObject> byNo = new HashMap<>();
        private final Map<String, JSONObject> byName = new HashMap<>();
        private final Set<String> dupNames = new HashSet<>();

        Roster(List<JSONObject> students) {
            this.students = students == null ? new ArrayList<>() : students;
            for (JSONObject s : this.students) {
                byNo.put(s.optString("student_no"), s);
                String n = s.optString("name").trim();
                if (byName.containsKey(n)) dupNames.add(n);
                byName.put(n, s);
            }
        }

        private static final Pattern NO_NAME = Pattern.compile("^(\\S+)\\s+(.+)$", Pattern.DOTALL);

        JSONObject find(String text) {
            String t = text == null ? "" : text.trim();
            if (t.isEmpty()) return null;
            Matcher m = NO_NAME.matcher(t);
            if (m.matches()) {
                JSONObject s = byNo.get(m.group(1));
                if (s != null && s.optString("name").equals(m.group(2).trim())) return s;
            }
            if (byName.containsKey(t) && !dupNames.contains(t)) return byName.get(t);
            return byNo.get(t);
        }

        JSONObject byId(int id) {
            for (JSONObject s : students) if (s.optInt("id") == id) return s;
            return null;
        }
    }
}
