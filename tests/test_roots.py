import re

from app import storage


def roots_in_file(data_dir):
    return storage.load_json(data_dir / "config.json")["roots"]


def add(client, path, label=""):
    return client.post("/api/roots", json={"path": path, "label": label})


def test_list_is_empty_at_first(client):
    res = client.get("/api/roots")
    assert res.status_code == 200
    assert res.json() == {"roots": []}


def test_add_saves_all_fields(client, data_dir, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    res = add(client, str(folder), "My Pack")
    assert res.status_code == 201
    body = res.json()
    assert body["warning"] is None

    saved = roots_in_file(data_dir)
    assert len(saved) == 1
    root = saved[0]
    assert set(root) == {"id", "label", "path", "enabled", "added_at"}
    assert re.fullmatch(r"r_[0-9a-f]{4}", root["id"])
    assert root["label"] == "My Pack"
    assert root["path"] == str(folder)
    assert root["enabled"] is True
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+09:00", root["added_at"])
    assert body["root"] == root
    assert client.get("/api/roots").json()["roots"] == saved


def test_label_defaults_to_folder_name(client, tmp_path):
    folder = tmp_path / "SciFiPack"
    folder.mkdir()
    assert add(client, str(folder)).json()["root"]["label"] == "SciFiPack"


def test_path_is_cleaned(client, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    # エクスプローラーの「パスのコピー」は両端に " がつく。末尾の \ も外す
    res = add(client, f'  "{folder}\\"  ')
    assert res.status_code == 201
    assert res.json()["root"]["path"] == str(folder)


def test_ids_are_unique(client, tmp_path):
    ids = set()
    for i in range(20):
        folder = tmp_path / f"f{i}"
        folder.mkdir()
        ids.add(add(client, str(folder)).json()["root"]["id"])
    assert len(ids) == 20


def test_empty_path_is_rejected(client, data_dir):
    for path in ("", "   ", '""'):
        res = add(client, path)
        assert res.status_code == 400
        assert "パスを入力" in res.json()["detail"]
    assert roots_in_file(data_dir) == []


def test_relative_path_is_rejected(client, data_dir):
    for path in ("Audio\\BGM", "\\Audio", "..\\x"):
        res = add(client, path)
        assert res.status_code == 400, path
        assert "絶対パス" in res.json()["detail"]
    assert roots_in_file(data_dir) == []


def test_duplicate_is_rejected(client, data_dir, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    assert add(client, str(folder), "First").status_code == 201
    # 大文字小文字・末尾の \ が違っても同じフォルダとみなす
    for same in (str(folder), str(folder).upper(), str(folder) + "\\"):
        res = add(client, same, "Second")
        assert res.status_code == 409, same
        assert "First" in res.json()["detail"]
    assert len(roots_in_file(data_dir)) == 1


def test_missing_folder_is_added_with_warning(client, data_dir, tmp_path):
    res = add(client, str(tmp_path / "not_here"), "External")
    assert res.status_code == 201
    assert "見つかりません" in res.json()["warning"]
    assert [r["label"] for r in roots_in_file(data_dir)] == ["External"]


def test_toggle_enabled(client, data_dir, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    rid = add(client, str(folder)).json()["root"]["id"]

    res = client.patch(f"/api/roots/{rid}", json={"enabled": False})
    assert res.status_code == 200
    assert res.json()["root"]["enabled"] is False
    assert roots_in_file(data_dir)[0]["enabled"] is False

    client.patch(f"/api/roots/{rid}", json={"enabled": True})
    assert roots_in_file(data_dir)[0]["enabled"] is True


def test_toggle_keeps_other_fields(client, data_dir, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    before = add(client, str(folder), "Pack").json()["root"]
    client.patch(f"/api/roots/{before['id']}", json={"enabled": False})
    assert roots_in_file(data_dir)[0] == {**before, "enabled": False}


def test_toggle_unknown_id_is_404(client):
    assert client.patch("/api/roots/r_none", json={"enabled": False}).status_code == 404


def test_toggle_requires_bool(client, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    rid = add(client, str(folder)).json()["root"]["id"]
    assert client.patch(f"/api/roots/{rid}", json={}).status_code == 422


def test_delete(client, data_dir, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ra = add(client, str(a), "A").json()["root"]
    add(client, str(b), "B")

    res = client.delete(f"/api/roots/{ra['id']}")
    assert res.status_code == 204
    assert [r["label"] for r in roots_in_file(data_dir)] == ["B"]
    assert a.is_dir()  # 登録を外すだけで、フォルダ自体には触らない


def test_delete_unknown_id_is_404(client):
    assert client.delete("/api/roots/r_none").status_code == 404


def test_can_add_again_after_delete(client, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    rid = add(client, str(folder)).json()["root"]["id"]
    client.delete(f"/api/roots/{rid}")
    assert add(client, str(folder)).status_code == 201


def test_other_config_values_are_kept(client, data_dir, tmp_path):
    folder = tmp_path / "Sounds"
    folder.mkdir()
    add(client, str(folder))
    config = storage.load_json(data_dir / "config.json")
    assert {k: v for k, v in config.items() if k != "roots"} == {
        k: v for k, v in storage.DEFAULT_CONFIG.items() if k != "roots"
    }
