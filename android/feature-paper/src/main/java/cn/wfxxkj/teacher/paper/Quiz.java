package cn.wfxxkj.teacher.paper;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

import cn.wfxxkj.teacher.core.net.Json;

/**
 * 在线自测的作答和判分（网页版 Paper.vue 的 resp / submitQuiz 搬过来）。
 * 选择、判断题自动判；操作题只记下作答文字，交卷后对照答案要点自评。
 */
final class Quiz {
    static final String OP = "操作题";

    /** 题目 id → 选的选项字母，或操作题写的步骤 */
    final Map<Long, String> resp = new HashMap<>();
    boolean graded;
    /** 答对题数、计分的客观题数、客观题得分、客观题满分、等人工评阅的分 */
    int right, obj, got, full, manual;

    void reset() {
        resp.clear();
        graded = false;
        right = obj = got = full = manual = 0;
    }

    /** 判断题的「正确/错误」在答题界面上对应 A / B */
    static String rightLetter(JSONObject q) {
        String a = Json.str(q, "answer").trim();
        if ("判断题".equals(Json.str(q, "type"))) {
            if ("正确".equals(a)) return "A";
            if ("错误".equals(a)) return "B";
        }
        return a;
    }

    /** 操作题靠自评；原卷没给答案的题不计分 */
    static boolean scorable(JSONObject q) {
        return !OP.equals(Json.str(q, "type")) && !Json.str(q, "answer").trim().isEmpty();
    }

    /** 这个选项是不是正确答案（多选题的答案是「ABD」这样连写的） */
    static boolean isRightOption(JSONObject q, String label) {
        String r = rightLetter(q);
        if (r.equals(label)) return true;
        return r.length() > 1 && r.matches("[A-Z]+") && label.length() == 1 && r.contains(label);
    }

    boolean isCorrect(JSONObject q) {
        String mine = resp.get(q.optLong("id"));
        return mine != null && mine.equals(rightLetter(q));
    }

    void submit(JSONObject paper) {
        right = obj = got = full = manual = 0;
        for (JSONObject g : Json.list(Json.arr(paper, "groups"))) {
            for (JSONObject q : Json.list(Json.arr(g, "items"))) {
                int s = Json.num(q, "score");
                if (OP.equals(Json.str(q, "type"))) {
                    manual += s;
                    continue;
                }
                if (!scorable(q)) continue;
                obj++;
                full += s;
                if (isCorrect(q)) {
                    right++;
                    got += s;
                }
            }
        }
        graded = true;
    }
}
