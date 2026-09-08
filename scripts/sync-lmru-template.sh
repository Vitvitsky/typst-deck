#!/usr/bin/env bash
# Подтягивает канонический шаблон Lemana Tech в templates/lmru-hr/.
# Источник — клон репозитория lmru--hr-analytics--design-template (по умолчанию рядом, в ~/projects).
# Канон копируется как есть, кроме двух правок:
#   1) lm-components-dir → "components": компоненты лежат рядом с шаблоном, потому что
#      typst-песочница не пускает выше корня сборки (README канона это предусматривает);
#   2) в списки шрифтов первым добавляется "TT Interphases Pro": именно так называется
#      семейство в TTF из references/TTInterphasesPro.zip, а канон просит "…Pro Trl"
#      (имя пробной версии), которого на сервере нет.
# deck.typ (адаптер контракта typst-deck) и template.json скриптом не трогаются.
set -euo pipefail
SRC="${1:-$HOME/projects/lmru--hr-analytics--design-template}"
DST="$(cd "$(dirname "$0")/.." && pwd)/templates/lmru-hr"
[ -f "$SRC/templates/typst/slides_template.typ" ] || { echo "нет канона в $SRC" >&2; exit 1; }
mkdir -p "$DST/components" "$DST/fonts"
sed -e 's|^#let lm-components-dir = ".*"|#let lm-components-dir = "components"  // typst-deck: компоненты рядом с шаблоном|' \
    -e 's|("TT Interphases Pro Trl", |("TT Interphases Pro", "TT Interphases Pro Trl", |g' \
    "$SRC/templates/typst/slides_template.typ" > "$DST/slides_template.typ"
rm -f "$DST/components/"*.svg
cp "$SRC/references/components/"*.svg "$DST/components/"
unzip -q -o -j "$SRC/references/TTInterphasesPro.zip" "TT Interphases Pro/ttf/*" -d "$DST/fonts"
( cd "$SRC" && git rev-parse --short HEAD 2>/dev/null || echo unknown ) > "$DST/CANON_REV"
echo "канон $(cat "$DST/CANON_REV") → $DST"
