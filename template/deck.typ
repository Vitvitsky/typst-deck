// Заглушка корпоративного шаблона. Реализует контракт из спеки (§4):
// шестнадцать функций, каждая функция слайда — ровно одна страница, текстовые
// параметры приходят как content (обёрнуты сервисом в маркер поля),
// data/labels/series — сырые массивы. Пакеты @preview не используются.

#let accent = rgb("#3b6ea5")
#let ink = rgb("#1f2a37")
#let muted = rgb("#6b7280")
#let negative = rgb("#c0392b") // падение на графиках: читается иначе, чем рост
#let palette = (accent, rgb("#e07a1f"), rgb("#2f9e6f"), rgb("#8e44ad"))

// Страница слайда: тело обрезается по границам, переполнение не создаёт
// вторую страницу (контракт «одна функция — одна страница»).
#let slide(body, ..args) = page(
  ..args.named(),
  box(width: 100%, height: 100%, clip: true, body),
)

#let deck(title: none, body) = {
  set document(title: if title == none { "Презентация" } else { title })
  set page(width: 16cm, height: 9cm, margin: (x: 1.1cm, top: 1cm, bottom: 0.8cm))
  set text(font: "DejaVu Sans", size: 11pt, fill: ink, lang: "ru")
  set list(marker: text(fill: accent)[•], spacing: 0.35em)
  body
}

// Кегль по месту: первый из размеров, при котором содержимое влезает в высоту h,
// иначе последний. Пределы из template.json приблизительны — широкие знаки всё
// равно вылезают, и это последний рубеж перед обрезкой.
#let fit-text(h, sizes, body, ..args) = layout(sz => context {
  let pick = sizes.last()
  for s in sizes {
    if measure(width: sz.width, text(size: s, ..args, body)).height <= h {
      pick = s
      break
    }
  }
  text(size: pick, ..args, body)
})

// Заголовок слайда: если в 19pt не помещается в полторы строки, уменьшается до 15pt.
#let heading-block(title) = {
  block(width: 100%, inset: (bottom: 5pt), stroke: (bottom: 1.2pt + accent))[
    #if title == none { v(19pt) } else { fit-text(19pt * 1.5, (19pt, 15pt), title, weight: "bold") }
  ]
  v(0.3cm)
}

// Общая зона тела: страницу целиком уже обрезает slide(), здесь — только ширина
// и клип по ширине. Высоту не задаём: box(height: 1fr) в Typst недопустим.
#let body-area(content) = block(width: 100%, clip: true, content)

#let slide-title(title: none, subtitle: none, author: none, department: none) = slide(
  background: place(top, rect(width: 100%, height: 1.1cm, fill: accent)),
)[
  #v(1fr)
  #if title != none { fit-text(2.4cm, (28pt, 22pt, 17pt, 14pt), title, weight: "bold") }
  #v(0.35cm)
  #if subtitle != none { fit-text(1.1cm, (14pt, 12pt, 10pt), subtitle, fill: muted) }
  #v(1.4fr)
  // автор и департамент — отдельные блоки контракта, прижаты к низу слайда;
  // порядок подписи: сначала человек, потом подразделение
  #if author != none { text(size: 10pt, fill: muted, author); linebreak() }
  #if department != none { text(size: 10pt, fill: muted, department) }
]

#let slide-section(title: none, subtitle: none) = slide(fill: accent)[
  #set text(fill: white)
  #v(1fr)
  #if title != none { fit-text(2.4cm, (26pt, 20pt, 16pt, 14pt), title, weight: "bold") }
  #if subtitle != none { v(0.3cm); fit-text(1.0cm, (13pt, 11pt), subtitle) }
  #v(1fr)
]

#let slide-agenda(title: none, items: ()) = slide[
  #heading-block(title)
  #body-area(enum(spacing: 0.45em, ..items))
]

#let slide-text(title: none, bullets: none) = slide[
  #heading-block(title)
  #body-area[#if bullets != none { bullets }]
]

#let slide-image(title: none, bullets: none, image: none, image-size: "medium", caption: none) = slide[
  #heading-block(title)
  #let img-w = (small: 30%, medium: 42%, large: 55%).at(image-size)
  #grid(
    columns: (1fr, img-w), column-gutter: 0.6cm,
    [#if bullets != none { bullets }],
    [
      // картинка приходит с width/height 100% и fit: contain — контейнер задаём здесь
      #box(width: 100%, height: 4.4cm, image)
      #if caption != none { v(2pt); text(size: 8pt, fill: muted, caption) }
    ],
  )
]

