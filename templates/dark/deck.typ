// Тёмный вариант заглушки: тот же контракт, другая палитра. Служит для проверки выбора шаблона.
// Заглушка корпоративного шаблона. Реализует контракт из спеки (§4):
// семь функций, каждая функция слайда — ровно одна страница, текстовые
// параметры приходят как content (обёрнуты сервисом в маркер поля),
// data/labels/series — сырые массивы. Пакеты @preview не используются.

#let accent = rgb("#d97a2b")
#let ink = rgb("#f3f4f6")
#let muted = rgb("#b5bcc7")
#let palette = (accent, rgb("#e07a1f"), rgb("#2f9e6f"), rgb("#8e44ad"))

// Страница слайда: тело обрезается по границам, переполнение не создаёт
// вторую страницу (контракт «одна функция — одна страница»).
#let slide(body, ..args) = page(
  ..args.named(),
  box(width: 100%, height: 100%, clip: true, body),
)

#let deck(title: none, body) = {
  set document(title: if title == none { "Презентация" } else { title })
  set page(width: 16cm, height: 9cm, margin: (x: 1.1cm, top: 1cm, bottom: 0.8cm), fill: rgb("#161b22"))
  set text(font: "DejaVu Sans", size: 11pt, fill: ink, lang: "ru")
  set list(marker: text(fill: accent)[•], spacing: 0.35em)
  body
}

// Заголовок слайда: если в 19pt не помещается в одну строку, уменьшается до 15pt.
#let heading-block(title) = {
  block(width: 100%, inset: (bottom: 5pt), stroke: (bottom: 1.2pt + accent))[
    #if title == none { v(19pt) } else {
      layout(sz => context {
        let big = text(size: 19pt, weight: "bold", title)
        let m = measure(width: sz.width, big)
        if m.height > 19pt * 1.5 { text(size: 15pt, weight: "bold", title) } else { big }
      })
    }
  ]
  v(0.3cm)
}

#let slide-title(title: none, subtitle: none) = slide(
  background: place(top, rect(width: 100%, height: 1.1cm, fill: accent)),
)[
  #v(1fr)
  #if title != none { text(size: 28pt, weight: "bold", title) }
  #v(0.35cm)
  #if subtitle != none { text(size: 14pt, fill: muted, subtitle) }
  #v(1.4fr)
]

#let slide-section(title: none, subtitle: none) = slide(fill: accent)[
  #set text(fill: white)
  #v(1fr)
  #if title != none { text(size: 26pt, weight: "bold", title) }
  #if subtitle != none { v(0.3cm); text(size: 13pt, subtitle) }
  #v(1fr)
]

#let slide-image(title: none, bullets: none, image: none, image-size: "medium", caption: none) = slide[
  #heading-block(title)
  #let img-w = (small: 30%, medium: 42%, large: 55%).at(image-size)
  #if image == none {
    if bullets != none { bullets }
  } else {
    grid(
      columns: (1fr, img-w), column-gutter: 0.6cm,
      [#if bullets != none { bullets }],
      [
        // картинка приходит с width/height 100% и fit: contain — контейнер задаём здесь
        #box(width: 100%, height: 4.4cm, image)
        #if caption != none { v(2pt); text(size: 8pt, fill: muted, caption) }
      ],
    )
  }
]

#let slide-bar-chart(title: none, data: (), unit: none, bullets: none) = slide[
  #heading-block(title)
  #let maxv = calc.max(1, ..data.map(d => d.value))
  #let chart = box(width: 100%, height: 4.6cm)[
    #grid(
      columns: data.map(_ => 1fr), column-gutter: 0.35cm, align: bottom + center,
      ..data.map(d => {
        let h = 3.4cm * d.value / maxv
        stack(
          dir: btt, spacing: 3pt,
          text(size: 8pt, fill: muted, d.label),
          rect(width: 100%, height: calc.max(h, 1pt), fill: accent, radius: (top: 2pt)),
          text(size: 8pt, str(d.value) + if unit != none { " " + unit } else { "" }),
        )
      }),
    )
  ]
  #if bullets == none { chart } else {
    grid(columns: (2fr, 1fr), column-gutter: 0.6cm, chart, text(size: 9.5pt, bullets))
  }
]

#let slide-chart(title: none, labels: (), series: (), unit: none, bullets: none) = slide[
  #heading-block(title)
  #let all = series.map(s => s.values).flatten()
  #let hi = calc.max(1, ..all)
  #let lo = calc.min(0, ..all)
  #let chart = layout(sz => {
    let w = sz.width
    let h = 3.4cm
    let pad = 1cm // чтобы крайние точки и подписи не обрезались
    let n = labels.len()
    let xstep = (w - 2 * pad) / calc.max(n - 1, 1)
    let y(v) = h - h * ((v - lo) / (hi - lo))
    box(width: w, height: h + 0.6cm)[
      #place(top + left, line(start: (0pt, h), end: (w, h), stroke: 0.5pt + muted))
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
  #let legend = series.enumerate().map(((i, s)) => box(inset: (right: 10pt))[
    #box(width: 8pt, height: 8pt, fill: palette.at(calc.rem(i, palette.len())))
    #h(3pt) #text(size: 8pt, s.name)
    #if unit != none { text(size: 8pt, fill: muted, ", " + unit) }
  ]).join()
  #legend
  #v(0.15cm)
  #if bullets == none { chart } else {
    grid(columns: (2fr, 1fr), column-gutter: 0.6cm, chart, text(size: 9.5pt, bullets))
  }
]

#let slide-final(title: none, contact: none) = slide(fill: accent)[
  #set text(fill: white)
  #v(1fr)
  #if title != none { text(size: 28pt, weight: "bold", title) }
  #if contact != none { v(0.4cm); text(size: 12pt, contact) }
  #v(1fr)
]
