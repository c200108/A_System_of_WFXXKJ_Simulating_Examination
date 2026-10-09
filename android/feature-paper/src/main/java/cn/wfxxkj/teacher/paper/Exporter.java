package cn.wfxxkj.teacher.paper;

import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 导出试卷：Excel、学生答题网页。下载后存进「下载/教学平台」，
 * 再弹一个小面板：打开（WPS、浏览器）或直接分享给学生（微信、QQ）。
 *
 * <p>core 的 Files.export 存完只给一个「打开」，这里要多一个「分享文件」，所以自己接了一层。
 */
final class Exporter {
    private Exporter() {}

    static void xlsx(Screen s, JSONObject paper) {
        run(s, "正在导出 Excel…", () -> PaperApi.exportXlsx(paper),
                Files.safeName(Json.str(paper, "title")) + ".xlsx", "试卷 Excel",
                "每道题一行：题型、题干、选项、答案、范围，可以再改再导入。");
    }

    static void studentHtml(Screen s, JSONObject paper) {
        run(s, "正在生成学生答题网页…", () -> PaperApi.exportStudentHtml(paper),
                Files.safeName(Json.str(paper, "title")) + "_学生答题.html", "学生答题网页",
                "单个网页文件，可以直接发给学生或传到网站上，学生用浏览器打开就能作答、自动判分。");
    }

    private static void run(final Screen s, String busy, final Screen.Task<Http.Download> task,
                            final String name, final String what, final String hint) {
        s.runBusy(busy, () -> {
            Http.Download d = task.call();
            Uri uri = Files.save(s.ctx(), d.file, name, d.mime);
            return new Object[]{uri, Files.displayName(s.ctx(), uri, name)};
        }, r -> {
            Uri uri = (Uri) ((Object[]) r)[0];
            String real = (String) ((Object[]) r)[1];
            done(s.ctx(), uri, real, what, hint);
        });
    }

    private static void done(final Context c, final Uri uri, final String name, String what, String hint) {
        final Sheet sh = new Sheet(c, "已导出" + what);
        sh.content(V.text(c, "保存在「下载/教学平台/" + name + "」", V.BODY));
        sh.content(V.space(c, 10));
        sh.content(V.notice(c, hint, Tone.INFO));
        sh.footer().addView(V.button(c, R.drawable.ic_open_in_new, "打开", V.BTN_OUTLINE, v -> {
            sh.dismiss();
            Files.open(c, uri, name);
        }), V.weight(1));
        sh.footer().addView(V.space(c, 12));
        sh.footer().addView(V.button(c, R.drawable.ic_share, "分享文件", V.BTN_PRIMARY, v -> {
            sh.dismiss();
            share(c, uri, name);
        }), V.weight(1));
        sh.show();
    }

    /** 把文件本身发出去（微信、QQ、邮件） */
    static void share(Context c, Uri uri, String name) {
        Intent i = new Intent(Intent.ACTION_SEND);
        i.setType(Files.guessMime(name, null));
        i.putExtra(Intent.EXTRA_STREAM, uri);
        i.putExtra(Intent.EXTRA_SUBJECT, name);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            c.startActivity(Intent.createChooser(i, "分享「" + name + "」").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (ActivityNotFoundException e) {
            android.widget.Toast.makeText(c, "手机上没有能分享文件的应用", android.widget.Toast.LENGTH_LONG).show();
        }
    }
}
