package cn.wfxxkj.teacher.typing;

import android.content.Context;
import android.view.View;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Palette;
import cn.wfxxkj.teacher.core.ui.SearchBox;
import cn.wfxxkj.teacher.core.ui.Sheet;
import cn.wfxxkj.teacher.core.ui.Ui;
import cn.wfxxkj.teacher.core.ui.V;

/**
 * 「学生对比」选人：可搜姓名 / 班级，最多选 {@link #MAX} 人（折线配色只验证到 8 种，同网页）。
 */
final class StudentPickSheet {
    static final int MAX = 8;

    interface Done {
        void done(List<String> keys);
    }

    private StudentPickSheet() {}

    static void show(Context c, List<JSONObject> options, List<String> picked, Done onDone) {
        Sheet s = new Sheet(c, "选学生对比（最多 " + MAX + " 人）");
        final Set<String> on = new LinkedHashSet<>(picked);
        final TextView count = V.text(c, "", V.CAPTION);
        SearchBox search = new SearchBox(c, "搜姓名或班级");
        s.content(search);
        V.pad(count, 4, 8, 0, 4);
        s.content(count);
        final LinearLayout rows = V.vbox(c);
        s.content(rows);
        final List<View> views = new ArrayList<>();
        final List<CheckBox> boxes = new ArrayList<>();
        Palette p = Palette.of(c);
        Runnable updateCount = () -> count.setText("已选 " + on.size() + " / " + MAX + " 人");
        for (final JSONObject o : options) {
            final String key = Json.str(o, "key");
            LinearLayout row = V.hbox(c);
            row.setMinimumHeight(Ui.dp(c, 48));
            V.pad(row, 0, 2, 4, 2);
            final CheckBox cb = new CheckBox(c);
            cb.setChecked(on.contains(key));
            cb.setClickable(false);
            row.addView(cb);
            LinearLayout texts = V.vbox(c);
            texts.addView(V.text(c, Json.str(o, "name"), V.BODY));
            texts.addView(V.text(c, Json.str(o, "class") + " · 练习 " + Json.num(o, "count") + " 次", V.CAPTION));
            row.addView(texts, V.fill());
            V.clickable(row, 8, v -> {
                if (on.contains(key)) {
                    on.remove(key);
                } else {
                    if (on.size() >= MAX) {
                        Toast.makeText(c, "最多选 " + MAX + " 人", Toast.LENGTH_SHORT).show();
                        return;
                    }
                    on.add(key);
                }
                cb.setChecked(on.contains(key));
                updateCount.run();
            });
            row.setTag((Json.str(o, "name") + " " + Json.str(o, "class")).toLowerCase());
            rows.addView(row, V.matchWrap());
            views.add(row);
            boxes.add(cb);
        }
        if (options.isEmpty()) {
            TextView t = V.text(c, "这段时间里还没有学生练习", V.BODY2);
            t.setTextColor(p.text3);
            V.pad(t, 4, 16, 4, 16);
            rows.addView(t);
        }
        search.setOnSearch(k -> {
            String q = k.toLowerCase();
            for (View v : views) {
                String tag = String.valueOf(v.getTag());
                v.setVisibility(q.isEmpty() || tag.contains(q) ? View.VISIBLE : View.GONE);
            }
        });
        updateCount.run();
        s.buttons("清空", () -> {
            on.clear();
            for (CheckBox b : boxes) b.setChecked(false);
            updateCount.run();
        }, "确定", () -> {
            s.dismiss();
            onDone.done(new ArrayList<>(on));
        });
        s.show();
    }
}
