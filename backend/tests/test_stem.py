"""从题干造检查点。**用的是题库里的真题干**，一个字都没改。

为什么坚持用真题干：自己编的例子会不自觉地照着解析器的写法编，测出来全绿，
一碰真题就散。下面这些是 `questions` 表里 Windows / WPS / 人工智能三类的原文。

造出来的是**草稿**：认得出的写成检查点，认不出的留在 `todo` 里给老师补。
所以这里既断言"该认出来的认出来了"，也断言"认不出来的老实承认"。
"""

import pytest

from app.services import sim, stem

# ————— 以下题干全部照抄自题库（questions 表），换行改成 \n —————
WIN_289 = """本题工作目录:D:\\EXAM windows操作
请打开本题工作目录下的系统基本操作文件夹，按要求完成以下操作:
①在winkt\\培训文件夹中新建一个演示文稿文件，命名为:"环保演讲稿.ptx"。
②将winkt\\fileclass文件夹中的文件"Myfiles.txt"和"Add11ie.mdb"都移动到winkt\\files文件夹中。"""

WIN_291 = """本题工作目录:D:\\EXAM\\windows操作
请打开本题工作目录下的系统基本操作文件夹，按要求完成以下操作:
①在"动物"文件夹中新建一个名为"珍稀动物"的文件夹。
②将"爱护动物.jpg"文件复制到"动物世界"文件夹中。"""

WIN_295 = """本题工作目录:D:\\EXAM\\windows操作03
请打开本题工作目录下的系统基本操作文件夹，按要求完成以下操作:
①将"命运共同体.xls"文件复制到"一带一路"文件夹中。
②把"丝绸之路\\古代丝绸之路"文件夹中的"海上丝绸之路.jpg"文件删除。"""

WPS_297 = """本题工作目录:D:\\EXAM\\WPS文字
请打开本题工作目录中的"A工具知多少.docx"，请完成以下操作:
①将文档中所有的"Deepsek"替换成"DeepSeek"。
②将文档中的标题设置为黑体、小二号、居中对齐。
③在文章最后输入一段新的文字:"即时AI：即时AI是即时下的AI设计工具。"。"""

WPS_298 = """本题工作目录:D:\\EXAM\\WPS文字
请打开本题工作目录中的"物联网改变生活.docx"文件，完成以下操作:
①将正文所有段落格式设置为首行缩进2字符，行距为固定值24磅。
②把文章中所有的"智慧"替换成"智能"。
③在文章最后输入一段新的文字:"物联网(IOT)是指通过信息传感设备。"。"""

WPS_299 = """本题工作目录:D:\\EXAM\\WPS文字02
请打开本题工作目录中的"智慧城市.docx"，请完成以下操作:
①将文档中的文本"智能城市"全部替换为"智慧城市"。
②设置文档第一段的段前间距为1行，段后间距0.5行，行距为1.5倍行距。
③在文章最后输入一段新的文字:"智慧城市是运用物联网、大数据、AI等技术。"。
④原名原位置保存并退出。"""

AI_318 = """本题工作目录:D:\\EXAM生成式人工智能
请使用给定的AI工具完成以下操作:
①请对"树树皆秋色，山山唯落晖。"这句诗，生成一段鉴赏文本。
②请为"青州古城"，生成一幅宣传画。
③请为白居易的《钱塘湖春行》，生成一幅国风图片。"""

HTML_305 = """为宣传潍坊市首届"科技引领未来"主题科技展，学校编程社团需制作系列宣传网页。
①修改网页标题为"潍坊科技展";
②使用相对路径设置图片链接为img文件夹下"无人机图片.jpg"，图片宽度为"500px"。"""

HTML_308 = """根据所给的HTML基础代码，进行简单的网页编辑操作，完成"班级风采展"页面的制作。
①将网页中的一级标题内容修改为"初二(3)班班级风采展示"；
②将班级照片"22.jpg"换成为"heying.jpg"，图片高度为"240px"。"""

HTML_311 = """根据所给的HTML基础代码，完成"智慧食堂"宣传页面的制作。
①修改网页标题为"智慧食堂"；
②将网页背景色修改为深红色"#980015"；网页中的图片修改为"智慧食堂.jpg"。"""

IOT_330 = """学校引进了"智慧食堂"管理系统，师生使用带有电子标签的餐盘，通过智能结算台，
可精准识别不同餐盘。请你仔细读图，将结构图补充完整。
从素材区选择合适的设备，拖动到答题区中相应的热区位置。"""

