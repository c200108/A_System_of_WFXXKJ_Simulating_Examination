"""把配置里跟界面有关的部分发给前端，让前后端共用同一份 config.yaml。

只发界面要用的字段，密钥、数据库地址这些一概不出现（它们在 .env 里，
本来也不在 config.yaml 中）。学生答题页也要读，所以不要求登录。
"""

from fastapi import APIRouter, Depends

from ..config import settings
from ..deps import get_current_user
from ..models import User
from ..services.netaddr import in_container, server_addresses
from ..siteconfig import site

router = APIRouter(prefix="/api/config", tags=["配置"])


@router.get("", summary="前端要用的配置（公开，不含任何密钥）")
def get_config():
    return {
        "school": site.school.name,
        # 平台名称等门面文案，改 config.yaml 重启后端即生效，前端不用重新构建
        "site": site.site.model_dump(),
        # 学生链接（考试、打字）拼这个前缀。为空时前端退回浏览器当前地址。
        "public_base_url": settings.public_url,
        "paper": {
            "default_title": site.paper.default_title,
            "default_duration": site.paper.default_duration,
            "default_counts": site.paper.default_counts,
            "shuffle_options": site.paper.shuffle_options,
            "require_answer": site.paper.require_answer,
            "use_pinned": site.paper.use_pinned,
            "section_numerals": site.paper.section_numerals,
            # 卷面结构。组卷页照这个渲染六个大题的题量和分值输入框，
            # 学校改 config.yaml 的 paper.sections，界面跟着变，前端不用重新构建。
            "sections": [s.model_dump() for s in site.paper.sections],
            "full_score": site.paper.full_score,
        },
        "exam": {
            "pass_score": site.exam.pass_score,
            "defaults": site.exam.defaults.model_dump(),
            # 哪些题型要老师人工评阅，界面上据此显示「待阅」
            "manual_types": site.exam.manual_types,
        },
        "upload": {
            "max_mb": site.upload.max_mb,
            "image_extensions": site.upload.image_extensions,
        },
    }


@router.get("/addresses", summary="服务器自己的可访问地址（拼学生链接用，要登录）")
def addresses(_: User = Depends(get_current_user)):
    """老师在服务器本机用 localhost 打开后台时，学生链接不能用 localhost，
    前端拿这里的地址换掉主机名（端口用浏览器实际的端口）。

    public_base_url 配了就以它为准；ips 是本机网卡上的 IPv4（公网在前、局域网其次），
    在 Docker 容器里查不到宿主机的地址，返回空并带 in_container，前端提示去配 PUBLIC_BASE_URL。
    不放进公开的 /api/config：内网地址不必告诉所有人。
    """
    return {
        "public_base_url": settings.public_url,
        "ips": server_addresses(),
        "in_container": in_container(),
    }