import json
from pathlib import Path

import pytest

from app import ai, storage
from tests.test_search import CONDITIONS, client_with, fake_claude, make_index

REPO_SITES = Path(__file__).resolve().parent.parent / "data" / "sites.json"

SITES = [
    {"id": "maou", "name": "魔王魂", "top_url": "https://maou.audio/", "search_url": "https://maou.audio/?s={q}",
     "kinds": ["bgm", "se"],
     "categories": [
         {"id": "game_battle", "name": "ゲーム音楽 > 戦闘曲", "kind": "bgm", "url": "https://maou.audio/category/game/game-battle/"},
         {"id": "se_magic", "name": "効果音 > 魔法", "kind": "se", "url": "https://maou.audio/category/se/se-magic/"},
     ], "note": ""},
    {"id": "selab", "name": "効果音ラボ", "top_url": "https://soundeffect-lab.info/", "search_url": None,
     "kinds": ["se", "ambient"],
     "categories": [{"id": "button", "name": "ボタン・システム音", "kind": "se", "url": "https://soundeffect-lab.info/sound/button/"}],
     "note": "BGMは扱わない"},
]


def links(raw, kind="bgm", sites=SITES):
    return ai.build_site_links(raw, sites, kind)


# ---------- URLの組み立て ----------

def test_category_url_comes_from_sites_json():
    assert links([{"site_id": "maou", "type": "category", "category_id": "game_battle"}]) == [
        {"site_id": "maou", "site_name": "魔王魂", "label": "ゲーム音楽 > 戦闘曲",
         "url": "https://maou.audio/category/game/game-battle/"}]


def test_search_word_is_url_encoded():
    [link] = links([{"site_id": "maou", "type": "search", "q": "ボス 戦闘&loop/#1"}])
    assert link["label"] == "検索：ボス 戦闘&loop/#1"
    # 日本語はUTF-8で、空白・& / # などの記号も含めてすべてエンコードする（URLの別の部分として読まれないように）
    assert link["url"] == "https://maou.audio/?s=%E3%83%9C%E3%82%B9%20%E6%88%A6%E9%97%98%26loop%2F%231"


def test_search_word_spaces_are_tidied():
    [link] = links([{"site_id": "maou", "type": "search", "q": "  ボス　\n戦闘 "}])
    assert link["label"] == "検索：ボス 戦闘"  # 全角空白・改行も1つの半角空白にまとめる
    assert link["url"].endswith("?s=%E3%83%9C%E3%82%B9%20%E6%88%A6%E9%97%98")


def test_order_is_kept_and_at_most_3_per_site():
    raw = [{"site_id": "maou", "type": "search", "q": f"語{i}"} for i in range(5)]
    assert [l["label"] for l in links(raw)] == ["検索：語0", "検索：語1", "検索：語2"]


# ---------- 不正な応答の除外（SPEC 6.4） ----------

@pytest.mark.parametrize("item", [
    {"site_id": "nosuch", "type": "category", "category_id": "game_battle"},  # sites.json にないサイト
    {"site_id": "maou", "type": "category", "category_id": "nosuch"},          # sites.json にないカテゴリ
    {"site_id": "maou", "type": "category"},                                    # カテゴリIDがない
    {"site_id": "maou", "type": "search", "q": "  "},                          # 空の検索語
    {"site_id": "maou", "type": "search"},                                      # 検索語がない
    {"site_id": "maou", "type": "search", "q": 3},                             # 検索語が文字列でない
    {"site_id": "maou", "type": "url", "q": "ボス"},                            # 決められていない type
    {"site_id": "maou", "type": "category", "category_id": "se_magic"},        # BGMの場面にSEのカテゴリ
    {"site_id": "selab", "type": "category", "category_id": "button"},         # BGMを扱わないサイト
    {"site_id": "maou", "url": "https://example.com/"},                        # URLを返してきた
    "maou",
    None,
])
def test_invalid_items_are_dropped(item):
    assert links([item]) == []