DRAG_324 = "请将符合智能家居的设备拖拽到指定区域。"


def asserts_of(got: dict) -> list[dict]:
    return [c["assert"] for c in got["checks"]]


# ================================================================ 认题型
@pytest.mark.parametrize("text,scope,want", [
    (WIN_289, "Windows系统操作", "win"),
    (WIN_291, "Windows系统操作", "win"),
    (WPS_297, "WPS文字操作", "wps"),
    (AI_318, "人工智能", "ai"),
])
def test_kind_is_recognised(text, scope, want):
    assert stem.guess_kind(text, scope) == want


def test_kind_trusts_the_stem_over_the_scope():
    """题库里有三道 WPS 文字题，知识范围却挂在「Windows系统操作」下面。
    **题干说了算** —— 按知识范围判会给它配一个文件操作环境，全错。"""
    misfiled = """本题工作目录:D:\\EXAM WPS文字
请打开本题工作目录中的"职业教育大有可为.docx"，请完成以下操作:
①将正文中所有的"qingchun"替换为"青春"。"""
    assert stem.guess_kind(misfiled, "Windows系统操作") == "wps"


# ================================================================ Windows
def test_new_file_in_a_subfolder():
    got = stem.parse(WIN_289)
    assert {"op": "exists", "path": "系统基本操作/winkt/培训/环保演讲稿.ptx",
            "is": "file"} in asserts_of(got)


def test_generated_environment_and_checks_agree_on_names():
    """「在winkt\培训文件夹中新建」——文件夹叫「培训」还是「培训文件夹」？中文里
    两种写法一样。**不用纠结**：环境和检查点是一起生成的，只要两边用同一个名字，
    学生在磁盘上看到什么就在什么里做，自洽。这条就是钉住这个自洽。"""
    got = stem.parse(WIN_289)
    fs = got["env"]["fs"]
    for c in asserts_of(got):
        if c["op"] == "exists" and c.get("is") != "dir":
            parent = "/".join(c["path"].split("/")[:-1])
            assert parent in fs, f"检查点指向 {c['path']}，但环境里没有 {parent}"


def test_moving_two_files_checks_both_ends():
    """「移动」要判两头：新位置有了、**老位置没了**。只判一头的话，
    学生按复制做也能满分。"""
    got = asserts_of(stem.parse(WIN_289))
    for name in ("Myfiles.txt", "Add11ie.mdb"):
        assert {"op": "exists", "path": f"系统基本操作/winkt/files/{name}"} in got
        assert {"op": "missing", "path": f"系统基本操作/winkt/fileclass/{name}"} in got


def test_new_folder_and_copy():
    got = asserts_of(stem.parse(WIN_291))
    assert {"op": "exists", "path": "系统基本操作/动物/珍稀动物", "is": "dir"} in got
    assert {"op": "exists", "path": "系统基本操作/动物世界/爱护动物.jpg"} in got


def test_copy_does_not_require_the_source_to_be_gone():
    """「复制」和「移动」差的就是这一条。判错了学生照做反而扣分。"""
    got = asserts_of(stem.parse(WIN_291))
    assert not any(a["op"] == "missing" for a in got), got


def test_delete_with_a_nested_path():
    got = asserts_of(stem.parse(WIN_295))
    assert {"op": "missing",
            "path": "系统基本操作/丝绸之路/古代丝绸之路/海上丝绸之路.jpg"} in got


def test_initial_files_are_inferred_from_the_operations():
    """题干只说"要做成什么样"，初始环境是倒推的 —— 要移动的文件开考时得在。"""
    fs = stem.parse(WIN_289)["env"]["fs"]
    assert fs["系统基本操作/winkt/fileclass/Myfiles.txt"]["type"] == "file"
    assert fs["系统基本操作/winkt/files"]["type"] == "dir"
    assert fs["系统基本操作/winkt/培训"]["type"] == "dir"


def test_parent_folders_are_filled_in():
    """判分器按路径找，父目录不在就找不到。"""
    fs = stem.parse(WIN_295)["env"]["fs"]
    assert "系统基本操作/丝绸之路" in fs
    assert fs["系统基本操作/丝绸之路"]["type"] == "dir"


