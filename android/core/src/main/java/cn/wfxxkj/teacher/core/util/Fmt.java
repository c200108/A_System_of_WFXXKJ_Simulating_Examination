package cn.wfxxkj.teacher.core.util;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * 显示用的格式化。服务器的时间都是不带时区的本地时间字符串（「2026-10-08T14:30:00」），
 * 这里直接按字符串截取，不做时区换算 —— 和网页版显示的一模一样。
 */
public final class Fmt {
    private Fmt() {}

    /** 3.0 → "3"，2.5 → "2.5"，2.333 → "2.33" */
    public static String num(double v) {
        if (Double.isNaN(v) || Double.isInfinite(v)) return "—";
        if (v == Math.rint(v)) return String.valueOf((long) v);
        String s = String.format(Locale.ROOT, "%.2f", v);
        while (s.endsWith("0")) s = s.substring(0, s.length() - 1);
        if (s.endsWith(".")) s = s.substring(0, s.length() - 1);
        return s;
    }

    public static String num(Double v) {
        return v == null ? "—" : num(v.doubleValue());
    }

    /** 0.8567 → "85.7%" */
    public static String percent(double ratio) {
        return num(Math.round(ratio * 1000) / 10.0) + "%";
    }

    /** 「2026-10-08 14:30」 */
    public static String dateTime(String iso) {
        if (iso == null || iso.length() < 16 || "null".equals(iso)) return iso == null || "null".equals(iso) ? "" : iso;
        return iso.substring(0, 10) + " " + iso.substring(11, 16);
    }

    /** 今年的省掉年份：「10-08 14:30」 */
    public static String shortDateTime(String iso) {
        String s = dateTime(iso);
        if (s.length() < 16) return s;
        String year = new SimpleDateFormat("yyyy", Locale.ROOT).format(new Date());
        return s.startsWith(year + "-") ? s.substring(5) : s;
    }

    /** 「2026-10-08」 */
    public static String date(String iso) {
        if (iso == null || iso.length() < 10 || "null".equals(iso)) return "";
        return iso.substring(0, 10);
    }

    /** 现在的本地时间，格式同服务器 */
    public static String nowIso() {
        return new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.ROOT).format(new Date());
    }

    /** 秒 → 「3 分 20 秒」 */
    public static String duration(long seconds) {
        if (seconds < 60) return seconds + " 秒";
        long m = seconds / 60, s = seconds % 60;
        if (m < 60) return s == 0 ? m + " 分钟" : m + " 分 " + s + " 秒";
        long h = m / 60;
        m = m % 60;
        return m == 0 ? h + " 小时" : h + " 小时 " + m + " 分";
    }

    /** 字节数 → 「1.2 MB」 */
    public static String size(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return num(Math.round(bytes / 102.4) / 10.0) + " KB";
        return num(Math.round(bytes / 104857.6) / 10.0) + " MB";
    }
}
