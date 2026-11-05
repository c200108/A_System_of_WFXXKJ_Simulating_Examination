package cn.wfxxkj.teacher.paper;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.net.Json;

/**
 * 组卷设置：卷面结构（config.yaml 的 paper.sections）+ 老师在界面上改的题量、分值、开关。
 * 和网页版 Paper.vue 里的 form 一一对应，{@link #payload} 拼成发给后端的请求。
 */
final class Blueprint {

    /** 大题里的一组：同一题型、同一范围的若干道 */
    static final class Slot {
        String type;
        int count;
        List<String> scopes = new ArrayList<>();
        String prefer;
        List<String> simKinds = new ArrayList<>();
    }

    /** 一个大题 */
    static final class Section {
        String name;
        int score;
        List<Slot> slots = new ArrayList<>();
    }

    /** 操作题的类别标签（config.yaml 里的 sim_kinds） */
    static String kindLabel(String k) {
        switch (k) {
            case "win":
                return "Windows 操作";
            case "wps":
                return "WPS 文字";
            case "html":
                return "网页文件";
            case "ai":
                return "AI 工具";
            case "drag":
                return "拖拽 / 热区 / 流程图";
            default:
                return k;
        }
    }

    // ---------- 配置（只读） ----------
    final List<Section> sections = new ArrayList<>();
    final List<String> numerals = new ArrayList<>();
    final List<String> scopes = new ArrayList<>();
    final List<String> types = new ArrayList<>();
    private final Map<String, Integer> defaultCounts = new LinkedHashMap<>();
    private String defaultTitle = "信息技术测试卷";
    private String defaultSchool = "";
    private String defaultDuration = "";
    private boolean defShuffle = true, defRequire = true, defPinned = true;

    // ---------- 老师改的 ----------
    String title, school, duration;
    boolean bySections = true;
    final Map<String, Integer> sectionCounts = new LinkedHashMap<>();
    final Map<String, Integer> sectionScores = new LinkedHashMap<>();
    final Map<String, Integer> counts = new LinkedHashMap<>();
    final List<String> pickedScopes = new ArrayList<>();
    boolean usePinned, requireAnswer, shuffleOptions;
    String seed = "";
    boolean save;

    /** config = /api/config 的返回，dicts = /api/dicts */
    Blueprint(JSONObject config, List<JSONObject> dicts) {
        JSONObject p = Json.obj(config, "paper");
        defaultSchool = Json.str(config, "school");
        defaultTitle = Json.str(p, "default_title", defaultTitle);
        defaultDuration = Json.str(p, "default_duration");
        // 选择判断题乱序（服务端 2.19.0）；老服务端只回 shuffle_options，退回读它
        defShuffle = p.optBoolean("shuffle_objective", p.optBoolean("shuffle_options", true));
        defRequire = p.optBoolean("require_answer", true);
        defPinned = p.optBoolean("use_pinned", true);
        numerals.addAll(Json.strings(Json.arr(p, "section_numerals")));
        JSONObject dc = Json.obj(p, "default_counts");
        java.util.Iterator<String> it = dc.keys();
        while (it.hasNext()) {
            String k = it.next();
            defaultCounts.put(k, dc.optInt(k, 0));
        }
        for (JSONObject s : Json.list(Json.arr(p, "sections"))) {
            Section sec = new Section();
            sec.name = Json.str(s, "name");
            sec.score = Json.num(s, "score");
            for (JSONObject sl : Json.list(Json.arr(s, "slots"))) {
                Slot slot = new Slot();
                slot.type = Json.str(sl, "type");
                slot.count = Json.num(sl, "count");
                slot.scopes.addAll(Json.strings(Json.arr(sl, "scopes")));
                slot.prefer = Json.str(sl, "prefer");
                slot.simKinds.addAll(Json.strings(Json.arr(sl, "sim_kinds")));
                sec.slots.add(slot);
            }
            sections.add(sec);
        }
        for (JSONObject d : dicts) {
            if (d.has("is_active") && !d.optBoolean("is_active", true)) continue;
            if ("scope".equals(Json.str(d, "category"))) scopes.add(Json.str(d, "name"));
            else if ("qtype".equals(Json.str(d, "category"))) types.add(Json.str(d, "name"));
        }
        // 没有卷面结构的学校只能按题型组卷
        bySections = !sections.isEmpty();
        resetAll();
    }

    /** 全部恢复成配置里的默认值 */
    void resetAll() {
        title = defaultTitle;
        school = defaultSchool;
        duration = defaultDuration;
        counts.clear();
        counts.putAll(defaultCounts);
        for (String t : types) if (!counts.containsKey(t)) counts.put(t, 0);
        pickedScopes.clear();
        usePinned = defPinned;
        requireAnswer = defRequire;
        shuffleOptions = defShuffle;
        seed = "";
        save = false;
        resetBlueprint();
    }

    /** 题量和大题分值恢复默认（网页上的「恢复默认」） */
    void resetBlueprint() {
        sectionCounts.clear();
        sectionScores.clear();
        for (Section sec : sections) {
            sectionScores.put(sec.name, sec.score);
            for (int i = 0; i < sec.slots.size(); i++) sectionCounts.put(slotKey(sec, i), sec.slots.get(i).count);
        }
    }

    /** 改题量用的键：大题名 + 第几组（和后端 slot_key 一致） */
    static String slotKey(Section sec, int i) {
        return sec.name + "/" + i;
    }

    String numeral(int i) {
        return i < numerals.size() ? numerals.get(i) : String.valueOf(i + 1);
    }

    /** 六大题时卷面总分 */
    int plannedFull() {
        int n = 0;
        for (Section sec : sections) n += val(sectionScores.get(sec.name));
        return n;
    }

    /** 当前设置一共要几道题 */
    int plannedCount() {
        int n = 0;
        if (bySections) for (Integer v : sectionCounts.values()) n += val(v);
        else for (Integer v : counts.values()) n += val(v);
        return n;
    }

    private static int val(Integer v) {
        return v == null ? 0 : v;
    }

    /** 发给 generate / preview-plan 的请求体 */
    JSONObject payload() {
        JSONObject o = new JSONObject();
        Json.put(o, "title", title);
        Json.put(o, "school", school);
        Json.put(o, "duration", duration);
        Json.put(o, "by_sections", bySections);
        Json.put(o, "section_counts", new JSONObject(sectionCounts));
        Json.put(o, "section_scores", new JSONObject(sectionScores));
        Json.put(o, "counts", new JSONObject(counts));
        Json.put(o, "scopes", pickedScopes.isEmpty() ? null : new ArrayList<>(pickedScopes));
        Json.put(o, "use_pinned", usePinned);
        Json.put(o, "require_answer", requireAnswer);
        // 新服务端认 shuffle_objective（选择判断题乱序，含选项乱序）；
        // shuffle_options 一起带上，连老服务端时照旧只管选项乱序
        Json.put(o, "shuffle_objective", shuffleOptions);
        Json.put(o, "shuffle_options", shuffleOptions);
        Json.put(o, "seed", seed == null || seed.trim().isEmpty() ? null : seed.trim());
        Json.put(o, "save", save);
        return o;
    }
}