# ================================================================ WPS 文字
def test_replace_checks_both_directions():
    """替换要判两条：新词有了、**旧词没了**。只判"有没有新词"的话，
    学生在文末补一句就能骗过去。"""
    got = asserts_of(stem.parse(WPS_297))
    assert {"op": "text", "absent": "Deepsek", "present": "DeepSeek"} in got


def test_title_format_is_split_into_separate_checks():
    """「黑体、小二号、居中」拆成三条：学生做对两项能拿两项的分，
    老师也一眼看出差在哪一项。"""
    got = [a for a in asserts_of(stem.parse(WPS_297)) if a["op"] == "para"]
    assert {"op": "para", "at": 0, "font": "黑体"} in got
    assert {"op": "para", "at": 0, "size": "小二"} in got
    assert {"op": "para", "at": 0, "align": "center"} in got


def test_body_indent_and_fixed_line_spacing():
    got = [a for a in asserts_of(stem.parse(WPS_298)) if a["op"] == "para"]
    assert {"op": "para", "at": 1, "indent": 2.0} in got
    assert {"op": "para", "at": 1, "line": {"type": "fixed", "value": 24.0}} in got


def test_paragraph_spacing_and_multiple_line_spacing():
    got = [a for a in asserts_of(stem.parse(WPS_299)) if a["op"] == "para"]
    assert {"op": "para", "at": 1, "before": 1.0} in got
    assert {"op": "para", "at": 1, "after": 0.5} in got
    assert {"op": "para", "at": 1, "line": {"type": "multiple", "value": 1.5}} in got


def test_new_paragraph_at_the_end():
    got = asserts_of(stem.parse(WPS_297))
    last = [a for a in got if a["op"] == "order"]
    assert last and last[0]["last"].startswith("即时AI")


def test_save_and_quit_is_not_a_checkpoint():
    """「④原名原位置保存并退出」不是要判的东西 —— 不保存的话前面几条自然
    判不过，单独出一条只会重复扣分。也不该留在 todo 里让老师白看一遍。"""
    got = stem.parse(WPS_299)
    assert not any("保存" in t for t in got["todo"]), got["todo"]


def test_the_word_to_be_replaced_is_actually_in_the_document():
    """**这条最要紧**：题目说「把 A 替换成 B」，生成的原文里必须真有 A。

    第一版生成的是两行占位符，学生打开文档根本找不到要替换的词，这一问谁也
    做不出来 —— 而且从题目和检查点上都看不出毛病。
    """
    for text, word in ((WPS_297, "Deepsek"), (WPS_298, "智慧"), (WPS_299, "智能城市")):
        paras = stem.parse(text)["env"]["paras"]
        whole = "".join(p["text"] for p in paras)
        assert word in whole, f"文档里没有「{word}」，这道题没法做：{whole[:60]}"


def test_the_document_has_a_title_and_enough_body():
    """标题类检查点指向第 0 段、正文类指向第 1 段 —— 文档得有这个结构。
    正文也要够长，不然「所有段落首行缩进」这类题看不出效果。"""
    paras = stem.parse(WPS_298)["env"]["paras"]
    assert len(paras) >= 4, "正文太短，排版题看不出效果"
    assert paras[0]["text"] and len(paras[0]["text"]) < 30, "第 0 段该是标题"
    assert all(len(p["text"]) > 20 for p in paras[1:]), "正文每段要有内容"


def test_material_files_have_content():
    """考场里的素材文件不能是空的 —— 学生打开一看空白会以为题目坏了。"""
    fs = stem.parse(WIN_289)["env"]["fs"]
    txt = fs["系统基本操作/winkt/fileclass/Myfiles.txt"]
    assert "Myfiles" in txt["content"] and len(txt["content"]) > 10


def test_document_name_comes_from_the_stem():
    assert stem.parse(WPS_297)["env"]["name"] == "A工具知多少.docx"
    assert stem.parse(WPS_298)["env"]["name"] == "物联网改变生活.docx"


# ================================================================ AI 工具
def test_ai_needs_no_checkpoints_at_all():
    """这类题老师什么都不用填 —— 检查点在判分时按题干现算。"""
    got = stem.parse(AI_318)
    assert got["kind"] == "ai" and got["checks"] == [] and got["todo"] == []