#let slide-columns(title: none, blocks: ()) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: blocks.map(_ => 1fr), column-gutter: 0.6cm,
    ..blocks.map(b => [
      #if b.heading != none { text(weight: "bold", b.heading); v(0.2cm) }
      #text(size: 9.5pt, b.text)
    ]),
  ))
]

#let slide-comparison(title: none, left: (:), right: (:)) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: (1fr, 1fr), column-gutter: 0.7cm,
    ..(left, right).map(side => [
      #if side.heading != none { text(weight: "bold", fill: accent, side.heading); v(0.2cm) }
      // bullets приходит массивом маркеров (не готовым list()) — оборачиваем сами
      #if side.bullets != none { text(size: 9.5pt, list(..side.bullets)) }
    ]),
  ))
]

#let slide-quote(text: none, author: none) = slide[
  #v(1fr)
  #if text != none { fit-text(3.2cm, (20pt, 17pt, 14pt), text, weight: "bold") }
  #if author != none { v(0.4cm); std.text(size: 10pt, fill: muted, author) }
  #v(1fr)
]

// Столбчатая диаграмма со знаком: общая нулевая линия, подписи категорий —
// единой строкой под всей зоной графика. Одна серия — столбец красится по
// знаку (рост accent, падение negative), подпись значения с внешней стороны
// столбца. Несколько серий — в каждой категории ряды встают группой друг
// рядом с другом с небольшим зазором, цвет ряда — из общей палитры; подписи
// значений на столбцах убраны (их называет легенда в slide-chart), иначе
// подписи соседних столбцов налезали бы друг на друга.
// height — зона столбцов на оба знака; параметр, а не константа, потому что
// slide-chart уменьшает её, когда сверху уже стоит легенда (иначе подписи
// категорий под графиком обрезаются клипом body-area).
#let bars(labels, series, unit, height: 3.4cm) = {
  let all = series.map(s => s.values).flatten()
  let hi = calc.max(0, ..all)
  let lo = calc.min(0, ..all)
  let span = calc.max(hi - lo, 0.000001) // все значения нулевые — делить не на что
  let full = height                      // высота зоны столбцов на оба знака
  let lab = 0.42cm                       // полоса под подпись значения над/под столбцом
  let up = full * hi / span
  let down = full * (-lo) / span
  let cols = labels.map(_ => 1fr)
  let n = series.len()
  let gutter = 1.5pt                     // зазор между столбцами одной группы
  let w = (100% - gutter * (n - 1)) / n
  let value-label(v) = text(size: 8pt, str(v) + if unit != none { " " + unit } else { "" })
  let slot(i) = box(width: 100%, height: lab + up + down + lab)[
    #if n == 1 {
      let v = series.at(0).values.at(i)
      let h = calc.max(full * calc.abs(v) / span, 1pt)
      if v >= 0 {
        place(bottom + center, dy: -lab - down,
          rect(width: 100%, height: h, fill: accent, radius: (top: 2pt)))
        place(bottom + center, dy: -lab - down - h - 3pt, value-label(v))
      } else {
        place(top + center, dy: lab + up,
          rect(width: 100%, height: h, fill: negative, radius: (bottom: 2pt)))
        place(top + center, dy: lab + up + h + 3pt, value-label(v))
      }
    } else {
      for (k, s) in series.enumerate() {
        let v = s.values.at(i)
        let h = calc.max(full * calc.abs(v) / span, 1pt)
        let color = palette.at(calc.rem(k, palette.len()))
        let dx = k * (w + gutter)
        if v >= 0 {
          place(bottom + left, dx: dx, dy: -lab - down,
            rect(width: w, height: h, fill: color, radius: (top: 2pt)))
        } else {
          place(top + left, dx: dx, dy: lab + up,
            rect(width: w, height: h, fill: color, radius: (bottom: 2pt)))
        }
      }
    }
  ]
  box(width: 100%)[
    #grid(columns: cols, column-gutter: 0.35cm, ..labels.enumerate().map(((i, _)) => slot(i)))
    #place(top + left, dy: lab + up,
      line(start: (0pt, 0pt), end: (100%, 0pt), stroke: 0.5pt + muted))
  ]
  grid(columns: cols, column-gutter: 0.35cm, align: center,
    ..labels.map(l => text(size: 8pt, fill: muted, l)))
}

