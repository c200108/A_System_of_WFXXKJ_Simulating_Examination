package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.graphics.Typeface;
import android.text.TextUtils;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 只读展示一个仿真任务的初始环境（手机上没有模拟器，用文字把环境摆出来给老师核对）：
 * <ul>
 * <li>Windows：文件树（文件夹 / 文件，缩进表示层级）和回收站；</li>
 * <li>WPS：文档名、页面设置、每段文字和格式；</li>
 * <li>网页编程：每个文件的代码；</li>
 * <li>AI 工具：工具名称和开场白。</li>
 * </ul>
 */
final class SimEnvView {
    private SimEnvView() {}

    static LinearLayout build(Context c, String kind, JSONObject env) {
        LinearLayout box = V.vbox(c);
        if ("win".equals(kind)) win(c, box, env);
        else if ("wps".equals(kind)) wps(c, box, env);
        else if ("html".equals(kind)) html(c, box, env);
        else if ("ai".equals(kind)) {
            box.addView(V.kv(c, "工具名称", Json.str(env, "tool")));
            box.addView(V.kv(c, "开场白", Json.str(env, "greeting")));
        } else {
            box.addView(code(c, env.toString()));
        }
        return box;
    }

    // ---------- Windows ----------

    private static void win(Context c, LinearLayout box, JSONObject env) {
        JSONObject fs = Json.obj(env, "fs");
        List<String> paths = new ArrayList<>();
        Iterator<String> it = fs.keys();
        while (it.hasNext()) paths.add(it.next());
        Collections.sort(paths, String.CASE_INSENSITIVE_ORDER);
        Palette p = Palette.of(c);
        if (paths.isEmpty()) box.addView(V.text(c, "（空）", V.BODY2));
        for (String path : paths) {
            JSONObject node = Json.obj(fs, path);
            boolean dir = "dir".equals(Json.str(node, "type"));
            int depth = 0;
            for (char ch : path.toCharArray()) if (ch == '/') depth++;
            String name = path.substring(path.lastIndexOf('/') + 1);
            if (name.isEmpty()) name = path;
            LinearLayout row = V.hbox(c);
            V.pad(row, Math.max(0, depth - 1) * 18, 4, 0, 4);
            row.addView(V.icon(c, dir ? R.drawable.ic_inbox : R.drawable.ic_description,
                    dir ? p.warning : p.text3, 18));
            TextView t = V.text(c, depth <= 1 ? path : name, V.BODY);
            LinearLayout.LayoutParams lp = V.fill();
            lp.setMarginStart(Ui.dp(c, 8));
            row.addView(t, lp);
            List<String> attrs = new ArrayList<>();
            if (Json.bool(node, "hidden")) attrs.add("隐藏");
            if (Json.bool(node, "readonly")) attrs.add("只读");
            String content = Json.str(node, "content");
            if (!content.isEmpty()) attrs.add(content.length() + " 字");
            if (!attrs.isEmpty()) row.addView(V.text(c, TextUtils.join(" · ", attrs), V.CAPTION));
            box.addView(row);
        }
        int recycle = Json.obj(env, "recycle").length();
        if (recycle > 0) V.addTop(box, V.text(c, "回收站里有 " + recycle + " 项", V.CAPTION), 6);
    }

    // ---------- WPS ----------

    private static void wps(Context c, LinearLayout box, JSONObject env) {
        box.addView(V.kv(c, "文档", Json.str(env, "name")));
        JSONObject page = Json.obj(env, "page");
        if (page.length() > 0) {
            box.addView(V.kv(c, "页面", ("landscape".equals(Json.str(page, "orient")) ? "横向" : "纵向")
                    + " · 页边距 上" + Json.str(page, "top") + " 下" + Json.str(page, "bottom")
                    + " 左" + Json.str(page, "left") + " 右" + Json.str(page, "right") + " 厘米"));
        }
        if (!Json.str(env, "header").isEmpty()) box.addView(V.kv(c, "页眉", Json.str(env, "header")));
        if (!Json.str(env, "footer").isEmpty()) box.addView(V.kv(c, "页脚", Json.str(env, "footer")));
        if (env.optInt("columns", 1) > 1) box.addView(V.kv(c, "分栏", env.optInt("columns") + " 栏"));
        List<JSONObject> paras = Json.list(Json.arr(env, "paras"));
        V.addTop(box, V.text(c, "正文（" + paras.size() + " 段）", V.LABEL), 8);
        Palette p = Palette.of(c);
        for (int i = 0; i < paras.size(); i++) {
            JSONObject para = paras.get(i);
            LinearLayout pb = V.vbox(c);
            pb.setBackground(V.round(c, p.surfaceAlt, 10));
            V.pad(pb, 12, 8, 12, 8);
            TextView t = V.text(c, Json.str(para, "text"), V.BODY);
            int style = (Json.bool(para, "bold") ? Typeface.BOLD : 0) | (Json.bool(para, "italic") ? Typeface.ITALIC : 0);
            t.setTypeface(Typeface.DEFAULT, style);
            String align = Json.str(para, "align");
            if ("center".equals(align)) t.setGravity(Gravity.CENTER_HORIZONTAL);
            else if ("right".equals(align)) t.setGravity(Gravity.END);
            pb.addView(t);
            List<String> fmt = new ArrayList<>();
            fmt.add("第 " + (i + 1) + " 段");
            if (!Json.str(para, "font").isEmpty()) fmt.add(Json.str(para, "font"));
            if (!Json.str(para, "size").isEmpty()) fmt.add(Json.str(para, "size"));
            if (Json.bool(para, "bold")) fmt.add("加粗");
            if (Json.bool(para, "italic")) fmt.add("倾斜");
            if (Json.bool(para, "underline")) fmt.add("下划线");
            if (!Json.str(para, "color").isEmpty()) fmt.add("颜色 " + Json.str(para, "color"));
            if ("center".equals(align)) fmt.add("居中");
            else if ("right".equals(align)) fmt.add("右对齐");
            else if ("justify".equals(align)) fmt.add("两端对齐");
            if (para.optDouble("indent", 0) > 0) fmt.add("首行缩进 " + Json.str(para, "indent"));
            V.addTop(pb, V.text(c, TextUtils.join(" · ", fmt), V.CAPTION), 4);
            V.addTop(box, pb, 6);
        }
    }

    // ---------- 网页编程 ----------

    private static void html(Context c, LinearLayout box, JSONObject env) {
        JSONObject files = Json.obj(env, "files");
        Iterator<String> it = files.keys();
        boolean first = true;
        while (it.hasNext()) {
            String name = it.next();
            TextView n = V.text(c, name, V.LABEL);
            if (first) box.addView(n);
            else V.addTop(box, n, 10);
            first = false;
            V.addTop(box, code(c, Json.str(files, name)), 4);
        }
        if (first) box.addView(V.text(c, "（没有文件）", V.BODY2));
    }

    /** 等宽小字代码块 */
    static TextView code(Context c, String text) {
        TextView t = V.text(c, text, V.CAPTION);
        t.setTypeface(Typeface.MONOSPACE);
        t.setTextColor(Palette.of(c).text2);
        t.setBackground(V.round(c, Palette.of(c).surfaceAlt, 10));
        t.setTextIsSelectable(true);
        V.pad(t, 10, 8, 10, 8);
        return t;
    }
}
