package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.StateView;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「班级 → 在线座次」（网页端 2.20～2.22 的在线座次，APP 版）。
 *
 * <p>和网页端读写同一张座次表：网页上导入的 Excel 样式、排好的座位，这里原样显示；
 * APP 上换的座、分的组、标的设备故障，保存后网页端也看得到。
 *
 * <ul>
 *   <li>点学生：加减分（+1 +2 +5 −1 −2 / 自定义）、得分记录（可撤销）、设班长 / 组长、分组、离开座位</li>
 *   <li>长按学生拖到别的格子：换座位（拖到空座就是挪过去）</li>
 *   <li>「多选」：点格子勾选几位同学，一起加减分、分组，或把选中的座位标成设备故障</li>
 *   <li>一键排座（自动识别座位号、男女交替、学困生固定区域、按学号或随机）、小组管理、课堂得分、课堂日志</li>
 * </ul>
 * 能编辑的是本班老师和管理员（后端判），别的老师只能看座次表，看不到分数和学困生。
 * 导入 Excel 样式、改格子样式还是在网页端做。
 */
final class SeatScreen extends Screen {
    private final JSONObject cls;
    private final int cid;
    private SeatSheet sheet;
    private SeatSheet.Roster roster = new SeatSheet.Roster(null);
    private final Map<String, Integer> points = new HashMap<>();
    private boolean canEdit, dirty, selecting, loaded;

    private SeatBoardView board;
    private StateView state;
    private TextView zoomText;
    private LinearLayout selBar;
    private TextView selText;

    SeatScreen(JSONObject cls) {
        this.cls = cls;
        this.cid = Kit.id(cls);
    }

    @Override
    public String title() {
        return "在线座次 · " + Json.str(cls, "display");
    }

    @Override
    public String subtitle() {
        if (selecting) return "多选：点格子勾选，已选 " + pickedStudents().size() + " 位同学";
        if (dirty) return "有改动还没保存";
        if (!loaded) return null;
        return canEdit ? "点学生加减分，长按拖动换座" : "只能查看（不是你带的班）";
    }

    @Override
    protected View onCreateView(Context ctx) {
        FrameLayout root = new FrameLayout(ctx);
        LinearLayout col = V.vbox(ctx);
        root.addView(col, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));

        LinearLayout bar = V.hbox(ctx);
        V.pad(bar, 12, 6, 12, 6);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.addView(V.iconButton(ctx, R.drawable.ic_remove, "缩小", v -> zoom(1 / 1.2f)));
        zoomText = V.text(ctx, "100%", V.BODY2);
        zoomText.setGravity(Gravity.CENTER);
        zoomText.setMinWidth(dp(52));
        bar.addView(zoomText);
        bar.addView(V.iconButton(ctx, R.drawable.ic_add, "放大", v -> zoom(1.2f)));
        bar.addView(V.button(ctx, "适应", V.BTN_TEXT, v -> {
            board.fit();
            showZoom();
        }));
        bar.addView(V.spring(ctx), V.fill());
        bar.addView(V.button(ctx, "课堂日志", V.BTN_TEXT, v -> push(new ClassLogScreen(cls, canEdit))));
        col.addView(bar, V.matchWrap());

        FrameLayout body = new FrameLayout(ctx);
        board = new SeatBoardView(ctx);
        body.addView(board, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        state = new StateView(ctx);
        body.addView(state, new FrameLayout.LayoutParams(V.MATCH, V.MATCH));
        col.addView(body, new LinearLayout.LayoutParams(V.MATCH, 0, 1f));

        selBar = V.hbox(ctx);
        V.pad(selBar, 12, 8, 12, 8);
        selBar.setGravity(Gravity.CENTER_VERTICAL);
        selBar.setBackgroundColor(cn.wfxxkj.teacher.core.ui.Palette.of(ctx).surface);
        selText = V.text(ctx, "", V.BODY2);
        selBar.addView(selText, V.fill());
        selBar.addView(V.button(ctx, "加减分", V.BTN_TONAL, v -> batchPointsMenu()));
        V.addStart(selBar, V.button(ctx, "分组", V.BTN_TONAL, v -> pickGroup(pickedStudents())), 6);
        V.addStart(selBar, V.button(ctx, "故障", V.BTN_TONAL, v -> toggleBrokenSelection()), 6);
        selBar.setVisibility(View.GONE);
        col.addView(selBar, V.matchWrap());

        board.setListener(new SeatBoardView.Listener() {
            @Override
            public void onTap(int x, int y) {
                guard("点格子", () -> tap(x, y));
            }

            @Override
            public boolean canDrag(int x, int y) {
                return canEdit && !selecting && studentAt(x, y) != null;
            }

            @Override
            public void onDrop(int fx, int fy, int tx, int ty) {
                guard("换座位", () -> drop(fx, fy, tx, ty));
            }
        });
        board.setDeco(new SeatBoardView.Deco() {
            @Override
            public int groupColor(int x, int y) {
                JSONObject s = studentAt(x, y);
                return s == null ? 0 : sheet.groupColor(s.optInt("id"));
            }

            @Override
            public String role(int x, int y) {
                JSONObject s = studentAt(x, y);
                return s == null ? null : s.optString("class_role", "");
            }

            @Override
            public String points(int x, int y) {
                JSONObject s = studentAt(x, y);
                if (s == null || !canEdit) return null;
                Integer p = points.get(String.valueOf(s.optInt("id")));
                return p == null || p == 0 ? null : (p > 0 ? "+" + p : String.valueOf(p));
            }

            @Override
            public String broken(int x, int y) {
                return sheet == null ? null : sheet.broken.get(SeatSheet.name(x, y));
            }
        });
        return root;
    }

