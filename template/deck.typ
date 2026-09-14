// Заглушка корпоративного шаблона. Реализует контракт из спеки (§4):
// шестнадцать функций, каждая функция слайда — ровно одна страница, текстовые
// параметры приходят как content (обёрнуты сервисом в маркер поля),
// data/labels/series — сырые массивы. Пакеты @preview не используются.

#let accent = rgb("#3b6ea5")
#let ink = rgb("#1f2a37")
#let muted = rgb("#6b7280")
#let negative = rgb("#c0392b") // падение на графиках: читается иначе, чем рост
#let palette = (accent, rgb("#e07a1f"), rgb("#2f9e6f"), rgb("#8e44ad"))
// Бумага страницы. Объявлена палитрой, а не подразумевается белой: общая часть
// шаблонов красит ею заливки таблицы и заглушки видео (tint ниже), и без неё
// тёмный шаблон снова получил бы светлые серые с потолка.
#let paper = rgb("#ffffff")

// Страница слайда: тело обрезается по границам, переполнение не создаёт
// вторую страницу (контракт «одна функция — одна страница»).
#let slide(body, ..args) = page(
  ..args.named(),
  box(width: 100%, height: 100%, clip: true, body),
)

#let deck(title: none, body) = {
  set document(title: if title == none { "Презентация" } else { title })
  set page(width: 16cm, height: 9cm, margin: (x: 1.1cm, top: 1cm, bottom: 0.8cm), fill: paper)
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

// Высота тела страницы — как в deck(): страница минус поля. Слайдам, чьё
// содержимое может не поместиться при пределах модели (agenda — до 7 пунктов,
// comparison — до 5 тезисов в колонке, metrics — до 4 колонок, dual-chart —
// оба графика), эта константа даёт бюджет высоты для measure(), а не число
// на глаз: без него body-area молча обрезает всё, что не влезло (см. clip:
// true выше) — так однажды уже пропадала третья строка повестки.
#let body-h = 9cm - 1cm - 0.8cm

// Низ зоны содержимого на странице: та же граница, по которой slide() обрезает
// тело. Нужен затем, что бюджет «body-h минус измеренная шапка» систематически
// завышен: measure(heading-block(…)) не учитывает ни v(0.3cm) в конце, ни
// отбивку между блоками — при заголовке в 120 знаков она отдаёт 75.14 пт, тогда
// как шапка занимает 101.54. Разницу в ~26 пт до сих пор гасил fit-safety, но
// там, где запаса нет (высота кадра картинки), она уводила содержимое под обрез.
// here().position().y — то же самое место, по которому считает маркер поля,
// поэтому «сколько осталось» получается точно, а не с поправкой на глаз.
#let body-bottom = 9cm - 0.8cm

// Запас между бюджетом и measure(): content, измеренный сам по себе, внутри
// настоящей колонки/грида выходит на несколько пунктов выше, чем показал
// measure() — тот же зазор, что slide-dual-chart уже приходилось учитывать
// отдельно (см. его safety ниже, тоже 24pt, замерено там независимо). Без
// запаса «влезает по measure()» иногда на деле обрезало последнюю строку.
#let fit-safety = 24pt

// Заливка — оттенок чернил на бумаге шаблона, а не зашитый серый. Замер:
// #eeeeee на тёмном шаблоне давал контраст 1.05:1 при минимуме 4.5:1 (заголовок
// таблицы и чётные строки пропадали), а tint(9%) даёт 12.26:1 на тёмном и
// 12.29:1 на светлом, повторяя прежний светлый серый почти в точности.
#let tint(k) = color.mix((ink, k), (paper, 100% - k), space: rgb)

