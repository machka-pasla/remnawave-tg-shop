::todo.md::

# ОБЗОР
Данный проект ‐ это Телеграм‐бот, созданный для продажи подписок на использование VPN‐сервиса, приема платежей и управления пользователями в панели Remnawave c помощью API.
Remnwave ‐ это панель управления для организации VPN‐сервиса, управления серверами и пользователями в ядре Xray‐core.
Данный todo.md описывает изменения, которые я хочу внести в этот проект бота.

# Примечание:
Весь код в этом проекте является полностью работающим, на момент до внесения изменений, описанных в этом файле todo.md. То есть код до изменений можно считать эталоном.

# Цели:
- Осуществить расширение функционала проекта с максимальным переиспользованием уже существующего кода и минимальными изменениями.

# Описание желаемого расширения функционала:
1) Защитить реальные Telegram‐ID пользователей.
В Телеграм регистрация возможна только по номеру телефона, который равен паспортным данным пользователя. Я не хочу хранить такую чувствительную информацию пользователей в своем сервисе, поэтому хочу реализовать шифрование Telegram‐ID (tid) в User‐ID (uid), который можно открыто хранить в сервисе и не беспокоиться, что настоящий Telegram‐ID могут украсть в результате взлома.
2) Реализовать дополнительные функции реферальной программы.
На данный момент в боте реализована реферальная программа с бонусными днями для реферера и реферала ‐ ее мы не трогаем и пишем новую логику с нуля. Подробное описание новой логики будет в соответствующей фазе.
3) Добавить слой дополнительной авторизации.
Сейчас присоединиться к боту может любой желающий, если знает название бота. Я хочу реализовать дополнительный слой авторизации в боте уже после команды /start. Но активировать эту дополнительную авторизацию только если в .env активен соответствующий парамент.
Этот слой авторизации должен использовать параметры, которые используются в реферальной программе из пункта 2

# Фаза 0
## Предварительная подготовка:
- Проанализировать все файлы проекта.
- Определить все файлы проекта, в которые необходимо внести изменения для реализации желаемого функционала.
- Определить все переиспользуемые участки кода, функции и переменные.
- Составить файл notes.md, сохранить его в корне проекта, описать в нем затрагиваемые изменениями файлы с обоснованием изменений.

## Подсказки ‐ это ускорители анализа, но нет 100% гарантии, что в подсказках указаны все файлы, в которые нужно внести изменения:
### 1. Заранее подготовленные файлы с уже реализованными изменениями:
- **./bot/utils/ecdc_core.py** ‐ уже реализованное ядро ширования, к нему не нужно обращаться напрямую, для него уже готова обертка.
- **./bot/utils/ecdc_api.py** ‐ обертка и сервис для ядра шифрования. Содержит в себе все необходимые функции и вызовы для зашифровывания tid-to-uid и расшифровывания uid-to-tid
- **./db/models.py** ‐ файл со схемой базы данных. Уже содержит 4 дополнительных таблицы для реализации реферальной программы и дополнительной авторизации.
- **./.env.example** ‐ это файл с переменными окружения. В нем уже прописаны названия всех переменных для нового функционала.

### 2. Карта точек преобразования tid‐to‐uid/uid‐to‐tid:
#### Вход (telegram → бот)
- `bot/app/web/web_server.py:13-55` — webhook-обработчик (`SimpleRequestHandler`) поднимает aiogram `Dispatcher`.
- `bot/app/controllers/dispatcher_controller.py:12-47` — создание `Dispatcher`, регистрация middleware, точка для включения UID-конвертера.
- `bot/routers.py:5-76` — объединение роутеров пользователей/админов.
- Хендлеры, читающие `from_user.id` / `chat.id`:
  - Пользователи: `bot/handlers/user/start.py`, `.../promo_user.py`, `.../referral.py`, `.../subscription/core.py`, `.../subscription/payments.py`, `.../subscription/payment_methods.py`, `.../trial_handler.py`, `.../payment.py`.
  - Админы: `bot/handlers/admin/common.py`, `.../logs_admin.py`, `.../broadcast.py`, `.../sync_admin.py`, `.../promo/*`.
  - Инлайн-режим: `bot/handlers/inline_mode.py`.