    @Override
    protected void onFirstShow() {
        load();
    }

    private void load() {
        state.loading();
        run(() -> {
            JSONObject got = StudentApi.seatSheet(cid);
            JSONObject pts = null;
            if (Json.bool(got, "can_edit")) {
                try {
                    pts = StudentApi.points(cid);
                } catch (Exception ignored) {
                    // 没权限看分数就不显示
                }
            }
            return new Object[]{got, pts};
        }, r -> {
            JSONObject got = (JSONObject) r[0];
            canEdit = Json.bool(got, "can_edit");
            roster = new SeatSheet.Roster(Json.list(Json.arr(got, "students")));
            points.clear();
            if (r[1] != null) readTotals(Json.obj((JSONObject) r[1], "totals"));
            loaded = true;
            JSONObject s = got.optJSONObject("sheet");
            if (s == null) {
                sheet = null;
                if (canEdit) {
                    state.empty("还没有在线座次表",
                            "可以在网页端「班级 → 在线座次」导入 Excel 样式，也可以先在这里建一张简单的座次表",
                            "新建座次表", this::createSimple);
                } else {
                    state.empty("这个班还没有在线座次表", "由班主任在网页端或 APP 里建好后，这里就能看到", null, null);
                }
            } else {
                setSheet(new SeatSheet(s));
            }
            dirty = false;
            invalidateChrome();
        }, e -> {
            state.error(e.getMessage(), this::load);
            return true;
        });
    }

    private void setSheet(SeatSheet s) {
        sheet = s;
        state.hide();
        board.setSheet(s);
        board.post(this::showZoom);
    }

    private void readTotals(JSONObject totals) {
        if (totals == null) return;
        for (Iterator<String> it = totals.keys(); it.hasNext(); ) {
            String k = it.next();
            points.put(k, totals.optInt(k));
        }
    }

    private JSONObject studentAt(int x, int y) {
        return sheet == null ? null : roster.find(sheet.get(x, y));
    }

    private void zoom(float f) {
        board.zoomBy(f);
        showZoom();
    }

    private void showZoom() {
        zoomText.setText(board.zoomPercent() + "%");
    }

    private void changed() {
        dirty = true;
        board.invalidate();
        invalidateChrome();
    }

    // ---------------------------------------------------------------- 顶栏

    @Override
    public List<Action> actions() {
        List<Action> a = new ArrayList<>();
        if (selecting) {
            a.add(Action.icon(R.drawable.ic_close, "退出多选", this::stopSelecting));
            return a;
        }
        if (canEdit && sheet != null) {
            a.add(Action.icon(R.drawable.ic_check, "保存", this::save).enabled(dirty));
            a.add(Action.menu(R.drawable.ic_check_circle, "多选（批量加减分 / 分组 / 设备故障）", this::startSelecting));
            a.add(Action.menu(R.drawable.ic_shuffle, "一键排座", this::openPlan));
            a.add(Action.menu(R.drawable.ic_groups, "小组", this::manageGroups));
            a.add(Action.menu(R.drawable.ic_emoji_events, "课堂得分", this::showScores));
        }
        a.add(Action.menu(R.drawable.ic_edit_note, "课堂日志", () -> push(new ClassLogScreen(cls, canEdit))));
        a.add(Action.menu(R.drawable.ic_refresh, "重新载入", () -> confirmDiscard(this::load)));
        if (canEdit && sheet != null) {
            a.add(Action.menu(R.drawable.ic_delete, "清空座次表", this::clearSheet).danger());
        }
        return a;
    }

    @Override
    public boolean onBack() {
        if (selecting) {
            stopSelecting();
            return true;
        }
        if (dirty) {
            Dialogs.confirm(ctx(), "座次表改了还没保存", "现在离开，这次的换座、分组、设备故障都不保存（加减分已经即时生效）。",
                    "不保存，离开", true, () -> {
                        dirty = false;
                        finish();
                    });
            return true;
        }
        return false;
    }

    private void confirmDiscard(Runnable then) {
        if (!dirty) {
            then.run();
            return;
        }
        Dialogs.confirm(ctx(), "放弃没保存的改动？", "换座、分组、设备故障这些改动还没保存。", "放弃", true, then);
    }

