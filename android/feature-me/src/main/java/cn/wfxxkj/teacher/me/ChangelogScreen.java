package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.ChipRow;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 更新日志（网页 Changelog.vue，仅管理员）。遵循 Keep a Changelog：新版本在前，版内按变动类型分组。
 *
 * <p>2.8.0 之后分成两条线：仿真环境走 3.x，学生桌面端走 4.x。网页是每条线一个折叠块，
 * APP 用顶部一排筛选条切换「线」，默认停在最新版本所在的那条线；分线之前的记录归在「共同历史」。
 */
public class ChangelogScreen extends Screen {

    /** 一条线：大版本号 → 名称、说明 */
    private static final String[][] TRACKS = {
            {"4", "学生桌面端", "机房里发的那个 exe"},
            {"3", "仿真环境", "网页里的操作题仿真器与判分"},
    };
    private static final String TRUNK = "trunk";
    private static final String ALL = "all";

    private ItemList<JSONObject> list;
    private ChipRow lines;
    private TextView lineHint;
    private List<JSONObject> versions = new ArrayList<>();
    private List<JSONObject> types = new ArrayList<>();
    private String line;

    @Override
    public String title() {
        return "更新日志";
    }

    @Override
    public String subtitle() {
        return versions.isEmpty() ? null : versions.size() + " 个版本，最新 " + Json.str(versions.get(0), "version");
    }

