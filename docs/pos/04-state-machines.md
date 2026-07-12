# 04 — Діаграми станів

Загальні правила для всіх машин:
- перехід виконується лише сервером, атомарно (`for_update` lock на документ);
- кожен перехід журналюється (state_history JSON + POS Event Log для чутливих);
- повтор запиту з тим самим idem_key повертає поточний стан без побічних ефектів;
- зі станів `*_Recovery` є і автоматичний (scheduler), і ручний (екран «Незавершені операції») вихід.

## 1. POS Order (продаж)

```mermaid
stateDiagram-v2
    [*] --> Building : створення кошика
    Building --> Held : відкласти
    Held --> Building : повернути
    Building --> Validating : "Оплатити" (F9)
    Validating --> Building : помилки валідації (показ причин)
    Validating --> AwaitingPayment : всі перевірки ok\n(зміна, ФОП-роутинг, ліміти,\nзалишки, серії/партії, ціни, клієнт,\nстан ПРРО/термінала/принтера)
    AwaitingPayment --> PaymentInProgress : старт спроб оплати
    PaymentInProgress --> AwaitingPayment : declined/cancelled → інший спосіб
    PaymentInProgress --> PaymentUnknown : термінал timeout/unknown
    PaymentUnknown --> PaymentInProgress : status-запит → confirmed
    PaymentUnknown --> AwaitingPayment : status-запит → declined
    PaymentUnknown --> ManualReview : статус не з'ясовано
    PaymentInProgress --> Paid : всі оплати confirmed
    Paid --> Posting : створення Sales Invoice (по ФОП)
    Posting --> Posted : SI submitted
    Posting --> PostingRecovery : помилка ERP-документа
    PostingRecovery --> Posted : ретрай ok
    PostingRecovery --> Compensating : рішення відмінити →\nvoid/refund оплат
    Posted --> Fiscalizing : режим fiscal
    Posted --> Printing : режим non-fiscal
    Fiscalizing --> Fiscalized : ORDERTAXNUM отримано
    Fiscalizing --> FiscalPending : ДПС недоступний/помилка
    FiscalPending --> Fiscalizing : ретрай (той самий UID)
    FiscalPending --> OfflineFiscal : дозволена офлайн-сесія ПРРО
    OfflineFiscal --> Fiscalized : чек в офлайн-черзі (локальний фіск. номер)
    Fiscalized --> Printing
    Printing --> Completed : чек надруковано (+гарантійний талон)
    Printing --> CompletedPrintError : друк failed — продаж НЕ дублюється,\nчек доступний для повторного друку
    CompletedPrintError --> Completed : повторний друк ok
    Compensating --> Cancelled : компенсації завершені
    Building --> Cancelled : очистити кошик
    ManualReview --> Compensating
    ManualReview --> Paid : менеджер підтвердив оплату (чек термінала)
    Completed --> [*]
```

Ключові інваріанти:
- **повторне «Оплатити»** у будь-якому стані ≠ Building — повертає поточний стан (idem_key);
- **браузер закрився**: стан живе в БД; при вході касир бачить банер «незавершений продаж» і
  продовжує з того самого стану;
- продаж без фіскалізації **не може** бути fallback'ом стану FiscalPending — лише окрема дія
  «перевести в нефіскальний» з дозволом менеджера, журналюється (event `mode_change`);
- Cancel можливий тільки до Paid; після — лише через Compensating (void платежів) або повернення.

## 2. POS Payment Attempt (платіж)

```mermaid
stateDiagram-v2
    [*] --> Created : план оплати зафіксовано
    Created --> CashTaken : kind=cash — введено "отримано", решта
    CashTaken --> Confirmed : підтвердження касира
    Created --> Sent : kind=card — команда sale на gateway
    Sent --> Confirmed : responseCode 0000 (rrn, auth_code)
    Sent --> Declined : відмова
    Sent --> CancelledByUser : скасовано на терміналі
    Sent --> Timeout : немає відповіді
    Timeout --> StatusCheck : запит статусу за operation_id
    StatusCheck --> Confirmed : знайдено успішну
    StatusCheck --> Declined : знайдено відмову
    StatusCheck --> Unknown : не з'ясовано
    Unknown --> StatusCheck : ретрай (scheduler / вручну)
    Unknown --> ManualResolved : менеджер: звірка з чеком термінала
    Created --> PendingConfirmation : kind=iban — очікує підтвердження (банк-імпорт/вручну)
    PendingConfirmation --> Confirmed
    PendingConfirmation --> Failed : не надійшло
    Created --> Confirmed : kind=bonus/gift_cert — списання модулем-власником
    Confirmed --> Reversed : void/refund (компенсація)
    Declined --> [*]
    Failed --> [*]
    Confirmed --> [*]
```

Інваріанти: **заборона нової спроби**, поки існує спроба у Sent/Timeout/StatusCheck/Unknown;
у Unknown **ніколи** не запускається повторний sale (тільки status/verify); operation_id — unique.
Змішана оплата = кілька Attempt одного Order; Order переходить у Paid лише коли Σ Confirmed = до сплати.

## 3. PRRO Receipt (фіскальна операція)