// Готовый список тезисов по месту: тот же приём, что у agenda/comparison —
// кандидаты от крупного к мелкому, берём первый, что уложился в бюджет, иначе
// последний. Список приходит от сервиса уже собранным (он обёрнут в маркер
// поля и правится по клику), поэтому интервал задаётся set-правилом, а не
// аргументом list().
//
// Ширину колонки передаёт вызывающий, и это не мелочь: layout() внутри ячейки
// грида отдаёт размер объемлющего контейнера, а не ячейки. Список в узкой
// колонке (slide-image, slide-chart) мерился бы по всей полосе тела, подгонка
// считала бы, что всё влезает, и текст всё равно уходил под обрез — замерено:
// image 6×200 давал +182 пт уже после подгонки. Так же, по явно посчитанной
// ширине, меряют slide-comparison и slide-columns.
// Нижние ступени лесенки (5pt и мельче) — не размер для чтения, а последний
// рубеж перед молчаливой обрезкой: на самом потолке модели (шесть тезисов по
// 200 знаков рядом с картинкой) читаемого кегля, при котором текст влезает,
// не существует — нужен примерно 4.9pt. Лучше мелко, но целиком, чем крупно и
// с отрезанной половиной; то, что потолок модели упирается в такие ступени, —
// повод сузить пределы в slots, а не растить зону.
#let fit-bullets(
  w, budget, bullets,
  steps: ((11pt, 0.35em), (10pt, 0.3em), (9pt, 0.25em), (8pt, 0.2em), (7pt, 0.16em),
          (6pt, 0.12em), (5.5pt, 0.1em), (5pt, 0.08em), (4.5pt, 0.07em), (4pt, 0.06em)),
) = context {
  let render(step) = {
    let (size, spacing) = step
    set list(spacing: spacing)
    text(size: size, bullets)
  }
  let pick = steps.last()
  for step in steps {
    // Мерить надо block(width: w), а не measure(width: w, …): именованная
    // ширина не доходит до layout() внутри маркера поля, тот берёт ширину
    // объемлющего контейнера, и список в узкой колонке мерился по всей полосе —
    // подгонка считала, что влезает, а текст уходил под обрез. Настоящий блок
    // заданной ширины такой контейнер и создаёт.
    if measure(block(width: w, render(step))).height + fit-safety <= budget {
      pick = step
      break
    }
  }
  render(pick)
}

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

// Кегль и интерлиньяж списка, при которых до семи пунктов (предел модели)
// укладываются в реально оставшуюся высоту тела — тем же приёмом, что и у
// slide-dual-chart: измеряем кандидатов от крупного к мелкому и берём первый,
// который не превышает бюджет; последний (самый убористый) — если не влез и он.
#let slide-agenda(title: none, items: ()) = slide[
  #heading-block(title)
  #layout(full-sz => context {
    let budget = body-h - measure(width: full-sz.width, heading-block(title)).height
    let steps = ((11pt, 0.45em), (10pt, 0.38em), (9pt, 0.3em), (8pt, 0.22em))
    let render(step) = {
      let (size, spacing) = step
      text(size: size, enum(spacing: spacing, ..items))
    }
    let pick = steps.last()
    for step in steps {
      if measure(width: full-sz.width, render(step)).height + fit-safety <= budget {
        pick = step
        break
      }
    }
    body-area(render(pick))
  })
]

// Единственный тяжёлый по телу тип, у которого подгонки не было вовсе: шесть
// тезисов по 200 знаков (предел модели) показывали три, остальное съедал
// clip: true молча. Теперь — тем же fit-bullets, что и у остальных.
#let slide-text(title: none, bullets: none) = slide[
  #heading-block(title)
  #layout(full-sz => context {
    let budget = body-bottom - here().position().y
    body-area[#if bullets != none { fit-bullets(full-sz.width, budget, bullets) }]
  })
]

