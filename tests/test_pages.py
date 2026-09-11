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
