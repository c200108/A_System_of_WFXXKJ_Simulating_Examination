package cn.wfxxkj.teacher.bank;

import android.content.Context;
import android.widget.LinearLayout;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 新建仿真任务。
 *
 * <p>网页上出题分两步，都是在桌面模拟器里点出来的：① 布置环境 ② 做一遍标准答案、自动生成检查点。
 * 手机上：
 * <ul>
 * <li>AI 工具题：不用环境和检查点，填名称、工具名、开场白就能建好；</li>
 * <li>网页编程题：环境就是几份 HTML/CSS 文本，手机上直接改代码，标准答案也是改代码，照样能生成检查点；</li>
 * <li>Windows 操作 / WPS 文字：要在模拟的 XP 桌面里拖拽、右键、用 WPS 工具栏排版，手机屏幕做不了，
 *     提示到电脑网页端录制；也可以先起个名字存成草稿，回头在电脑上补。</li>
 * </ul>
 */
final class SimCreate {
    interface Created {
        void created(long id);
    }

    private SimCreate() {}

    static void start(Screen s, Created done) {
        Context c = s.ctx();
        List<Option> opts = new ArrayList<>();
        for (int i = 0; i < Bank.KINDS.length; i++) {
            String sub = Bank.KIND_DESC[i];
            if (needsDesktop(Bank.KINDS[i])) sub += "（需在电脑上录制）";
            opts.add(new Option(Bank.KINDS[i], Bank.KIND_NAMES[i], sub));
        }
        Dialogs.choose(c, "新建哪种仿真题", opts, null, o -> {
            String kind = String.valueOf(o.value);
            if (needsDesktop(kind)) desktopOnly(s, kind, done);
            else form(s, kind, done);
        });
    }

    /** Windows / WPS 的环境和标准答案只能在桌面模拟器里点出来 */
    static boolean needsDesktop(String kind) {
        return "win".equals(kind) || "wps".equals(kind);
    }

    private static void desktopOnly(Screen s, String kind, Created done) {
        Context c = s.ctx();
        Sheet sh = new Sheet(c, Bank.kindName(kind) + "：请到电脑上出题");
        LinearLayout body = V.vbox(c);
        body.addView(V.text(c, "这类题要在网页里的模拟" + ("win".equals(kind) ? " XP 桌面里新建、拖动、右键改名删除文件"
                : " WPS 里用工具栏设置字体、段落、页面") + "，把初始环境摆好，再从头做一遍标准答案，"
                + "系统才能对比前后差异生成检查点。手机屏幕太小，模拟器在这里用不了。", V.BODY2));
        V.addTop(body, V.notice(c, "在电脑浏览器打开教师端 →「题库」→「仿真操作题」→ 新建。\n地址：" + Bank.webSimsUrl(),
                Tone.INFO), 12);
        V.addTop(body, V.text(c, "也可以先在手机上起个名字存成草稿，回头在电脑上打开它补环境和检查点。"
                + "草稿没有检查点，挂到题目上学生做什么都是 0 分，别急着挂。", V.CAPTION), 12);
        V.addTop(body, V.button(c, R.drawable.ic_content_copy, "复制电脑端地址", V.BTN_TONAL, v -> {
            Sys.copy(c, "教师端地址", Bank.webSimsUrl());
            s.toast("地址已复制，发到电脑上打开");
        }), 14);
        V.addTop(body, V.button(c, R.drawable.ic_share, "发送到电脑（微信、QQ）", V.BTN_OUTLINE,
                v -> Sys.share(c, "仿真操作题出题地址", "在电脑浏览器打开，出" + Bank.kindName(kind) + "仿真题：" + Bank.webSimsUrl())), 8);
        sh.content(body);
        sh.buttons("关闭", null, "先存草稿", () -> {
            sh.dismiss();
            form(s, kind, done);
        });
        sh.show();
    }

    private static void form(Screen s, String kind, Created done) {
        Context c = s.ctx();
        Sheet sh = new Sheet(c, "新建" + Bank.kindName(kind) + "仿真题");
        Form f = new Form(c);
        Form.Text title = f.text("名称", "", "如：新建文件夹并改名（win02）").required();
        title.maxLength(128);
        Form.Text tool = null, greeting = null;
        if ("ai".equals(kind)) {
            tool = f.text("工具名称", "AI 助手", "如：通义千问 / 文心一言 / DeepSeek");
            greeting = f.text("开场白", "你好，把题目要求发给我，我来帮你完成。", "学生打开时 AI 说的第一句话");
            f.note("这类题不用做标准答案，也不用出检查点：学生把题干要求完整地描述给 AI 工具并发送就得分，判分时按题干现算。"
                    + "对话里的回复由本地模板生成，不联网调用真实大模型。");
        } else if ("html".equals(kind)) {
            f.note("建好后在详情页里：① 改 index.html / style.css 布置学生打开时看到的代码；"
                    + "② 按题目要求改一遍代码当标准答案，生成检查点。");
        } else {
            f.note("草稿只有空白环境，没有检查点。到电脑网页端打开它补上环境和标准答案。");
        }
        sh.content(f.view());
        final Form.Text toolF = tool, greetF = greeting;
        sh.buttons("取消", null, "创建", () -> {
            if (!f.validate()) return;
            final String t = title.value();
            sh.dismiss();
            s.runBusy("正在创建…", () -> {
                JSONObject env = BankApi.simBlank(kind);
                if (toolF != null) {
                    Json.put(env, "tool", toolF.value());
                    Json.put(env, "greeting", greetF.value());
                }
                return BankApi.simCreate(kind, t, env, null);
            }, saved -> {
                s.toast("已创建");
                done.created(saved.optLong("id"));
            });
        });
        sh.show();
    }

    /** 顶栏「?」：出仿真题的流程说明 */
    static void explain(Context c) {
        Dialogs.alert(c, "仿真操作题怎么出",
                "一个仿真任务 = 初始环境 + 检查点。\n\n"
                        + "① 布置环境：把学生打开时该看到的文件夹 / 文档 / 代码摆好。\n"
                        + "② 做标准答案：从初始环境开始按题目要求做一遍，系统把前后差异翻译成一条条检查点，改改措辞和分值就行。\n"
                        + "③ 试判：按答案做完应该满分，什么都不做应该 0 分。\n"
                        + "④ 到「题库管理」编辑一道操作题，把它挂上。\n\n"
                        + "手机上能做的：所有种类的查看、改名称、改检查点描述和分值、删检查点、试判、删除；"
                        + "AI 工具题和网页编程题可以从头出完。\n"
                        + "Windows 操作和 WPS 文字的环境布置与标准答案录制要在桌面模拟器里拖拽、右键、点工具栏，"
                        + "请到电脑网页端完成：" + Bank.webSimsUrl());
    }
}
