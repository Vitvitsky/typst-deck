#import "/template/deck.typ": *
#import "/fields.typ": field
#show: deck.with(title: "Полная")
#slide-title(title: field("s000001", "title", "Итоги"), subtitle: field("s000001", "subtitle", "Q3 2026"))
#slide-section(title: field("s000002", "title", "Финансы"), subtitle: none)
#slide-image(title: field("s000003", "title", "Рост"), bullets: field("s000003", "bullets", list("Первый", "Второй")), image: field("s000003", "image", image("/assets/a000001.png", width: 100%, height: 100%, fit: "contain")), image-size: "large", caption: field("s000003", "caption", "Рис. 1"))
#slide-bar-chart(title: field("s000004", "title", "Регионы"), data: ((label: "Центр", value: 42.0), (label: "Север", value: 17.5),), unit: "млн", bullets: none)
#slide-chart(title: field("s000005", "title", "Динамика"), labels: ("Q1", "Q2",), series: ((name: "Выручка", values: (1.0, 2.0,)),), unit: none, bullets: field("s000005", "bullets", list("Рост")))
#slide-final(title: field("s000006", "title", "Спасибо"), contact: field("s000006", "contact", "team@corp"))
