package cn.wfxxkj.teacher.student;

import android.content.Context;
import android.graphics.Typeface;

import java.util.List;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 批量建号的两条入口：上传 Excel/CSV、粘贴名单。两条路认同样的四列「学号 姓名 班级 性别」
 * （后端共用 services/roster.py），初始密码都是学号。
 */
final class RosterImport {
    private RosterImport() {}

    private static final String[] TYPES = {
            Files.XLSX, Files.XLS, "text/csv", "text/comma-separated-values", "text/plain",
            "application/octet-stream"};

    /** 下载导入模板（第三页列好了所有可用班级） */
    static void template(Screen host) {
        Files.export(host, "正在下载模板…", StudentApi::template, "学生导入模板.xlsx");
    }

    /** 从 Excel / CSV 导入 */
    static void excel(final Screen host, List<JSONObject> classes, Integer preset, final Runnable done) {
        Context c = host.ctx();
        boolean admin = host.session().isAdmin();
        Sheet s = new Sheet(c, "从 Excel / CSV 导入");
        Form f = new Form(c);
        final Form.Select cls = f.select("默认班级", Kit.classOptions(classes, "不指定"), preset == null ? Kit.NONE : preset)
                .help("表里没写班级的行归到这里" + (admin ? "；不指定就是「未分班」" : "；老师不能导未分班的学生，这些行会被跳过"));
        s.content(f.view());
        s.content(V.notice(c, "表格四列：学号、姓名、班级、性别，第一行写表头会自动跳过。\n"
                + "• 工作簿里每一张表都会读，一个年级一张表、按班分表都行，报错会指明是哪张表的第几行。\n"
                + "• 班级要和「班级」页里的名称完全一致（如「七年级1班」），写错的行会被跳过并报出来；模板的「可用班级」页列好了所有班。\n"
                + "• 性别填「男」或「女」，选填。\n"
                + "• 支持 .xlsx 和 .csv（UTF-8 或 GBK），单个文件不超过 5 MB。已存在的学号会跳过，初始密码 123456。",
                Tone.NEUTRAL));
        s.buttons("下载模板", () -> template(host), "选择文件", () -> host.pickFile(TYPES, uri -> {
            s.dismiss();
            final Integer classId = Kit.idOf(cls.value());
            host.runBusy("正在导入，人多时要等一会…", () -> StudentApi.importFile(uri, classId), res -> {
                Kit.touch();
                Dialogs.alert(c, "导入完成", Kit.importReport(res, true));
                done.run();
            });
        }));
        s.show();
    }

    /** 粘贴名单批量建号 */
    static void paste(final Screen host, List<JSONObject> classes, Integer preset, final Runnable done) {
        Context c = host.ctx();
        boolean admin = host.session().isAdmin();
        Sheet s = new Sheet(c, "粘贴名单批量建号");
        Form f = new Form(c);
        final Form.Select cls = f.select("班级", Kit.classOptions(classes, admin ? "不分班" : "不指定"), preset == null ? Kit.NONE : preset)
                .help("名单里没写班级的行归到这个班");
        final Form.Text text = f.area("名单", "", 8);
        text.hint("20260101 张三\n20260102 李四\n20260103 王五");
        text.edit.setTypeface(Typeface.MONOSPACE);
        text.edit.setTextSize(14);
        text.required();
        s.content(f.view());
        s.content(V.notice(c, "一行一个学生，四列：学号、姓名、班级、性别，后两列选填 —— 和「从 Excel 导入」认的是同一套。\n"
                + "• 从 Excel 直接复制粘贴即可，自带制表符分隔；手打的话「学号 姓名」中间用空格隔开。\n"
                + "• 单个空格不当列分隔，姓名里带空格（如「钱 七」）不会被拆散；要粘多列请用逗号隔开。\n"
                + "• 已存在的学号自动跳过，初始密码 123456。", Tone.NEUTRAL));
        s.buttons("取消", null, "开始导入", () -> {
            if (!f.validate()) return;
            final String body = text.raw();
            final Integer classId = Kit.idOf(cls.value());
            host.runBusy("正在导入…", () -> StudentApi.batch(classId, body), res -> {
                s.dismiss();
                Kit.touch();
                Dialogs.alert(c, "导入完成", Kit.importReport(res, false));
                done.run();
            });
        });
        s.show();
    }
}
