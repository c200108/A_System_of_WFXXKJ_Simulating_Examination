package cn.wfxxkj.teacher.me;

import android.content.Context;
import android.graphics.Typeface;
import android.net.Uri;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;

import cn.wfxxkj.teacher.core.R;
import cn.wfxxkj.teacher.core.io.Files;
import cn.wfxxkj.teacher.core.nav.Action;
import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.ApiException;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Dialogs;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Tone;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 数据备份与系统更新（网页端「我的账号」里系统管理员才有的那一块，服务端 2.18.0 起，只有在线版有）。
 *
 * <ul>
 *   <li>导出数据：服务器打一个 exam-data 压缩包，存到手机「下载/教学平台」</li>
 *   <li>导入数据：选 exam-data 压缩包上传，体检通过后服务器上的主机助手覆盖数据并重建容器</li>
 *   <li>一键更新：服务器从 GitHub 下载 main 压缩包升级，或者上传一个 main 压缩包</li>
 * </ul>
 * 导入、更新都要再输一次登录密码；执行过程和日志在下面实时显示（升级时后端重启，问不通是正常的，接着问）。
 */
final class SystemScreen extends Screen {
    private LinearLayout content;
    private TextView agentText, jobTitle, jobLog;
    private JSONObject status;
    private JSONObject job;
    private int offline;
    private boolean polling;

    @Override
    public String title() {
        return "数据备份与系统更新";
    }

    @Override
    protected View onCreateView(Context c) {
        content = V.page(c);
        agentText = V.notice(c, "正在查服务器状态…", Tone.INFO);
        content.addView(agentText, V.matchWrap());

        LinearLayout backup = V.card(c);
        backup.addView(V.text(c, "数据备份", V.H3));
        V.addTop(backup, V.text(c, "导出：全部数据表 + 题目配图 + 平台配置，打成一个 exam-data 压缩包存到手机（不含任何口令）。", V.BODY2), 6);
        V.addTop(backup, V.button(c, R.drawable.ic_download, "导出数据", V.BTN_PRIMARY, v -> doExport()), 10);
        V.addTop(backup, V.text(c, "导入：选导出得到的 exam-data 压缩包，先体检试算，通过后覆盖本机数据并重建容器，"
                + "期间网站会有一段时间打不开，请避开考试时段。导入前服务器会自动存一份回滚点。", V.BODY2), 14);
        V.addTop(backup, V.button(c, R.drawable.ic_upload_file, "选压缩包导入…", V.BTN_DANGER_TONAL, v -> doImport()), 10);
        V.addTop(content, backup, 12);

        LinearLayout update = V.card(c);
        update.addView(V.text(c, "教师端一键更新", V.H3));
        V.addTop(update, V.text(c, "服务器从 GitHub 下载项目最新的 main 压缩包，运行里面的升级脚本：先备份、再构建（期间网站照常能用）、"
                + "最后切换，切换时网页会有十几秒打不开。题库、成绩、账号、上传文件、.env、config.yaml 都原样保留。", V.BODY2), 6);
        V.addTop(update, V.button(c, R.drawable.ic_refresh, "从 GitHub 更新", V.BTN_PRIMARY, v -> doGithub()), 10);
        V.addTop(update, V.text(c, "服务器连不上 GitHub 时：在 GitHub 仓库页 Code → Download ZIP 下载 main 压缩包（不用解压），在这里上传。", V.BODY2), 14);
        V.addTop(update, V.button(c, R.drawable.ic_upload_file, "上传 main 压缩包更新…", V.BTN_TONAL, v -> doZip()), 10);
        V.addTop(content, update, 12);

        LinearLayout jobCard = V.card(c);
        jobTitle = V.text(c, "还没有执行记录", V.H3);
        jobCard.addView(jobTitle);
        jobLog = V.text(c, "", V.CAPTION);
        jobLog.setTypeface(Typeface.MONOSPACE);
        jobLog.setTextIsSelectable(true);
        V.addTop(jobCard, jobLog, 8);
        V.addTop(content, jobCard, 12);
        return V.scroll(c, content);
    }