- Middleware, читающие `event_from_user.id`: `bot/middlewares/ban_check_middleware.py`, `.../profile_sync.py`, `.../i18n.py`, `.../action_logger_middleware.py`.

#### Выход (бот → telegram)
- Прямые вызовы `Bot.send_*`: `bot/services/notification_service.py`, `bot/services/referral_service.py`, `bot/services/subscription_service.py`, `bot/services/crypto_pay_service.py`, `bot/services/stars_service.py`, `bot/services/tribute_service.py`, `bot/handlers/admin/sync_admin.py`, `bot/middlewares/ban_check_middleware.py`.
- Вызовы через очередь: `bot/utils/__init__.py`, `bot/utils/message_queue.py`.
- Использование `Message.answer/edit_text` и `CallbackQuery.answer`: повсеместно в `bot/handlers/**`.
- Регистрация вебхуков: `bot/main_bot.py:on_startup_configured`.

#### Логи и аудит
- `bot/middlewares/action_logger_middleware.py` — пишет в `message_logs` (`user_id`, `raw_update_preview`).
- Дополнительные `logging.info/error` с TID: см. хендлеры (`start.py`, `promo_user.py`, `subscription/core.py`, `subscription/payment_methods.py`, `admin/sync_admin.py`, `services/referral_service.py`, `services/stars_service.py`, `services/subscription_service.py`).
- DAL: `db/dal/message_log_dal.py`, `db/dal/user_dal.py` — сохраняют/читают `user_id` в формате BigInteger.



## Фаза 1. Защита шифрованием реальных Telegram‐ID пользователей.
### Описание желаемого изменения естественным языком:


Введение
- Переносим систему на работающие внутри UID, превращая входящие TID в UID в единой точке и обратно на выходе. Это снижает утечки идентификаторов и локализует шифрование в одном слое.
- Сохраняем принцип минимальных диффов: добавляем обёртки и адаптеры (middleware, helper, Telegram-адаптер), не трогая бизнес-логику глубже, чем необходимо.
- Новые функции (реферальные скидки, одноразовые инвайты, закрытое комьюнити) встраиваем поверх существующих сервисов, опираясь на DAL и текущие FSM/hander’ы.

## Карта точек
### Вход (telegram → бот)
- `bot/app/web/web_server.py:13-55` — webhook-обработчик (`SimpleRequestHandler`) поднимает aiogram `Dispatcher`.
- `bot/app/controllers/dispatcher_controller.py:12-47` — создание `Dispatcher`, регистрация middleware, точка для включения UID-конвертера.
- `bot/routers.py:5-76` — объединение роутеров пользователей/админов.
- Хендлеры, читающие `from_user.id` / `chat.id`:
  - Пользователи: `bot/handlers/user/start.py`, `.../promo_user.py`, `.../referral.py`, `.../subscription/core.py`, `.../subscription/payments.py`, `.../subscription/payment_methods.py`, `.../trial_handler.py`, `.../payment.py`.
  - Админы: `bot/handlers/admin/common.py`, `.../logs_admin.py`, `.../broadcast.py`, `.../sync_admin.py`, `.../promo/*`.
  - Инлайн-режим: `bot/handlers/inline_mode.py`.
- Middleware, читающие `event_from_user.id`: `bot/middlewares/ban_check_middleware.py`, `.../profile_sync.py`, `.../i18n.py`, `.../action_logger_middleware.py`.

### Выход (бот → telegram)
- Прямые вызовы `Bot.send_*`: `bot/services/notification_service.py`, `bot/services/referral_service.py`, `bot/services/subscription_service.py`, `bot/services/crypto_pay_service.py`, `bot/services/stars_service.py`, `bot/services/tribute_service.py`, `bot/handlers/admin/sync_admin.py`, `bot/middlewares/ban_check_middleware.py`.
- Вызовы через очередь: `bot/utils/__init__.py`, `bot/utils/message_queue.py`.
- Использование `Message.answer/edit_text` и `CallbackQuery.answer`: повсеместно в `bot/handlers/**`.
- Регистрация вебхуков: `bot/main_bot.py:on_startup_configured`.

