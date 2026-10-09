package cn.wfxxkj.teacher.paper;

import android.app.Activity;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.util.List;

import cn.wfxxkj.teacher.core.net.Http;
import cn.wfxxkj.teacher.core.net.Json;

/**
 * 打印 / 存 PDF。把卷面排成 A4 的打印稿交给系统打印服务（选「另存为 PDF」就是 PDF 文件）。
 *
 * <p>为什么不用 core 的 Printer：它把整块界面画成一张长位图再切页，一份 50 多道题的卷子位图
 * 会很大，而且切页会把一行字从中间切断。这里用系统 WebView 只做排版引擎（不显示、不联网取页面），
 * 文字按行分页，和网页版「打印」出来的卷面一样。
 */
final class PrintDoc {
    private PrintDoc() {}

    /** 打印期间要攥着 WebView，否则被回收打印就断了 */
    private static WebView holder;

    static void print(final Activity a, final JSONObject paper, final boolean answerKey, List<String> numerals) {
        final String job = Json.str(paper, "title") + (answerKey ? "_答案卷" : "");
        WebView wv = new WebView(a);
        holder = wv;
        wv.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                PrintManager pm = a.getSystemService(PrintManager.class);
                if (pm != null) {
                    pm.print(job, view.createPrintDocumentAdapter(job),
                            new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());
                }
            }
        });
        String html = answerKey ? keyHtml(paper, numerals) : paperHtml(paper, numerals);
        wv.loadDataWithBaseURL(Http.absolute("/"), html, "text/html", "utf-8", null);
    }

    private static String esc(String s) {
        return s == null ? "" : s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\n", "<br>");
    }

    private static String num(List<String> n, int i) {
        return i < n.size() ? n.get(i) : String.valueOf(i + 1);
    }

    private static final String CSS = "<style>"
            + "body{font-family:'Noto Serif CJK SC','Source Han Serif SC',serif;font-size:14px;line-height:1.85;color:#000;margin:0}"
            + "h1{text-align:center;font-size:21px;margin:0 0 4px;font-family:sans-serif}"
            + ".meta{text-align:center;color:#444;font-size:12.5px}"
            + ".fill{display:flex;justify-content:center;gap:28px;border-top:1px dashed #999;border-bottom:1px dashed #999;"
            + "padding:6px 0;margin:10px 0 14px;font-size:13px}.fill u{display:inline-block;width:70px}"
            + "h2{font-size:15.5px;margin:18px 0 2px;font-family:sans-serif}.sd{color:#555;font-size:12.5px;margin-bottom:6px}"
            + ".q{margin:0 0 10px;page-break-inside:avoid}.no{font-weight:bold;margin-right:4px}.pt{color:#555;font-size:12.5px}"
            + ".opts{margin:2px 0 0 20px;display:flex;flex-wrap:wrap;gap:2px 24px}.opts span{min-width:42%}"
            + "img{max-width:340px;display:block;margin:6px 0 4px 20px}"
            + ".akey{display:flex;flex-wrap:wrap;gap:6px}.akey div{border:1px solid #bbb;border-radius:4px;padding:1px 8px;min-width:54px;text-align:center}"
            + ".ai{border-left:3px solid #888;padding:2px 0 2px 8px;margin-bottom:8px}.na{color:#a60}"
            + "</style>";

    private static String head(JSONObject paper) {
        StringBuilder sb = new StringBuilder("<h1>").append(esc(Json.str(paper, "title"))).append("</h1><div class=meta>");
        if (!Json.str(paper, "school").isEmpty()) sb.append(esc(Json.str(paper, "school"))).append("　·　");
        if (!Json.str(paper, "duration").isEmpty()) sb.append("考试时长 ").append(esc(Json.str(paper, "duration"))).append(" 分钟　·　");
        if (Json.num(paper, "full_score") > 0) sb.append("满分 ").append(Json.num(paper, "full_score")).append(" 分　·　");
        sb.append(esc(Json.str(paper, "code"))).append("</div>");
        return sb.toString();
    }

    static String paperHtml(JSONObject paper, List<String> numerals) {
        StringBuilder sb = new StringBuilder("<!doctype html><html><head><meta charset=utf-8>").append(CSS).append("</head><body>");
        sb.append(head(paper));
        sb.append("<div class=fill><span>班级：<u></u></span><span>姓名：<u></u></span><span>学号：<u></u></span><span>得分：<u></u></span></div>");
        int n = 0, gi = 0;
        for (JSONObject g : Json.list(Json.arr(paper, "groups"))) {
            List<JSONObject> items = Json.list(Json.arr(g, "items"));
            String name = Json.str(g, "name").isEmpty() ? Json.str(g, "type") : Json.str(g, "name");
            sb.append("<h2>").append(num(numerals, gi++)).append("、").append(esc(name)).append("（共 ").append(items.size()).append(" 题");
            if (Json.num(g, "score") > 0) sb.append("，共 ").append(Json.num(g, "score")).append(" 分");
            sb.append("）</h2><div class=sd>").append(PaperScreen.sectionHint(items, false)).append("</div>");
            for (JSONObject q : items) {
                sb.append("<div class=q><span class=no>").append(++n).append(".</span>").append(esc(Json.str(q, "stem")));
                if (Json.num(q, "score") > 0) sb.append(" <span class=pt>（").append(Json.num(q, "score")).append(" 分）</span>");
                if (!Json.str(q, "image_url").isEmpty()) sb.append("<img src=\"").append(esc(Http.absolute(Json.str(q, "image_url")))).append("\">");
                List<JSONObject> opts = Json.list(Json.arr(q, "options"));
                if (!opts.isEmpty()) {
                    sb.append("<div class=opts>");
                    for (JSONObject o : opts) {
                        sb.append("<span><b>").append(esc(Json.str(o, "label"))).append("</b>　").append(esc(Json.str(o, "content"))).append("</span>");
                    }
                    sb.append("</div>");
                }
                sb.append("</div>");
            }
        }
        return sb.append("</body></html>").toString();
    }

    static String keyHtml(JSONObject paper, List<String> numerals) {
        StringBuilder sb = new StringBuilder("<!doctype html><html><head><meta charset=utf-8>").append(CSS).append("</head><body>");
        sb.append(head(paper)).append("<h2 style='text-align:center'>参考答案</h2>");
        int n = 0, gi = 0;
        for (JSONObject g : Json.list(Json.arr(paper, "groups"))) {
            List<JSONObject> items = Json.list(Json.arr(g, "items"));
            String name = Json.str(g, "name").isEmpty() ? Json.str(g, "type") : Json.str(g, "name");
            sb.append("<h2>").append(num(numerals, gi++)).append("、").append(esc(name)).append("</h2>");
            boolean allOp = true;
            for (JSONObject q : items) if (!Quiz.OP.equals(Json.str(q, "type"))) allOp = false;
            if (allOp) {
                for (JSONObject q : items) {
                    String a = Json.str(q, "answer");
                    sb.append("<div class=ai><b>第 ").append(++n).append(" 题</b>　").append(esc(Json.str(q, "scope"))).append("<br>")
                            .append(a.isEmpty() ? "<span class=na>原卷未给答案</span>" : esc(a)).append("</div>");
                }
            } else {
                sb.append("<div class=akey>");
                for (JSONObject q : items) {
                    String a = Json.str(q, "answer");
                    sb.append("<div>").append(++n).append("　<b>");
                    if (Quiz.OP.equals(Json.str(q, "type"))) sb.append("<span class=na>人工阅</span>");
                    else sb.append(a.isEmpty() ? "—" : esc(a));
                    sb.append("</b></div>");
                }
                sb.append("</div>");
            }
        }
        return sb.append("</body></html>").toString();
    }
}
