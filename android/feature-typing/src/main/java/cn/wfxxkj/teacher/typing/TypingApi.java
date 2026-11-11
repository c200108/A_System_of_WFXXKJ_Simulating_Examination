package cn.wfxxkj.teacher.typing;

import android.net.Uri;

import org.json.JSONObject;

import java.util.Collection;
import java.util.List;

import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.net.Params;
import cn.wfxxkj.teacher.core.session.Session;

/**
 * 打字训练的接口（对应网页 api.js 里 typing* 那一组，后端 routers/typing_train.py）。
 * 全是同步调用，只能在 Screen.run(...) 的后台任务里用。
 */
final class TypingApi {
    private TypingApi() {}

    /** 三个模块，和后端 MODULES 一致 */
    static final String[] MODULES = {"中文", "英文", "键盘"};
    /** 默认难度（取不到 /typing/config 时用） */
    static final String[] DIFFICULTIES = {"简单", "中等", "困难"};

    // ---------------------------------------------------------------- 成绩

    /** 成绩页的筛选条件。分页查询、导出、按条件删除用同一份 —— 删掉的正是看到的 */
    static final class Filter {
        String studentClass = "";
        String module = "";
        String difficulty = "";
        String keyword = "";
        /** yyyy-MM-dd，空 = 不限 */
        String dateFrom = "";
        String dateTo = "";
        /** time / speed / accuracy / duration / stars / name / class */
        String sort = "time";
        String order = "desc";

        Params params() {
            return Params.of("student_class", studentClass).add("module", module)
                    .add("difficulty", difficulty).add("keyword", keyword)
                    .add("date_from", dateFrom).add("date_to", dateTo);
        }

        /** 除排序以外有没有筛选条件 */
        boolean filtered() {
            return !(studentClass.isEmpty() && module.isEmpty() && difficulty.isEmpty()
                    && keyword.isEmpty() && dateFrom.isEmpty() && dateTo.isEmpty());
        }

        /** 筛选条件（不含模块、姓名，这两样页面上直接看得到）有几项，显示在「筛选」按钮的角标上 */
        int sheetCount() {
            int n = 0;
            if (!studentClass.isEmpty()) n++;
            if (!difficulty.isEmpty()) n++;
            if (!dateFrom.isEmpty() || !dateTo.isEmpty()) n++;
            if (!"time".equals(sort) || !"desc".equals(order)) n++;
            return n;
        }

        Filter copy() {
            Filter f = new Filter();
            f.studentClass = studentClass;
            f.module = module;
            f.difficulty = difficulty;
            f.keyword = keyword;
            f.dateFrom = dateFrom;
            f.dateTo = dateTo;
            f.sort = sort;
            f.order = order;
            return f;
        }
    }

    /** 分页查成绩：{total, items:[...]} */
    static JSONObject search(Filter f, int page, int pageSize) throws ApiException {
        return Http.getObj("/typing/records/search", f.params().add("sort", f.sort).add("order", f.order)
                .add("page", page).add("page_size", pageSize));
    }

    /** 全站概况：练习人次、人数、平均正确率、平均用时、各模块次数 */
    static JSONObject stats() throws ApiException {
        return Http.getObj("/typing/stats", null);
    }

    /** 出现过的班级 */
    static List<String> classes() throws ApiException {
        return Json.strings(Http.getArr("/typing/classes", null));
    }

    static Http.Download export(Filter f) throws ApiException {
        return Http.download("GET", "/typing/export.xlsx", f.params(), null);
    }

    static void deleteOne(long id) throws ApiException {
        Http.delete("/typing/records/" + id, null);
    }

    /** 删勾选的，返回删了几条 */
    static int deleteMany(Collection<?> ids) throws ApiException {
        JSONObject r = Http.asObj(Http.post("/typing/records/delete", Json.of("ids", Json.array(ids))));
        return Json.num(r, "deleted");
    }

    /** 按筛选条件删（不带条件 = 清空），返回删了几条 */
    static int deleteFiltered(Filter f) throws ApiException {
        return Json.num(Http.asObj(Http.delete("/typing/records", f.params())), "deleted");
    }