    private void save() {
        if (sheet == null) return;
        final JSONObject body = sheet.toJson();
        runBusy("正在保存…", () -> StudentApi.saveSeatSheet(cid, body), row -> {
            dirty = false;
            Kit.touch();
            invalidateChrome();
            toast("座次表已保存");
        });
    }

    private void clearSheet() {
        Dialogs.confirm(ctx(), "清空座次表", "整张在线座次表（座位、小组、设备故障）都删掉，网页端也一起没了。课堂得分和日志不受影响。",
                "清空", true, () -> runBusy("正在清空…", () -> {
                    StudentApi.deleteSeatSheet(cid);
                    return true;
                }, r -> {
                    Kit.touch();
                    toast("已清空");
                    load();
                }));
    }

    /** 没有座次表时建一张简单的：每列一组座位号 + 座位，第一行是讲台 */
    private void createSimple() {
        Context c = ctx();
        Sheet s = new Sheet(c, "新建座次表");
        Form f = new Form(c);
        f.note("按机房的排列建一张简单的座次表：每一列座位前面有一格座位号（A1、A2…），建好后可以「一键排座」把本班学生排进去。"
                + "想要和机房一模一样的样式，到网页端导入 Excel。");
        final Form.Stepper cols = f.stepper("几列（A、B、C…）", 4, 1, 12);
        final Form.Stepper rows = f.stepper("每列几个座位", 12, 1, 40);
        f.row(cols, rows);
        s.content(f.view());
        s.buttons("取消", null, "建表", () -> {
            s.dismiss();
            int nc = cols.value(), nr = rows.value();
            try {
                JSONArray data = new JSONArray();
                JSONArray head = new JSONArray();
                for (int x = 0; x < nc * 2; x++) head.put(x == 0 ? "讲台" : "");
                data.put(head);
                for (int y = 0; y < nr; y++) {
                    JSONArray line = new JSONArray();
                    for (int g = 0; g < nc; g++) {
                        line.put(String.valueOf((char) ('A' + g)) + (y + 1));
                        line.put("");
                    }
                    data.put(line);
                }
                JSONArray w = new JSONArray();
                JSONObject style = new JSONObject();
                for (int x = 0; x < nc * 2; x++) {
                    w.put(x % 2 == 0 ? 44 : 110);
                    for (int y = 1; y <= nr; y++) {
                        style.put(SeatSheet.name(x, y), x % 2 == 0
                                ? "text-align:center;color:#888888;font-size:12px;"
                                : "text-align:center;border-top:1px solid #999999;border-right:1px solid #999999;"
                                + "border-bottom:1px solid #999999;border-left:1px solid #999999;");
                    }
                }
                style.put("A1", "text-align:center;font-weight:bold;background-color:#EEEEEE;");
                JSONObject merge = new JSONObject();
                merge.put("A1", new JSONArray(Arrays.asList(nc * 2, 1)));
                JSONObject raw = Json.of("version", 1, "data", data, "colWidths", w, "style", style,
                        "mergeCells", merge, "rowHeights", new JSONObject());
                SeatSheet ns = new SeatSheet(raw);
                ns.seatRanges = SeatSheet.toRanges(ns.detectSeats(roster));
                setSheet(ns);
                changed();
                toast("建好了，记得保存；可以先「一键排座」");
            } catch (Exception e) {
                showError(e);
            }
        });
        s.show();
    }

    // ---------------------------------------------------------------- 点、拖

    private void tap(int x, int y) {
        if (sheet == null) return;
        String name = SeatSheet.name(x, y);
        if (selecting) {
            Set<String> sel = board.selection();
            if (!sel.remove(name)) sel.add(name);
            board.invalidate();
            updateSelBar();
            return;
        }
        JSONObject st = studentAt(x, y);
        if (!canEdit) {
            if (st != null) toast(Json.str(st, "name"));
            return;
        }
        if (st != null) {
            studentMenu(st, x, y);
            return;
        }
        cellMenu(x, y);
    }

    private void drop(int fx, int fy, int tx, int ty) {
        JSONObject a = studentAt(fx, fy);
        String bText = sheet.get(tx, ty);
        JSONObject b = roster.find(bText);
        String to = SeatSheet.name(tx, ty);
        if (a == null) return;
        if (!bText.trim().isEmpty() && b == null) {
            toast(to + " 写着「" + bText.trim() + "」，不是学生座位，换不过去");
            return;
        }
        if (sheet.covered.contains(to)) return;
        if (sheet.broken.containsKey(to)) {
            String why = sheet.broken.get(to);
            toast(to + " 设备故障（" + (TextUtils.isEmpty(why) ? "不可入座" : why) + "），不能坐");
            return;
        }
        String aText = sheet.get(fx, fy);
        sheet.set(tx, ty, aText);
        sheet.set(fx, fy, bText);
        changed();
        toast(b != null ? Json.str(a, "name") + " ⇄ " + Json.str(b, "name") + " 互换了座位"
                : Json.str(a, "name") + " 换到了 " + to);
    }

