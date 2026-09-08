// Маркер редактируемого поля: пишет в метаданные положение и размер содержимого.
// Сервис читает их через `typst eval 'query(<edit>)'` и кладёт кликабельные зоны поверх SVG.
#let field(slide, name, body) = layout(sz => context {
  let pos = here().position()
  let m = measure(width: sz.width, body)
  [#metadata((slide: slide, field: name, page: pos.page,
              x: pos.x.pt(), y: pos.y.pt(), w: m.width.pt(), h: m.height.pt())) <edit>]
  body
})
