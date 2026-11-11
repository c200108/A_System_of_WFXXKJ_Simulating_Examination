package cn.wfxxkj.teacher.typing;

import org.json.JSONObject;

import cn.wfxxkj.teacher.core.nav.Screen;
import cn.wfxxkj.teacher.core.net.Json;
import cn.wfxxkj.teacher.core.ui.Form;
import cn.wfxxkj.teacher.core.ui.Option;
import cn.wfxxkj.teacher.core.ui.Sheet;

/** 添加 / 编辑一段练习文本（语言建好后不能改，同网页） */
final class TextEditSheet {
    private TextEditSheet() {}

    /**
     * @param row       要改的那段，null = 新建
     * @param mode      新建时默认的语言
     * @param difficulty 新建时默认的难度
     */
    static void show(final Screen s, final JSONObject row, String mode, String difficulty, String[] difficulties,
                     java.util.List<JSONObject> themes, Integer defaultTheme, final Runnable onSaved) {
        final boolean editing = row != null;
        Sheet sh = new Sheet(s.ctx(), editing ? "编辑文本" : "添加文本");
        Form f = new Form(s.ctx());
        Form.Choice lang = null;
        if (editing) {
            f.note("语言：" + Option.labelOf(TextListScreen.MODES, Json.str(row, "mode"))
                    + "（语言不能改，需要换请删了重建）");
        } else {
            lang = f.choice("语言", TextListScreen.MODES, mode);
        }
        Form.Choice diff = f.choice("难度", Option.of(difficulties),
                editing ? Json.str(row, "difficulty") : (difficulty.isEmpty() ? difficulties[0] : difficulty));
        if (lang != null) f.row(lang, diff);
        final Form.Choice langF = lang;
        final Form.Choice theme = themes.isEmpty() ? null : f.choice("主题", themeOptions(themes),
                editing && !Json.isNull(row, "theme_id") && row.has("theme_id") ? Integer.valueOf(Json.num(row, "theme_id")) : defaultTheme);
        final Form.Text content = f.area("内容", editing ? Json.str(row, "content") : "", 5)
                .hint("一段完整的练习文本")
                .rule(v -> v.length() < 5 ? "文本太短，至少 5 个字符" : null);
        content.required();
        content.help("中文建议 20~60 字，英文建议 10~40 词。");
        sh.content(f.view());
        sh.buttons("取消", null, "保存", () -> {
            if (!f.validate()) return;
            final String m = langF == null ? Json.str(row, "mode") : langF.string(), d = diff.string(), text = content.value();
            final Integer th = theme == null || theme.value() == null ? null : ((Number) theme.value()).intValue();
            s.runBusy("正在保存…", () -> {
                if (editing) {
                    JSONObject patch = Json.of("difficulty", d, "content", text);
                    if (th != null) Json.put(patch, "theme_id", th);
                    return TypingApi.updateText(row.optLong("id"), patch);
                }
                return TypingApi.createText(m, d, text, th);
            }, r -> {
                sh.dismiss();
                s.toast("已保存");
                onSaved.run();
            });
        });
        sh.show();
    }

    static java.util.List<Option> themeOptions(java.util.List<JSONObject> themes) {
        java.util.List<Option> o = new java.util.ArrayList<>();
        for (JSONObject t : themes) {
            o.add(new Option(Integer.valueOf(Json.num(t, "id")), Json.str(t, "name") + (Json.bool(t, "is_enabled") ? "" : "（停用）")));
        }
        return o;
    }
}