    // ---------------------------------------------------------------- 学生菜单

    private void studentMenu(JSONObject st, int x, int y) {
        int id = st.optInt("id");
        int total = points.containsKey(String.valueOf(id)) ? points.get(String.valueOf(id)) : 0;
        JSONObject g = sheet.group(sheet.groupOf.get(String.valueOf(id)));
        String role = st.optString("class_role", "");
        StringBuilder title = new StringBuilder(Json.str(st, "name"));
        title.append("  ").append(total > 0 ? "+" : "").append(total).append(" 分");
        if (!role.isEmpty()) title.append(" · ").append(role);
        if (g != null) title.append(" · ").append(g.optString("name"));

        List<Action> a = new ArrayList<>();
        for (final int d : new int[]{1, 2, 5, -1, -2}) {
            a.add(Action.menu((d > 0 ? "+" : "") + d + " 分", () -> addPoint(st, d, "")));
        }
        a.add(Action.menu(R.drawable.ic_edit, "自定义加减分（可写原因）", () -> customPoints(java.util.Collections.singletonList(st))));
        a.add(Action.menu(R.drawable.ic_history, "得分记录（可撤销）", () -> history(st)));
        if (!"班长".equals(role)) a.add(Action.menu(R.drawable.ic_star, "设为班长", () -> setRole(st, "班长")));
        if (!"组长".equals(role)) a.add(Action.menu(R.drawable.ic_star, "设为组长", () -> setRole(st, "组长")));
        if (!role.isEmpty()) a.add(Action.menu(R.drawable.ic_close, "取消" + role, () -> setRole(st, "")));
        a.add(Action.menu(R.drawable.ic_groups, "分组…", () -> pickGroup(java.util.Collections.singletonList(st))));
        a.add(Action.menu(R.drawable.ic_logout, "离开座位（清空这一格）", () -> {
            sheet.set(x, y, "");
            changed();
        }));
        Dialogs.actions(ctx(), title.toString(), a);
    }

    /** 空座位、写着别的字的格子：设备故障、改字 */
    private void cellMenu(int x, int y) {
        final String name = SeatSheet.name(x, y);
        List<Action> a = new ArrayList<>();
        boolean bk = sheet.broken.containsKey(name);
        if (bk) {
            a.add(Action.menu(R.drawable.ic_check_circle, "修好了（可以坐人）", () -> clearBroken(java.util.Collections.singletonList(name))));
        } else if (sheet.get(x, y).trim().isEmpty()) {
            a.add(Action.menu(R.drawable.ic_warning, "标成设备故障（不可入座）", () -> markBroken(java.util.Collections.singletonList(name))));
        }
        a.add(Action.menu(R.drawable.ic_edit, "改这一格的文字", () -> Dialogs.prompt(ctx(), "改 " + name, "格子里的文字",
                sheet.get(x, y), 2, "确定", t -> {
                    sheet.set(x, y, t.trim());
                    changed();
                })));
        String cur = sheet.get(x, y).trim();
        Dialogs.actions(ctx(), name + (cur.isEmpty() ? (bk ? " · 设备故障" : " · 空格子") : " · " + cur), a);
    }

    // ---------------------------------------------------------------- 加减分

    private void addPoint(JSONObject st, int delta, String reason) {
        final int id = st.optInt("id");
        run(() -> StudentApi.addPoint(cid, id, delta, reason), r -> {
            int total = Json.num(r, "total");
            points.put(String.valueOf(id), total);
            board.invalidate();
            toast(Json.str(st, "name") + " " + (delta > 0 ? "+" : "") + delta + " 分"
                    + (reason.isEmpty() ? "" : "（" + reason + "）") + "，现在 " + total + " 分");
        });
    }

    private void addPoints(List<JSONObject> list, int delta, String reason) {
        if (list.isEmpty()) {
            toast("先勾选坐着学生的格子");
            return;
        }
        final List<Integer> ids = new ArrayList<>();
        for (JSONObject s : list) ids.add(s.optInt("id"));
        run(() -> StudentApi.addPoints(cid, ids, delta, reason), r -> {
            readTotals(Json.obj(r, "totals"));
            board.invalidate();
            toast(list.size() + " 位同学各 " + (delta > 0 ? "+" : "") + delta + " 分" + (reason.isEmpty() ? "" : "（" + reason + "）"));
        });
    }

    private static final Pattern CUSTOM = Pattern.compile("^\\s*([+\\-－]?)(\\d{1,3})\\s*(.*)$", Pattern.DOTALL);

