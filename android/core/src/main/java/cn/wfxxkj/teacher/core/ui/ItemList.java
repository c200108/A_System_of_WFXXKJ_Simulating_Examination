package cn.wfxxkj.teacher.core.ui;

import android.content.Context;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.content.res.ColorStateList;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AbsListView;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import cn.wfxxkj.teacher.core.R;

/**
 * 列表：卡片式条目、下拉刷新、滑到底自动加载下一页、空/出错状态、长按多选。
 * 窗口宽了自动排成多列（手机 1 列，大屏手机横屏 2 列，平板横屏 3 列）。
 *
 * <pre>
 * ItemList&lt;JSONObject&gt; list = new ItemList&lt;&gt;(ctx, new ItemList.Binder&lt;JSONObject&gt;() {
 *     public View create(Context c) { return new ExamCard(c); }
 *     public void bind(View v, JSONObject exam, int pos) { ((ExamCard) v).bind(exam); }
 * });
 * list.setOnItemClick((exam, pos) -&gt; push(new ExamDetailScreen(exam)));
 * list.setOnRefresh(this::reload);
 * list.loading();             // 显示加载中
 * list.setItems(exams);       // 有数据就显示列表，空了显示 empty 文案
 * </pre>
 */
public class ItemList<T> extends FrameLayout {

    public interface Binder<T> {
        /** 建一个条目的视图（会被复用） */
        View create(Context c);

        /** 把数据填进视图 */
        void bind(View v, T item, int position);
    }

    public interface Click<T> {
        void click(T item, int position);
    }

    /** 多选时用来认条目（一般返回 id） */
    public interface Key<T> {
        Object key(T item);
    }

    public interface SelectionChanged {
        void changed(int count);
    }

    private final Binder<T> binder;
    private final ListView list;
    private final RefreshLayout refresh;
    private final StateView state;
    private final List<T> items = new ArrayList<>();
    private final Adapter adapter = new Adapter();
    private final LinearLayout footer;
    private final ProgressBar footerSpinner;
    private final TextView footerText;
    private int minCellDp = 340;
    private int maxColumns = 3;
    private int columns = 1;
    private int gap;
    private Click<T> onClick;
    private Click<T> onLongClick;
    private Runnable onLoadMore;
    private boolean hasMore;
    private boolean loadingMore;
    private String emptyText = "这里还没有内容";
    private String emptyHint;
    private String emptyAction;
    private Runnable onEmptyAction;
    private boolean flat;

    // 多选
    private Key<T> keyFn;
    private boolean selecting;
    private final Map<Object, T> selected = new LinkedHashMap<>();
    private SelectionChanged onSelection;

