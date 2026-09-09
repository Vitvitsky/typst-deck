// Адаптер контракта typst-deck поверх канонического шаблона Lemana Tech.
// Канон (slides_template.typ) не меняется, кроме константы lm-components-dir —
// так предписывает README шаблона. Здесь только семь функций контракта:
// deck, slide-title, slide-section, slide-image, slide-bar-chart, slide-chart, slide-final.
#import "slides_template.typ": *

#let chart-palette = (lm-yellow, lm-dark, lm-turquoise, lm-light-brown)
#let body-height = 250mm     // зона тела при фиксированной зоне заголовка: ровно одна страница
#let title-zone = 50mm       // до двух строк 48pt

#let deck(title: none, body) = {
  set document(title: if title == none { "Презентация" } else { title })
  set text(font: body-font, size: size-body, fill: lm-dark, lang: "ru")
  set list(marker: text(fill: lm-yellow, size: 1.2em)[•], spacing: 0.7em, indent: 0pt, body-indent: 0.5em)
  body
}

#let num = context counter(page).display()
#let or-empty(x) = if x == none { "" } else { x }

// Тело слайда: обрезанный box фиксированной высоты — переполнение не создаёт вторую страницу.
#let body-box(content) = box(width: 100%, height: body-height, clip: true, content)

#let slide-title(title: none, subtitle: none) = title-slide(
  title: or-empty(title), subtitle: or-empty(subtitle), author: "", department: "",
)

#let slide-section(title: none, subtitle: none) = divider-slide-black(
  title: or-empty(title), subtitle: or-empty(subtitle),
)

#let slide-image(title: none, bullets: none, image: none, image-size: "medium", caption: none) = {
  let img-w = (small: 30%, medium: 42%, large: 55%).at(image-size)
  content-slide(title: or-empty(title), slide-number: num, title-size: size-h1-compact, title-height: title-zone, body-box[
    #if image == none {
      if bullets != none { bullets }
    } else {
      grid(
        columns: (1fr, img-w), gutter: 15mm, align: (top, top),
        [#if bullets != none { bullets }],
        [
          // картинка приходит с width/height 100% и fit: contain — контейнер задаём здесь
          #box(width: 100%, height: 200mm, image)
          #if caption != none { v(3mm); text(fill: lm-gray, size: size-caption, style: "italic", caption) }
        ],
      )
    }
  ])
}

// Диаграмма средствами Typst в фирменных цветах (канонический chart-slide ждёт файл графика).
#let bar-chart(data, unit) = {
  let maxv = calc.max(1, ..data.map(d => d.value))
  box(width: 100%, height: 200mm)[
    #grid(
      columns: data.map(_ => 1fr), column-gutter: 10mm, align: bottom + center,
      ..data.map(d => {
        let h = 150mm * d.value / maxv
        stack(
          dir: btt, spacing: 4mm,
          text(size: size-caption, fill: lm-gray, d.label),
          rect(width: 100%, height: calc.max(h, 2mm), fill: lm-yellow),
          text(size: size-caption, weight: "bold", str(d.value) + if unit != none { " " + unit } else { "" }),
        )
      }),
    )
  ]
}

#let line-chart(labels, series, unit) = layout(sz => {
  let all = series.map(s => s.values).flatten()
  let hi = calc.max(1, ..all)
  let lo = calc.min(0, ..all)
  let w = sz.width
  let h = 160mm
  let pad = 20mm
  let n = labels.len()
  let xstep = (w - 2 * pad) / calc.max(n - 1, 1)
  let y(v) = h - h * ((v - lo) / (hi - lo))
  box(width: w, height: h + 22mm)[
    #place(top + left, line(start: (0pt, h), end: (w, h), stroke: 1.5pt + lm-gray))
    #for (i, s) in series.enumerate() {
      let color = chart-palette.at(calc.rem(i, chart-palette.len()))
      let pts = s.values.enumerate().map(((j, v)) => (pad + xstep * j, y(v)))
      place(top + left, curve(stroke: 5pt + color, curve.move(pts.at(0)), ..pts.slice(1).map(p => curve.line(p))))
      for p in pts { place(top + left, dx: p.at(0) - 5pt, dy: p.at(1) - 5pt, circle(radius: 5pt, fill: color)) }
    }
    #for (j, l) in labels.enumerate() {
      place(top + left, dx: pad + xstep * j - 25mm, dy: h + 5mm, box(width: 50mm, align(center, text(size: size-caption, fill: lm-gray, l))))
    }
  ]
})

#let legend(series, unit) = series.enumerate().map(((i, s)) => box(inset: (right: 12mm))[
  #box(width: 9mm, height: 9mm, fill: chart-palette.at(calc.rem(i, chart-palette.len())))
  #h(3mm) #text(size: size-caption, s.name)
  #if unit != none { text(size: size-caption, fill: lm-gray, ", " + unit) }
]).join()

// Раскладка как у канонического chart-slide: 38% выводы, 62% график.
#let chart-layout(chart, bullets) = if bullets == none { chart } else {
  grid(
    columns: (38%, 62%), gutter: 12mm, align: (top, top),
    [
      #text(size: 32pt, weight: "bold", font: title-font)[Выводы]
      #v(4mm)
      #bullets
    ],
    chart,
  )
}

#let slide-bar-chart(title: none, data: (), unit: none, bullets: none) = content-slide(
  title: or-empty(title), slide-number: num, title-size: size-h1-compact, title-height: title-zone,
  body-box[#chart-layout(bar-chart(data, unit), bullets)],
)

#let slide-chart(title: none, labels: (), series: (), unit: none, bullets: none) = content-slide(
  title: or-empty(title), slide-number: num, title-size: size-h1-compact, title-height: title-zone,
  body-box[
    #chart-layout([#legend(series, unit) #v(4mm) #line-chart(labels, series, unit)], bullets)
  ],
)

#let slide-final(title: none, contact: none) = conclusion-slide(
  title: if title == none { "Спасибо за внимание!" } else { title }, contact: or-empty(contact),
)