    private void customPoints(List<JSONObject> list) {
        String title = list.size() == 1 ? "给 " + Json.str(list.get(0), "name") + " 加减分"
                : "给选中的 " + list.size() + " 位同学一起加减分";
        Dialogs.prompt(ctx(), title, "先写分值，后面可以跟原因，如「+3 回答问题」「-2 上课说话」", "", 1, "确定", t -> {
            Matcher m = CUSTOM.matcher(t);
            if (!m.matches()) {
                toast("开头写分值，如 +3 或 -2");
                return;
            }
            int delta = ("-".equals(m.group(1)) || "－".equals(m.group(1)) ? -1 : 1) * Integer.parseInt(m.group(2));
            String reason = m.group(3).trim();
            if (reason.length() > 64) reason = reason.substring(0, 64);
            if (delta == 0) {
                toast("分值不能是 0");
                return;
            }
            if (Math.abs(delta) > 100) {
                toast("一次最多加减 100 分");
                return;
            }
            if (list.size() == 1) addPoint(list.get(0), delta, reason);
            else addPoints(list, delta, reason);
        });
    }

    private void batchPointsMenu() {
        final List<JSONObject> list = pickedStudents();
        if (list.isEmpty()) {
            toast("先点格子勾选坐着学生的座位");
            return;
        }
        List<Action> a = new ArrayList<>();
        for (final int d : new int[]{1, 2, 5, -1, -2}) {
            a.add(Action.menu("每人 " + (d > 0 ? "+" : "") + d + " 分", () -> addPoints(list, d, "")));
        }
        a.add(Action.menu(R.drawable.ic_edit, "自定义加减分（可写原因）", () -> customPoints(list)));
        Dialogs.actions(ctx(), "给选中的 " + list.size() + " 位同学加减分", a);
    }

    /** 一位学生的得分记录，点「撤销」撤掉那一笔 */
    private void history(JSONObject st) {
        final int id = st.optInt("id");
        Sheet s = new Sheet(ctx(), Json.str(st, "name") + " 的得分记录");
        LinearLayout box = V.vbox(ctx());
        box.addView(V.text(ctx(), "加载中…", V.BODY2));
        s.content(box);
        s.buttons(null, null, "关闭", s::dismiss);
        s.show();
        run(() -> StudentApi.points(cid), r -> renderHistory(s, box, st, Json.list(Json.arr(r, "recent")), id));
    }

    private void renderHistory(Sheet s, LinearLayout box, JSONObject st, List<JSONObject> recent, int id) {
        Context c = ctx();
        box.removeAllViews();
        int n = 0;
        for (final JSONObject p : recent) {
            if (p.optInt("student_id") != id) continue;
            n++;
            LinearLayout row = V.hbox(c);
            V.pad(row, 0, 6, 0, 6);
            row.setGravity(Gravity.CENTER_VERTICAL);
            int d = p.optInt("delta");
            TextView v = V.bold(V.text(c, (d > 0 ? "+" : "") + d, V.H3));
            v.setTextColor(d > 0 ? 0xFF2E7D32 : 0xFFC62828);
            v.setMinWidth(dp(44));
            row.addView(v);
            LinearLayout texts = V.vbox(c);
            String reason = Json.str(p, "reason");
            texts.addView(V.text(c, reason.isEmpty() ? "（没写原因）" : reason, V.BODY2));
            texts.addView(V.text(c, Json.str(p, "created_at").replace('T', ' ').replaceAll("\\..*$", "")
                    + " · " + Json.str(p, "author_name"), V.CAPTION));
            row.addView(texts, V.fill());
            row.addView(V.button(c, "撤销", V.BTN_TEXT, b -> run(() -> StudentApi.undoPoint(cid, p.optInt("id")), r -> {
                points.put(String.valueOf(id), Json.num(r, "total"));
                board.invalidate();
                toast("已撤销，" + Json.str(st, "name") + " 现在 " + Json.num(r, "total") + " 分");
                List<JSONObject> rest = new ArrayList<>(recent);
                rest.remove(p);
                renderHistory(s, box, st, rest, id);
            })));
            box.addView(row, V.matchWrap());
        }
        if (n == 0) box.addView(V.text(c, "最近没有加减分记录", V.BODY2));
    }

    /** 全班得分：小组合计 + 每位同学总分，点人看记录 */
    private void showScores() {
        Context c = ctx();
        Sheet s = new Sheet(c, "课堂得分");
        LinearLayout box = V.vbox(c);
        // 小组合计
        if (!sheet.groups.isEmpty()) {
            box.addView(V.text(c, "小组", V.CAPTION));
            for (JSONObject g : sheet.groups) {
                String gid = String.valueOf(g.opt("id"));
                int n = 0, sum = 0;
                List<String> leaders = new ArrayList<>();
                for (JSONObject st : roster.students) {
                    String k = String.valueOf(st.optInt("id"));
                    if (!gid.equals(sheet.groupOf.get(k))) continue;
                    n++;
                    Integer p = points.get(k);
                    sum += p == null ? 0 : p;
                    if ("组长".equals(st.optString("class_role"))) leaders.add(Json.str(st, "name"));
                }
                box.addView(V.kv(c, g.optString("name") + "（" + n + " 人" + (leaders.isEmpty() ? "" : "，组长 "
                        + TextUtils.join("、", leaders)) + "）", (sum > 0 ? "+" : "") + sum + " 分"));
            }
            V.addTop(box, V.text(c, "个人", V.CAPTION), 12);
        }
        List<JSONObject> list = new ArrayList<>(roster.students);
        java.util.Collections.sort(list, (a, b) -> Integer.compare(score(b), score(a)));
        for (final JSONObject st : list) {
            int p = score(st);
            LinearLayout row = V.kv(c, Json.str(st, "name") + (st.optString("class_role").isEmpty() ? ""
                    : " · " + st.optString("class_role")), (p > 0 ? "+" : "") + p + " 分");
            V.clickable(row, 8, v -> history(st));
            box.addView(row);
        }
        if (list.isEmpty()) box.addView(V.text(c, "这个班还没有学生", V.BODY2));
        s.content(V.scroll(c, box));
        s.buttons(null, null, "关闭", s::dismiss);
        s.show();
    }