    @Override
    protected void onFirstShow() {
        refresh();
    }

    @Override
    protected void onDestroy() {
        polling = false;
    }

    @Override
    public List<Action> actions() {
        return Collections.singletonList(Action.icon(R.drawable.ic_refresh, "刷新", this::refresh));
    }

    private void refresh() {
        run(MeApi::systemStatus, s -> {
            status = s;
            boolean ok = Json.bool(Json.obj(s, "agent"), "installed");
            agentText.setText(ok ? "✓ 服务器主机助手已就绪，导入数据、一键更新都能用"
                    : "服务器上还没装「主机助手」，导入数据和一键更新暂时用不了（导出数据不受影响）。"
                    + "在服务器项目目录里运行一次：sudo bash scripts/host-agent-install.sh");
            JSONObject busy = s.optJSONObject("busy");
            List<JSONObject> recent = Json.list(Json.arr(s, "recent"));
            if (busy != null) watch(busy);
            else if (job == null && !recent.isEmpty()) {
                job = recent.get(0);
                pollOnce();
            }
            renderJob();
        }, e -> {
            if (e instanceof ApiException && ((ApiException) e).code == 404) {
                agentText.setText("这台服务器没有「数据备份与系统更新」（机房局域网版没有这一块，或服务端版本低于 2.18.0）。");
                return true;
            }
            agentText.setText("查不到服务器状态：" + e.getMessage());
            return true;
        });
    }

    private boolean agentOk() {
        return status != null && Json.bool(Json.obj(status, "agent"), "installed");
    }

    private boolean busy() {
        if (job == null) return false;
        String st = Json.str(job, "status");
        return "queued".equals(st) || "running".equals(st);
    }

    // ---------- 导出 ----------

