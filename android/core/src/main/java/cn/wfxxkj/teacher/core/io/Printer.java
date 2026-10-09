package cn.wfxxkj.teacher.core.io;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.pdf.PdfDocument;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.print.PageRange;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintDocumentInfo;
import android.print.PrintManager;
import android.view.View;

import java.io.FileOutputStream;

/**
 * 打印（或另存为 PDF）一块界面：成绩分析、学情报告这类。
 * 把视图按 A4 宽度缩放后切成若干页，交给系统打印服务，选「另存为 PDF」就能存成文件。
 */
public final class Printer {
    private Printer() {}

    public static void print(Activity a, final View content, String jobName) {
        PrintManager pm = a.getSystemService(PrintManager.class);
        if (pm == null) return;
        // 先把整块内容画成一张长图（白底）
        final Bitmap full = Bitmap.createBitmap(Math.max(1, content.getWidth()), Math.max(1, content.getHeight()),
                Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(full);
        c.drawColor(Color.WHITE);
        content.draw(c);

        pm.print(jobName, new PrintDocumentAdapter() {
            private PrintAttributes attrs;

            @Override
            public void onLayout(PrintAttributes old, PrintAttributes attributes, CancellationSignal cancel,
                                 LayoutResultCallback cb, Bundle extras) {
                attrs = attributes;
                cb.onLayoutFinished(new PrintDocumentInfo.Builder(jobName + ".pdf")
                        .setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT).build(), true);
            }

            @Override
            public void onWrite(PageRange[] pages, ParcelFileDescriptor dest, CancellationSignal cancel,
                                WriteResultCallback cb) {
                PrintAttributes.MediaSize ms = attrs != null && attrs.getMediaSize() != null
                        ? attrs.getMediaSize() : PrintAttributes.MediaSize.ISO_A4;
                int pw = (int) (ms.getWidthMils() / 1000f * 72), ph = (int) (ms.getHeightMils() / 1000f * 72);
                int margin = 28;
                float scale = (pw - margin * 2f) / full.getWidth();
                int sliceH = (int) ((ph - margin * 2f) / scale);
                PdfDocument doc = new PdfDocument();
                int pageNo = 0;
                for (int y = 0; y < full.getHeight(); y += sliceH, pageNo++) {
                    PdfDocument.Page page = doc.startPage(new PdfDocument.PageInfo.Builder(pw, ph, pageNo).create());
                    Canvas pc = page.getCanvas();
                    pc.translate(margin, margin);
                    pc.scale(scale, scale);
                    int h = Math.min(sliceH, full.getHeight() - y);
                    pc.drawBitmap(full, new Rect(0, y, full.getWidth(), y + h), new Rect(0, 0, full.getWidth(), h), null);
                    doc.finishPage(page);
                }
                try {
                    FileOutputStream out = new FileOutputStream(dest.getFileDescriptor());
                    doc.writeTo(out);
                    out.close();
                    cb.onWriteFinished(new PageRange[]{PageRange.ALL_PAGES});
                } catch (Exception e) {
                    cb.onWriteFailed(e.getMessage());
                } finally {
                    doc.close();
                }
            }
        }, null);
    }
}