### Логи и аудит
- `bot/middlewares/action_logger_middleware.py` — пишет в `message_logs` (`user_id`, `raw_update_preview`).
- Дополнительные `logging.info/error` с TID: см. хендлеры (`start.py`, `promo_user.py`, `subscription/core.py`, `subscription/payment_methods.py`, `admin/sync_admin.py`, `services/referral_service.py`, `services/stars_service.py`, `services/subscription_service.py`).
- DAL: `db/dal/message_log_dal.py`, `db/dal/user_dal.py` — сохраняют/читают `user_id` в формате BigInteger.

## Фазы

### Фаза 1 — UID граница и конфигурация
- **Цель:** Ввести единый слой преобразования TID↔UID, настроить env/settings на хранение UID, исключить прямые обращения к TID вне адаптеров.
- **Критерии готовности:** ECDC инициализируется один раз; `data["user_uid"]` / `data["chat_uid"]` доступны; все новые вызовы Telegram используют `dec_utt` только в адаптерах; `ADMIN_IDS`/`LOG_CHAT_ID` в env — UID-строки.
- **Файлы:** `bot/utils/identity.py` (новый), `bot/middlewares/uid_transform.py` (новый), `bot/app/controllers/dispatcher_controller.py`, `bot/main_bot.py`, `config/settings.py`, `.env.example`, `bot/utils/message_queue.py`, `bot/utils/__init__.py`, `bot/services/notification_service.py`.
- **Риски:** неверная инициализация ECDC приведёт к падению бота; забытый `dec_utt` на выходе вызовет ошибки Telegram API; неправильный формат UID в env — неудобные отладочные кейсы.

#### Задачи
- [ ] `bot/utils/identity.py` (новый)
  - **Правки:** создать helper с функциями `ensure_service(settings)`, `tid_to_uid`, `uid_to_tid`, типами `UID=str`, `TelegramIdentity(cid_tid: int, uid: str)`; добавить кеширование сервиса.
  - **Тесты:** модульный (pytest) — `tid_to_uid(dec_utt(enc_ttu(tid))) == tid`; fallback при незапущенном сервисе выбрасывает `RuntimeError`.
  - **Почему так:** централизуем преобразования, чтобы остальные модули не импортировали `ecdc_api` напрямую.

- [ ] `bot/middlewares/uid_transform.py` (новый)
  - **Правки:** middleware на `dp.update.outer_middleware` — при поступлении апдейта извлекает `event_from_user`/`chat`, добавляет в `data`: `user_tid`, `user_uid`, `chat_tid`, `chat_uid`, `identity` объект; заменяет `data["event_from_user"]` на прокси с `id=uid`.
  - **Тесты:** интеграционный — симулировать `Message` апдейт, убедиться, что handler получает `event_from_user.id` == uid и `data["user_tid"]` сохраняется.
  - **Почему так:** минимальное вторжение — дублируем данные вместо переписывания aiogram core.

- [ ] `bot/app/controllers/dispatcher_controller.py`
  - **Правки:** инициализировать ECDC через `ensure_service(settings)`; зарегистрировать `UIDTransformMiddleware` перед `DBSessionMiddleware`; скорректировать сигнатуры.
  - **Тесты:** smoke — загрузка диспетчера без Telegram (unit), проверка порядка middleware.
  - **Почему так:** одна точка старта гарантирует, что все апдейты проходят через наше преобразование.

- [ ] `bot/main_bot.py`
  - **Правки:** до сборки сервисов вызывать `ensure_service(settings_param)`; передавать UID-aware queue manager, добавлять задачу очистки инвайтов (см. фазу 4).
  - **Тесты:** manual — запуск в dev, проверка, что webhook сетап не падает, ECDC не переинициализируется.
  - **Почему так:** `main_bot` уже отвечает за bootstrap; не плодим дополнительных входов.

- [ ] `config/settings.py`
  - **Правки:** заменить `ADMIN_IDS` -> `ADMIN_UIDS` (список str), обновить валидацию; добавить `COMMUNITY_IS_OPEN: bool = True`; `LOG_CHAT_UID: Optional[str]`; и метод `telegram_admin_tids()` (конвертирует через helper).
  - **Тесты:** pydantic — пустые строки → None; неверные UID поднимают ValueError.
  - **Почему так:** настройки остаются источником правды, но UID живут в строках.

