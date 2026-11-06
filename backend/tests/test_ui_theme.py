"""全站界面主题、字号（系统管理员在「数据备份与系统更新」里选）。"""


def test_默认主题和字号(client):
    ui = client.get("/api/config").json()["ui"]
    assert ui == {"theme": "default", "font": "large"} or set(ui) == {"theme", "font"}


def test_只有系统管理员能改_改了大家都生效(client, auth, teacher_auth):
    assert client.put("/api/config/ui", json={"theme": "primer", "font": "larger"},
                      headers=teacher_auth).status_code == 403
    res = client.put("/api/config/ui", json={"theme": "primer", "font": "larger"}, headers=auth)
    assert res.status_code == 200, res.text
    assert client.get("/api/config").json()["ui"] == {"theme": "primer", "font": "larger"}
    assert client.put("/api/config/ui", json={"theme": "不存在", "font": "large"}, headers=auth).status_code == 422
    client.put("/api/config/ui", json={"theme": "default", "font": "large"}, headers=auth)