def test_search_on_site_without_search_url_is_dropped():
    assert links([{"site_id": "selab", "type": "search", "q": "カード"}], kind="se") == []
    # 同じサイトでもカテゴリなら通る
    assert len(links([{"site_id": "selab", "type": "category", "category_id": "button"}], kind="se")) == 1


def test_duplicates_are_dropped():
    item = {"site_id": "maou", "type": "category", "category_id": "game_battle"}
    assert len(links([item, dict(item)])) == 1


def test_sites_not_a_list_gives_no_links():
    assert links({"site_id": "maou"}) == []
    assert links(None) == []


# ---------- APIを通した動き ----------

def write_sites(data_dir):
    storage.save_json(data_dir / "sites.json", {"version": 1, "sites": SITES})


def test_search_api_returns_built_links(data_dir):
    ids = make_index(data_dir, 1)
    write_sites(data_dir)
    answer = {"conditions": {**CONDITIONS, "kind": "se", "tempo": None, "loop": None}, "local": [{"id": ids[0]}],
              "sites": [{"site_id": "selab", "type": "category", "category_id": "button"},
                        {"site_id": "maou", "type": "search", "q": "カード"},
                        {"site_id": "maou", "type": "category", "category_id": "game_battle"},  # SEの場面にBGM → 捨てる
                        {"site_id": "selab", "type": "search", "q": "カード"}]}                   # 検索なし → 捨てる
    runner = fake_claude(answer)
    res = client_with(data_dir, runner).post("/api/search", json={"query": "カードを引くときの軽い音"})

    assert res.status_code == 200
    assert res.json()["sites"] == [
        {"site_id": "selab", "site_name": "効果音ラボ", "label": "ボタン・システム音", "url": "https://soundeffect-lab.info/sound/button/"},
        {"site_id": "maou", "site_name": "魔王魂", "label": "検索：カード", "url": "https://maou.audio/?s=%E3%82%AB%E3%83%BC%E3%83%89"},
    ]
    # AIにはサイト一覧を渡すが、URLは見せない
    prompt = runner.calls[0]["prompt"]
    assert "selab" in prompt and "button" in prompt
    assert "https://" not in prompt


def test_search_api_without_sites_json(data_dir):
    ids = make_index(data_dir, 1)
    answer = {"conditions": CONDITIONS, "local": [{"id": ids[0]}],
              "sites": [{"site_id": "maou", "type": "search", "q": "ボス"}]}
    res = client_with(data_dir, fake_claude(answer)).post("/api/search", json={"query": "ボス"})
    assert res.status_code == 200
    assert res.json()["sites"] == []


def test_schema_asks_for_sites_without_url():
    items = ai.RESPONSE_SCHEMA["properties"]["sites"]["items"]
    assert "url" not in items["properties"]
    assert "sites" in ai.RESPONSE_SCHEMA["required"]


# ---------- 本物の sites.json の形（SPEC 9.6） ----------

def test_repo_sites_json_is_well_formed():
    data = json.loads(REPO_SITES.read_text(encoding="utf-8"))
    assert data["version"] == 1
    sites = data["sites"]
    assert [s["id"] for s in sites] == ["maou", "soundeffect_lab", "opentracks"]
    for s in sites:
        assert set(s) == {"id", "name", "top_url", "search_url", "kinds", "categories", "note"}
        assert s["top_url"].startswith("https://")
        assert s["search_url"] is None or (s["search_url"].startswith("https://") and s["search_url"].count("{q}") == 1)
        assert s["kinds"] and set(s["kinds"]) <= set(ai.KINDS)
        cat_ids = [c["id"] for c in s["categories"]]
        assert len(cat_ids) == len(set(cat_ids)), f"{s['id']} のカテゴリIDが重複しています"
        for c in s["categories"]:
            assert set(c) == {"id", "name", "kind", "url"}
            assert c["kind"] in s["kinds"]
            assert c["url"].startswith(s["top_url"])
    # BGMの場面・SEの場面どちらにも、案内できるサイトがある
    assert any("bgm" in s["kinds"] for s in sites)
    assert any("se" in s["kinds"] for s in sites)
    assert "bgm" not in next(s for s in sites if s["id"] == "soundeffect_lab")["kinds"]
