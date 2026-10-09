package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.view.Gravity;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.io.Images;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.session.Session;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/** 题库模块里几处共用的常量和小部件：难度、题型颜色、仿真题种类、看大图、删除权限 */
final class Bank {
    private Bank() {}

    // ---------- 难度 1~5 ----------

    static final String[] LEVEL_TEXT = {"", "很容易", "容易", "中等", "较难", "很难"};

    /** 难度下拉的选项（存数字，后面的话只是说明） */
    static List<Option> levelOptions() {
        List<Option> out = new ArrayList<>();
        for (int i = 1; i <= 5; i++) out.add(new Option(i, i + " 级　" + LEVEL_TEXT[i]));
        return out;
    }

    /** 和网页难度小圆点一样：1、2 绿，3 灰，4 橙，5 红 */
    static Tone levelTone(int lv) {
        if (lv <= 2) return Tone.SUCCESS;
        if (lv == 3) return Tone.NEUTRAL;
        if (lv == 4) return Tone.WARNING;
        return Tone.DANGER;
    }

    /** 难度圆点 */
    static TextView levelDot(Context c, int lv) {
        int[] t = Palette.of(c).tone(levelTone(lv));
        TextView v = V.text(c, String.valueOf(lv), V.CAPTION);
        v.setTextColor(levelTone(lv) == Tone.NEUTRAL ? Palette.of(c).text2 : t[0]);
        V.bold(v);
        v.setGravity(Gravity.CENTER);
        v.setBackground(V.round(c, t[1], 11));
        int s = Ui.dp(c, 22);
        v.setLayoutParams(new LinearLayout.LayoutParams(s, s));
        return v;
    }

    // ---------- 题型 ----------

    static Tone typeTone(String type) {
        if ("选择题".equals(type)) return Tone.PRIMARY;
        if ("判断题".equals(type)) return Tone.INFO;
        if ("操作题".equals(type)) return Tone.VIOLET;
        if ("填空题".equals(type)) return Tone.WARNING;
        return Tone.NEUTRAL;
    }

    // ---------- 仿真任务种类 ----------

    static final String[] KINDS = {"win", "wps", "html", "ai"};
    static final String[] KIND_NAMES = {"Windows 操作", "WPS 文字", "网页编程", "AI 工具"};
    static final String[] KIND_DESC = {
            "XP 桌面，二十多种文件类型，新建改名移动删除",
            "照着 WPS 界面做的排版环境",
            "写 HTML/CSS，服务端解析标签和样式判分",
            "对话界面。不用出检查点，按题干自动判分"};

    static String kindName(String kind) {
        for (int i = 0; i < KINDS.length; i++) if (KINDS[i].equals(kind)) return KIND_NAMES[i];
        return kind == null ? "" : kind;
    }

    static Tone kindTone(String kind) {
        if ("win".equals(kind)) return Tone.PRIMARY;
        if ("wps".equals(kind)) return Tone.INFO;
        if ("html".equals(kind)) return Tone.WARNING;
        if ("ai".equals(kind)) return Tone.VIOLET;
        return Tone.NEUTRAL;
    }

    /** 检查点分值合计 */
    static int fullScore(JSONObject sim) {
        int n = 0;
        for (JSONObject c : Json.list(Json.arr(sim, "checks"))) n += Math.max(0, c.optInt("score", 0));
        return n;
    }

    /** 电脑网页端出仿真题的地址（题库 → 仿真操作题） */
    static String webSimsUrl() {
        return Session.get().server() + "/js/bank?panel=sims";
    }

    // ---------- 看大图 ----------

    static void showImage(Context c, String url) {
        Sheet s = new Sheet(c, "题目配图");
        ImageView iv = new ImageView(c);
        iv.setAdjustViewBounds(true);
        iv.setScaleType(ImageView.ScaleType.FIT_CENTER);
        iv.setBackground(V.round(c, Palette.of(c).surfaceAlt, 12));
        s.content(iv);
        Images.load(iv, url, c.getResources().getDisplayMetrics().widthPixels);
        s.buttons(null, null, "关闭", s::dismiss);
        s.show();
    }

    // ---------- 删除权限 ----------

    /** 普通教师默认删不了公共题库（后端 require_delete_permission），先在本地挡一下说清楚 */
    static boolean canDelete(Context c) {
        Session s = Session.get();
        if (s.isAdmin() || Json.bool(s.user(), "can_delete")) return true;
        Dialogs.alert(c, "没有删除权限",
                "题库是全校共用的，误删一条所有人都受影响，所以普通教师默认删不了。\n"
                        + "需要请管理员在「账号」页面给你开通「删除权」后再操作。增、改、查不受影响。");
        return false;
    }
}
