"""货架后端回归测试。

测试按定义顺序执行（pytest 默认，无随机插件）：读 → CORS → 未登录写被拒
→ setup 登录 → 登录后写操作。共享一个 module 级 client + 临时库。
"""
import io
import zipfile


# ---------- 读（公开） ----------
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_seed_list(client):
    r = client.get("/api/scripts")
    assert r.status_code == 200
    slugs = sorted(s["slug"] for s in r.json())
    assert slugs == ["coklw", "jmcomic", "ptfans"]


def test_detail(client):
    d = client.get("/api/scripts/coklw").json()
    assert d["version"] and d["field_count"] >= 1 and d["has_icon"]
    assert len(d["manifest_yaml"]) > 50


def test_category_default(client):
    """lifespan 给已知脚本默认归类。"""
    s = {x["slug"]: x for x in client.get("/api/scripts").json()}
    assert s["ptfans"]["category"] == "PT站"
    assert s["jmcomic"]["category"] == "漫画动漫"
    assert s["coklw"]["category"] == "论坛社区"


def test_detail_404(client):
    assert client.get("/api/scripts/nonexistent").status_code == 404


def test_bundle_zip_compatible(client):
    """bundle 必须含 manifest+main、不含垃圾（= 能被管家接受的硬保证）。"""
    r = client.get("/api/scripts/coklw/bundle.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "manifest.yaml" in names and "main.py" in names
    assert not any(".backups" in n or "__pycache__" in n or n.endswith(".log") for n in names)


def test_icon(client):
    assert client.get("/api/scripts/coklw/icon").status_code == 200


def test_cors_public_read(client):
    """公共仓库：任意来源读返回 ACAO:*（第三方管家市场页对接前提）。"""
    r = client.get("/api/scripts", headers={"Origin": "https://anyone.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"


# ---------- 未登录写被拒（此刻尚未 setup，client 无 cookie） ----------
def test_write_requires_auth(client):
    z = client.get("/api/scripts/coklw/bundle.zip").content
    assert client.post("/api/scripts/upload", files={"file": ("x.zip", z, "application/zip")}).status_code == 401
    assert client.delete("/api/scripts/ptfans").status_code == 401


# ---------- setup + 登录 ----------
def test_setup_and_me(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "test12345"})
    assert r.status_code == 200 and r.json()["is_admin"]
    assert client.get("/api/auth/me").status_code == 200  # cookie 已就位


# ---------- 登录后写 ----------
def test_upload_force_overwrite(client):
    z = client.get("/api/scripts/coklw/bundle.zip").content
    up = client.post("/api/scripts/upload?force=true", files={"file": ("coklw.zip", z, "application/zip")})
    assert up.status_code == 200
    body = up.json()
    assert body["slug"] == "coklw" and body["created"] is False


def test_file_read_write(client):
    files = client.get("/api/scripts/coklw/files").json()["files"]
    assert any(f["path"] == "main.py" for f in files)
    rf = client.get("/api/scripts/coklw/files/manifest.yaml")
    assert rf.status_code == 200 and "slug" in rf.json()["content"]
    assert client.put("/api/scripts/coklw/files/README.md", json={"content": "# coklw\ntest\n"}).status_code == 200


def test_path_traversal_blocked(client):
    bad = client.get("/api/scripts/coklw/files/../../../etc/passwd")
    assert bad.status_code in (403, 404)


def test_update_tags(client):
    r = client.patch("/api/scripts/coklw", json={"tags": ["签到", "WordPress"]})
    assert r.status_code == 200 and r.json()["tags"] == ["签到", "WordPress"]


def test_update_category(client):
    r = client.patch("/api/scripts/coklw", json={"category": "技术开发"})
    assert r.status_code == 200 and r.json()["category"] == "技术开发"


def test_change_password(client):
    bad = client.post("/api/auth/change-password", json={"old_password": "wrong", "new_password": "newpass123"})
    assert bad.status_code == 401  # 旧密码错
    ok = client.post("/api/auth/change-password", json={"old_password": "test12345", "new_password": "newpass123"})
    assert ok.status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "admin", "password": "newpass123"}).status_code == 200


def test_delete(client):
    assert client.delete("/api/scripts/ptfans").status_code == 204
    after = sorted(s["slug"] for s in client.get("/api/scripts").json())
    assert "ptfans" not in after and "coklw" in after
