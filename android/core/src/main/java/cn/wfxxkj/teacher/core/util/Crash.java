package cn.wfxxkj.teacher.core.util;

import android.content.Context;
import android.os.Build;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

import cn.wfxxkj.teacher.core.io.Sys;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 出错时把「哪儿错了」说出来，而不是让 APP 一声不吭地退回桌面。
 *
 * <p>老师报上来的「点开就回到桌面」，在电脑上的模拟环境里怎么也复现不出来 —— 和手机型号、系统版本、
 * 真实数据有关。没有错误信息只能靠猜。所以：
 * <ul>
 *   <li>页面打开、数据回来画页面时出的错，由主界面接住，当场弹出错误详情（能一键复制），页面退回上一层，APP 不退；</li>
 *   <li>别处漏网的错误让 APP 退出前先记到本机文件里，下次打开 APP 时弹出来。</li>
 * </ul>
 * 老师把这段文字发给维护者，一看就知道是哪一行。
 */
public final class Crash {

    private static final String FILE = "last_crash.txt";

    private Crash() {}

    /** 错误详情：机型、系统、时间、错误类型和消息，以及调用栈（本 APP 的那几行排前面）。 */
    public static String describe(Throwable t, String where) {
        StringBuilder sb = new StringBuilder();
        sb.append("时间：").append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(new Date()))
                .append('\n');
        sb.append("机型：").append(Build.MANUFACTURER).append(' ').append(Build.MODEL)
                .append("　安卓 ").append(Build.VERSION.RELEASE).append("（API ").append(Build.VERSION.SDK_INT)
                .append("）\n");
        if (where != null) sb.append("位置：").append(where).append('\n');
        Throwable cur = t;
        int depth = 0;
        while (cur != null && depth < 4) {
            sb.append(depth == 0 ? "错误：" : "原因：").append(cur.getClass().getName());
            if (cur.getMessage() != null) sb.append(": ").append(cur.getMessage());
            sb.append('\n');
            int shown = 0;
            for (StackTraceElement e : cur.getStackTrace()) {
                boolean ours = e.getClassName().startsWith("cn.wfxxkj");
                if (shown < 6 || ours && shown < 25) {
                    sb.append("  at ").append(e).append('\n');
                    shown++;
                }
            }
            cur = cur.getCause() == cur ? null : cur.getCause();
            depth++;
        }
        return sb.toString();
    }

    /** APP 要退出前记一笔，下次打开时 {@link #takeSaved} 取出来给老师看。 */
    public static void save(Context c, Throwable t) {
        try (FileOutputStream out = new FileOutputStream(new File(c.getFilesDir(), FILE))) {
            out.write(describe(t, "APP 异常退出").getBytes(StandardCharsets.UTF_8));
        } catch (Throwable ignored) {
            // 记不下来也不能再抛：这里本来就在处理崩溃
        }
    }

    /** 上次异常退出留下的记录；取过就删，只提醒一次。没有返回 null。 */
    public static String takeSaved(Context c) {
        File f = new File(c.getFilesDir(), FILE);
        if (!f.isFile()) return null;
        try (FileInputStream in = new FileInputStream(f)) {
            byte[] buf = new byte[(int) Math.min(f.length(), 64 * 1024)];
            int n = in.read(buf);
            return n > 0 ? new String(buf, 0, n, StandardCharsets.UTF_8) : null;
        } catch (Throwable e) {
            return null;
        } finally {
            //noinspection ResultOfMethodCallIgnored
            f.delete();
        }
    }

    /** 弹出错误详情，能复制。 */
    public static void show(Context c, String title, String detail) {
        Sheet s = new Sheet(c, title);
        s.content(V.text(c, "请点「复制错误信息」，发给管理员或维护者，方便尽快修好。", V.BODY2));
        android.widget.TextView t = V.text(c, detail, V.CAPTION);
        t.setTextIsSelectable(true);
        V.addTop(s.body(), t, 8);
        s.buttons("关闭", s::dismiss, "复制错误信息", () -> {
            Sys.copy(c, "错误信息", detail);
            s.dismiss();
        });
        s.show();
    }
}
