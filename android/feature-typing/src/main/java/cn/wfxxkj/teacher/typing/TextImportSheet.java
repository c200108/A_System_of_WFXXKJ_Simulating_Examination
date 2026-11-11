package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 上传 txt 批量导入：选导入到哪个语言 / 难度、怎么分段，再从手机里挑一个 .txt 文件。
 * 网页是拖文件进框，APP 里换成系统的文件选择器。
 */
final class TextImportSheet {
    private TextImportSheet() {}

    static void show(final Screen s, String mode, String difficulty, String[] difficulties,
                     java.util.List<JSONObject> themes, Integer defaultTheme, final Runnable onDone) {
        Context c = s.ctx();
        Sheet sh = new Sheet(c, "上传 txt 批量导入");
        Form f = new Form(c);
        final Form.Choice lang = f.choice("导入到", TextListScreen.MODES, mode);
        final Form.Choice diff = f.choice("难度", Option.of(difficulties),
                difficulty.isEmpty() ? difficulties[0] : difficulty);
        f.row(lang, diff);
        final Form.Choice theme = themes.isEmpty() ? null
                : f.choice("归到主题", TextEditSheet.themeOptions(themes), defaultTheme);
        final Form.Choice split = f.choice("分段方式", Option.pairs("line", "一行一段", "blank", "空行分段"), "line");
        LinearLayout tips = V.vbox(c);
        TextView t1 = V.notice(c, "一行一段：文件里每行就是一段练习文本，空行自动忽略。多数情况用这个。\n"
                + "空行分段：用空行隔开的整块算一段，段内换行会折成空格。贴整篇文章时用。", Tone.INFO);
        tips.addView(t1);
        f.custom(tips);
        f.note("支持 UTF-8 和 GBK 编码，单个文件不超过 2 MB；重复内容自动跳过。");
        sh.content(f.view());
        sh.buttons("取消", null, "选择 .txt 文件", () -> s.pickFile(new String[]{"text/plain", "application/octet-stream"}, uri -> {
            final String m = lang.string(), d = diff.string(), sp = split.string();
            final Integer th = theme == null || theme.value() == null ? null : ((Number) theme.value()).intValue();
            s.runBusy("正在导入…", () -> TypingApi.importTxt(m, d, sp, th, uri), r -> {
                sh.dismiss();
                onDone.run();
                showResult(c, r);
            });
        }));
        // 主按钮带个图标，一眼看出是选文件
        LinearLayout footer = sh.footer();
        if (footer.getChildCount() > 0) {
            TextView primary = (TextView) footer.getChildAt(footer.getChildCount() - 1);
            android.graphics.drawable.Drawable d = c.getDrawable(R.drawable.ic_upload_file);
            if (d != null) {
                d = d.mutate();
                int px = cn.wfxxkj.teacher.core.ui.Ui.dp(c, 18);
                d.setBounds(0, 0, px, px);
                d.setTint(primary.getCurrentTextColor());
                primary.setCompoundDrawablesRelative(d, null, null, null);
                primary.setCompoundDrawablePadding(cn.wfxxkj.teacher.core.ui.Ui.dp(c, 6));
            }
        }
        sh.show();
    }

    private static void showResult(Context c, JSONObject r) {
        Dialogs.alert(c, "导入完成", "扫描 " + Json.num(r, "total") + " 段：成功导入 " + Json.num(r, "added")
                + " 段，重复跳过 " + Json.num(r, "skipped") + " 段，太短忽略 " + Json.num(r, "too_short") + " 段。");
    }
}
