# 01 — Gap analysis: ERPNext v16.26 / Frappe v16.25

Перевірено на живому інстансі (erp.huntervua.pp.ua, кастомний образ `erpnext-huntervua:v16.26.2-1`).

## 1. Що дає стандарт і що з цього беремо

| Область | Стандарт v16 | Вердикт |
|---|---|---|
| Товари, штрихкоди | Item, Item Barcode (декілька ШК на товар), Item Group, UOM | ✅ **використовуємо як є** |
| Партії | Batch (expiry_date), Serial and Batch Bundle | ✅ використовуємо; FEFO-рекомендація — своя логіка у POS API |
| Серійні номери | Serial No + Serial and Batch Bundle | ✅ використовуємо; «суворий/легкий» режим — custom field на Item/Item Group + власна валідація |
| Склади | Warehouse (прив'язаний до Company) | ✅ використовуємо; склад каси — поле POS Cash Desk |
| Резервування | Stock Reservation Entry (проти Sales Order) | ✅ використовуємо для «резерву» з POS |
| Переміщення | Stock Entry (Material Transfer), Material Request | ✅ використовуємо для запиту/переміщення між складами |
| Продаж | Sales Invoice: `is_pos`, `update_stock`, `payments` (Sales Invoice Payment), `is_return`/`return_against` | ✅ **обліковий документ продажу і повернення** |
| Рахунок/замовлення | Quotation, Sales Order (без руху складу), advance Payment Entry, Delivery Note | ✅ рахунок = Sales Order; передоплата = Payment Entry (advance); видача = SI з update_stock |
| Оплати | Mode of Payment (+рахунки по компаніях), Payment Entry, мультивалютність, Currency Exchange | ✅ використовуємо; POS-семантика способу оплати — custom fields на Mode of Payment |
| Ціни/знижки | Price List, Item Price, Pricing Rule, Promotional Scheme, Coupon Code | ✅ використовуємо (акції/промокоди) |
| Лояльність | Loyalty Program, Loyalty Point Entry | ✅ джерело балів; POS лише викликає |
| Клієнти | Customer, Customer Group, системний «Роздрібний покупець» | ✅ використовуємо |
| Виміри обліку | Accounting Dimension | ✅ вимір «FOP Profile» на фазі 1 |
| Працівники | Employee (у складі erpnext/setup, HRMS не потрібен) | ✅ + custom fields (штрихкод-хеш, PIN-хеш) |
| Друковані форми | Print Format + print_designer (уже в образі) | ✅ для офісних документів (рахунок, накладна — вже є в `erpnext_ua/ua_fop/print_format`) |
| Журнал змін | Version, Activity Log, Frappe audit | ✅ базовий рівень; POS-події — власний журнал |

## 2. Стандартний POS-стек ERPNext: чому НЕ використовуємо

Стандарт: сторінка `point_of_sale`, POS Profile, POS Invoice (+ Merge Log → консолідація в SI), POS Opening/Closing Entry, POS Settings, Cashier Closing.

| Вимога проєкту | Стандартний POS v16 | Розрив |
|---|---|---|
| Управлінська зміна незалежна від фіскальної, N фіскальних змін на одну касову | POS Opening/Closing Entry: 1 зміна = 1 POS Profile = 1 Company, без розділення упр./фіск. | ❌ несумісна модель зміни |
| Покупюрний перерахунок по валютах | Opening/Closing balance — лише сума по Mode of Payment | ❌ немає номіналів і мультивалютної готівки |
| МультиФОП: маршрутизація, спліт кошика, ліміти | POS Profile жорстко прив'язаний до однієї Company | ❌ немає концепції |
| Фіскалізація ПРРО, idempotency, офлайн-сесія | Відсутня (українська фіскалізація не підтримується) | ❌ немає |
| Барикод-first desktop UI, гарячі клавіші, статус-панель ПРРО/термінала | point_of_sale — тач-орієнтований, картки товарів, без фіскальних статусів | ❌ UI непридатний, кастомізація сторінки ядра = форк |
| Синхронний контроль залишків/серій/партій при сканy | POS Invoice працює з локальним кешем (offline-first), звірка при консолідації | ❌ протилежна філософія: нам потрібен онлайн ERP, офлайн — лише ПРРО |
| Термінал, unknown-стани, звірка | «Оплата» = вибір Mode of Payment, без інтеграції з ECR | ❌ немає |
| Інкасації, витрати з каси, передачі між касами | Немає (Cashier Closing — застарілий рудимент) | ❌ немає |
| Повернення лише зі скану ШК первинного чека, контроль повернутої кількості за способами оплати | Повернення POS Invoice — вручну, без токена і по-модальних лімітів | ❌ частково |

**Висновок:** беремо обліковий фундамент (SI/PE/Stock/Pricing/Loyalty), відмовляємось від
POS-прошарку (POS Invoice, point_of_sale, POS Opening/Closing). Це не «переписування ядра»,
а вибір іншого підмножини стандартних документів + власний тонкий шар оркестрації.

POS Invoice додатково має ризик: у roadmap ERPNext він позначений як кандидат на deprecation
на користь Sales Invoice — прив'язка до нього створила б міграційний борг.

## 3. Розриви, які закриває custom app (module `ua_pos`)

1. **POS Order** — оркестрація продажу (saga), спліт по ФОП, токен чека, стани відновлення.
2. **Управлінська каса** — Operational Shift, Cash Movement ledger, Cash Transfer, Expense, Discrepancy Act, покупюрні перерахунки.
3. **Допуск працівника** — штрихкод/PIN, доступ до каси, передача відповідальності, журнал.
4. **МультиФОП** — Fiscal Routing Rule, політики ФОП, ліміти (розширення існуючого `income_monitor`), dashboard.
5. **Фіскальний шар** — `FiscalAdapter` поверх існуючого `ua_fiscal`, розширення PRRO Shift/Receipt (ідемпотентність, офлайн, компенсації).
6. **Платежі терміналом** — `TerminalAdapter`, POS Payment Attempt, Terminal Transaction, звірка.
7. **Друк** — POS Printer, POS Print Job (черга, повтор, «Копія»), службові чеки, гарантійні талони.
8. **POS UI** — власна сторінка, гарячі клавіші, статуси обладнання.
9. **Журнал POS-подій** — єдиний audit-журнал чутливих дій.
10. **Звіти** — касовий/товарний звіт зміни, контрольні звіти, звірка ERP/ПРРО/термінал/каса.

## 4. Що вже є у власних апках (не дублювати)

| Актив | Де | Стан |
|---|---|---|
| FOP Profile (РНОКПП, групи ЄП, IBAN, ставки) | `erpnext_ua/ua_fop` | ✅ готово, розширити політиками ФОП |
| Ліміти доходу ЄП | `ua_fop/income_monitor.py` + UA Tax Parameters (fixtures 2026) | ✅ база є; додати джерело «фіскальні чеки», пороги, dashboard |
| Податковий календар | `ua_fop/tax_calendar.py` | ✅ не чіпаємо |
| ПРРО-клієнт ДПС (`/cmd`, `/doc`, `/pck`) | `ua_fiscal/fiscal_client.py` | ✅ транспорт+підпис готові |
| XML check01 (продаж, службові, офлайн) | `ua_fiscal/xml_builder.py` | ✅ база є; додати знижки (DISCOUNTSUM), решту, часткове повернення |
| PRRO Cash Register / Shift / Receipt / Settings / UA KEP Key | `ua_fiscal/doctype` | ✅ каркас є; розширення описані в 03 |
| Підпис ДСТУ-4145 (CMS/CAdES) | `prro-signer` (Node, jkurwa) | ✅ готово; перевірити CAdES-T (TSP) для онлайн-режиму |
| Банківський термінал ПБ | `ukrainian_integrations/payments/privat_pos` + `pb-pos-gateway` (Go) | ⚠️ працює для разових оплат з Sales Invoice; для POS бракує: status за operation_id, ідемпотентності на legacy `/purchase`, void |
| Друкформи UA (рахунок, накладна, акт) | `erpnext_ua/ua_fop/print_format` | ✅ використовуються для офісного друку |
| SMS (TurboSMS), дзвінки (VitalPBX), банки (mono/PB API) | `ukrainian_integrations` | ✅ канали для ідентифікації клієнта та IBAN-звірки |
| Журнал інтеграцій | Hunter Integration Log | ✅ для технічного логування адаптерів |

## 5. Відомі обмеження стандарту, які впливають на дизайн

- **Warehouse ↔ Company жорстко пов'язані.** Продаж з SI компанії B не може списати склад компанії A.
  Це головний аргумент моделі «одна Company + ФОП-вимір» на фазі 1 (див. 02 §3 і blocking question №1).
- **Sales Invoice Payment** (child) не має статусів транзакції — тому платіжні спроби/термінал живуть
  у власних DocType, а в SI потрапляє лише підтверджений розподіл оплат.
- **Готівкова валюта:** ERPNext вміє мультивалютні рахунки, але «готівка USD у скриньці» — це наш
  Cash Movement ledger (по валютах), GL на фазі 1 не мультивалютимо. Функція за feature-flag (юридика — див. 08).
- **Pricing Rule** застосовуються на рівні документа — POS має проганяти кошик через сервер
  (`frappe` API) при кожній зміні, а не рахувати знижки в браузері. Це закладено в контракт POS API.
