"""测试用的隔离环境：临时目录 + 临时 SQLite，不碰 data/app.db 里的真实题库。

环境变量必须在 import app.* 之前设好，因为 app.config 在导入时就把配置读死了。
"""

import os
import pathlib
import tempfile

TMP = pathlib.Path(tempfile.mkdtemp(prefix="exam_test_"))

# 默认跑在临时 SQLite 上：快、不用起服务、随手就能跑。
# 想验证 MySQL 方言有没有问题，指定一个**专用的空库**再跑：
#   set TEST_DATABASE_URL=mysql+pymysql://exam:密码@127.0.0.1:3306/exam_test?charset=utf8mb4
#   pytest -q
# 注意：测试开始时会把该库的表全部删掉重建，绝不要指向正式库。
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "sqlite:///" + (TMP / "test.db").as_posix()
)
os.environ["UPLOAD_DIR"] = str(TMP / "uploads")
os.environ["JWT_SECRET"] = "test-secret-not-used-in-production"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.database import engine
    from app.main import app
    from app.models import Base
    from app.seed import seed

    # 指向 MySQL 时表会留在库里，先清干净再建，保证每次都是同样的起点
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    res = client.post("/api/auth/login", data={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