- [ ] `.env.example`
  - **Правки:** подчеркнуть, что `ADMIN_UIDS`/`LOG_CHAT_UID` принимают UID-формат; добавить `COMMUNITY_IS_OPEN`; удалить прямые TID-примеры.
  - **Тесты:** н/д (ручная проверка).
  - **Почему так:** разработчики не перепутают формат.

- [ ] `bot/utils/message_queue.py`
  - **Правки:** очередь хранит `chat_uid`, перед отправкой через адаптер переводит в TID (общий helper); метод `_is_group_chat` использовать `user_tid` (по необходимости); добавить поддержку `identity.uid_to_tid`.
  - **Тесты:** unit — мок `Bot.send_message`, убедиться, что реальный вызов получает TID.
  - **Почему так:** одна точка выхода для массовых сообщений.

- [ ] `bot/utils/__init__.py`
  - **Правки:** функции `send_message_by_type`/`send_direct_message` принимать `uid` и вызывать `uid_to_tid`; очищаем прямые обращения к `chat_id` как `uid`.
  - **Тесты:** unit с моками — проверка вызова `queue_manager.send_message` с TID.
  - **Почему так:** адаптер уже скрывает детали, менять бизнес-код минимально.

- [ ] `bot/services/notification_service.py`
  - **Правки:** внутренне работать с UID, при отправке использовать helper; `_format_user_display` обновить сигнатуру (uid -> masked view, tid берём через helper при необходимости).
  - **Тесты:** unit — имитация отправки в лог-чат/админам без Telegram (моки).
  - **Почему так:** концентрируем «админ-коммуникации» в одном сервисе.

### Фаза 2 — Хранилище и DAL на UID
- **Цель:** перевести БД и DAL на UID (string), чтобы ни одна таблица не хранила TID; обновить middleware/handlers, читающие `user_id`.
- **Критерии готовности:** `db.models.*.user_id` => `String(36)` (или аналогичный); все DAL-функции ожидают `uid`; миграция выполнена; логи пишут UID.
- **Файлы:** `db/models.py`, `db/migrator.py`, `db/dal/*.py`, `db/database_setup.py`, `bot/middlewares/action_logger_middleware.py`, `bot/middlewares/profile_sync.py`, `bot/middlewares/i18n.py`, `bot/middlewares/ban_check_middleware.py`, `bot/filters/admin_filter.py`, `bot/handlers/**` (где сохраняется в БД), `bot/services/*` (логика с user_id).
- **Риски:** миграция типов может требовать ALTER COLUMN (можно занять время/lock DB); забытая конвертация ломает foreign keys; старые данные нужно конвертировать (миграция должна выполнить `UPDATE`).

#### Задачи
- [ ] `db/models.py`
  - **Правки:** заменить `BigInteger` на `String(36)` для `User.user_id`, `Subscription.user_id`, `Payment.user_id`, `PromoCode.created_by_admin_id`, `PromoCodeActivation.user_id`, `MessageLog.user_id/target_user_id`, `AdAttribution.user_id`; расширить длину `referral_code` поля (см. фазу 3); добавить модель `ReferralInvite`.
  - **Тесты:** alembic-style (миграция) — проверка, что `Base.metadata.create_all` создаёт колонку string.
  - **Почему так:** один источник схемы — ORM.

- [ ] `db/migrator.py`
  - **Правки:** добавить обработку `ALTER COLUMN TYPE` с кастом `USING` (для PostgreSQL: `ALTER TABLE users ALTER COLUMN user_id TYPE TEXT USING user_id::text` и т.п.); создать таблицу `referral_invites`.
  - **Тесты:** прогон на тестовой БД до/после (integration).
  - **Почему так:** существующий migrator только добавляет колонки; расширяем.

- [ ] `db/dal/user_dal.py` (и остальные DAL)
  - **Правки:** поменять сигнатуры на `user_uid: str`; привести типы; добавить helper `get_by_uid`.
  - **Тесты:** unit с async pg/SQLite — CRUD с UID.
  - **Почему так:** DAL — единственное место SQL.

- [ ] `db/database_setup.py`
  - **Правки:** удостовериться, что миграция вызывается после `create_all`; возможно, добавить лог об изменении типов.
  - **Тесты:** smoke — запуск init_db.
  - **Почему так:** миграция строк запускается автоматически.

