"""打字练习文本加「主题」

- typing_themes：主题表（名称、是否启用、排序、是否内置）。建一个内置的「信息生活」
- typing_texts.theme_id：文本所属主题。升级前的文本（内置的、老师加的、导入的）全部归「信息生活」

Revision ID: 0021
Revises: 0020
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

DEFAULT_THEME = "信息生活"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "typing_themes" not in insp.get_table_names():
        op.create_table(
            "typing_themes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(32), nullable=False, unique=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    themes = sa.table("typing_themes", sa.column("id", sa.Integer), sa.column("name", sa.String),
                      sa.column("is_enabled", sa.Boolean), sa.column("sort_order", sa.Integer),
                      sa.column("is_builtin", sa.Boolean), sa.column("created_at", sa.DateTime))
    tid = bind.execute(sa.select(themes.c.id).where(themes.c.name == DEFAULT_THEME)).scalar()
    if tid is None:
        bind.execute(themes.insert().values(name=DEFAULT_THEME, is_enabled=True, sort_order=0,
                                            is_builtin=True, created_at=datetime.now()))
        tid = bind.execute(sa.select(themes.c.id).where(themes.c.name == DEFAULT_THEME)).scalar()

    if "theme_id" not in {c["name"] for c in insp.get_columns("typing_texts")}:
        with op.batch_alter_table("typing_texts") as batch:
            batch.add_column(sa.Column("theme_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_typing_texts_theme", "typing_themes", ["theme_id"], ["id"],
                                     ondelete="SET NULL")
            batch.create_index("ix_typing_texts_theme_id", ["theme_id"])
    texts = sa.table("typing_texts", sa.column("theme_id", sa.Integer))
    bind.execute(texts.update().where(texts.c.theme_id.is_(None)).values(theme_id=tid))


def downgrade() -> None:
    with op.batch_alter_table("typing_texts") as batch:
        batch.drop_index("ix_typing_texts_theme_id")
        batch.drop_constraint("fk_typing_texts_theme", type_="foreignkey")
        batch.drop_column("theme_id")
    op.drop_table("typing_themes")