#let slide-image(title: none, bullets: none, image: none, image-size: "medium", caption: none) = slide[
  #heading-block(title)
  #layout(full-sz => context {
    let budget = body-bottom - here().position().y
    // Запасной вид без картинки: модель её требует, но render.py всё ещё
    // печатает image: none, когда файла ассета нет. Сетка резервировала бы
    // 30–55 % ширины под пустой бокс и ставила подпись рядом с ничем — вместо
    // этого тезисы растекаются на всю полосу, как было до смены набора типов.
    if image == none {
      body-area[
        #if bullets != none { fit-bullets(full-sz.width, budget, bullets) }
        #if caption != none { v(2pt); text(size: 8pt, fill: muted, caption) }
      ]
    } else {
      let img-frac = (small: 0.30, medium: 0.42, large: 0.55).at(image-size)
      let gap = 0.6cm
      // ширина колонки тезисов: полоса тела минус картинка и зазор
      let text-w = full-sz.width - img-frac * full-sz.width - gap
      body-area(grid(
        columns: (1fr, img-frac * 100%), column-gutter: gap,
        [#if bullets != none { fit-bullets(text-w, budget, bullets) }],
        // Высота кадра — не константа и не измерение. Прежние 4.4 см не знали
        // про высоту шапки: при заголовке в 120 знаков тело начинается только
        // на y = 129.89, и кадр с подписью кончался на 309.72 при границе
        // 232.44. Померить подпись заранее тоже нельзя — measure не удерживает
        // ширину внутри маркера поля (см. оговорку у fit-bullets), и подпись
        // считалась двумя строками вместо трёх. Поэтому раскладку делает сам
        // grid: колонка ровно в оставшуюся высоту, подпись занимает своё
        // (auto), кадр — всё остальное (1fr). Ни одно число не берётся на глаз.
        block(height: budget, grid(
          rows: (1fr, auto), row-gutter: 2pt,
          // картинка приходит с width/height 100% и fit: contain — контейнер задаём здесь
          box(width: 100%, height: 100%, image),
          if caption != none { text(size: 8pt, fill: muted, caption) } else { [] },
        )),
      ))
    }
  })
]

// Кегль общий на все колонки и подбирается по самой длинной: разные размеры
// шрифта в соседних блоках читались бы как ошибка вёрстки. Без подбора слайд
// на потолке модели (3 блока по 300 знаков) терял последние строки всех трёх.
#let slide-columns(title: none, blocks: ()) = slide[
  #heading-block(title)
  #layout(full-sz => context {
    let budget = body-bottom - here().position().y
    let gap = 0.6cm
    let w = (full-sz.width - gap * (blocks.len() - 1)) / calc.max(blocks.len(), 1)
    let block-body(b, step) = {
      let (hs, ts) = step
      [
        #if b.heading != none { text(size: hs, weight: "bold", b.heading); v(0.2cm) }
        #text(size: ts, b.text)
      ]
    }
    let steps = ((11pt, 9.5pt), (10pt, 8.5pt), (9pt, 7.5pt), (8pt, 6.5pt), (7pt, 6pt), (6pt, 5.5pt))
    let pick = steps.last()
    for step in steps {
      // block(width: w), а не measure(width: w, …) — см. оговорку у fit-bullets
      let tallest = calc.max(0pt, ..blocks.map(b => measure(block(width: w, block-body(b, step))).height))
      if tallest + fit-safety <= budget {
        pick = step
        break
      }
    }
    body-area(grid(
      columns: blocks.map(_ => 1fr), column-gutter: gap,
      ..blocks.map(b => block-body(b, pick)),
    ))
  })
]

