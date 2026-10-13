async def test_pages_and_static(client):
    r = await client.get("/")
    assert r.status_code == 200 and "typst-deck" in r.text and 'href="./"' in r.text
    r = await client.get("/d/abc")
    assert r.status_code == 200 and 'href="../"' in r.text
    for name in ("deck.js", "index.js", "api.js", "style.css"):
        assert (await client.get(f"/static/{name}")).status_code == 200
    assert (await client.get("/api/health")).json()["ok"] is True


async def test_index_and_catalog_pages(client):
    r = await client.get("/")
    assert "Новая презентация" in r.text and 'id="sidebar"' in r.text
    r = await client.get("/decks")
    assert 'id="decks"' in r.text and 'id="sidebar"' in r.text
    assert 'id="sidebar"' in (await client.get("/d/x")).text
    assert (await client.get("/api/health")).json()["model"] == "deepseek-chat"


async def test_section_pages(client):
    for path in ("/decks", "/history", "/templates"):
        r = await client.get(path)
        assert r.status_code == 200 and "typst-deck" in r.text, path


async def test_static_and_pages_revalidate(client):
    for path in ("/static/deck.js", "/", "/d/x"):
        r = await client.get(path)
        assert "no-cache" in r.headers.get("cache-control", ""), path


async def test_pptx_buttons_are_wired(client):
    assert 'id="pptx"' in (await client.get("/d/x")).text
    for name in ("deck.js", "decks.js"):
        assert "deck.pptx" in (await client.get(f"/static/{name}")).text, name


async def test_all_slide_types_are_offered(client):
    js = (await client.get("/static/deck.js")).text
    for t in ("agenda", "text", "columns", "comparison", "quote", "dual-chart",
              "metrics", "table", "gallery", "video"):
        assert f'"{t}"' in js or f"{t}:" in js, t


async def test_composite_fields_have_editors_not_raw_json(client):
    js = (await client.get("/static/deck.js")).text
    assert "JSON.parse(control.value)" not in js and "JSON.stringify(v ?? []" not in js
    assert 'from "./editors.js"' in js
    ed = await client.get("/static/editors.js")
    assert ed.status_code == 200
    for name in ("compositeEditor", "tableEditor", "comparisonEditor", "dualChartEditor", "metricsEditor", "blocksEditor"):
        assert f"function {name}" in ed.text, name


async def test_video_player_is_wired(client):
    html = (await client.get("/d/x")).text
    assert 'id="player"' in html and 'id="player-frame"' in html
    js = (await client.get("/static/deck.js")).text
    assert "▶ Смотреть" in js and "embedUrl" in js
    ed = (await client.get("/static/editors.js")).text
    assert "function galleryEditor(slide" in ed and "function videoEditor(slide" in ed
    assert "следующем обновлении" not in ed
