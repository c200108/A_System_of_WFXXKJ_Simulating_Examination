package cn.wfxxkj.teacher.core.ui;

import android.content.Context;

import cn.wfxxkj.teacher.core.R;

/**
 * 当前（深色/浅色）配色。颜色定义在 res/values(-night)/colors.xml，这里只是取出来方便代码用。
 *
 * <pre>Palette p = Palette.of(ctx); text.setTextColor(p.text2);</pre>
 */
public final class Palette {
    public final int primary, primaryPressed, primarySoft, onPrimary;
    public final int page, surface, surfaceAlt, border, divider, ripple, scrim;
    public final int text, text2, text3;
    public final int success, successSoft, warning, warningSoft, danger, dangerSoft;
    public final int info, infoSoft, violet, violetSoft;

    private static Palette cached;
    private static int cachedMode = -1;

    private Palette(Context c) {
        primary = c.getColor(R.color.wf_primary);
        primaryPressed = c.getColor(R.color.wf_primary_pressed);
        primarySoft = c.getColor(R.color.wf_primary_soft);
        onPrimary = c.getColor(R.color.wf_on_primary);
        page = c.getColor(R.color.wf_page);
        surface = c.getColor(R.color.wf_surface);
        surfaceAlt = c.getColor(R.color.wf_surface_alt);
        border = c.getColor(R.color.wf_border);
        divider = c.getColor(R.color.wf_divider);
        ripple = c.getColor(R.color.wf_ripple);
        scrim = c.getColor(R.color.wf_scrim);
        text = c.getColor(R.color.wf_text);
        text2 = c.getColor(R.color.wf_text2);
        text3 = c.getColor(R.color.wf_text3);
        success = c.getColor(R.color.wf_success);
        successSoft = c.getColor(R.color.wf_success_soft);
        warning = c.getColor(R.color.wf_warning);
        warningSoft = c.getColor(R.color.wf_warning_soft);
        danger = c.getColor(R.color.wf_danger);
        dangerSoft = c.getColor(R.color.wf_danger_soft);
        info = c.getColor(R.color.wf_info);
        infoSoft = c.getColor(R.color.wf_info_soft);
        violet = c.getColor(R.color.wf_violet);
        violetSoft = c.getColor(R.color.wf_violet_soft);
    }

    public static Palette of(Context c) {
        int mode = Ui.isNight(c) ? 1 : 0;
        if (cached == null || cachedMode != mode) {
            cached = new Palette(c);
            cachedMode = mode;
        }
        return cached;
    }

    /** 色调对应的 [前景色, 浅底色] */
    public int[] tone(Tone t) {
        switch (t) {
            case PRIMARY:
                return new int[]{primary, primarySoft};
            case SUCCESS:
                return new int[]{success, successSoft};
            case WARNING:
                return new int[]{warning, warningSoft};
            case DANGER:
                return new int[]{danger, dangerSoft};
            case INFO:
                return new int[]{info, infoSoft};
            case VIOLET:
                return new int[]{violet, violetSoft};
            default:
                return new int[]{text2, surfaceAlt};
        }
    }

    /** 图表用的一组好分辨的颜色（按顺序取） */
    public int series(int i) {
        int[] s = {primary, success, warning, violet, info, danger, 0xFF14B8A6, 0xFFEC4899, 0xFF64748B};
        return s[((i % s.length) + s.length) % s.length];
    }
}