    public ItemList(Context c, Binder<T> binder) {
        super(c);
        this.binder = binder;
        gap = Ui.dp(c, 10);
        list = new ListView(c);
        list.setDivider(new ColorDrawable(0));
        list.setDividerHeight(0);
        list.setSelector(new ColorDrawable(0));
        list.setClipToPadding(false);
        list.setScrollBarStyle(View.SCROLLBARS_OUTSIDE_OVERLAY);
        list.setCacheColorHint(0);
        setSidePadding(Ui.wide(c) ? 24 : 16);

        footer = V.hbox(c);
        footer.setGravity(Gravity.CENTER);
        V.pad(footer, 0, 12, 0, 12);
        footerSpinner = new ProgressBar(c);
        footerSpinner.setIndeterminateTintList(ColorStateList.valueOf(Palette.of(c).primary));
        footer.addView(footerSpinner, new LinearLayout.LayoutParams(Ui.dp(c, 22), Ui.dp(c, 22)));
        footerText = V.text(c, "", V.CAPTION);
        V.addStart(footer, footerText, 8);
        list.addFooterView(footer, null, false);
        footer.setVisibility(GONE);

        list.setAdapter(adapter);
        list.setOnScrollListener(new AbsListView.OnScrollListener() {
            @Override
            public void onScrollStateChanged(AbsListView v, int s) {}

            @Override
            public void onScroll(AbsListView v, int first, int visible, int total) {
                if (hasMore && !loadingMore && onLoadMore != null && total > 0 && first + visible >= total - 2) {
                    loadingMore = true;
                    renderFooter();
                    onLoadMore.run();
                }
            }
        });

        refresh = new RefreshLayout(c);
        refresh.setContent(list);
        addView(refresh, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT));
        state = new StateView(c);
        addView(state, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT, Gravity.TOP));
        state.setVisibility(GONE);
    }

    // ---------- 设置 ----------

    /** 每列至少多宽（dp），默认 340；maxColumns 默认 3。设成很大就永远单列 */
    public ItemList<T> setCell(int minCellDp, int maxColumns) {
        this.minCellDp = minCellDp;
        this.maxColumns = maxColumns;
        requestLayout();
        return this;
    }

    /** 平铺样式：条目之间不留缝，适合「设置项」一样的紧凑列表（条目自己画分隔线） */
    public ItemList<T> setFlat(boolean on) {
        flat = on;
        gap = on ? 0 : Ui.dp(getContext(), 10);
        if (on) setSidePadding(0);
        adapter.notifyDataSetChanged();
        return this;
    }

    public void setSidePadding(int dp) {
        int s = Ui.dp(getContext(), dp);
        list.setPadding(s, Ui.dp(getContext(), 8), s, Ui.dp(getContext(), 96));
    }

    /** 列表上方跟着一起滚动的内容（筛选条、统计卡片） */
    public void addHeader(View v) {
        list.addHeaderView(v, null, false);
    }

    public void removeHeader(View v) {
        list.removeHeaderView(v);
    }

    public ListView listView() {
        return list;
    }

    public void setOnItemClick(Click<T> c) {
        onClick = c;
    }

    public void setOnItemLongClick(Click<T> c) {
        onLongClick = c;
    }

    public void setOnRefresh(Runnable r) {
        refresh.setOnRefresh(r == null ? null : r::run);
    }

    /** 滑到底时加载下一页；加载完调 {@link #appendItems} 并告诉还有没有更多 */
    public void setOnLoadMore(Runnable r) {
        onLoadMore = r;
    }

    public void setEmpty(String text, String hint) {
        emptyText = text;
        emptyHint = hint;
        emptyAction = null;
        onEmptyAction = null;
    }

    public void setEmpty(String text, String hint, String action, Runnable onAction) {
        emptyText = text;
        emptyHint = hint;
        emptyAction = action;
        onEmptyAction = onAction;
    }

    // ---------- 数据 ----------

    /** 显示「加载中」（已有数据时只转刷新圈，不清空列表） */
    public void loading() {
        if (items.isEmpty() && list.getHeaderViewsCount() == 0) {
            state.loading();
        } else if (!refresh.isRefreshing()) {
            refresh.setRefreshing(true);
        }
    }

    public void setItems(Collection<T> data) {
        setItems(data, false);
    }

    /** hasMore = 还有下一页 */
    public void setItems(Collection<T> data, boolean hasMore) {
        items.clear();
        if (data != null) items.addAll(data);
        this.hasMore = hasMore;
        loadingMore = false;
        refresh.setRefreshing(false);
        if (selecting) pruneSelection();
        adapter.notifyDataSetChanged();
        renderFooter();
        renderState();
    }

    public void appendItems(Collection<T> data, boolean hasMore) {
        if (data != null) items.addAll(data);
        this.hasMore = hasMore;
        loadingMore = false;
        adapter.notifyDataSetChanged();
        renderFooter();
        renderState();
    }

    /** 加载失败：没数据时整页显示错误和重试，有数据时只弹提示由调用方处理 */
    public void error(String message, Runnable retry) {
        loadingMore = false;
        refresh.setRefreshing(false);
        renderFooter();
        if (items.isEmpty()) {
            state.error(message, retry);
            state.setTranslationY(headerHeight());
        }
    }

    public List<T> items() {
        return items;
    }

    public int size() {
        return items.size();
    }

    /** 数据里某条改了，重画 */
    public void refreshViews() {
        adapter.notifyDataSetChanged();
        renderState();
    }

    public void scrollToTop() {
        list.setSelection(0);
    }

    // ---------- 多选 ----------

    /** 开启长按多选。key 用来认条目（一般返回 id） */
    public void enableSelection(Key<T> key, SelectionChanged changed) {
        keyFn = key;
        onSelection = changed;
    }

    public boolean isSelecting() {
        return selecting;
    }

    public void startSelection() {
        if (keyFn == null) return;
        selecting = true;
        adapter.notifyDataSetChanged();
        if (onSelection != null) onSelection.changed(selected.size());
    }

    public void stopSelection() {
        selecting = false;
        selected.clear();
        adapter.notifyDataSetChanged();
        if (onSelection != null) onSelection.changed(-1);
    }

    public List<T> selection() {
        return new ArrayList<>(selected.values());
    }

    public List<Object> selectedKeys() {
        return new ArrayList<>(selected.keySet());
    }

    public void selectAll() {
        for (T it : items) selected.put(keyFn.key(it), it);
        adapter.notifyDataSetChanged();
        if (onSelection != null) onSelection.changed(selected.size());
    }

    public boolean isSelectedItem(T item) {
        return keyFn != null && selected.containsKey(keyFn.key(item));
    }

    private void toggle(T item) {
        Object k = keyFn.key(item);
        if (selected.containsKey(k)) selected.remove(k);
        else selected.put(k, item);
        adapter.notifyDataSetChanged();
        if (onSelection != null) onSelection.changed(selected.size());
    }

    private void pruneSelection() {
        Map<Object, T> keep = new LinkedHashMap<>();
        for (T it : items) {
            Object k = keyFn.key(it);
            if (selected.containsKey(k)) keep.put(k, it);
        }
        selected.clear();
        selected.putAll(keep);
        if (onSelection != null) onSelection.changed(selected.size());
    }

    // ---------- 内部 ----------

    private void renderFooter() {
        boolean show = !items.isEmpty() && (hasMore || loadingMore || onLoadMore != null);
        footer.setVisibility(show ? VISIBLE : GONE);
        footerSpinner.setVisibility(loadingMore || hasMore ? VISIBLE : GONE);
        footerText.setText(loadingMore || hasMore ? "正在加载…" : "没有更多了");
    }

    private void renderState() {
        if (items.isEmpty()) {
            if (emptyAction != null) state.empty(emptyText, emptyHint, emptyAction, onEmptyAction);
            else state.empty(emptyText, emptyHint);
            state.setTranslationY(headerHeight());
        } else {
            state.hide();
        }
    }

    private int headerHeight() {
        int h = 0;
        for (int i = 0; i < list.getChildCount() && i < list.getHeaderViewsCount(); i++) {
            h += list.getChildAt(i).getHeight();
        }
        return h;
    }

    @Override
    protected void onSizeChanged(int w, int h, int ow, int oh) {
        super.onSizeChanged(w, h, ow, oh);
        int inner = w - list.getPaddingLeft() - list.getPaddingRight();
        int n = Ui.columns(getContext(), inner + gap, minCellDp, maxColumns);
        if (n != columns) {
            columns = n;
            post(adapter::notifyDataSetChanged);
        }
    }

    private final class Adapter extends BaseAdapter {
        @Override
        public int getCount() {
            return (items.size() + columns - 1) / columns;
        }

        @Override
        public Object getItem(int row) {
            return items.get(row * columns);
        }

        @Override
        public long getItemId(int row) {
            return row;
        }

        @Override
        public View getView(int row, View convert, ViewGroup parent) {
            LinearLayout rowView;
            if (convert instanceof LinearLayout && ((LinearLayout) convert).getChildCount() == columns) {
                rowView = (LinearLayout) convert;
            } else {
                rowView = new LinearLayout(getContext());
                rowView.setOrientation(LinearLayout.HORIZONTAL);
                for (int i = 0; i < columns; i++) {
                    Cell cell = new Cell(getContext());
                    LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f);
                    if (i > 0) lp.setMarginStart(gap);
                    rowView.addView(cell, lp);
                }
                rowView.setBaselineAligned(false);
            }
            rowView.setPadding(0, 0, 0, gap);
            for (int i = 0; i < columns; i++) {
                Cell cell = (Cell) rowView.getChildAt(i);
                int idx = row * columns + i;
                if (idx < items.size()) {
                    cell.setVisibility(VISIBLE);
                    cell.bind(items.get(idx), idx);
                } else {
                    cell.setVisibility(INVISIBLE);
                }
            }
            return rowView;
        }
    }

    /** 一个格子：包着 binder 建的视图，管点击、长按、选中样式 */
    private final class Cell extends FrameLayout {
        final View content;
        final ImageView check;
        final RippleDrawable ripple;
        T item;
        int pos;

        Cell(Context c) {
            super(c);
            content = binder.create(c);
            addView(content, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.WRAP_CONTENT));
            Palette p = Palette.of(c);
            ripple = new RippleDrawable(ColorStateList.valueOf(p.ripple), null,
                    V.round(c, 0xFFFFFFFF, flat ? 0 : 16));
            setForeground(ripple);
            check = V.icon(c, R.drawable.ic_check_circle, p.primary, 24);
            LayoutParams lp = new LayoutParams(Ui.dp(c, 24), Ui.dp(c, 24), Gravity.TOP | Gravity.END);
            lp.topMargin = Ui.dp(c, 10);
            lp.setMarginEnd(Ui.dp(c, 10));
            addView(check, lp);
            check.setVisibility(GONE);
            setOnClickListener(v -> {
                if (item == null) return;
                if (selecting) toggle(item);
                else if (onClick != null) onClick.click(item, pos);
            });
            setOnLongClickListener(v -> {
                if (item == null) return false;
                if (keyFn != null && !selecting) {
                    selecting = true;
                    toggle(item);
                    return true;
                }
                if (onLongClick != null) {
                    onLongClick.click(item, pos);
                    return true;
                }
                return false;
            });
        }

        void bind(T it, int position) {
            item = it;
            pos = position;
            binder.bind(content, it, position);
            boolean sel = selecting && isSelectedItem(it);
            check.setVisibility(sel ? VISIBLE : GONE);
            if (selecting) {
                Palette p = Palette.of(getContext());
                GradientDrawable ring = V.round(getContext(), 0, flat ? 0 : 16);
                ring.setStroke(Ui.dp(getContext(), 2), sel ? p.primary : 0);
                if (sel) ring.setColor((p.primary & 0x00FFFFFF) | 0x14000000);
                setForeground(new android.graphics.drawable.LayerDrawable(
                        new android.graphics.drawable.Drawable[]{ring, ripple}));
                check.bringToFront();
            } else {
                setForeground(ripple);
            }
        }
    }
}
