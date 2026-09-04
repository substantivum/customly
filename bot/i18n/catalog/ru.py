"""Russian catalog.

Mirrors `en.py` key for key; `tests/test_i18n.py` fails the build if the two
drift apart or if a placeholder set stops matching.
"""
from __future__ import annotations

STRINGS: dict[str, str] = {
    # ------------------------------------------------------------- общее ---
    "common.owner": "Владелец",
    "common.state": "Статус",
    "common.seats": "Места",
    "common.players": "Игроки",
    "common.waitlist": "Лист ожидания",
    "common.game": "Игра",
    "common.maps": "Карты",
    "common.draft": "Драфт",
    "common.captains": "Капитаны",
    "common.selected": "Выбрано",
    "common.teams": "Команды",
    "common.waiting_on": "Ожидание",
    "common.team_a": "Команда A",
    "common.team_b": "Команда B",
    "common.enabled": "включена",
    "common.disabled": "выключена",
    "common.auto_note": " _(авто)_",
    "common.auto_paren": " (авто)",
    "common.its_channel": "его канале",
    "common.hidden": "🔒 скрыт",

    "rank.player": "Игрок",
    "rank.admin": "Админ",
    "rank.superadmin": "Суперадмин",
    "role.player": "игрок",
    "role.admin": "админ",
    "role.superadmin": "суперадмин",

    "state.registration": "набор",
    "state.full": "состав собран",
    "state.ready": "проверка готовности",
    "state.veto": "вето карт",
    "state.live": "идёт игра",
    "state.done": "завершён",

    "tier.player": "Кастомы",
    "tier.admin": "Админ",
    "tier.superadmin": "Суперадмин",

    # ------------------------------------------------------------ кнопки ---
    "btn.register": "Записаться",
    "btn.leave": "Выйти",
    "btn.confirm": "Подтвердить",
    "btn.force": "Принудительно",
    "btn.cancel": "Отмена",
    "btn.back": "Назад",
    "btn.refresh": "Обновить",
    "btn.continue": "Далее",
    "btn.browse": "Выбрать и записаться",
    "btn.create_custom": "Создать кастом",
    "btn.manage_customs": "Мои кастомы",
    "btn.manage_any": "Любой кастом",
    "btn.maps": "Карты",
    "btn.bans": "Баны",
    "btn.riot_approvals": "Проверка рангов",
    "btn.approve": "Одобрить",
    "btn.deny": "Отклонить",
    "btn.audit": "Журнал",
    "btn.bot_roles": "Роли бота",
    "btn.prune": "Удалить все кастомы",
    "btn.language": "Язык",
    "btn.ready_check": "Проверка готовности",
    "btn.start": "Начать",
    "btn.force_start": "Начать принудительно",
    "btn.end": "Завершить",
    "btn.delete": "Удалить",
    "btn.seed": "Загрузить стандартные",
    "btn.add_map": "Добавить карту",
    "btn.remove_map": "Удалить карту",
    "btn.competitive_pool": "Соревновательный пул",
    "btn.ban": "Забанить",
    "btn.unban": "Разбанить",
    "btn.grant": "Выдать",
    "btn.revoke": "Снять",
    "btn.set_code": "Задать код лобби",
    "btn.set_code.cs2": "Задать IP лобби",
    "btn.set_code.dota2": "Задать данные лобби",
    "btn.end_custom": "Завершить кастом",
    "btn.ready": "Готов",
    "btn.cant_play": "Не могу играть",
    "btn.attack": "Атака",
    "btn.defence": "Защита",

    # ------------------------------------------------------------ ошибки ---
    "error.generic": "Что-то пошло не так.",
    "error.need_role": "Для этого действия нужна роль **{role}**.",
    "error.need_role_cmd": "Для этого нужна роль **{role}**.",
    "error.config_channel": "Выполните это в настроенном канале конфигурации.",
    "error.custom_gone": "Кастом #{custom_id} больше не существует.",
    "error.custom_not_found": "Кастом не найден.",
    "error.cant_manage": "У вас нет прав управлять этим кастомом.",
    "error.superadmin_only": "Только для суперадмина.",
    "error.force_superadmin": "Принудительный режим доступен только суперадмину.",
    "error.delete_perm": "Удалить может только владелец или суперадмин.",
    "error.manage_perm": "Это может сделать только владелец или суперадмин.",
    "error.start_perm": "Начать этот кастом может только владелец или суперадмин.",
    "error.transfer_perm": "Передать кастом может только владелец или суперадмин.",
    "error.already_owner": "{name} уже владеет кастомом #{custom_id}.",
    "error.bot_owner": "Бот не может владеть кастомом.",
    "error.code_perm": (
        "Задать код может только участник этого кастома (или админ)."
    ),
    "error.end_perm": "Завершить может только участник этого кастома (или админ).",
    "error.not_starter": "Вы не в основном составе этой игры.",
    "error.not_your_call": "Сейчас не ваш ход.",
    "error.not_your_turn": "Сейчас не ваш ход бана/пика.",
    "error.not_your_side": "Сторону выбирает не ваша команда.",
    "error.not_your_pick": "Сейчас не ваш пик.",
    "error.bad_start": "Время старта — `ЧЧ:ММ` или ISO `2026-06-24T20:00`.",
    "error.no_queue": "У этого кастома нет очереди.",
    "error.no_channel": "У кастома не осталось канала, чтобы провести матч.",
    "error.no_match_yet": "В этом кастоме матч ещё не начался.",
    "error.code_charset": "Код должен быть буквенно-цифровым (можно `-`, `_`, `.` и `:`).",
    "error.lobby_name_required": "Название лобби не может быть пустым.",
    "error.already_ended": "Этот кастом уже завершён.",
    "error.not_started": "Кастом ещё не начался — удалите его вместо завершения.",
    "error.match_not_found": "Матч не найден.",
    "error.result_perm": "Результаты может внести только капитан этого матча или админ.",
    "error.no_draw": "Карта не может закончиться ничьёй — счёт должен различаться.",
    "error.result_race": "Два результата пришли одновременно — попробуйте отправить ещё раз.",
    "error.result_missing": (
        "Никто ещё не внёс результат — он пропадёт в момент завершения "
        "кастома. Капитан или админ может внести его кнопкой "
        "**Завершить кастом** либо командой `/match result`."
    ),
    "error.result_perm_end": (
        "Результат матча ещё не внесён, а внести его может только капитан "
        "этого матча или админ — попросите кого-то из них завершить кастом."
    ),
    "error.bad_score": "**{map}**: `{value}` — это не счёт, пишите как `13-11`.",
    "error.result_gap": (
        "**{map}** оставлена пустой, а более поздняя карта заполнена — карты "
        "играются по порядку, заполняйте их сверху вниз."
    ),
    "error.force_admin": "Завершить матч без результата может только админ.",
    "error.riot_id": "Riot ID должен быть вида `TenZ#NA1` (Имя#ТЕГ).",
    "error.riot_not_found": (
        "Аккаунт Valorant `{tag}` не найден — проверьте написание и попробуйте снова."
    ),
    "error.riot_rate_limited": "Сервис рангов сейчас перегружен — попробуйте через минуту.",
    "error.riot_timeout": "Сервис рангов не ответил вовремя — попробуйте чуть позже.",
    "error.riot_unavailable": "Не удалось связаться с сервисом рангов — попробуйте позже.",
    "error.faceit_unconfigured": (
        "Ранг CS2 на этом сервере ещё не настроен (нет ключа Faceit API). "
        "Обратитесь к админу."
    ),
    "error.faceit_not_found": "Игрока Faceit CS2 с ником `{nick}` не найдено — проверьте написание.",
    "error.faceit_rate_limited": "Faceit сейчас занят — попробуйте через минуту.",
    "error.faceit_timeout": "Faceit не ответил вовремя — попробуйте ещё раз.",
    "error.faceit_unavailable": "Не удалось связаться с Faceit — попробуйте позже.",
    "error.dota_bad_id": "Dota 2 friend id — это число, ваш внутриигровой Friend ID.",
    "error.dota_not_found": (
        "Нет открытого профиля Dota 2 для friend id `{friend}` — откройте историю "
        "матчей (Настройки → Соцсети) и попробуйте снова."
    ),
    "error.dota_rate_limited": "OpenDota сейчас занят — попробуйте через минуту.",
    "error.dota_timeout": "OpenDota не ответил вовремя — попробуйте ещё раз.",
    "error.dota_unavailable": "Не удалось связаться с OpenDota — попробуйте позже.",
    "error.flow_step": (
        "⚠️ Не удалось перейти к этапу «{what}» — `{error}`.\n"
        "Попросите админа завершить кастом и запустить его заново "
        "(подробности — в логе бота)."
    ),
    "error.team_vcs": (
        "⚠️ Не удалось создать голосовые каналы команд — `{error}`. "
        "Продолжаем вето; создайте их вручную или освободите категорию "
        "кастомов перед следующей игрой."
    ),

    "error.ready_running": (
        "По кастому #{custom_id} идёт проверка готовности. Дождитесь её или "
        "нажмите **Начать** / **Начать принудительно**, чтобы прервать."
    ),
    "error.match_in_progress": (
        "В кастоме #{custom_id} уже идёт матч (статус: {state}). "
        "Завершите его или выполните `/custom delete`, чтобы начать заново."
    ),
    "error.pool_recreate": "{reason} Пересоздайте кастом с подходящим пулом карт.",
    "error.partial_even": "Для ручного старта нужно чётное число игроков ≥ 2 (сейчас {n}).",
    "error.queue_not_full": (
        "Очередь не заполнена ({have}/{size}). "
        "Используйте принудительный старт, чтобы начать текущим составом."
    ),
    "error.manual_both": "Ручной выбор капитанов: укажите обоих капитанов.",
    "error.manual_distinct": "Капитаны должны быть двумя разными игроками.",
    "error.manual_registered": "Оба капитана должны быть записаны в этот кастом.",

    "error.ready_already": "По кастому #{custom_id} проверка готовности уже идёт.",
    "error.ready_state": (
        "Кастом #{custom_id} в статусе `{state}` — проверка готовности имеет "
        "смысл только до начала матча."
    ),
    "error.ready_no_channel": "У кастома нет канала для проверки готовности.",
    "error.ready_even": "Для проверки готовности нужно чётное число игроков ≥ 2 (сейчас {n}).",

    "error.banned": "Вам запрещено записываться на игры этого сервера.",
    "error.not_open": "Кастом #{custom_id} закрыт для записи.",
    "error.match_started": (
        "Кастом #{custom_id} уже начался — нельзя покинуть его во время матча."
    ),
    "error.conflict": "Пересекается с **{name}** ({start}–{end}).",
    "error.already_registered": "Вы уже записаны.",
    "error.game": "Игра должна быть одной из: {games}.",
    "error.format_for_game": "Кастомы {game} должны использовать один из форматов: {formats}.",
    "error.team_size": "Размер команды — от 1 до 5 (от 1v1 до 5v5).",
    "error.draft_mode": "Режим драфта должен быть одним из: {modes}.",
    "error.captain_method": "Способ выбора капитанов должен быть одним из: {methods}.",
    "error.unknown_captain": "Неизвестный способ выбора капитанов: {method}",
    "error.manual_two": "Для ручного способа нужно выбрать двух капитанов.",
    "error.volunteers": "Нужно минимум два добровольца.",
    "error.no_votes": "Голоса не зафиксированы.",
    "error.need_two_candidates": "Нужны голоса минимум за двух разных кандидатов.",
    "error.need_two_players": "Нужно минимум два игрока, чтобы выбрать капитанов.",
    "error.no_comp_pool": (
        "Соревновательный пул для сервера ещё не задан — админ может задать его "
        "в **Панель админа → Карты → Соревновательный пул**."
    ),
    "error.no_maps_pool": (
        "Карты не указаны, а включённого пула на сервере нет. "
        "Сначала выполните `/maps seed` или передайте карты."
    ),
    "error.maps_not_enabled": "Карты вне включённого пула: {maps}",
    "error.in_progress_guard": (
        "Оба голосовых канала команд заняты — идёт матч. "
        "Сначала завершите его или (суперадмин) передайте force:true."
    ),

    "veto.pool.exact": "ровно {n} карт",
    "veto.pool.min": "минимум {n} карт",
    "error.veto_format": "Формат должен быть одним из: {formats}.",
    "error.veto_pool": "Для {fmt} нужно {requirement} в пуле (сейчас {n}).",
    "error.veto_pool_hint": " Укажите `competitive`, чтобы взять соревновательный пул.",
    "error.veto_pool_max": (
        "Для {fmt} в пуле должно быть не больше {max} карт (сейчас {n}) — "
        "у вето не может быть больше кнопок бана/пика. Сократите пул или "
        "укажите список карт поменьше."
    ),

    # ------------------------------------------------------------ кастом ---
    "custom.asap": "**СЕЙЧАС**",
    "custom.asap_full": "**СЕЙЧАС** — как только лобби будет готово",
    "custom.reg.announce": "Регистрируйтесь на кастом **{game}** ниже!",
    "custom.reg.title": "Кастом #{custom_id} — {name}",
    "custom.reg.body": (
        "**Игра:** {game}\n"
        "**Формат:** {fmt}  ·  **{size}v{size}**\n"
        "**Начало:** {start}\n"
        "**Интервал:** {from_time} – {to_time}\n"
        "**Пул карт:** {pool}\n"
        "**Драфт:** {draft}\n"
        "**Капитаны:** {captains}"
    ),
    "custom.reg.body_no_maps": (
        "**Игра:** {game}\n"
        "**Формат:** {fmt}  ·  **{size}v{size}**\n"
        "**Начало:** {start}\n"
        "**Интервал:** {from_time} – {to_time}\n"
        "**Драфт:** {draft}\n"
        "**Капитаны:** {captains}"
    ),
    "custom.reg.registered": "Записались ({n}/{size})",
    "custom.reg.waitlist": "Лист ожидания ({n})",
    "custom.reg.waitlist_more": "\n_…и ещё {n}_",
    "custom.reg.waitlist_note": "\n_Запасные поднимаются автоматически, когда кто-то выходит._",
    "custom.reg.footer": "Используйте кнопки ниже, чтобы записаться или выйти.",
    "custom.created": "Создан **кастом #{custom_id}** ({size}v{size}) → {channel}",
    "custom.joined": "Вы записаны на кастом #{custom_id} — ждите проверку готовности.",
    "custom.joined_waitlist": (
        "Кастом #{custom_id} заполнен — вы **#{position} в листе ожидания** "
        "и подниметесь автоматически, если кто-то выйдет."
    ),
    "custom.left": "Вы вышли из кастома #{custom_id}.",
    "custom.promoted_channel": (
        "<@{user_id}> — освободилось место в **{name}**, вы в игре."
    ),
    "custom.promoted_dm": (
        "Вы поднялись из листа ожидания в **кастом #{custom_id} — {name}** "
        "на сервере **{guild}**. Вы играете."
    ),
    "custom.transfer_note": (
        "Владение **кастомом #{custom_id} — {name}** передано "
        "{new_owner} (передал {actor})."
    ),
    "custom.transfer_dm": (
        "Теперь вы владеете **кастомом #{custom_id} — {name}** на сервере "
        "**{guild}** (передал {actor}).\n"
        "Начать, завершить, передать или удалить его можно в "
        "**Панель админа → Мои кастомы** или в {where}."
    ),
    "custom.transferred": "Владение кастомом #{custom_id} → {member} (уведомление отправлено).",
    "custom.transferred_short": "Владение #{custom_id} → {member} (уведомление отправлено).",
    "custom.ending": "Завершаем кастом — голосовые каналы и этот канал будут удалены.",
    "custom.ending_cmd": "Завершаем кастом #{custom_id}…",
    "custom.ended": "Кастом #{custom_id} завершён.",
    "custom.deleted": "Кастом #{custom_id} удалён.",
    "custom.pruned": "Удалено кастомов: {n}.",
    "custom.pruned_skipped": " Пропущены (идёт игра): {ids}.",
    "custom.none_active": "Активных кастомов нет.",
    "custom.list_line": (
        "**#{custom_id}** {name} · {fmt} · {size}v{size} · владелец <@{owner_id}> · {state}"
    ),

    # ------------------------------------------------------------ панели ---
    "board.player.title": "Кастомы",
    "board.player.desc": (
        "Ниже перечислены все открытые игры. Нажмите **Выбрать и записаться**, "
        "чтобы выбрать игру, записаться или выйти, посмотреть состав."
    ),
    "board.admin.title": "Панель админа",
    "board.admin.desc": "Создание и ведение кастомов.",
    "board.super.title": "Панель суперадмина",
    "board.super.desc": "Настройки сервера.",
    "board.open_games": "Открытые игры ({n})",
    "board.active_customs": "Активные кастомы ({n})",
    "board.customs_active": "Кастомы (активных: {n})",
    "board.map_pool": "Пул карт",
    "board.map_pool_count": "включено **{enabled}/{total}**",
    "board.map_pool_unseeded": "_Пул пуст — используйте **Карты → Загрузить стандартные**._",
    "board.map_pool_line": "{mark} {game} — включено **{enabled}/{total}**",
    "board.map_pool_line_empty": "{mark} {game} — _пул пуст_",
    "board.competitive": "Соревновательный пул",
    "board.competitive_line": "{mark} {game}: {maps}",
    "board.admins": "Админы",
    "board.superadmins": "Суперадмины",
    "board.banned": "Забаненные игроки",
    "board.config": "Конфигурация",
    "board.language": "Язык",
    "board.more_granted": "_+ ещё {n}_",
    "board.nothing_running": "_Сейчас ничего не идёт._",
    "board.and_more": "_…и ещё {n}._",
    "board.none_active": "_активных нет_",
    "board.line.seats": "{fmt} · {size}v{size} · **{taken}/{total}** мест",
    "board.line.waiting": " (+{n} в ожидании)",
    "board.line.starts": "старт {when}",
    "board.line.owner": "владелец {owner}",
    "board.footer.player": "Обновляется автоматически · ваше меню видно только вам",
    "board.footer.staff": "Обновляется при изменениях в кастомах",
    "board.cfg.category": "категория кастомов",
    "board.cfg.config_channel": "канал конфигурации",
    "board.cfg.admin_channel": "канал админов",
    "board.cfg.super_channel": "канал суперадминов",

    "panel.err.pinned": (
        "Панель **{tier}** закреплена за <#{channel_id}> (`{env}`). Выполните команду там."
    ),
    "panel.err.reserved": (
        "Этот канал зарезервирован под панель **{other}** — "
        "разместите панель {tier} в другом месте."
    ),
    "picker.desc": "{fmt} · {size}v{size} · {state}",

    # ------------------------------------------------------------ экраны ---
    "screen.gone.title": "Удалён",
    "screen.customs.title": "Кастомы — выберите игру",
    "screen.customs.desc": "Выберите игру ниже, чтобы увидеть состав и записаться.",
    "screen.customs.empty": "Сейчас нет открытых игр. Загляните позже.",
    "screen.customs.youre_in": "  ✅ **вы в игре**",
    "screen.customs.pick": "Выберите игру…",
    "screen.custom.you": "Вы",
    "screen.custom.you_waitlist": "В листе ожидания — сыграете, если кто-то из основы выйдет.",
    "screen.custom.you_in": "✅ Вы в игре.",
    "screen.custom.closed": "Запись на эту игру закрыта.",

    "screen.create.title": "Создание кастома",
    "screen.create.desc": (
        "Здесь задайте пул карт и режим драфта, затем нажмите **Далее** — "
        "название, формат, размер команды и время старта."
    ),
    "screen.create.all_maps": "_все включённые карты ({n})_",
    "screen.create.no_maps": "⚠️ Нет включённых карт — сначала заполните пул в разделе **Карты**.",
    "screen.create.no_comp": (
        "Соревновательный пул ещё не задан — задайте его в "
        "**Карты → Соревновательный пул**."
    ),
    "screen.create.min_maps": "Выберите минимум 2 карты или ни одной, чтобы взять весь пул.",
    "screen.create.pool_ph": "Пул карт — выберите 2+ карты (пусто = весь включённый пул)…",
    "screen.create.draft_ph": "Режим драфта — змейка (по умолчанию) или по одному…",
    "screen.create.captains_ph": "Капитаны — как выбираются два капитана…",
    "screen.create.game_ph": "Игра — Valorant, Dota 2 или CS2…",

    "game.valorant": "Valorant",
    "game.dota2": "Dota 2",
    "game.cs2": "CS2",

    "screen.manage_list.title": "Управление кастомами",
    "screen.manage_list.desc_all": "Все активные кастомы на сервере.",
    "screen.manage_list.desc_own": "Кастомы, которыми вы владеете.",
    "screen.manage_list.active": "Активные ({n})",
    "screen.manage_list.empty_own": (
        "У вас нет активного кастома. Создайте его или попросите суперадмина "
        "передать вам существующий."
    ),
    "screen.manage_list.pick": "Выберите кастом для управления…",

    "screen.manage.title": "Кастом #{custom_id} — {name}",
    "screen.manage.body": (
        "{dot} **{state}**  ·  {fmt}  ·  **{size}v{size}**\n"
        "**Начало:** {start}\n"
        "**Пул карт:** {pool}\n"
        "**Драфт:** {draft}\n"
        "**Капитаны:** {captains} _(задано при создании)_"
    ),
    "screen.manage.ready_title": "Идёт проверка готовности",
    "screen.manage.ready_body": (
        "Игроки подтверждают участие в канале кастома. **Начать** или "
        "**Начать принудительно** прервёт проверку и запустит матч."
    ),
    "screen.manage.transfer_ph": "Передать владение…",

    "screen.maps.empty": "Карты не настроены — нажмите **Загрузить стандартные**.",
    "screen.maps.footer": "Отметка карты соревновательной автоматически включает её.",
    "screen.maps.toggle_ph": "Включить/выключить карты (можно несколько)…",
    "screen.maps.comp_ph": "Соревновательный пул — отметьте текущую ротацию…",
    "screen.maps.game_ph": "Игра — какой пул вы редактируете…",
    "screen.maps.in_comp": "в соревновательном пуле",
    "screen.maps.flipped": "**{name}** → {state}",
    "screen.maps.nothing": "Нечего переключать.",
    "screen.maps.delete.title": "Удалить карту",
    "screen.maps.delete.desc": "Выберите карту для удаления из пула {game} — позже её можно вернуть.",
    "screen.maps.delete_ph": "Выберите карту для удаления…",

    "screen.bans.title": "Баны",
    "screen.bans.desc": "Забаненные игроки не могут записываться на игры этого сервера.",
    "screen.bans.count": "Забанено ({n})",
    "screen.bans.more": "_…и ещё {n}._",
    "screen.bans.pick_hint": "_выберите игрока ниже_",
    "screen.bans.player_ph": "Игрок…",

    "screen.riot_approvals.title": "Проверка Riot ID",
    "screen.riot_approvals.desc": (
        "Проверьте заявки на Riot ID, прежде чем ранг игрока где-либо учтётся."
    ),
    "screen.riot_approvals.count": "На проверке ({n})",
    "screen.riot_approvals.pick": "Выберите заявку для проверки",
    "screen.riot_approvals.more": "_…и ещё {n}._",

    "screen.rank_approvals.title": "Проверка рангов",
    "screen.rank_approvals.desc": (
        "Одобрите поданную личность — Riot ID, ник Faceit или Dota friend id — "
        "прежде чем её ранг начнёт учитываться. Владение нельзя проверить "
        "автоматически, поэтому убедитесь, что это действительно они."
    ),
    "screen.rank_approvals.count": "На проверке ({n})",
    "screen.rank_approvals.pick": "Выберите заявку для проверки…",
    "screen.rank_approvals.more": "_…и ещё {n}._",
    "screen.rank_approvals.line": "{mark} {member} — `{identity}`",

    "screen.audit.title": "Журнал действий",
    "screen.audit.empty": "_Записей пока нет._",
    "screen.audit.footer": "15 последних записей",

    "screen.roles.title": "Роли бота",
    "screen.roles.desc": (
        "Роли, выданные здесь, действуют вдобавок к Discord-ролям `ADMIN_ROLE` / "
        "`SUPERADMIN_ROLE` из `.env`."
    ),
    "screen.roles.count": "{role} ({n})",
    "screen.roles.selected": "{member} → **{role}**",
    "screen.roles.pick_hint": "_выберите участника_",
    "screen.roles.member_ph": "Участник…",
    "screen.roles.role_ph": "Роль…",

    "screen.language.title": "Язык",
    "screen.language.desc": (
        "Язык, на котором бот говорит на этом сервере. Действует для всех: "
        "панели, меню, сообщения матча и ошибки."
    ),
    "screen.language.current": "Текущий",
    "screen.language.pick": "Выберите язык…",

    "confirm.force_note": (
        "Принудительный режим также обходит защиту от удаления идущей игры "
        "(отключает всех из голосовых каналов команд)."
    ),
    "confirm.delete.title": "⚠️ Удалить кастом #{custom_id}?",
    "confirm.delete.desc": (
        "**{name}** — его канал, голосовые каналы и очередь будут удалены. "
        "Это необратимо."
    ),
    "confirm.prune.title": "⚠️ Удалить все кастомы на этом сервере?",
    "confirm.prune.desc": (
        "**{n} активных** кастомов плюс все завершённые, вместе с их каналами "
        "и очередями. Это необратимо."
    ),

    # ------------------------------------------------------------- карты ---
    "maps.added": "Добавлена карта **{name}**.",
    "maps.err.empty": "Название карты не может быть пустым.",
    "maps.err.exists": "**{name}** уже есть в пуле.",
    "maps.comp_set": "Соревновательный пул: **{maps}** (карты включены).",
    "maps.comp_cleared": "Соревновательный пул очищен.",
    "maps.comp_unknown": "\nНет в списке карт этого сервера (пропущено): {maps}",
    "maps.seeded": "Добавлено карт: {n}.",
    "maps.already_seeded": "Пул уже заполнен.",
    "maps.none_configured": "Карты не настроены. Админ: `/maps seed` загрузит стандартные.",
    "maps.seeded_ok": "Стандартный пул загружен.",
    "maps.added_cmd": "Добавлена карта {name}.",
    "maps.removed": "Карта {name} удалена.",
    "maps.no_such": "Такой карты нет.",
    "maps.toggled": "Карта {name} теперь {state}.",
    "maps.list_line": "{dot} {name}",
    "maps.list_line_comp": "{dot} {name} — соревновательная",

    # -------------------------------------------------------------- баны ---
    "bans.banned": "Бан выдан: {member}.",
    "bans.already_banned": "Бан уже был выдан: {member}.",
    "bans.unbanned": "Бан снят: {member}.",
    "bans.not_banned": "Бана не было: {member}.",
    "bans.reason_suffix": "\nПричина: {reason}",
    "bans.none": "Забаненных игроков нет.",

    # ------------------------------------------------- проверка riot id ---
    "riot_approvals.approved": "{member} одобрен(а).",
    "riot_approvals.denied": "{member} отклонён(а).",
    "riot_approvals.gone": "Эта заявка уже была рассмотрена.",
    "riot.dm.approved": (
        "Ваш Riot ID **{tag}** одобрен на сервере **{guild}** — теперь ваш "
        "ранг виден в профиле."
    ),
    "riot.dm.denied": (
        "Ваш Riot ID **{tag}** отклонён на сервере **{guild}**. Запустите "
        "/register с правильным Riot ID, чтобы попробовать снова."
    ),
    "rank_approvals.approved": "Личность {member} для {game} одобрена.",
    "rank_approvals.denied": "Личность {member} для {game} отклонена.",
    "rank_approvals.gone": "Эта заявка уже была рассмотрена.",
    "rank.dm.approved": (
        "Ваша личность {game} **{identity}** одобрена на сервере **{guild}** — "
        "теперь ваш ранг учитывается и виден в профиле."
    ),
    "rank.dm.denied": (
        "Ваша личность {game} **{identity}** отклонена на сервере **{guild}**. "
        "Подайте заявку заново с правильными данными."
    ),

    "roles.granted": "Роль **{role}** выдана: {member}.",
    "roles.already_granted": "У {member} уже есть роль **{role}**.",
    "roles.revoked": "Роль **{role}** снята: {member}.",
    "roles.not_granted": "У {member} не было роли **{role}**.",
    "admin.notify_role.set": "Роль уведомлений установлена: {role}.",
    "admin.notify_role.cleared": "Роль уведомлений сброшена.",

    "audit.none": "Записей в журнале нет.",
    "audit.line": "`{ts}` {actor} **{action}** {target}",

    # ---------------------------------------------------------- капитаны ---
    "captain.random": "Случайно",
    "captain.highest_rr": "Наибольший RR",
    "captain.highest_peak": "Наивысший пиковый ранг",
    "captain.highest_wins_peak": "Больше всего побед в кастомках (по пиковому рангу при равенстве)",
    "captain.highest_wins_rr": "Больше всего побед в кастомках (по RR при равенстве)",
    "captain.manual": "Выбраны вручную",
    "captain.volunteer": "Добровольцы",
    "captain.vote": "Голосованием",
    "captain.help.random": "два случайных игрока из лобби",
    "captain.help.highest_rr": "двое с наибольшим текущим RR — нужны заполненные профили",
    "captain.help.highest_peak": "двое с наивысшим пиковым рангом — нужны заполненные профили",
    "captain.help.highest_wins_peak": (
        "двое с наибольшим числом побед в кастомках — равенство решает пиковый ранг"
    ),
    "captain.help.highest_wins_rr": (
        "двое с наибольшим числом побед в кастомках — равенство решает текущий RR"
    ),

    # ------------------------------------------------------------- драфт ---
    "draft.mode.snake": "Змейка (A, BB, AA, …)",
    "draft.mode.alternate": "По одному (A, B, A, B, …)",
    "draft.snake.label": "Драфт змейкой",
    "draft.snake.desc": "A, BB, AA, BB … — сглаживает преимущество первого пика",
    "draft.alternate.label": "По одному",
    "draft.alternate.desc": "A, B, A, B … — строго по очереди",
    "draft.title.snake": "Драфт змейкой",
    "draft.title.alternate": "Драфт (по одному)",
    "draft.title": "{mode} — матч #{match_id}",
    "draft.on_clock": "Ход",
    "draft.on_clock_value": "{captain} ({side}) — осталось {n}",
    "draft.complete": "Готово",
    "draft.complete_value": "Все игроки распределены.",
    "draft.pick_ph": "Выберите игрока…",

    # ------------------------------------------------------- лента этапов ---
    "flow.phase": "Этап",
    "flow.coin": "Монета",
    "flow.draft": "Драфт",
    "flow.veto": "Вето",
    "flow.live": "Игра",

    # ------------------------------------------------------------ монета ---
    "coin.title": "Жеребьёвка — матч #{match_id}",
    "coin.heads": "Орёл",
    "coin.tails": "Решка",
    "coin.calling": "Загадывает",
    "coin.call": "Загадано",
    "coin.landed": "Выпало",
    "coin.winner": "Победитель жеребьёвки",
    "coin.wait_call": "орёл или решка",
    "coin.wait_letter": (
        "{captain} — **Команда A** или **Команда B**\n"
        "Команда A драфтит первой и банит первой."
    ),
    "coin.teams_value": (
        "Команда A {cap_a} · Команда B {cap_b}\n"
        "Команда A драфтит первой и банит первой."
    ),

    # -------------------------------------------------------------- вето ---
    "veto.title": "Вето карт — матч #{match_id}",
    "veto.remaining": "Осталось",
    "veto.picked": "Выбрано",
    "veto.sides": "Стороны",
    "veto.turn": "Ход",
    "veto.attack": "атака",
    "veto.defence": "защита",
    "veto.action.ban": "бан",
    "veto.action.pick": "пик",
    "veto.turn_action": "{captain} — {action}",
    "veto.turn_side": "{captain} выбирает сторону на карте **{map}**",
    "veto.side_text": "**{map}** — Команда {chooser} {choice}, Команда {other} {flip}",
    "veto.result_maps": "Выбор карт завершён{note}.\n{lines}",
    "veto.result_simple": "Вето завершено{note}. Карты: **{maps}**",

    # -------------------------------------------------------- готовность ---
    "ready.title": "Проверка готовности — кастом #{custom_id} · {name}",
    "ready.round": " (раунд {n})",
    "ready.desc": (
        "Все ниже должны подтвердить готовность до начала матча.\nЗакроется {when}.\n"
        "**Не могу играть** сразу освобождает ваше место для запасного."
    ),
    "ready.count": "Готовы {n}/{total}",
    "ready.ping": "**Проверка готовности** — {mentions}",
    "ready.posted": (
        "Проверка готовности отправлена в {channel} — у {n} игрок(ов) есть {seconds} с."
    ),
    "ready.resolving": "Обрабатываем…",
    "ready.cancel.manual": "Прервано — {actor} запустил матч вручную.",
    "ready.cancel.deleted": "Кастом удалён.",
    "ready.outcome.all_ready": "✅ Все готовы — запускаем матч.",
    "ready.outcome.incomplete": "⚠️ Подтвердили не все. Исключены: {dropped}",
    "ready.subs_round": (
        "{dropped} потеряли места — запасные подняты. "
        "Запускаем раунд проверки **{round}**."
    ),
    "ready.failed": (
        "⚠️ **Проверка готовности не пройдена** для кастома #{custom_id} — {why}. "
        "Мест занято {filled}/{size}; запись снова открыта. "
        "Админ может повторить проверку или запустить принудительно."
    ),
    "ready.why.no_subs": "запасных не было",
    "ready.cooldown_retry": (
        "⚠️ Проверка готовности не удалась {n} раз(а) подряд — повторим "
        "автоматически через {seconds} сек."
    ),

    # -------------------------------------------------------------- матч ---
    "match.announce": (
        "**Матч #{match_id}** ({per_side}v{per_side}) — "
        "капитаны <@{cap_a}> против <@{cap_b}> ({method})."
    ),
    "match.subs": (
        "**Запасные (не в этом матче):** {subs} — вы записались после того, "
        "как места закончились."
    ),
    "match.captains_fallback_random": (
        "⚠️ Недостаточно игроков с подтверждённым рангом — выбираем капитанов "
        "случайно вместо **{method}**."
    ),
    "match.starting": (
        "Матч #{match_id} запускается ({per_side}v{per_side}) в {channel}. "
        "Капитаны: <@{cap_a}> против <@{cap_b}> — жеребьёвка решит, кто Команда A."
    ),
    "match.result_recorded": "Записано {map}: A {score_a}–{score_b} B (победа {winner}).",
    "result.line": "**{map}** — A {score_a}–{score_b} B",
    "result.recorded_ending": (
        "Результат записан:\n{lines}\n\nЗавершаем кастом — голосовые каналы "
        "и этот канал будут удалены."
    ),
    "result.none_ending": (
        "Результат не записан — победа никому не засчитана. "
        "Завершаем кастом."
    ),

    # -------------------------------------------------------------- лобби ---
    "lobby.title": "Лобби матча — кастом #{custom_id}",
    "lobby.full_title": "{name} — матч #{match_id} ({fmt})",
    "lobby.team_cap": "{team} (кап. {captain})",
    "lobby.party_code": "Код лобби",
    "lobby.party_code.cs2": "IP лобби",
    "lobby.lobby_name": "Название лобби",
    "lobby.lobby_password": "Пароль лобби",
    "lobby.voice": "Голосовые каналы",
    "lobby.map_line": "**{index}. {map}** — Команда A {side_a} · Команда B {side_b}",
    "lobby.map_line_plain": "**{index}. {map}**",
    "lobby.map_card": "Карта {index}/{total} — {map}",
    "lobby.map_card_decider": "Карта {index}/{total} — {map} · решающая",
    "lobby.map_card_sides": "Команда A {side_a} · Команда B {side_b}",
    "lobby.footer": (
        "Любой участник кастома может задать код. При завершении у "
        "капитана сначала спросят результат."
    ),
    "code.updated": "Код лобби обновлён.",
    "code.updated.cs2": "IP лобби обновлён.",
    "code.updated.dota2": "Данные лобби обновлены.",
    "modal.create.title": "Создать кастом",
    "modal.create.name": "Название",
    "modal.create.name_ph": "Пятничный 5x5",
    "modal.create.fmt": "Формат (BO1/BO3/BO5)",
    "modal.create.team_size": "Размер команды (1-5)",
    "modal.create.start": "Начало — пусто = ASAP",
    "modal.create.start_ph": "20:00 (время сервера) или ISO — пусто, чтобы играть сейчас",
    "modal.addmap.title": "Добавить карту",
    "modal.addmap.name": "Название карты",
    "modal.addmap.name_ph": "Ascent",
    "modal.ban.title": "Забанить игрока",
    "modal.ban.reason": "Причина (необязательно)",
    "modal.code.title": "Код лобби",
    "modal.code.label": "Код лобби / группы",
    "modal.code.ph": "7F3K2",
    "modal.code.title.cs2": "IP лобби",
    "modal.code.label.cs2": "IP сервера",
    "modal.code.ph.cs2": "203.0.113.10:27015",
    "modal.code.title.dota2": "Лобби Dota 2",
    "modal.code.name_label": "Название лобби",
    "modal.code.name_ph": "Пятничный кастом",
    "modal.code.password_label": "Пароль (необязательно)",
    "modal.code.password_ph": "оставьте пустым, если без пароля",
    "modal.result.title": "Результат матча",
    "modal.result.map": "{index}. {map}: {cap_a} vs {cap_b}",
    "modal.result.ph": "13-11 — пусто, если не играли",
    "modal.result.score_ph": "напр. 13",
    "code.set": "Код лобби для кастома #{custom_id} задан.",
    "code.set.cs2": "IP лобби для кастома #{custom_id} задан.",
    "code.set.dota2": "Данные лобби для кастома #{custom_id} заданы.",
    "code.announced": "**Код лобби — кастом #{custom_id}:** `{code}`  (задал {actor})",
    "code.announced.cs2": "**IP лобби — кастом #{custom_id}:** `{code}`  (задал {actor})",
    "code.announced.dota2": (
        "**Лобби — кастом #{custom_id}:** Название: `{name}` · Пароль: `{password}`  "
        "(задал {actor})"
    ),

    # ------------------------------------------------------------ профиль ---
    "profile.register.pending": (
        "Заявка на **{tag}** отправлена на проверку — админ одобрит или "
        "отклонит её, прежде чем ваш ранг станет виден."
    ),
    "profile.register.unchanged": "По-прежнему **{tag}** — статус проверки не изменился.",
    "profile.none": "Профиль не зарегистрирован.",
    "profile.unregister.done": (
        "Ваш Riot ID удалён из профиля. Используйте `/register` в любое "
        "время, чтобы подтвердить его заново."
    ),
    "profile.refresh.not_approved": "У вас ещё нет одобренной личности — обновлять нечего.",
    "profile.refresh.done": "Ранг обновлён: **{rank}** ({rr} RR), пик — **{peak}**.",
    "profile.refresh.done_all": "Ранги обновлены — смотрите **/profile**.",
    "profile.refresh.failed": "Не удалось связаться с серверами Riot — попробуйте позже.",
    "profile.title": "Профиль — {name}",
    "profile.riot_id": "Riot ID",
    "profile.main_role": "Основная роль",
    "profile.rank": "Ранг",
    "profile.rr": "RR",
    "profile.peak": "Пик",
    "profile.wins": "Побед в кастомках",
    "profile.role.duelist": "Дуэлянт",
    "profile.role.controller": "Контроллер",
    "profile.role.initiator": "Зачинщик",
    "profile.role.sentinel": "Страж",
    "profile.role.flex": "Флекс",
    # единая карточка
    "profile.header_main": "Основная · {mark} {game} · побед в кастомках: {wins}",
    "profile.header_nomain": "Побед в кастомках: {wins}",
    "profile.not_linked": "Не привязано",
    "profile.status.pending": "на проверке",
    "profile.status.approved": "подтверждён",
    "profile.status.denied": "отклонён",
    "profile.val.linked": (
        "Riot ID: **{riot}**{status}\n"
        "Ранг: {rank} · {rr} RR · Пик: {peak}\n"
        "Роль: {role}"
    ),
    "profile.steam.line": "Steam: `{steam}`",
    "profile.dota.friend": "Friend ID: `{friend}`",
    # CS2 (Faceit)
    "profile.cs2.linked": "Faceit: **{nick}**{status}",
    "profile.cs2.rank": "Уровень {level} · {elo} elo",
    "profile.cs2.empty": "Укажите ваш ник Faceit для регистрации.",
    "profile.cs2.pending": "Faceit **{nick}** отправлен на проверку админу.",
    "profile.cs2.unchanged": "По-прежнему **{nick}** — статус проверки не изменился.",
    # Dota 2 (OpenDota)
    "profile.dota.linked": "Friend ID: `{friend}`{status}",
    "profile.dota.rank": "Ранг: {rank}",
    "profile.dota.unranked": "Без ранга",
    "profile.dota.pending": "Friend id **{friend}** отправлен на проверку админу.",
    "profile.dota.unchanged": "По-прежнему **{friend}** — статус проверки не изменился.",
    # привязка / отвязка / основная игра
    "profile.link.empty": "Укажите Steam для привязки.",
    "profile.link.done": "Steam **{steam}** привязан.",
    "profile.unlink.opt.valorant": "Valorant (Riot ID)",
    "profile.unlink.opt.cs2": "CS2 (Faceit)",
    "profile.unlink.opt.dota": "Dota 2 (friend id)",
    "profile.unlink.opt.steam": "Steam",
    "profile.unlink.nothing": "Здесь нечего отвязывать.",
    "profile.unlink.done": "Отвязано: **{what}**.",
    "profile.main.done": "Основная игра: **{game}**.",

    # ----------------------------------------------------------- статистика ---
    "stats.none": "Статистики пока нет.",
    "stats.title": "Ваша статистика",
    "stats.played": "Сыграно",
    "stats.wl": "П/П",
    "stats.mvps": "MVP",
    "stats.leaderboard.title": "Таблица лидеров",
    "stats.top": "Топ {n}",
    "stats.leader_line": "{rank}. {name} — побед: {wins}",

    # ------------------------------------------------------------ очередь ---
    "queue.none": "У этого кастома нет очереди.",
    "queue.empty": "_пусто_",
    "queue.header": "**Очередь кастома #{custom_id}** ({n}/{size})",
    "queue.waitlist": "\n**Лист ожидания:** {members}",

    # --------------------------------------------------------------- язык ---
    "lang.changed": "Язык сервера установлен: **{language}**.",
    "lang.unchanged": "Язык сервера уже **{language}**.",
    "lang.unknown": "Неизвестный язык `{lang}`. Доступны: {available}.",
    "lang.name.en": "английский",
    "lang.name.ru": "русский",

    # ----------------------------------------------------- описания команд ---
    "cmd.panel.desc": "Разместить живую панель управления в этом канале.",
    "cmd.panel.tier": "Какую панель разместить. По умолчанию — настроенная для этого канала.",
    "cmd.panel.choice.player": "Кастомы — для всех",
    "cmd.panel.choice.admin": "Админ",
    "cmd.panel.choice.superadmin": "Суперадмин",

    "cmd.language.desc": "Задать язык бота на этом сервере (суперадмин).",
    "cmd.language.param": "Язык для всех сообщений на этом сервере.",

    "cmd.custom.create.desc": "Создать кастом (админ, в канале конфигурации).",
    "cmd.custom.create.name": "Название кастома",
    "cmd.custom.create.format": "BO1/BO3/BO5",
    "cmd.custom.create.start": "ЧЧ:ММ (время сервера) или ISO — пусто = начать сейчас",
    "cmd.custom.create.maps": "Пул через запятую или `competitive` (пусто — все включённые карты)",
    "cmd.custom.create.team_size": "Игроков в команде: 1 (1v1) … 5 (5v5). По умолчанию 5.",
    "cmd.custom.create.draft": "Как драфтить игроков: змейкой или по одному. По умолчанию змейкой.",
    "cmd.custom.create.captains": "Как выбираются капитаны при старте. По умолчанию случайно.",
    "cmd.custom.create.game": (
        "Для какой игры этот кастом. По умолчанию Valorant. "
        "CS2 — только BO1; в Dota 2 нет вето карт."
    ),
    "cmd.custom.register.desc": "Записаться на кастом по id.",
    "cmd.custom.leave.desc": "Выйти из кастома по id.",
    "cmd.custom.list.desc": "Список активных кастомов.",
    "cmd.custom.transfer.desc": "Передать владение кастомом.",
    "cmd.custom.delete.desc": "Удалить кастом по id (владелец/суперадмин).",
    "cmd.custom.delete.force": "Обход защиты от удаления идущей игры (суперадмин)",
    "cmd.custom.prune.desc": "Удалить ВСЕ кастомы (суперадмин).",

    "cmd.match.start.desc": "Запустить кастом целиком: капитаны → драфт → вето.",
    "cmd.match.forcestart.desc": "Ручной старт: начать текущим составом записавшихся.",
    "cmd.match.custom_id": "Кастом для запуска",
    "cmd.match.captains": "Переопределить способ выбора капитанов только для этого запуска",
    "cmd.match.captain_a": "(только вручную) капитан Команды A",
    "cmd.match.captain_b": "(только вручную) капитан Команды B",
    "cmd.match.readycheck.desc": "Проверка готовности: каждый из основы должен подтвердить.",
    "cmd.match.readycheck.custom_id": "Кастом для проверки",
    "cmd.match.result.desc": "Внести результат карты (капитан или админ).",
    "cmd.match.partycode.desc": (
        "Задать/обновить код лобби, IP сервера или название лобби (любой участник). Виден всем."
    ),
    "cmd.match.partycode.custom_id": "Кастом, к матчу которого это относится",
    "cmd.match.partycode.code": "Код лобби/группы, IP сервера для CS2, или название лобби для Dota 2",
    "cmd.match.partycode.password": "(только Dota 2) пароль лобби",
    "cmd.match.end.desc": "Завершить матч: отметить готовым и удалить его каналы.",
    "cmd.match.end.custom_id": "Кастом, матч которого завершить",
    "cmd.match.end.force": "Завершить, даже если результат никто не внёс (админ)",

    "cmd.maps.list.desc": "Показать пул карт сервера.",
    "cmd.maps.seed.desc": "Загрузить стандартный пул для игры (по умолчанию Valorant).",
    "cmd.maps.competitive.desc": "Задать соревновательный пул (админ). Пусто — очистить.",
    "cmd.maps.competitive.maps": "Карты текущей ротации через запятую — пусто, чтобы очистить",
    "cmd.maps.game": "Пул карт какой игры. По умолчанию Valorant.",
    "cmd.maps.add.desc": "Добавить карту.",
    "cmd.maps.remove.desc": "Удалить карту.",
    "cmd.maps.toggle.desc": "Включить/выключить карту.",

    "cmd.admin.grant.desc": "Выдать роль бота (админ/суперадмин — только суперадмин).",
    "cmd.admin.revoke.desc": "Снять роль бота.",
    "cmd.admin.audit.desc": "Посмотреть последние записи журнала.",
    "cmd.admin.ban.desc": "Запретить игроку записываться на будущие игры.",
    "cmd.admin.unban.desc": "Снять бан с игрока.",
    "cmd.admin.bans.desc": "Список забаненных игроков.",
    "cmd.admin.notify_role.desc": "Установить (или сбросить) роль, которую упоминают при открытии кастома.",
    "cmd.admin.notify_role.param": "Роль для упоминания (не указывайте, чтобы сбросить).",

    "cmd.profile.register.desc": (
        "Зарегистрировать профиль с вашим Riot ID — требует одобрения админа."
    ),
    "cmd.profile.register.riot_id": "Ваш Riot ID, например TenZ#NA1",
    "cmd.profile.register.main_role": "Предпочитаемая роль (необязательно)",
    "cmd.profile.unregister.desc": "Удалить ваш зарегистрированный Riot ID.",
    "cmd.profile.refresh.desc": "Обновить ранги во всех играх, где вы одобрены.",
    "cmd.profile.view.desc": "Посмотреть профиль игрока.",
    "cmd.register_cs2.desc": "Зарегистрировать ник CS2 Faceit — с проверкой админом.",
    "cmd.register_cs2.nick": "Ваш ник Faceit",
    "cmd.register_dota.desc": "Зарегистрировать Dota 2 friend id — с проверкой админом.",
    "cmd.register_dota.friend": "Ваш внутриигровой Dota 2 Friend ID (число)",
    "cmd.link.desc": "Привязать косметический Steam-хендл к профилю.",
    "cmd.link.steam": "Ваш Steam: ник, ID или ссылка на профиль",
    "cmd.link.friend": "Dota 2 friend ID в игре (необязательно)",
    "cmd.unlink.desc": "Удалить привязанную личность из профиля.",
    "cmd.unlink.what": "Что отвязать",
    "cmd.setmain.desc": "Указать основную игру — она задаёт акцент карточки профиля.",
    "cmd.setmain.game": "Ваша основная игра",

    "cmd.stats.me.desc": "Ваша статистика.",
    "cmd.stats.leaderboard.desc": "Таблица лидеров по победам.",

    "cmd.queue.status.desc": "Показать статус очереди кастома.",

    "cmd.help.desc": "Показать список всех доступных вам команд.",

    # -------------------------------------------------------------- помощь ---
    "help.title": "\U0001f4d6 Гид по командам Customly",
    "help.desc": "Всё, что вы можете сделать, по разделам — пункты для "
                 "админов/суперадминов видны только тем, у кого есть эта роль.",
    "help.section.customs": "\U0001f3ae Кастомы",
    "help.section.match": "⚔️ Матч",
    "help.section.queue": "\U0001f4cb Очередь",
    "help.section.maps": "\U0001f5fa️ Карты",
    "help.section.profile": "\U0001f464 Профиль и ранг",
    "help.section.stats": "\U0001f4ca Статистика",
    "help.section.panel": "\U0001f39b️ Панель и язык",
    "help.section.admin": "\U0001f6e1️ Админ",
    "help.footer": "Введите команду, чтобы увидеть её параметры и варианты выбора.",
}
