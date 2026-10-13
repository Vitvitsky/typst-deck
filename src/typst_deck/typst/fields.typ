// Маркер редактируемого поля: пишет в метаданные положение и размер содержимого.
// Сервис читает их через `typst eval 'query(<edit>)'` и кладёт кликабельные зоны поверх SVG.
// here() — левый край области layout, а текст в ней может стоять по центру или вправо
// (метрики, числа в таблице): x сдвигается на свободное место по выравниванию.
#let field(slide, name, body) = layout(sz => context {
  let pos = here().position()
  let m = measure(width: sz.width, body)
  let ax = align.alignment.x
  let k = if ax == center { 0.5 } else if ax == right or (ax == end and text.dir != rtl) or (ax == start and text.dir == rtl) { 1 } else { 0 }
  let free = sz.width - m.width
  let dx = if k > 0 and free > 0pt and free < 100000pt { free * k } else { 0pt }
  [#metadata((slide: slide, field: name, page: pos.page,
              x: (pos.x + dx).pt(), y: pos.y.pt(), w: m.width.pt(), h: m.height.pt())) <edit>]
  body
})