    /**
     * 学生练习页地址：后端配了 PUBLIC_BASE_URL 就用它，否则用 APP 连的服务器地址。
     * 和网页 studentLink('/dazi') 一个意思。
     */
    static String studentUrl() {
        String base = "";
        try {
            base = Json.str(Http.getObj("/config", null), "public_base_url");
        } catch (ApiException ignored) {
            // 取不到就用当前服务器地址
        }
        if (base.isEmpty()) base = Session.get().server();
        while (base.endsWith("/")) base = base.substring(0, base.length() - 1);
        return base + "/dazi";
    }

    // ---------------------------------------------------------------- 学情分析

    /**
     * 学情分析。module 空 = 全部模块；days 0 = 全部时间；
     * classes / students（「班级|姓名」）都空 = 全体。
     */
    static JSONObject analysis(String module, int days, List<String> classes, List<String> students)
            throws ApiException {
        Params p = Params.of("module", module).add("days", days);
        if (students != null && !students.isEmpty()) p.addAll("students", students);
        else if (classes != null && !classes.isEmpty()) p.addAll("classes", classes);
        return Http.getObj("/typing/analysis", p);
    }

    // ---------------------------------------------------------------- 练习文本

    /** 难度档（后端 config 里配的），取不到用默认三档 */
    static String[] difficulties() {
        try {
            List<String> d = Json.strings(Json.arr(Http.getObj("/typing/config", null), "difficulties"));
            if (!d.isEmpty()) return d.toArray(new String[0]);
        } catch (ApiException ignored) {
            // 用默认三档
        }
        return DIFFICULTIES;
    }

    static List<JSONObject> texts(String mode, String difficulty, String keyword, Integer themeId) throws ApiException {
        return Json.list(Http.getArr("/typing/texts",
                Params.of("mode", mode).add("difficulty", difficulty).add("keyword", keyword).add("theme_id", themeId)));
    }

    // ---------- 主题（服务端 2.15.0 起） ----------

    /** 主题列表：{id, name, is_enabled, sort_order, is_builtin, counts:{chinese:{简单:8}}, total} */
    static List<JSONObject> themes() throws ApiException {
        return Json.list(Http.getArr("/typing/themes", null));
    }

    static JSONObject createTheme(String name) throws ApiException {
        return Http.postObj("/typing/themes", Json.of("name", name));
    }

    /** 改名 / 启用停用 / 排序，只传要改的 */
    static JSONObject updateTheme(int id, JSONObject patch) throws ApiException {
        return Http.asObj(Http.put("/typing/themes/" + id, patch));
    }

    /** 删主题，返回 {moved}：它下面的文本归回「信息生活」 */
    static JSONObject deleteTheme(int id) throws ApiException {
        return Http.asObj(Http.delete("/typing/themes/" + id, null));
    }

    /** {english:{简单:12,...}, chinese:{...}}，只数启用的 */
    static JSONObject textStats() throws ApiException {
        return Http.getObj("/typing/texts/stats", null);
    }

    static JSONObject createText(String mode, String difficulty, String content, Integer themeId) throws ApiException {
        return Http.asObj(Http.post("/typing/texts",
                Json.of("mode", mode, "difficulty", difficulty, "content", content, "theme_id", themeId)));
    }

    /** 改难度、内容或启用状态，只传要改的 */
    static JSONObject updateText(long id, JSONObject patch) throws ApiException {
        return Http.asObj(Http.put("/typing/texts/" + id, patch));
    }

    static void deleteText(long id) throws ApiException {
        Http.delete("/typing/texts/" + id, null);
    }

    /** action：delete / enable / disable / theme（改到 themeId），返回实际处理了几段 */
    static int bulkTexts(Collection<?> ids, String action, Integer themeId) throws ApiException {
        JSONObject r = Http.asObj(Http.post("/typing/texts/bulk",
                Json.of("ids", Json.array(ids), "action", action, "theme_id", themeId)));
        return Json.num(r, "affected");
    }

    /** 上传 txt 批量导入：{added, skipped, too_short, total} */
    static JSONObject importTxt(String mode, String difficulty, String split, Integer themeId, Uri file) throws ApiException {
        return Http.asObj(Http.upload("/typing/texts/import",
                Params.of("mode", mode).add("difficulty", difficulty).add("split", split).add("theme_id", themeId),
                "file", file));
    }
}