- [ ] `bot/middlewares/action_logger_middleware.py`
  - **Правки:** брать `user_uid` из `data`; в лог грузить только UID; `raw_update_preview` почистить от TID (по возможности truncate/replace).
  - **Тесты:** unit — вызов middleware без user_dal, ensure log stored uid.
  - **Почему так:** выполняем требование «никаких TID в логах».

- [ ] `bot/middlewares/profile_sync.py`, `bot/middlewares/i18n.py`, `bot/middlewares/ban_check_middleware.py`, `bot/filters/admin_filter.py`
  - **Правки:** заменить обращения к `event_from_user.id` на `user_uid`; при вызове Telegram (ban message) использовать helper `uid_to_tid`.
  - **Тесты:** unit — мок handler, проверка корректного UID.
  - **Почему так:** middleware — первый слой, должны быть чистыми.

- [ ] `bot/handlers/**` (где сохраняемся в БД)
  - **Правки:** для каждого файла из списка `rg`:
    - присваивать `user_uid = data["user_uid"]` или через helper.
    - при записи в БД передавать UID.
    - убрать f-строки с TID → UID.
  - **Тесты:** сценарные (manual) — `/start`, оплата, промокоды.
  - **Почему так:** минимальные точечные правки; бизнес-логика не ломается.

- [ ] `bot/services/*` (subscription, referral, stars, crypto, tribute)
  - **Правки:** заменить параметры `user_id` на `user_uid`; взаимодействие с Panel API (где нужен tid) — использовать helper `uid_to_tid`.
  - **Тесты:** unit с моками panel_service — проверка корректной передачи tid.
  - **Почему так:** сервисы оперируют доменными UID, только на периметре — tid.

### Фаза 3 — Реферальные скидки и временные инвайты
- **Цель:** добавить скидки за активных рефералов, одноразовые инвайты с TTL, фоновый клинер.
- **Критерии готовности:** таблица `referral_invites` в БД, DAL/сервис для выдачи и погашения, инвайты истекают через 10 минут, скидка применяется при оплате (ceil 100%).
- **Файлы:** `db/models.py` (таблица), `db/dal/referral_invite_dal.py` (новый), `bot/services/referral_service.py`, `bot/handlers/inline_mode.py`, `bot/services/subscription_service.py`, `bot/handlers/user/subscription/payments.py`, `bot/services/promo_code_service.py` (если используется), `bot/app/web/web_server.py` (фоновый клинер регистрация через dispatcher? см. фазу 4).
- **Риски:** неверно определён «активный реферал» → переплаты; инвайты могут не инвалидироваться → злоупотребления; concurrency (двойное использование кода).

#### Задачи
- [ ] `db/models.py` (см. фазу 2)
  - **Правки:** модель `ReferralInvite(id PK, referral_code UNIQUE, referrer_uid FK, status Enum, expires_at timestamptz, used_by_uid nullable, created_at default now)`; Enum можно хранить как `String`.
  - **Тесты:** ORM — `ReferralInvite(status="issued")` сохраняется.
  - **Почему так:** отдельная таблица => аудит + TTL.

- [ ] `db/dal/referral_invite_dal.py` (новый)
  - **Правки:** методы `create_invite(referrer_uid)`, `get_valid_by_code(code, now)`, `mark_used(invite, used_by_uid)`, `expire_old(now)`, `cleanup()`.
  - **Тесты:** unit (async) — проверка одноразовости и TTL.
  - **Почему так:** DAL скрывает SQL.

- [ ] `bot/services/referral_service.py`
  - **Правки:** 
    - обновить `generate_referral_link` → создаёт invite через DAL, генерирует UID-friendly код (например, base32), TTL 10 мин, возвращает ссылку `...?start=ref_<code>`.
    - добавить `compute_discount_percentage(session, referrer_uid, billing_month)` — использует локальные `Subscription` (истина: проверяем `end_date` >= первое число месяца); fallback на `panel_service.get_active_subscription_details` если нет локальной записи.
    - пересчитать `apply_referral_bonuses_for_payment` для UID.
  - **Тесты:** unit — фальшивые подписки → ожидаемый процент, потолок 100%.
  - **Почему так:** логика скидок/инвайтов остаётся внутри одного сервиса.

