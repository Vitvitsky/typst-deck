"""Картинки колоды: выдача редактору."""
import pytest

from typst_deck.model import Deck

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="2"><script>alert(1)</script></svg>'


def new_deck(client) -> str:
    return client.app.state.store.create(Deck(title="T", slides=[{"type": "final"}])).id


async def upload(client, d, name, data, mime) -> str:
    r = await client.post(f"/api/decks/{d}/assets", files={"file": (name, data, mime)})
    return r.json()["asset_id"]


async def test_picture_is_served_with_its_type(client, png_bytes):
    d = new_deck(client)
    aid = await upload(client, d, "p.png", png_bytes, "image/png")
    r = await client.get(f"/api/decks/{d}/assets/{aid}")
    assert r.status_code == 200 and r.content == png_bytes and r.headers["content-type"] == "image/png"
    assert "immutable" in r.headers["cache-control"]


async def test_svg_cannot_run_scripts_on_our_origin(client):
    d = new_deck(client)
    aid = await upload(client, d, "x.svg", SVG, "image/svg+xml")
    r = await client.get(f"/api/decks/{d}/assets/{aid}")
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["content-security-policy"] == "sandbox" and r.headers["x-content-type-options"] == "nosniff"


# «..» буквально не проверить: httpx схлопывает путь до /api/decks/{id} ещё до
# запроса. До маршрута «..» доходит только закодированным — это %2e%2e.
@pytest.mark.parametrize("name", [".tmp", "nope.png", "%2e%2e", "a%2F..%2Fdeck.json"])
async def test_only_real_assets_are_served(client, name):
    d = new_deck(client)
    (client.app.state.store.deck_dir(d) / "assets" / ".tmp").write_bytes(b"x")
    assert (await client.get(f"/api/decks/{d}/assets/{name}")).status_code == 404


async def test_asset_of_a_missing_deck_is_404(client):
    assert (await client.get("/api/decks/nope/assets/a.png")).status_code == 404