    private int score(JSONObject st) {
        Integer p = points.get(String.valueOf(st.optInt("id")));
        return p == null ? 0 : p;
    }

    // ---------------------------------------------------------------- 班干部、小组

    private void setRole(JSONObject st, String role) {
        final int id = st.optInt("id");
        run(() -> StudentApi.patchStudent(id, Json.of("class_role", role)), r -> {
            if ("班长".equals(role)) {
                for (JSONObject s : roster.students) if ("班长".equals(s.optString("class_role"))) Json.put(s, "class_role", "");
            }
            Json.put(st, "class_role", role);
            Kit.touch();
            board.invalidate();
            toast(role.isEmpty() ? "已取消 " + Json.str(st, "name") + " 的班干部" : "已设 " + Json.str(st, "name") + " 为" + role);
        });
    }

    private void pickGroup(List<JSONObject> list) {
        if (list.isEmpty()) {
            toast("先点格子勾选坐着学生的座位");
            return;
        }
        List<Option> opts = new ArrayList<>();
        for (JSONObject g : sheet.groups) opts.add(new Option(String.valueOf(g.opt("id")), g.optString("name")));
        opts.add(new Option("", "不分组"));
        opts.add(new Option("__new", "＋ 新建一个小组再分进去"));
        String cur = list.size() == 1 ? sheet.groupOf.get(String.valueOf(list.get(0).optInt("id"))) : null;
        Dialogs.choose(ctx(), list.size() == 1 ? Json.str(list.get(0), "name") + " 分到哪个组"
                : list.size() + " 位同学分到哪个组", opts, cur == null ? "" : cur, o -> {
            String gid = String.valueOf(o.value);
            if ("__new".equals(gid)) gid = String.valueOf(sheet.addGroup().opt("id"));
            for (JSONObject s : list) {
                String k = String.valueOf(s.optInt("id"));
                if (gid.isEmpty()) sheet.groupOf.remove(k);
                else sheet.groupOf.put(k, gid);
            }
            changed();
            JSONObject g = sheet.group(gid);
            toast((list.size() == 1 ? Json.str(list.get(0), "name") : list.size() + " 位同学")
                    + (g == null ? " 不分组了" : " 分到「" + g.optString("name") + "」"));
        });
    }

