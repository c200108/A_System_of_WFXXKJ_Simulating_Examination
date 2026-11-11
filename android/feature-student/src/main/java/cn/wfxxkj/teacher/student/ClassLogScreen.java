package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.text.TextUtils;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.ItemList;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 课堂情况日志（网页端在线座次右边那一栏）：每次上机记一条 —— 请假缺勤、设备问题、课堂情况。
 * 谁都能看（任课老师想知道上节课机房出了什么事）；写、改、删只有本班老师和管理员。
 */
final class ClassLogScreen extends Screen {
    private final JSONObject cls;
    private final int cid;
    private final boolean canEdit;
    private ItemList<JSONObject> list;
    private List<JSONObject> students;

    ClassLogScreen(JSONObject cls, boolean canEdit) {
        this.cls = cls;
        this.cid = Kit.id(cls);
        this.canEdit = canEdit;
    }

    @Override
    public String title() {
        return "课堂日志 · " + Json.str(cls, "display");
    }

    @Override
    public String subtitle() {
        return list == null || list.size() == 0 ? null : "共 " + list.size() + " 条";
    }

    @Override
    protected View onCreateView(Context ctx) {
        list = new ItemList<>(ctx, new ItemList.Binder<JSONObject>() {
            @Override
            public View create(Context c) {
                LinearLayout card = V.card(c);
                return card;
            }

            @Override
            public void bind(View v, JSONObject log, int position) {
                bindCard((LinearLayout) v, log);
            }
        });
        list.setCell(320, 2);
        list.setOnRefresh(this::load);
        list.setOnItemClick((log, pos) -> {
            if (canEdit) edit(log);
            else Dialogs.alert(ctx(), dayLabel(Json.str(log, "lesson_date")) + " " + Json.str(log, "title"),
                    Json.str(log, "content"));
        });
        if (canEdit) list.setOnItemLongClick((log, pos) -> remove(log));
        return list;
    }

