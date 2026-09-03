"""把配置里跟界面有关的部分发给前端，让前后端共用同一份 config.yaml。

只发界面要用的字段，密钥、数据库地址这些一概不出现（它们在 .env 里，
本来也不在 config.yaml 中）。学生答题页也要读，所以不要求登录。
"""

from fastapi import APIRouter

from ..siteconfig import site

router = APIRouter(prefix="/api/config", tags=["配置"])


@router.get("", summary="前端要用的配置（公开，不含任何密钥）")
def get_config():
    return {
        "school": site.school.name,
        "paper": {
            "default_title": site.paper.default_title,
            "default_duration": site.paper.default_duration,
            "default_counts": site.paper.default_counts,
            "shuffle_options": site.paper.shuffle_options,
            "require_answer": site.paper.require_answer,
            "use_pinned": site.paper.use_pinned,
            "section_numerals": site.paper.section_numerals,
        },
        "exam": {
            "pass_score": site.exam.pass_score,
            "defaults": site.exam.defaults.model_dump(),
        },
        "upload": {
            "max_mb": site.upload.max_mb,
            "image_extensions": site.upload.image_extensions,
        },
    }
