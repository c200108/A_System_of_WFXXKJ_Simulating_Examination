package cn.wfxxkj.teacher.core.nav;

/**
 * 底部标签栏（宽屏是左侧导航栏）的一项。每个功能模块提供一个，主界面把它们排起来。
 */
public final class TabSpec {

    public interface Factory {
        Screen create();
    }

    /** 唯一标识，Host.switchTab 用 */
    public final String key;
    public final String title;
    /** 未选中时的图标（线条） */
    public final int icon;
    /** 选中时的图标（实心） */
    public final int iconSelected;
    public final Factory root;

    public TabSpec(String key, String title, int icon, int iconSelected, Factory root) {
        this.key = key;
        this.title = title;
        this.icon = icon;
        this.iconSelected = iconSelected;
        this.root = root;
    }
}