```mermaid
stateDiagram-v2
    [*] --> Draft : XML сформовано (UID згенеровано)
    Draft --> Signing : запит до prro-signer
    Signing --> SignError : ключ недоступний/помилка
    SignError --> Signing : ретрай
    Signing --> Sending : CMS готовий
    Sending --> Delivered : ДПС OK → ORDERTAXNUM,\nквитанція збережена
    Sending --> Rejected : ДПС відхилив (код+текст) — новий чек\nлише новим документом, зв'язаним з цим
    Sending --> TransportError : мережа/timeout
    TransportError --> QueryState : Check/Documents-запит за UID
    QueryState --> Delivered : документ прийнято (без дубля!)
    QueryState --> Sending : не знайдено → повтор того ж підписаного документа
    TransportError --> OfflineQueued : офлайн дозволено → локальний\nфіск. номер (CRC32), PREVDOCHASH-ланцюг
    OfflineQueued --> PackageSent : /pck вивантаження пакета
    PackageSent --> Delivered : пакет прийнято
    PackageSent --> PackageError : розбір помилок по документах
    Delivered --> Compensated : створено сторно/повернення (link)
    Delivered --> [*]
    Rejected --> [*]
```

Інваріанти: UID незмінний для документа — повтор надсилання завжди з тим самим підписаним
пейлоадом; перед повтором обов'язковий QueryState (перевірка результату) — це закриває
«втрату зв'язку після успішної фіскалізації» (сценарій 34); unique (pos_order, kind, Delivered).
Офлайн: ланцюг PREVDOCHASH (SHA-256) підтримується PRRO Offline Session; типи в одній зміні
не змішуються з тестовими.

## 4. POS Operational Shift (управлінська зміна)

```mermaid
stateDiagram-v2
    [*] --> Identification : скан штрихкоду працівника
    Identification --> Denied : немає допуску → журнал failed_access
    Identification --> OpeningCount : допуск ok
    OpeningCount --> Open : покупюрний перерахунок по валютах\nпідтверджено → документ відкриття
    Open --> Open : продажі / повернення / внесення /\nінкасації / витрати / перекази
    Open --> HandoverPending : передача каси
    HandoverPending --> Open : новий відповідальний підтвердив (скан)\n→ запис handover
    Open --> ClosingCount : закриття зміни
    ClosingCount --> DiscrepancyReview : розбіжність ≠ 0 по будь-якій валюті
    ClosingCount --> Closed : розбіжність = 0
    DiscrepancyReview --> Closed : акт розбіжності (коментар касира,\nза потреби manager approval,\nliability entry)
    Open --> ForceClosed : адміністратор (незакрита зміна) —\nокремий permission + журнал
    Closed --> [*]
    ForceClosed --> [*]
```

Інваріанти: одна Open-зміна на касу; всі грошові операції вимагають Open-зміни цієї каси;
закриття блокується, якщо є POS Order у незавершених станах або відкриті PRRO Shift
(пропонується закрити Z-звітами або явно перенести — рішення менеджера, журналюється).

## 5. Повернення

```mermaid
stateDiagram-v2
    [*] --> Scanned : скан lookup-токена чека
    Scanned --> NotFound : токен не знайдено / період недоступний\nдля ролі → підвищений дозвіл
    Scanned --> Loaded : продаж знайдено — показ позицій,\nвже повернутого, оплат, ФОП, фіск. даних
    Loaded --> Selecting : вибір позицій/кількостей (≤ залишку до повернення)
    Selecting --> SerialCheck : суворі серійні товари → скан серійника,\nзвірка з первинним продажем
    SerialCheck --> Selecting
    Selecting --> RefundPlanning : розподіл повернення по способах оплати\n(≤ сплаченого кожним; алгоритм зміш. оплати —\nblocking question №4)
    RefundPlanning --> Validating
    Validating --> RefundInProgress : створення return-SI (is_return),\nсерійники → на склад / визначений статус
    RefundInProgress --> FiscalReturn : первинний продаж фіскальний →\nфіскальне повернення (ORDERRETNUM)
    RefundInProgress --> CashRefund : нефіскальний → нефіскальне повернення
    FiscalReturn --> MoneyOut : чек повернення Delivered
    CashRefund --> MoneyOut
    MoneyOut --> Completed : Movement(refund) / refund на термінал /\nсторно бонусів — друк документа
    Completed --> [*]
```

Правила: фіскальний продаж → тільки фіскальне повернення (і навпаки) — жорстка серверна заборона;
повернення завжди посилається на первинний POS Order/SI; часткові повернення акумулюються
(returned_qty на позиціях); обмін (за бізнес-правилом — лише нефіскальні) = зв'язана пара
«повернення + новий продаж» зі взаємними посиланнями (окремого документа не вводимо).

## 6. Сторнування: розведення операцій

| Ситуація | Операція | Документи |
|---|---|---|
| Кошик не оплачено | скасування кошика | POS Order → Cancelled |
| Оплата карткою пройшла, продаж не завершено | void на терміналі | Attempt → Reversed |
| SI створено помилково, фіскалізації не було | ERP cancel + reversal рухів | SI cancel, Movement reversal |
| Чек фіскалізовано, помилка виявлена одразу | фіскальне сторно (якщо підтримує протокол) або фіскальне повернення | PRRO Receipt kind=storno/return + return-SI |
| Продаж завершено, клієнт повертає | повернення (розділ 5) | повний ланцюг |

Кнопка «Сторно» в UI контекстна: показує лише допустиму для поточного стану операцію.