    /** 小组管理：新建、改名、换颜色、删除、清空分组 */
    private void manageGroups() {
        Context c = ctx();
        Sheet s = new Sheet(c, "小组");
        LinearLayout box = V.vbox(c);
        s.content(box);
        Runnable[] render = new Runnable[1];
        render[0] = () -> {
            box.removeAllViews();
            box.addView(V.text(c, "小组跟着学生走：换座位时底色跟着人一起走。点学生也能单独分组。改完记得保存座次表。", V.CAPTION));
            for (final JSONObject g : new ArrayList<>(sheet.groups)) {
                String gid = String.valueOf(g.opt("id"));
                int n = 0;
                for (String v : sheet.groupOf.values()) if (gid.equals(v)) n++;
                LinearLayout row = V.hbox(c);
                V.pad(row, 0, 6, 0, 6);
                row.setGravity(Gravity.CENTER_VERTICAL);
                View dot = new View(c);
                dot.setBackground(V.round(c, SeatSheet.color(g.optString("color"), 0xFFE6E9EE), 6));
                V.clickable(dot, 6, v -> {
                    int i = Arrays.asList(SeatSheet.GROUP_COLORS).indexOf(g.optString("color").toUpperCase());
                    Json.put(g, "color", SeatSheet.GROUP_COLORS[(i + 1) % SeatSheet.GROUP_COLORS.length]);
                    changed();
                    render[0].run();
                });
                row.addView(dot, new LinearLayout.LayoutParams(dp(28), dp(28)));
                V.addStart(row, V.text(c, g.optString("name") + "  · " + n + " 人", V.BODY), 10);
                row.addView(V.spring(c), V.fill());
                row.addView(V.button(c, "改名", V.BTN_TEXT, v -> Dialogs.prompt(c, "小组改名", "如 第1组、红队",
                        g.optString("name"), 1, "确定", t -> {
                            if (t.trim().isEmpty()) return;
                            Json.put(g, "name", t.trim().length() > 16 ? t.trim().substring(0, 16) : t.trim());
                            changed();
                            render[0].run();
                        })));
                final int members = n;
                row.addView(V.button(c, "删除", V.BTN_TEXT, v -> {
                    Runnable del = () -> {
                        sheet.removeGroup(g);
                        changed();
                        render[0].run();
                    };
                    if (members == 0) del.run();
                    else Dialogs.confirm(c, "删除小组", "「" + g.optString("name") + "」里有 " + members
                            + " 位同学，删掉后他们变成不分组。", "删除", true, del);
                }));
                box.addView(row, V.matchWrap());
            }
            if (sheet.groups.isEmpty()) V.addTop(box, V.text(c, "还没有小组。点颜色块可以换颜色。", V.BODY2), 8);
            LinearLayout btns = V.hbox(c);
            btns.addView(V.button(c, "新建小组", V.BTN_TONAL, v -> {
                sheet.addGroup();
                changed();
                render[0].run();
            }));
            V.addStart(btns, V.button(c, "一次建 6 个", V.BTN_TEXT, v -> {
                while (sheet.groups.size() < 6) sheet.addGroup();
                changed();
                render[0].run();
            }), 6);
            V.addStart(btns, V.button(c, "清空分组", V.BTN_TEXT, v -> Dialogs.confirm(c, "清空分组",
                    "所有同学都变成不分组（小组本身留着）？", "清空", true, () -> {
                        sheet.groupOf.clear();
                        changed();
                        render[0].run();
                    })), 6);
            V.addTop(box, btns, 12);
        };
        render[0].run();
        s.buttons(null, null, "完成", s::dismiss);
        s.show();
    }

    // ---------------------------------------------------------------- 多选

    private void startSelecting() {
        selecting = true;
        board.selection().clear();
        selBar.setVisibility(View.VISIBLE);
        updateSelBar();
        invalidateChrome();
        toast("点格子勾选，再点下面的按钮");
    }

    private void stopSelecting() {
        selecting = false;
        board.selection().clear();
        selBar.setVisibility(View.GONE);
        board.invalidate();
        invalidateChrome();
    }

    private void updateSelBar() {
        selText.setText("已选 " + board.selection().size() + " 格 · " + pickedStudents().size() + " 位同学");
        invalidateChrome();
    }

    private List<JSONObject> pickedStudents() {
        Map<Integer, JSONObject> seen = new LinkedHashMap<>();
        if (sheet == null) return new ArrayList<>();
        for (String n : board.selection()) {
            int[] p = SeatSheet.parse(n);
            JSONObject s = p == null ? null : studentAt(p[0], p[1]);
            if (s != null) seen.put(s.optInt("id"), s);
        }
        return new ArrayList<>(seen.values());
    }

    // ---------------------------------------------------------------- 设备故障

    private void toggleBrokenSelection() {
        List<String> cells = new ArrayList<>(board.selection());
        if (cells.isEmpty()) {
            toast("先点格子勾选座位（座位号右边的格子）");
            return;
        }
        boolean all = true;
        for (String n : cells) if (!sheet.broken.containsKey(n)) all = false;
        if (all) clearBroken(cells);
        else markBroken(cells);
    }

    private void markBroken(List<String> cells) {
        final List<String> list = new ArrayList<>();
        for (String n : cells) if (!sheet.broken.containsKey(n)) list.add(n);
        if (list.isEmpty()) return;
        List<String> seated = new ArrayList<>();
        for (String n : list) {
            int[] p = SeatSheet.parse(n);
            JSONObject s = p == null ? null : studentAt(p[0], p[1]);
            if (s != null) seated.add(Json.str(s, "name"));
        }
        String title = list.size() == 1 ? list.get(0) + " 设备故障" : list.size() + " 个座位设备故障";
        String hint = "写一句是什么问题（显示在格子里），如：显示器不亮" + (seated.isEmpty() ? ""
                : "。上面坐着 " + TextUtils.join("、", seated) + "，会先请他们离开");
        Dialogs.prompt(ctx(), title, hint, "", 1, "标成故障", t -> {
            String why = t.trim().length() > 20 ? t.trim().substring(0, 20) : t.trim();
            for (String n : list) {
                int[] p = SeatSheet.parse(n);
                if (p != null && studentAt(p[0], p[1]) != null) sheet.set(p[0], p[1], "");
                sheet.broken.put(n, why);
            }
            changed();
            toast("已标 " + list.size() + " 个座位设备故障，排座位时会跳过");
        });
    }

    private void clearBroken(List<String> cells) {
        int n = 0;
        for (String c : cells) if (sheet.broken.remove(c) != null) n++;
        if (n > 0) {
            changed();
            toast(n + " 个座位修好了，可以坐人");
        }
    }