// Линейный график: одна или несколько серий, точки соединены кривой,
// цвет ряда — из общей палитры. height — как в bars(): убавляется слайдом,
// когда сверху рисуется легенда.
#let lines(labels, series, height: 3.4cm) = {
  let all = series.map(s => s.values).flatten()
  let hi = calc.max(1, ..all)
  let lo = calc.min(0, ..all)
  layout(sz => {
    let w = sz.width
    let h = height
    let pad = 1cm // чтобы крайние точки и подписи не обрезались
    let n = labels.len()
    let xstep = (w - 2 * pad) / calc.max(n - 1, 1)
    let y(v) = h - h * ((v - lo) / (hi - lo))
    box(width: w, height: h + 0.6cm)[
      #place(top + left, line(start: (0pt, y(0)), end: (w, y(0)), stroke: 0.5pt + muted))
      #for (i, s) in series.enumerate() {
        let color = palette.at(calc.rem(i, palette.len()))
        let pts = s.values.enumerate().map(((j, v)) => (pad + xstep * j, y(v)))
        place(top + left, curve(
          stroke: 1.5pt + color,
          curve.move(pts.at(0)),
          ..pts.slice(1).map(p => curve.line(p)),
        ))
        for p in pts {
          place(top + left, dx: p.at(0) - 2pt, dy: p.at(1) - 2pt, circle(radius: 2pt, fill: color))
        }
      }
      #for (j, l) in labels.enumerate() {
        place(top + left, dx: pad + xstep * j - 1cm, dy: h + 3pt,
          box(width: 2cm, align(center, text(size: 7pt, fill: muted, l))))
      }
    ]
  })
}

#let slide-chart(title: none, kind: "line", labels: (), series: (), unit: none, bullets: none) = slide[
  #heading-block(title)
  // столбцы: знак у одной серии красится, у нескольких — палитра по рядам;
  // линии: как раньше, легенда сверху. Легенда занимает часть высоты над
  // графиком — зону графика убавляем ровно настолько, чтобы подписи
  // категорий под ним не съехали под клип body-area (замерено рендером).
  #let show-legend = kind == "line" or series.len() > 1
  #let chart-h = if show-legend { 2.9cm } else { 3.4cm }
  #let chart = if kind == "bar" { bars(labels, series, unit, height: chart-h) } else { lines(labels, series, height: chart-h) }
  #let legend = if show-legend {
    series.enumerate().map(((i, s)) => box(inset: (right: 10pt))[
      #box(width: 8pt, height: 8pt, fill: palette.at(calc.rem(i, palette.len())))
      #h(3pt) #text(size: 8pt, s.name)
      #if unit != none { text(size: 8pt, fill: muted, ", " + unit) }
    ]).join()
  }
  #if legend != none { legend; v(0.15cm) }
  #if bullets == none { chart } else {
    grid(columns: (2fr, 1fr), column-gutter: 0.6cm, chart, text(size: 9.5pt, bullets))
  }
]

// Высота тела страницы — как в deck(): страница минус поля. Нужна
// slide-dual-chart, чтобы посчитать высоту графика от места, которое
// реально остаётся под шапкой, а не подбирать число на глаз для каждой ветки.
#let body-h = 9cm - 1cm - 0.8cm