    private void doExport() {
        String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT).format(new Date());
        Files.export(this, "服务器正在打包数据…（数据多时要等一会儿）", MeApi::exportBackup, "exam-data-" + stamp + ".zip");
    }

    // ---------- 导入 / 更新 ----------

    private interface WithPassword {
        void go(String password);
    }

    /** 弹一个确认框，要求再输一次登录密码 */
    private void askPassword(String title, String warn, WithPassword then) {
        Context c = ctx();
        Sheet s = new Sheet(c, title);
        Form f = new Form(c);
        f.note(warn);
        final Form.Text pw = f.password("登录密码", "输入你的登录密码确认").required();
        s.content(f.view());
        s.buttons("取消", null, "确认执行", () -> {
            if (!f.validate()) return;
            s.dismiss();
            then.go(pw.raw());
        }, true);
        s.show();
    }

    private boolean ready() {
        if (!agentOk()) {
            Dialogs.alert(ctx(), "主机助手还没装", "在服务器项目目录里运行一次：\nsudo bash scripts/host-agent-install.sh\n装好后再回来。");
            return false;
        }
        if (busy()) {
            toast("还有一个任务在执行，等它做完");
            return false;
        }
        return true;
    }

    private void doImport() {
        if (!ready()) return;
        pickFile(new String[]{"application/zip", "application/x-zip-compressed", "application/octet-stream"}, uri -> {
            String name = Files.displayName(ctx(), uri, "压缩包");
            askPassword("导入数据并重建容器", "用「" + name + "」里的数据覆盖本机数据库。导入前会自动存一份回滚点；"
                    + ".env、口令、表结构都不动。导完会重建容器，期间网站会有一段时间打不开。", pw ->
                    runBusy("正在上传并体检…", () -> MeApi.importBackup(uri, pw), got -> {
                        String dry = Json.str(got, "dry_run");
                        toast("体检通过，已交给服务器执行");
                        if (!dry.isEmpty()) Dialogs.alert(ctx(), "体检结果", dry);
                        watch(got);
                    }));
        });
    }

    private void doGithub() {
        if (!ready()) return;
        askPassword("一键更新（从 GitHub 下载）", "服务器会从 GitHub 下载项目最新的 main 压缩包并运行升级脚本："
                + "先备份，再构建新版本，最后切换 —— 切换时网页会有十几秒打不开。数据原样保留。", pw ->
                runBusy("正在提交…", () -> MeApi.updateFromGithub(pw), this::watch));
    }

    private void doZip() {
        if (!ready()) return;
        pickFile(new String[]{"application/zip", "application/x-zip-compressed", "application/octet-stream"}, (Uri uri) -> {
            String name = Files.displayName(ctx(), uri, "压缩包");
            askPassword("上传压缩包更新", "用「" + name + "」升级（GitHub 仓库页 Code → Download ZIP 下的那个，不用解压）。"
                    + "先备份、再构建、最后切换 —— 切换时网页会有十几秒打不开。数据原样保留。", pw ->
                    runBusy("正在上传…", () -> MeApi.updateFromZip(uri, pw), this::watch));
        });
    }

    // ---------- 进度 ----------

    private void watch(JSONObject j) {
        job = j;
        offline = 0;
        renderJob();
        if (!polling) {
            polling = true;
            pollLoop();
        }
    }

    private void pollLoop() {
        if (!polling || isDestroyed() || job == null) {
            polling = false;
            return;
        }
        final String id = Json.str(job, "id");
        final String was = Json.str(job, "status");
        run(() -> MeApi.systemJob(id), got -> {
            job = got;
            offline = 0;
            renderJob();
            String st = Json.str(got, "status");
            if ("ok".equals(st) || "failed".equals(st) || "lost".equals(st)) {
                polling = false;
                if ("queued".equals(was) || "running".equals(was)) finished(got);
                return;
            }
            post(this::pollLoop, 3000);
        }, e -> {
            // 升级、重建容器时后端在重启：问不通是正常的，接着问
            offline++;
            renderJob();
            post(this::pollLoop, 3000);
            return true;
        });
    }

    private void pollOnce() {
        if (job == null) return;
        final String id = Json.str(job, "id");
        run(() -> MeApi.systemJob(id), got -> {
            job = got;
            renderJob();
        }, e -> true);
    }

    private void finished(JSONObject j) {
        if ("ok".equals(Json.str(j, "status"))) {
            Dialogs.alert(ctx(), "import".equals(Json.str(j, "action")) ? "导入完成" : "更新完成",
                    "import".equals(Json.str(j, "action")) ? "数据已导入，容器已重建。核对一下题目数、学生数。"
                            : "已经升级到最新版本，数据库和上传文件原样保留。");
        } else {
            toast(Json.str(j, "label") + "没做成，看下面日志最后几行");
        }
    }

    private void renderJob() {
        if (job == null) return;
        String st = Json.str(job, "status");
        String label;
        switch (st) {
            case "queued":
                label = "等待服务器接单";
                break;
            case "running":
                label = "正在执行";
                break;
            case "ok":
                label = "完成";
                break;
            case "failed":
                label = "没做成";
                break;
            default:
                label = "已结束（没有结果）";
                break;
        }
        jobTitle.setText(Json.str(job, "label") + " · " + label + (offline > 0 ? "（服务重启中，第 " + offline + " 次重试…）" : ""));
        String msg = Json.str(job, "message");
        String log = Json.str(job, "log");
        jobLog.setText((msg.isEmpty() ? "" : msg + "\n\n") + (log.isEmpty() ? "" : tail(log, 6000)));
        View root = view();
        if (root instanceof ScrollView && busy()) ((ScrollView) root).post(() -> ((ScrollView) root).fullScroll(View.FOCUS_DOWN));
    }

    private static String tail(String s, int n) {
        return s.length() <= n ? s : "…" + s.substring(s.length() - n);
    }
}
