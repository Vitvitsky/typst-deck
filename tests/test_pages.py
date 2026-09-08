async def test_pages_and_static(client):
    r = await client.get("/")
    assert r.status_code == 200 and "typst-deck" in r.text and 'href="./"' in r.text
    r = await client.get("/d/abc")
    assert r.status_code == 200 and 'href="../"' in r.text
    for name in ("deck.js", "index.js", "api.js", "style.css"):
        assert (await client.get(f"/static/{name}")).status_code == 200
    assert (await client.get("/api/health")).json()["ok"] is True