    @Override
    protected View onCreateView(Context c) {
        list = new ItemList<>(c, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context ctx) {
                return new ChangelogCard(ctx, ChangelogScreen.this::entryMenu);
            }

            @Override
            public void bind(View v, JSONObject ver, int pos) {
                ((ChangelogCard) v).bind(ver, pos == 0);
            }
        });
        list.setCell(480, 2);
        list.setOnRefresh(this::load);
        list.setEmpty("还没有更新记录", null, "添加记录", this::openAdd);

        LinearLayout head = V.vbox(c);
        V.pad(head, 0, 4, 0, 6);
        LinearLayout intro = V.hbox(c);
        intro.addView(V.text(c, "记录平台每一次改动，遵循 Keep a Changelog 规范与语义化版本。长按某一条可复制或删除。",
                V.CAPTION), V.fill());
        TextView link = V.button(c, "规范", V.BTN_TEXT,
                v -> Sys.openUrl(ctx(), "https://keepachangelog.com/zh-CN/1.1.0/"));
        intro.addView(link);
        head.addView(intro);
        lines = new ChipRow(c);
        lines.setOnPicked(o -> {
            line = String.valueOf(o.value);
            session().prefs().setUi("changelog.line", line);
            render();
        });
        V.addTop(head, lines, 6);
        lineHint = V.notice(c, "", Tone.NEUTRAL);
        V.addTop(head, lineHint, 8);
        list.addHeader(head);
        return list;
    }

    @Override
    protected void onFirstShow() {
        list.loading();
        load();
    }

    void load() {
        run(() -> {
            Object[] r = new Object[2];
            r[0] = MeApi.changelog();
            r[1] = MeApi.changelogTypes();
            return r;
        }, r -> {
            @SuppressWarnings("unchecked") List<JSONObject> v = (List<JSONObject>) r[0];
            @SuppressWarnings("unchecked") List<JSONObject> t = (List<JSONObject>) r[1];
            versions = v;
            types = t;
            buildLines();
            render();
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return false;
        });
    }

    // ---------- 分线 ----------

    private static String majorOf(JSONObject v) {
        String s = Json.str(v, "version");
        int dot = s.indexOf('.');
        return dot < 0 ? s : s.substring(0, dot);
    }

    private static int majorNum(String m) {
        try {
            return Integer.parseInt(m.trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    /** 这个版本属于哪条线：≤2 是分线前的共同历史，其余按大版本号 */
    private static String lineOf(JSONObject v) {
        String m = majorOf(v);
        return majorNum(m) <= 2 ? TRUNK : m;
    }

    private static String titleOf(String key) {
        if (TRUNK.equals(key)) return "共同历史";
        for (String[] t : TRACKS) if (t[0].equals(key)) return t[1];
        return key + ".x";
    }

    private void buildLines() {
        // 出现过的线，按最新版本出现的先后排
        Map<String, Integer> count = new LinkedHashMap<>();
        for (JSONObject v : versions) {
            String k = lineOf(v);
            Integer n = count.get(k);
            count.put(k, n == null ? 1 : n + 1);
        }
        List<Option> opts = new ArrayList<>();
        opts.add(new Option(ALL, "全部 " + versions.size()));
        // 已知的两条线固定在前，其他大版本号跟在后面，共同历史放最后
        List<String> keys = new ArrayList<>();
        for (String[] t : TRACKS) if (count.containsKey(t[0])) keys.add(t[0]);
        for (String k : count.keySet()) if (!keys.contains(k) && !TRUNK.equals(k)) keys.add(0, k);
        if (count.containsKey(TRUNK)) keys.add(TRUNK);
        for (String k : keys) {
            String t = titleOf(k);
            String label = TRUNK.equals(k) ? t + " ≤2.x" : t.endsWith(".x") ? t : t + " " + k + ".x";
            opts.add(new Option(k, label + "  " + count.get(k)));
        }
        String saved = session().prefs().ui("changelog.line", "");
        // 默认停在最新那个版本所在的线：大多数人来这儿就是想知道「刚更新了什么」
        String def = versions.isEmpty() ? ALL : lineOf(versions.get(0));
        line = (!saved.isEmpty() && (ALL.equals(saved) || count.containsKey(saved))) ? saved : def;
        lines.setOptions(opts, line);
        lines.setVisibility(versions.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void render() {
        List<JSONObject> shown = new ArrayList<>();
        for (JSONObject v : versions) if (ALL.equals(line) || line.equals(lineOf(v))) shown.add(v);
        String hint;
        if (versions.isEmpty()) {
            hint = null;
        } else if (ALL.equals(line)) {
            hint = "按发布时间排列。从 2.8.0 起分成两条线：仿真环境走 3.x，学生桌面端走 4.x。";
        } else if (TRUNK.equals(line)) {
            hint = "从 2.8.0 起分成两条线：仿真环境走 3.x，学生桌面端走 4.x。这里是分线之前（以及 2.x 延续）的共同记录。";
        } else {
            String desc = null;
            for (String[] t : TRACKS) if (t[0].equals(line)) desc = t[2];
            hint = (desc == null ? "" : desc + "　·　") + line + ".x　·　" + shown.size() + " 个版本"
                    + (shown.isEmpty() ? "" : "，最新 " + Json.str(shown.get(0), "version"));
        }
        lineHint.setText(hint == null ? "" : hint);
        lineHint.setVisibility(hint == null ? View.GONE : View.VISIBLE);
        list.setItems(shown);
        list.scrollToTop();
    }

    // ---------- 添加、删除 ----------

    @Override
    public Action fab() {
        return Action.icon(R.drawable.ic_add, "添加记录", this::openAdd);
    }

    @Override
    public List<Action> actions() {
        return Arrays.asList(Action.icon(R.drawable.ic_refresh, "刷新", () -> {
            list.loading();
            load();
        }));
    }

    private void openAdd() {
        Context c = ctx();
        Sheet s = new Sheet(c, "添加更新记录");
        Form f = new Form(c);
        // 默认沿用最新版本号，改个末位数字即可
        String latest = versions.isEmpty() ? "1.0.0" : Json.str(versions.get(0), "version");
        Form.Text ver = f.text("版本号", latest, "如 1.4.1").maxLength(32).required();
        ver.help("语义化版本：功能变更升次版本号，只修 bug 升修订号");
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT).format(new Date());
        Form.DateTime date = f.date("发布日期", today + "T00:00:00");
        f.row(ver, date);
        List<Option> typeOpts = new ArrayList<>();
        if (types.isEmpty()) {
            for (String t : new String[]{"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}) {
                typeOpts.add(new Option(t, t));
            }
        }
        for (JSONObject t : types) {
            typeOpts.add(new Option(Json.str(t, "value"), Json.str(t, "label") + "  " + Json.str(t, "value")));
        }
        Form.Select type = f.select("变动类型", typeOpts, "Added");
        Form.Text content = f.area("内容", "", 3).maxLength(1000).required();
        content.hint("说清楚改了什么、对使用者意味着什么，而不是罗列改了哪个文件");
        s.content(f.view());
        s.buttons("取消", null, "添加", () -> {
            if (!f.validate()) return;
            final String v = ver.value(), d = date.date(), tp = type.string(), body = content.value();
            runBusy("正在添加…", () -> {
                MeApi.changelogCreate(v, TextUtils.isEmpty(d) ? null : d, tp, body);
                return true;
            }, ok -> {
                s.dismiss();
                toast("已添加");
                load();
            });
        });
        s.show();
    }

    private void entryMenu(JSONObject entry, String version) {
        final String text = Json.str(entry, "content");
        Dialogs.actions(ctx(), version, Arrays.asList(
                Action.menu(R.drawable.ic_content_copy, "复制内容", () -> {
                    Sys.copy(ctx(), "更新日志", text);
                    toast("已复制");
                }),
                Action.menu(R.drawable.ic_delete, "删除这条", () -> confirmDelete(entry)).danger()));
    }

    private void confirmDelete(JSONObject entry) {
        final long id = entry.optLong("id");
        Dialogs.confirm(ctx(), "删除更新记录", "删除这条更新记录？\n\n" + Json.str(entry, "content"), "删除", true,
                () -> runBusy("正在删除…", () -> {
                    MeApi.changelogDelete(id);
                    return true;
                }, ok -> {
                    toast("已删除");
                    load();
                }));
    }
}