// Обе колонки на одном кегле, иначе разные объёмы тезисов дали бы разные
// размеры шрифта слева и справа — измеряем по более длинной стороне.
#let slide-comparison(title: none, left: (:), right: (:)) = slide[
  #heading-block(title)
  #layout(full-sz => context {
    let budget = body-h - measure(width: full-sz.width, heading-block(title)).height
    let gap = 0.7cm
    let w = (full-sz.width - gap) / 2
    let side-block(side, step) = {
      let (size, spacing) = step
      [
        #if side.heading != none { text(weight: "bold", fill: accent, side.heading); v(0.2cm) }
        // bullets приходит массивом маркеров (не готовым list()) — оборачиваем сами
        #if side.bullets != none { text(size: size, list(spacing: spacing, ..side.bullets)) }
      ]
    }
    let steps = ((9.5pt, 0.35em), (8.5pt, 0.28em), (7.5pt, 0.22em), (6.5pt, 0.16em))
    let pick = steps.last()
    for step in steps {
      if calc.max(
        measure(width: w, side-block(left, step)).height,
        measure(width: w, side-block(right, step)).height,
      ) + fit-safety <= budget {
        pick = step
        break
      }
    }
    body-area(grid(
      columns: (1fr, 1fr), column-gutter: gap,
      side-block(left, pick), side-block(right, pick),
    ))
  })
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
  // Колонка выводов — та же подгонка, что у slide-text, но в узкой колонке и от
  // прежнего кегля 9.5pt вниз: без неё четыре вывода по 200 знаков (предел
  // модели) показывали примерно один. Бюджет — тело минус шапка и легенда.
  #if bullets == none { chart } else {
    layout(full-sz => context {
      // здесь мы уже стоим ниже шапки и легенды, поэтому вычитать их отдельно
      // не нужно: here() и так показывает, сколько осталось до низа полосы
      let budget = body-bottom - here().position().y
      let gap = 0.6cm
      // колонка выводов — треть полосы за вычетом зазора (грид 2fr : 1fr)
      let text-w = (full-sz.width - gap) / 3
      grid(
        columns: (2fr, 1fr), column-gutter: gap, chart,
        fit-bullets(
          text-w, budget, bullets,
          steps: ((9.5pt, 0.3em), (8.5pt, 0.25em), (7.5pt, 0.2em), (6.5pt, 0.16em),
                  (6pt, 0.12em), (5.5pt, 0.1em), (5pt, 0.08em), (4.5pt, 0.07em), (4pt, 0.06em)),
        ),
      )
    })
  }
]

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
        // единицу называет легенда — как в slide-chart. Иначе unit, объявленный
        // спекой полем стороны, не показывался нигде: bars() печатает его только
        // у единственной серии, а у линий подписей значений нет вовсе.
        let legend = if show-legend {
          side.series.enumerate().map(((i, s)) => box(inset: (right: 6pt))[
            #box(width: 6pt, height: 6pt, fill: palette.at(calc.rem(i, palette.len())))
            #h(2pt) #text(size: 6.5pt, s.name)
            #if side.unit != none { text(size: 6.5pt, fill: muted, ", " + side.unit) }
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

// Колонки прижаты к верху (не к середине — «horizon» давал лесенку сам по
// себе), а значение, подпись и дельта — три строки грида, а не переводы
// строки внутри одной ячейки: перевод строки делает высоту ячейки зависимой
// от того, перенеслись ли именно её значение или подпись на вторую строку,
// и колонки с разным числом строк съезжают друг относительно друга. Строкой
// грид выравнивает все ячейки одной строки по высоте самой высокой — подписи
// и дельты остаются на одной высоте, сколько бы строк ни занял самый длинный
// value по соседству. Кегль — тем же измерением, что у agenda/comparison: до
// четырёх колонок (предел модели) должны уложиться в бюджет тела, не срезая
// нижнюю дельту.
#let slide-metrics(title: none, items: ()) = slide[
  #heading-block(title)
  #layout(full-sz => context {
    let budget = body-h - measure(width: full-sz.width, heading-block(title)).height
    let gap = 0.5cm
    let cols = items.map(_ => 1fr)
    let value-cell(m, vs) = text(size: vs, weight: "bold", m.value)
    let label-cell(m, ls) = if m.label != none { text(size: ls, fill: muted, m.label) } else { [] }
    let delta-cell(m, ds) = if m.delta != none {
      text(size: ds, fill: if m.trend == "down" { negative } else if m.trend == "up" { accent } else { muted }, m.delta)
    } else { [] }
    let rows(step) = {
      let (vs, ls, ds) = step
      items.map(m => value-cell(m, vs)) + items.map(m => label-cell(m, ls)) + items.map(m => delta-cell(m, ds))
    }
    let build(step) = grid(
      columns: cols, column-gutter: gap, row-gutter: 4pt, align: center + top,
      ..rows(step),
    )
    let steps = ((28pt, 9pt, 9pt), (22pt, 8pt, 8pt), (18pt, 7pt, 7pt), (14pt, 6.5pt, 6.5pt))
    let pick = steps.last()
    for step in steps {
      if measure(width: full-sz.width, build(step)).height + fit-safety <= budget {
        pick = step
        break
      }
    }
    body-area(build(pick))
  })
]

#let slide-table(title: none, header: (), rows: (), numeric: ()) = slide[
  #heading-block(title)
  #body-area(table(
    columns: header.map(_ => 1fr),
    align: numeric.map(n => if n { right } else { left }),
    stroke: 0.5pt + tint(18%),
    fill: (_, y) => if y == 0 { tint(9%) } else if calc.even(y) { tint(4%) },
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
    #let frame = box(width: 100%, height: 3.6cm, fill: if poster == none { tint(12%) } else { none })[
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