- [ ] `bot/handlers/inline_mode.py`
  - **Правки:** выдача ссылки через новый сервис (UID); отменить кэширование старых TID; показать TTL в описании.
  - **Тесты:** manual — инлайн-запрос → ссылка.
  - **Почему так:** пользователи получают новые одноразовые ссылки.

- [ ] `bot/handlers/user/subscription/payments.py`
  - **Правки:** перед показом цен вызывать `referral_service.compute_discount...`; пересчитывать `price_rub` и UI; сохранять скидку в скрытые данные (callback) для повторной валидации; ограничить 100%.
  - **Тесты:** manual — пользователь с 3 активными рефералами → 30% скидка.
  - **Почему так:** одно место, где пользователь видит цену.

- [ ] `bot/services/subscription_service.py`
  - **Правки:** добавить применение скидок на этапе выставления счетов (YooKassa, Crypto, Stars) — проверка, что переданный в handler процент не изменился (антифрод); задокументировать источник истины (`subscription_dal.get_active_subscriptions_for_user`).
  - **Тесты:** unit с моками — расчёт суммы, проверка потолка.
  - **Почему так:** фактическое списание должно валидировать входящие данные.

- [ ] Клинер инвайтов (см. фазу 4).

### Фаза 4 — Закрытое сообщество и обслуживание инвайтов
- **Цель:** если `COMMUNITY_IS_OPEN=false`, новые пользователи допускаются только с валидным инвайтом; добавить фоновую задачу очистки инвайтов.
- **Критерии готовности:** `/start` без записи в БД → запрос кода; валидный код создаёт пользователя (UID), помечает invite как used; фон очищает просроченные/использованные инвайты раз в сутки.
- **Файлы:** `bot/handlers/user/start.py`, `bot/states/user_states.py` (добавить FSM состояние), `bot/services/notification_service.py` (логика уведомления об отклонении?), `bot/main_bot.py` (регистрация фоновой задачи), `bot/app/web/web_server.py` (передать session factory клинеру), `bot/utils/date_utils.py` (вспомогательные функции).
- **Риски:** блокировка реальных пользователей при ошибке в invite; гонки при одновременном использовании кода; нужно корректно завершить диалог при отказе.

#### Задачи
- [ ] `bot/states/user_states.py`
  - **Правки:** добавить `class UserStartStates(StatesGroup): waiting_for_invite = State()`.
  - **Тесты:** н/д (FSM конфигурация).
  - **Почему так:** FSM уже используется в других местах.

- [ ] `bot/handlers/user/start.py`
  - **Правки:** 
    - использовать `user_uid`.
    - при `COMMUNITY_IS_OPEN=False` и отсутствии пользователя → отправить запрос ввода кода, установить FSM.
    - обработчик ввода: валидировать ссылку/код (regex), вызвать `referral_invite_dal.get_valid_by_code`, при успехе создать пользователя, привязать `referrer_uid`, сбросить состояние; при провале — отправить ответ и завершить диалог (`state.clear()`).
    - ensure logging/notifications используют UID.
  - **Тесты:** сценарные — новый user без invites (отказ), с валидным invite (успех), повторное использование (отказ).
  - **Почему так:** `/start` — логичное место проверки допуска.

- [ ] `bot/main_bot.py` / `bot/app/web/web_server.py`
  - **Правки:** при запуске создать `asyncio.create_task(invite_cleanup_job(session_factory))`; использовать `asyncio.sleep(24h)`; graceful shutdown (task cancel).
  - **Тесты:** unit — проверка, что функция вызывается; manual — уменьшить интервал для dev.
  - **Почему так:** простая реализация cron в рамках существующего цикла.

- [ ] `bot/utils/date_utils.py`
  - **Правки:** добавить вспомогательные функции `start_of_month(dt)` для проверки активности реферала.
  - **Тесты:** unit — разные даты → верный 1-е число.
  - **Почему так:** переиспользуем в скидках.