// Два графика рядом: та же пара bars/lines, что и в slide-chart, но без
// общих bullets — у каждой стороны легенда (по тому же правилу, что в
// slide-chart: линии — всегда, столбцы — от двух серий, только компактнее —
// колонка вдвое уже) и подпись под графиком.
//
// Высоту графика каждая сторона считает сама, а не берёт готовое число:
// у столбцов после самого графика есть ещё строка подписей категорий,
// у линий — нет, а между соседними блоками (легенда/график/подпись) Typst
// сам добавляет отступы, которые на глаз не предсказать. Поэтому вместо
// констант — измерение: собираем ту же стопку (легенда, если есть, график
// пробной высоты, подпись, если есть) целиком и меряем её реальную высоту;
// разница между этим измерением и пробной высотой графика — это «всё
// остальное» (легенда, отступы, строка категорий), и высота графика — это
// оставшееся место минус «всё остальное». Раньше числа 2.6cm/3cm были
// подобраны на глаз и либо обрезали подпись (столбцы с легендой — обе серии
// на «Центр/Север/Юг»), либо занижали график там, где место было (одна серия
// без легенды) — правило §7 требует высоту от содержимого, а не с потолка.
#let slide-dual-chart(title: none, left: (:), right: (:)) = slide[
  #heading-block(title)
  #layout(full-sz => context {
    // высоту шапки меряем, а не берём с потолка: заголовок — от одной до
    // двух строк (fit-text), и от этого зависит, сколько места остаётся ниже
    let budget = body-h - measure(width: full-sz.width, heading-block(title)).height
    body-area(grid(
      columns: (1fr, 1fr), column-gutter: 0.7cm,
      ..(left, right).map(side => layout(sz => context {
        let show-legend = side.kind == "line" or side.series.len() > 1
        let legend = if show-legend {
          side.series.enumerate().map(((i, s)) => box(inset: (right: 6pt))[
            #box(width: 6pt, height: 6pt, fill: palette.at(calc.rem(i, palette.len())))
            #h(2pt) #text(size: 6.5pt, s.name)
          ]).join()
        }
        let caption = if side.caption != none { align(center, text(size: 8pt, fill: muted, side.caption)) }
        let probe-h = 2cm // с любой пробной высотой — линейно, разница даёт «остальное»
        let probe-chart = if side.kind == "bar" {
          bars(side.labels, side.series, side.unit, height: probe-h)
        } else {
          lines(side.labels, side.series, height: probe-h)
        }
        let stack = [
          #if legend != none { legend; v(0.1cm) }
          #probe-chart
          #if caption != none { v(2pt); caption }
        ]
        let rest = measure(width: sz.width, stack).height - probe-h
        // измеренная «стопка» вне страницы выходит короче той же стопки внутри
        // настоящей колонки грида — на реальном рендере разница стабильно
        // около 13.2pt (замерено на обеих сторонах отдельно); запас берёт это
        // с небольшим избытком, а не тютелька в тютельку, как было в round 2
        let safety = 24pt
        let chart-h = budget - rest - safety
        [
          #if legend != none { legend; v(0.1cm) }
          #if side.kind == "bar" { bars(side.labels, side.series, side.unit, height: chart-h) } else { lines(side.labels, side.series, height: chart-h) }
          #if caption != none { v(2pt); caption }
        ]
      })),
    ))
  })
]

#let slide-metrics(title: none, items: ()) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: items.map(_ => 1fr), column-gutter: 0.5cm, align: center + horizon,
    ..items.map(m => [
      #text(size: 28pt, weight: "bold", m.value)
      #if m.label != none { linebreak(); text(size: 9pt, fill: muted, m.label) }
      #if m.delta != none {
        linebreak()
        text(size: 9pt, fill: if m.trend == "down" { negative } else if m.trend == "up" { accent } else { muted }, m.delta)
      }
    ]),
  ))
]

#let slide-table(title: none, header: (), rows: (), numeric: ()) = slide[
  #heading-block(title)
  #body-area(table(
    columns: header.map(_ => 1fr),
    align: numeric.map(n => if n { right } else { left }),
    stroke: 0.5pt + rgb("#dddddd"),
    fill: (_, y) => if y == 0 { rgb("#eeeeee") } else if calc.even(y) { rgb("#f8f8f8") },
    table.header(..header.map(h => text(size: 9pt, weight: "bold", h))),
    ..rows.flatten().map(c => text(size: 9pt, c)),
  ))
]

#let slide-gallery(title: none, images: ()) = slide[
  #heading-block(title)
  #body-area(grid(
    columns: if images.len() == 4 { (1fr, 1fr) } else { images.map(_ => 1fr) },
    column-gutter: 0.4cm, row-gutter: 0.3cm,
    ..images.map(p => [
      #box(width: 100%, height: if images.len() == 4 { 1.7cm } else { 3.6cm }, p.image)
      #if p.caption != none { v(2pt); text(size: 8pt, fill: muted, p.caption) }
    ]),
  ))
]

#let slide-video(title: none, poster: none, url: none, caption: none) = slide[
  #heading-block(title)
  #body-area[
    #let frame = box(width: 100%, height: 3.6cm, fill: if poster == none { muted.lighten(70%) } else { none })[
      #if poster != none { poster }
      #place(center + horizon, circle(radius: 0.6cm, fill: accent.transparentize(20%))[
        #align(center + horizon, text(fill: white, size: 14pt, "▶"))
      ])
    ]
    #if url == none { frame } else { link(url, frame) }
    #if caption != none { v(2pt); text(size: 8pt, fill: muted, caption) }
  ]
]

#let slide-final(title: none, contact: none) = slide(fill: accent)[
  #set text(fill: white)
  #v(1fr)
  #if title != none { text(size: 28pt, weight: "bold", title) }
  #if contact != none { v(0.4cm); text(size: 12pt, contact) }
  #v(1fr)
]