def test_ai_checks_are_computed_from_the_stem_at_grading_time():
    """接上一条：造出来的空检查点，交到判分器手里会变成真检查点。"""
    checks = sim.checks_for("ai", [], AI_318, total=10)
    assert len(checks) >= 2
    good = {"messages": [{"role": "user", "text":
                          "请对树树皆秋色山山唯落晖这句诗生成一段鉴赏文本，"
                          "再为青州古城生成一幅宣传画，为钱塘湖春行生成国风图片"}]}
    assert sim.run_checks("ai", checks, good)["score"] > 0


# ================================================================ 网页
def test_page_title_and_relative_image_path():
    got = asserts_of(stem.parse(HTML_305))
    assert {"op": "title", "equals": "潍坊科技展"} in got
    assert {"op": "attr", "selector": "img", "name": "src",
            "has": "无人机图片.jpg"} in got
    assert {"op": "attr", "selector": "img", "name": "src", "has": "img/"} in got,         "题目要求用相对路径指到 img 文件夹，这一问也得判"
    assert {"op": "attr", "selector": "img", "name": "width", "has": "500"} in got


def test_heading_and_image_swap_with_height():
    got = asserts_of(stem.parse(HTML_308))
    assert {"op": "sel", "selector": "h1", "text": "初二(3)班班级风采展示"} in got
    assert {"op": "attr", "selector": "img", "name": "src", "has": "heying.jpg"} in got
    assert {"op": "attr", "selector": "img", "name": "height", "has": "240"} in got


def test_background_colour_goes_through_css():
    """背景色可能写在 style.css、<style> 块或行内 —— 判分器三种都认，
    所以这里出 css 检查点而不是抠源码。"""
    got = asserts_of(stem.parse(HTML_311))
    assert {"op": "css", "selector": "body", "prop": "background-color",
            "equals": "#980015"} in got


# ================================================================ 认不出来的
def test_electronic_tags_are_not_html():
    """「带有电子标签的餐盘」是物联网题。早先拿「标签」两个字当网页题的线索，
    把它误判成了 HTML —— 线索太宽会造出一堆判不准的检查点。"""
    assert stem.guess_kind(IOT_330, "物联网") != "html"



def test_drag_and_drop_questions_are_left_alone():
    """拖拽题（物联网、网络结构图）题干里没有可判的终态。硬造只会造出判不准的
    检查点 —— **老实返回 None，留给老师**，比造一个差不多的强。"""
    assert stem.parse(DRAG_324, "物联网") is None


def test_unparsed_lines_go_to_todo_not_silently_dropped():
    """认不出的句子要留痕。悄悄扔掉的话，老师以为题目判全了，实际漏判。"""
    odd = """本题工作目录:D:\\EXAM\\windows操作
①在"资料"文件夹中新建一个名为"备份"的文件夹。
②请将该文件夹的属性设置为隐藏并只读。"""
    got = stem.parse(odd)
    assert len(got["checks"]) == 1
    assert got["todo"] and "隐藏" in got["todo"][0]


WPS_Q299 = """本题工作目录:C:\\EXAM
请打开本题工作目录中的"人工智能教育.docx"，请完成以下操作:
①将文档的第一自然段（人工智能……文化情景的有力支撑。）段落格式设置为文本之前缩进2字符，文本之后缩进2字符。
②将文档标题字体格式设置为黑体、二号，正文字体格式设置为宋体、四号。
③在文章最后输入一段新的文字:"人工智能教育是以学习者为中心，融合人工智能、大数据、虚拟现实等技术，贯穿教育全流程的新型教育模式。"。
④原名原位置保存并退出。"""


def test_bracket_excerpt_lands_in_document():
    """括号里抄的原文也要进文档，而且按内容定位，不能落到标题上。"""
    got = stem.parse(WPS_Q299)
    texts = [p["text"] for p in got["env"]["paras"]]
    assert any(t.startswith("人工智能，文化情景的有力支撑。") for t in texts[1:])
    left = [a for a in asserts_of(got) if a.get("left")]
    assert left and left[0]["at"] == {"has": "人工智能"}


def test_typed_text_with_fullwidth_colon_and_trailing_blank():
    """学生打的全角冒号、末尾多敲的空段，都不该让"最后输入一段文字"判错。"""
    from app.services import sim
    chk = [c for c in stem.parse(WPS_297)["checks"] if c["assert"]["op"] == "order"][0]
    state = {"paras": [{"text": "标题"},
                       {"text": "即时AI：即时AI是即时下的AI设计工具。"}, {"text": ""}]}
    assert sim.run_checks("wps", [chk], state)["results"][0]["ok"]