## Изменения по файлам (патч-план)
- `bot/utils/identity.py` + `bot/middlewares/uid_transform.py` — новые модули с helper’ами и middleware для UID.
- `bot/app/controllers/dispatcher_controller.py`, `bot/main_bot.py` — включение UID-мiddleware, инициализация ECDC, регистрация фоновых задач.
- `config/settings.py`, `.env.example` — переход на UID в настройках, новый флаг комьюнити.
- `bot/utils/message_queue.py`, `bot/utils/__init__.py`, `bot/services/notification_service.py`, `bot/services/*` — адаптация выходов к UID/TID.
- `db/models.py`, `db/migrator.py`, `db/dal/*` — переход на string UID, новая таблица инвайтов.
- `bot/middlewares/*`, `bot/filters/admin_filter.py`, `bot/handlers/**` — замена TID на UID, логирование.
- `bot/services/referral_service.py`, `bot/handlers/user/subscription/payments.py`, `bot/handlers/inline_mode.py` — скидки и одноразовые инвайты.
- `bot/handlers/user/start.py`, `bot/states/user_states.py` — закрытое комьюнити, обработка инвайтов.
- Дополнительно: `bot/utils/date_utils.py`, `bot/utils/message_queue.py` — вспомогательные функции и расписание.

## Миграции
- **Изменение типов:** для каждой таблицы `ALTER TABLE ... ALTER COLUMN user_id TYPE TEXT USING user_id::text;` и аналогично для FK (PostgreSQL).
- **Новая таблица `referral_invites`:**
  ```sql
  CREATE TABLE referral_invites (
      id SERIAL PRIMARY KEY,
      referral_code TEXT UNIQUE NOT NULL,
      referrer_uid TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
      status TEXT NOT NULL CHECK (status IN ('issued','used','expired')),
      expires_at TIMESTAMPTZ NOT NULL,
      used_by_uid TEXT NULL REFERENCES users(user_id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );
  CREATE INDEX idx_referral_invites_status_exp ON referral_invites(status, expires_at);

Инициализация данных: UPDATE users SET user_id = enc_ttu(user_id::bigint) выполняется оффлайн-скриптом либо мигратор запускает процедуру (нужно подготовить stand-alone CLI).
ENV / settings
Новые ключи: ADMIN_UIDS, LOG_CHAT_UID, COMMUNITY_IS_OPEN=true|false.
Документация по ECDC: напоминание о необходимости заполнить secret/tweak.
Обновить README: хранение UID вместо TID.
Риски и откаты
Миграция UID: обратимое обновление данных должно быть протестировано на staging; держать dump для отката.
ECDC ключи: при смене secret все UID станут недешифруемыми — нужно предупредить (wrap в документации).
Инвайты: TTL 10 мин — риск, что пользователи не успеют; предусмотреть сообщение и генерацию нового.
Скидки: неправильное определение активности реферала может снизить выручку; добавить логирование расчётов.
Закрытое комьюнити: при ошибке invite DAL бот перестанет принимать новых пользователей; предусмотреть override через env.
Приложение — справочник ECDC
bot/utils/ecdc_api.py:
enc_ttu(tid: int) -> str — используем в UIDTransformMiddleware для входящих апдейтов.
dec_utt(uid: str) -> int — используем в identity.uid_to_tid и Telegram-адаптерах (очередь, прямые send).
init_from_settings(settings) / get_service() — вызываем при старте (dispatcher_controller, identity.ensure_service).


- `bot/utils/identity.py`: слой преобразования TID↔UID, кеш ECDC.
- `bot/middlewares/uid_transform.py`: middleware, прокидывающее UID в `data`.
- `bot/app/controllers/dispatcher_controller.py`: инициализация ECDC, регистрация UID-middleware.
- `bot/main_bot.py`: вызов `ensure_service`, планировщик очистки инвайтов.
- `config/settings.py`: UID-настройки, `COMMUNITY_IS_OPEN`.
- `.env.example`: инструкции для UID, новый флаг.
- `db/models.py`, `db/migrator.py`, `db/dal/*`: UID-колонки, таблица инвайтов.
- `bot/middlewares/*`, `bot/filters/admin_filter.py`, `bot/handlers/**`, `bot/services/*`: переход на UID, адаптация Telegram-вызовов.
- `bot/services/referral_service.py`, `bot/handlers/user/subscription/payments.py`, `bot/handlers/inline_mode.py`, `bot/handlers/user/start.py`, `bot/states/user_states.py`: скидки, одноразовые инвайты, закрытая регистрация.
- `bot/utils/message_queue.py`, `bot/utils/__init__.py`, `bot/services/notification_service.py`: конвертация UID→TID на выходе.