    private void bindCard(LinearLayout card, JSONObject log) {
        Context c = card.getContext();
        card.removeAllViews();
        LinearLayout head = V.hbox(c);
        head.addView(V.bold(V.text(c, dayLabel(Json.str(log, "lesson_date")), V.BODY)));
        String t = Json.str(log, "title");
        if (!t.isEmpty()) V.addStart(head, V.oneLine(V.text(c, t, V.BODY2)), 8);
        card.addView(head);
        String content = Json.str(log, "content").trim();
        if (!content.isEmpty()) V.addTop(card, V.lines(V.text(c, content, V.BODY2), 8), 6);
        TextView meta = V.text(c, Json.str(log, "author_name") + " · " + stamp(Json.str(log, "updated_at"))
                + (canEdit ? " · 点开修改，长按删除" : ""), V.CAPTION);
        V.addTop(card, meta, 6);
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    private void load() {
        list.loading();
        run(() -> StudentApi.logs(cid), rows -> {
            list.setEmpty("还没有课堂日志", canEdit ? "每次上机后记一条：请假缺勤、设备问题、课堂情况" : null,
                    canEdit ? "写一条" : null, canEdit ? () -> edit(null) : null);
            list.setItems(rows);
            invalidateChrome();
        }, e -> {
            list.error(e.getMessage(), this::load);
            return true;
        });
    }

    @Override
    public List<Action> actions() {
        return Collections.singletonList(Action.icon(R.drawable.ic_refresh, "刷新", this::load));
    }

    @Override
    public Action fab() {
        return canEdit ? Action.icon(R.drawable.ic_add, "写一条日志", () -> edit(null)) : null;
    }

    // ---------- 写 / 改 ----------

    private void edit(final JSONObject log) {
        Context c = ctx();
        Sheet s = new Sheet(c, log == null ? "写课堂日志" : "修改课堂日志");
        Form f = new Form(c);
        final Form.DateTime date = f.date("上课日期", log == null ? today() : Json.str(log, "lesson_date"));
        final Form.Text title = f.text("标题", log == null ? "第 " + (list.size() + 1) + " 次上机" : Json.str(log, "title"),
                "可以不写");
        title.maxLength(64);
        final Form.Text content = f.area("内容", log == null ? "请假 / 缺勤：\n设备问题：\n课堂情况："
                : Json.str(log, "content"), 6);
        f.custom(V.button(c, "从名单里选缺勤的同学", V.BTN_TEXT, v -> pickAbsent(content)));
        s.content(V.scroll(c, f.view()));
        s.buttons("取消", null, "保存", () -> {
            String d = date.date();
            if (TextUtils.isEmpty(d)) {
                toast("先选上课日期");
                return;
            }
            if (title.value().trim().isEmpty() && content.raw().trim().isEmpty()) {
                toast("标题和内容至少写一样");
                return;
            }
            final Integer lid = log == null ? null : Kit.id(log);
            runBusy("正在保存…", () -> StudentApi.saveLog(cid, lid, d, title.value().trim(), content.raw()), row -> {
                s.dismiss();
                toast("日志已保存");
                load();
            });
        });
        s.show();
    }

    /** 选几位缺勤的同学，写进「请假 / 缺勤：」那一行（没有这一行就加在最前面），同网页端 */
    private void pickAbsent(final Form.Text content) {
        if (students == null) {
            run(() -> StudentApi.students(cid, null), rows -> {
                students = rows;
                pickAbsent(content);
            });
            return;
        }
        List<Option> opts = new ArrayList<>();
        for (JSONObject s : students) {
            if (!Json.bool(s, "is_active")) continue;
            opts.add(new Option(Json.str(s, "name"), Json.str(s, "name"), Json.str(s, "student_no")));
        }
        if (opts.isEmpty()) {
            toast("这个班还没有学生");
            return;
        }
        Dialogs.chooseMany(ctx(), "选缺勤的同学", opts, null, values -> {
            if (values.isEmpty()) return;
            List<String> names = new ArrayList<>();
            for (Object o : values) names.add(String.valueOf(o));
            String joined = TextUtils.join("、", names);
            String[] lines = content.raw().split("\n", -1);
            int hit = -1;
            for (int i = 0; i < lines.length; i++) if (lines[i].startsWith("请假") || lines[i].startsWith("缺勤")) {
                hit = i;
                break;
            }
            StringBuilder out = new StringBuilder();
            if (hit < 0) {
                out.append("请假 / 缺勤：").append(joined).append('\n').append(content.raw());
            } else {
                String l = lines[hit];
                int k = Math.max(l.indexOf(':'), l.indexOf('：'));
                if (l.indexOf(':') >= 0 && l.indexOf('：') >= 0) k = Math.min(l.indexOf(':'), l.indexOf('：'));
                String head = k >= 0 ? l.substring(0, k + 1) : l + "：";
                String rest = k >= 0 ? l.substring(k + 1).trim() : "";
                lines[hit] = head + (rest.isEmpty() ? joined : rest + "、" + joined);
                out.append(TextUtils.join("\n", lines));
            }
            content.set(out.toString());
        });
    }

    private void remove(final JSONObject log) {
        Dialogs.confirm(ctx(), "删除日志", "删掉 " + dayLabel(Json.str(log, "lesson_date")) + " 这条日志？", "删除", true,
                () -> runBusy("正在删除…", () -> {
                    StudentApi.deleteLog(cid, Kit.id(log));
                    return true;
                }, r -> {
                    toast("已删除");
                    load();
                }));
    }

    // ---------- 日期 ----------

    private static String today() {
        Calendar c = Calendar.getInstance();
        return String.format(Locale.ROOT, "%04d-%02d-%02d", c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1,
                c.get(Calendar.DAY_OF_MONTH));
    }

    private static final String WEEK = "日一二三四五六";

    /** 2026-11-11 → 11 月 11 日 周三 */
    static String dayLabel(String s) {
        try {
            String[] p = s.split("-");
            int y = Integer.parseInt(p[0]), m = Integer.parseInt(p[1]), d = Integer.parseInt(p[2].substring(0, 2));
            Calendar c = Calendar.getInstance();
            c.set(y, m - 1, d);
            return m + " 月 " + d + " 日 周" + WEEK.charAt(c.get(Calendar.DAY_OF_WEEK) - 1);
        } catch (RuntimeException e) {
            return s;
        }
    }

    private static String stamp(String s) {
        s = s == null ? "" : s.replace('T', ' ');
        return s.length() >= 16 ? s.substring(5, 16) : s;
    }
}
