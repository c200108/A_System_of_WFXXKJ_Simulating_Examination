"""真常量 + 从 config.yaml 转出来的业务默认值。

这里不再写死知识范围和题型 —— 它们在 config.yaml 里（首次建库的初始值），
运行期真正生效的是数据库 dict_items 表。
"""

from .siteconfig import site

# 字典表的两个分类名，属于代码内部约定，不对外配置
DICT_SCOPE = "scope"
DICT_TYPE = "qtype"

# 下面几个都是从 config.yaml 读出来的，保留同名变量方便老代码引用
SCOPES: list[str] = site.bank.scopes
ALL_TYPES: list[str] = site.bank.types
DEFAULT_QTY: dict[str, int] = site.paper.default_counts
IMPORT_HEADERS: list[str] = site.import_.headers