    // ---------------------------------------------------------------- 一键排座

    private void openPlan() {
        Context c = ctx();
        if (TextUtils.isEmpty(sheet.seatRanges)) sheet.seatRanges = SeatSheet.toRanges(sheet.detectSeats(roster));
        int weak = 0;
        for (JSONObject s : roster.students) if (s.optBoolean("struggling")) weak++;
        Sheet s = new Sheet(c, "一键导入本班学生");
        Form f = new Form(c);
        f.note("把本班 " + roster.students.size() + " 位同学排进座次表。排好先看一眼，没问题再点右上角保存。");
        final Form.Text ranges = f.area("放学生的区域", sheet.seatRanges, 2);
        ranges.help("格子名或区域，用逗号隔开，如 B2:B15, D2:D15");
        TextView auto = V.button(c, "自动识别座位（座位号右边那格）", V.BTN_TEXT, v -> {
            List<String> seats = sheet.detectSeats(roster);
            if (seats.isEmpty()) {
                toast("表里没认出座位号（A1、B2 这种），请手写区域");
                return;
            }
            ranges.set(SeatSheet.toRanges(seats));
            int nb = 0;
            for (String n : seats) if (sheet.broken.containsKey(n)) nb++;
            toast("认出 " + seats.size() + " 个座位" + (nb > 0 ? "，其中 " + nb + " 个设备故障会跳过" : ""));
        });
        f.custom(auto);
        final Form.Choice order = f.choice("顺序", Arrays.asList(new Option(true, "随机打乱"), new Option(false, "按学号顺序")), true);
        final Form.Choice content = f.choice("格子里写", Arrays.asList(new Option("name", "姓名"), new Option("no_name", "学号 + 姓名")), "name");
        final Form.Toggle gender = f.toggle("男女交替", "同一排男女生错开坐", false);
        final Form.Toggle zoneOn = f.toggle("学困生坐固定区域", "本班标了 " + weak + " 位学困生，安排在下面的区域里（方便辅导）", false);
        final Form.Text zone = f.text("固定区域", sheet.zoneRanges, "如 B2:B5");
        zone.setVisible(false);
        zoneOn.onChange(() -> zone.setVisible(zoneOn.value()));
        s.content(V.scroll(c, f.view()));
        s.buttons("取消", null, "排座位", () -> {
            String rg = ranges.value().trim();
            if (rg.isEmpty()) {
                ranges.setError("先写要放学生的区域，或点「自动识别座位」");
                return;
            }
            sheet.seatRanges = rg;
            sheet.zoneRanges = zone.value().trim();
            List<String> skip = new ArrayList<>(sheet.covered);
            skip.addAll(sheet.broken.keySet());
            JSONObject body = Json.of("ranges", rg, "zone", sheet.zoneRanges, "alternate_gender", gender.value(),
                    "struggling_zone", zoneOn.value(), "shuffle", Boolean.TRUE.equals(order.value()),
                    "content", String.valueOf(content.value()), "skip", skip,
                    "seed", System.currentTimeMillis() + "-" + Math.random());
            runBusy("正在排座位…", () -> StudentApi.seatPlan(cid, body), got -> {
                s.dismiss();
                applyPlan(got, rg);
            });
        });
        s.show();
    }

    private void applyPlan(JSONObject got, String rg) {
        final List<JSONObject> assigns = Json.list(Json.arr(got, "assignments"));
        int filled = 0;
        for (JSONObject a : assigns) {
            int[] p = SeatSheet.parse(Json.str(a, "cell"));
            if (p != null && !sheet.get(p[0], p[1]).trim().isEmpty()) filled++;
        }
        Runnable apply = () -> {
            Set<String> seats = new HashSet<>();
            for (JSONObject a : assigns) seats.add(Json.str(a, "cell").toUpperCase());
            for (String n : SeatSheet.expand(rg)) {
                if (seats.contains(n)) continue;
                int[] p = SeatSheet.parse(n);
                if (p != null) sheet.set(p[0], p[1], "");
            }
            for (JSONObject a : assigns) {
                int[] p = SeatSheet.parse(Json.str(a, "cell"));
                if (p != null) sheet.set(p[0], p[1], Json.str(a, "text"));
            }
            changed();
            List<String> warns = Json.strings(Json.arr(got, "warnings"));
            Dialogs.alert(ctx(), "排好了", "排好了 " + assigns.size() + " 位同学（共 " + Json.num(got, "seats")
                    + " 个座位）。看过没问题点右上角「保存」。" + (warns.isEmpty() ? "" : "\n\n" + TextUtils.join("\n", warns)));
        };
        if (filled > 0) {
            Dialogs.confirm(ctx(), "重新排座位", "这些座位里已经有 " + filled + " 个格子写了字，重新排会覆盖掉，确定吗？",
                    "覆盖并重新排", true, apply);
        } else {
            apply.run();
        }
    }
}
