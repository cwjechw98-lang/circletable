# README для следующего ИИ

Этот файл нужен как технический handoff для следующего ИИ, который будет дорабатывать проект.

## 1. Что это за проект

`circletable` — это локальное приложение с фронтендом на Vite/React и backend на FastAPI, где несколько ИИ-персонажей обсуждают заданную тему за виртуальным круглым столом.

Текущее состояние проекта уже ушло далеко от простого бесконечного чата. Сейчас здесь есть:
- комнаты;
- сессии;
- раунды;
- сохранённые персонажи;
- скамейка;
- наблюдатель `Хрономант`;
- межраундовая аналитика;
- восстановление сессии после перезапуска.

## 2. Главные точки входа

Backend:
- [backend/main.py](backend/main.py)
- [backend/debate.py](backend/debate.py)
- [backend/storage.py](backend/storage.py)
- [backend/chronomancer.py](backend/chronomancer.py)
- [backend/casting.py](backend/casting.py)
- [backend/defaults.py](backend/defaults.py)

Frontend:
- [frontend/src/App.jsx](frontend/src/App.jsx)
- [frontend/src/components/ControlPanel.jsx](frontend/src/components/ControlPanel.jsx)
- [frontend/src/components/RoomsDrawer.jsx](frontend/src/components/RoomsDrawer.jsx)
- [frontend/src/components/InventoryDrawer.jsx](frontend/src/components/InventoryDrawer.jsx)
- [frontend/src/components/CastingAssistantModal.jsx](frontend/src/components/CastingAssistantModal.jsx)
- [frontend/src/components/ChatPanel.jsx](frontend/src/components/ChatPanel.jsx)
- [frontend/src/index.css](frontend/src/index.css)
- [frontend/index.html](frontend/index.html)

## 3. Как запускать проект

Основной пользовательский сценарий:
- [start.bat](start.bat)

Что он делает:
- проверяет `Ollama`;
- пытается подготовить стартовую локальную модель;
- запускает backend и frontend через [start_core.bat](start_core.bat).

Полезные вспомогательные сценарии:
- [00_check_ollama.bat](00_check_ollama.bat) — проверка `Ollama`
- [01_prepare_ollama_models.bat](01_prepare_ollama_models.bat) — установка стартовой локальной модели
- [02_refresh_project_models.bat](02_refresh_project_models.bat) — обновление списка моделей в проекте
- [03_start_round_table.bat](03_start_round_table.bat) — алиас запуска
- [04_shutdown_round_table.bat](04_shutdown_round_table.bat) — ручное завершение dev-сеанса

Обычные адреса:
- backend: `http://127.0.0.1:43117`
- frontend: `http://127.0.0.1:43118`

## 4. Где хранится состояние

Постоянная база:
- [backend/data/circletable.db](backend/data/circletable.db)

Таблицы:
- `app_state`
- `character_profiles`
- `rooms`
- `room_participants`
- `sessions`
- `rounds`
- `messages`
- `room_events`
- `observer_reviews`

### Что где хранится

`character_profiles`
- глобальные сохранённые профили персонажей;
- не привязаны к одной комнате;
- не удаляются при удалении комнаты.

`rooms`
- постоянные комнаты;
- их название;
- режим наблюдателя;
- текущая сводка;
- последняя тема.

`sessions`
- конкретный запуск внутри комнаты;
- тема;
- статус;
- хроника;
- сигналы финализации;
- число продлений.

`room_participants`
- экземпляры персонажей внутри конкретной комнаты;
- статус `active` или `benched`;
- снимок имени, роли, специализации и модели.

`observer_reviews`
- межраундовые обзоры Хрономанта;
- сводка;
- дельты характеристик;
- ачивки;
- рекомендации по финализации.

## 5. Основные сущности проекта

### Комната
Долгоживущая сущность. Содержит состав, историю и последовательность сессий.

### Сессия
Один запуск внутри комнаты.

Поддерживаемые статусы:
- `idle`
- `running`
- `pause_requested`
- `paused`
- `observer_review`
- `finalizing`
- `stopped`
- `completed`

### Раунд
Один полный проход по активным участникам.

### Хроника
Короткая накопительная сводка по всей сессии.

### Профиль персонажа
Сохранённый “инвентарный” персонаж, который можно повторно сажать за стол.

### Хрономант
Отдельный наблюдатель, который анализирует завершённый раунд и влияет на следующий шаг беседы.

## 6. Что уже умеет backend

### REST

Реализованы маршруты:
- `GET /api/providers`
- `POST /api/providers/refresh`
- `POST /api/system/shutdown`
- `GET /api/rooms`
- `POST /api/rooms`
- `GET /api/rooms/{roomId}`
- `PATCH /api/rooms/{roomId}`
- `DELETE /api/rooms/{roomId}`
- `GET /api/rooms/{roomId}/sessions`
- `GET /api/characters`
- `POST /api/characters`
- `PATCH /api/characters/{characterId}`
- `DELETE /api/characters/{characterId}`
- `GET /api/rooms/{roomId}/inventory`
- `GET /api/sessions/{sessionId}`
- `POST /api/sessions/{sessionId}/open`
- `POST /api/sessions/{sessionId}/continue`
- `PATCH /api/sessions/{sessionId}`
- `DELETE /api/sessions/{sessionId}`
- `GET /api/sessions/{sessionId}/export.md`
- `POST /api/casting/suggest`
- `GET /api/lab/profiles` — сводка досье всех сохранённых персонажей (профиль + карьерные счётчики + число оценок Хрономанта)
- `GET /api/lab/profiles/{profileId}` — полное досье: текущие статы, суммарные приросты, стартовые значения, эволюция по раундам (`delta`/`values`), таймлайн ачивок, персональные заметки Хрономанта

### WebSocket-команды

Поддерживаются:
- `get_providers`
- `load_room`
- `load_session`
- `continue_session`
- `start_session`
- `pause_session`
- `resume_session`
- `stop_session`
- `request_wrap`
- `request_final_round`
- `submit_user_question`
- `add_participant_from_inventory`
- `create_and_add_participant`
- `bench_participant`
- `restore_participant`
- `observer_mode_changed`

Поддержка старых команд для обратной совместимости тоже оставлена:
- `start`
- `stop`
- `reset`
- `update_agents`

### WebSocket-события

Основные новые события:
- `room_loaded`
- `session_state`
- `pause_requested`
- `paused`
- `resumed`
- `round_completed`
- `observer_review_started`
- `observer_review_completed`
- `observer_suggestion`
- `participant_stats_updated`
- `participant_roster_changed`
- `user_question_accepted`
- `session_completed`
- `session_final_summary`
- `app_shutdown_requested`

## 7. Что уже умеет фронтенд

### Основной экран

На экране постоянно видны:
- стол с активными участниками;
- чат;
- панель управления;
- статус подключения;
- кнопка `Завершить сеанс`.

### Drawer комнат

Файл:
- [frontend/src/components/RoomsDrawer.jsx](frontend/src/components/RoomsDrawer.jsx)

Функции:
- создание комнаты;
- выбор комнаты;
- переименование;
- удаление.
- раскрытие списка сохранённых диалогов внутри комнаты;
- поиск по диалогам;
- чтение завершённой или остановленной сессии без запуска генерации;
- продолжение выбранной сессии;
- переименование, удаление и экспорт диалога в Markdown.

### Кастинг-помощник

Файлы:
- [backend/casting.py](backend/casting.py)
- [frontend/src/components/CastingAssistantModal.jsx](frontend/src/components/CastingAssistantModal.jsx)

Функции:
- кнопка `Помощь` рядом с темой открывает окно подбора состава;
- пользователь выбирает количество персонажей;
- backend просит быструю модель предложить имена, роли, специализации, образы и краткие заметки;
- перед посадкой за стол предложения можно отредактировать или удалить;
- если модель недоступна, включается эвристический fallback-состав.

### Drawer инвентаря

Файл:
- [frontend/src/components/InventoryDrawer.jsx](frontend/src/components/InventoryDrawer.jsx)

Функции:
- активные участники;
- скамейка;
- все сохранённые профили;
- добавление за стол;
- отправка на скамейку;
- возврат;
- сохранение/обновление профиля;
- удаление профиля.

### Лаборатория персонажей (Фаза 1)

Файлы:
- [backend/http_api/routes_lab.py](backend/http_api/routes_lab.py)
- [frontend/src/components/LabDrawer.jsx](frontend/src/components/LabDrawer.jsx)
- [frontend/src/components/Sparkline.jsx](frontend/src/components/Sparkline.jsx)

Функции:
- кнопка `Лаборатория` в панели управления открывает drawer с досье всех персонажей;
- карточка в списке: спрайт, роль/специальность, модель, карьерная строка (сессий/реплик/оценок);
- детальное досье: 5 показателей со спарклайнами эволюции по раундам (данные из `observer_reviews.stats_delta_json`, восстановление стартовых значений от текущих статов минус сумма дельт);
- таймлайн ачивок Хрономанта с номером раунда и причиной;
- персональные заметки Хрономанта (`comments_json` по profile_id);
- карьерный блок: сессии, раунды, реплики (из `messages` через `room_participants`), число оценок;
- редактирование профиля по-прежнему в Инвентаре — Лаборатория пока read-only.

### Панель управления

Файл:
- [frontend/src/components/ControlPanel.jsx](frontend/src/components/ControlPanel.jsx)

Функции:
- запуск сессии;
- пауза;
- продолжение;
- остановка;
- `Закругляться`;
- `Финальный раунд`;
- выбор режима Хрономанта;
- создание нового персонажа;
- отправка пользовательского вопроса;
- ручное обновление списка моделей;
- открытие лаборатории персонажей.

Важно по смыслу кнопок:
- `Закругляться` — мягкий сигнал участникам двигаться к выводу.
- `Финальный раунд` — следующий раунд должен подвести итог; после завершения сессия остаётся в архиве комнаты.
- `Остановить` — прервать текущую сессию на безопасной точке без финального раунда.

## 8. Текущая стратегия по моделям

### Главное правило

Для тестов и дефолтов больше нельзя опираться на тяжёлые локальные модели, которые висят на CPU и съедают много ОЗУ.

Текущее поведение:
- приоритет отдан быстрым `Ollama Cloud`-моделям;
- основной дефолт: `gemini-3-flash-preview:cloud`.

Ключевой файл:
- [backend/defaults.py](backend/defaults.py)

Дополнительно:
- bootstrap базы обновляет системных персонажей на быстрый дефолт;
- observer provider/model тоже подхватываются из быстрого набора;
- фронтенд-билдер новых персонажей использует тот же дефолт.

### Важный нюанс

Сценарии `00/01/start.bat` по-прежнему умеют готовить локальную `Ollama`-модель как запасной сценарий. Но это не отменяет того, что внутренняя стратегия по умолчанию теперь ориентирована на быстрый cloud-вариант.

## 9. Хрономант

Файл:
- [backend/chronomancer.py](backend/chronomancer.py)

### Что получает на вход
- тему сессии;
- хронику сессии;
- полный лог завершённого раунда;
- активный состав;
- события изменения состава.

### Что возвращает
- обновлённую хронику;
- сводку раунда;
- комментарий для пользователя;
- рекомендации по участникам;
- дельты 5 характеристик;
- ачивки;
- рекомендацию по финализации.

### Режимы
- `manual` — пользователь сам управляет финалом;
- `suggest` — Хрономант советует, но не принимает решение сам;
- `auto` — Хрономант сам ведёт финализацию с ограничением на продления.

## 10. Пауза и восстановление

Файлы:
- [backend/debate.py](backend/debate.py)
- [backend/storage.py](backend/storage.py)
- [backend/main.py](backend/main.py)

Текущая логика:
- пауза не рвёт поток в середине сообщения;
- реальная остановка происходит в безопасной точке;
- после перезапуска незавершённые сессии переводятся в `paused`;
- UI показывает такие комнаты как `На паузе`;
- сигналы `Закругляться`, `Финальный раунд` и пользовательский вопрос поддерживаются и для восстановленной паузы.

## 11. Завершение dev-сеанса

Файлы:
- [backend/main.py](backend/main.py)
- [shutdown_round_table.ps1](shutdown_round_table.ps1)
- [04_shutdown_round_table.bat](04_shutdown_round_table.bat)
- [frontend/src/App.jsx](frontend/src/App.jsx)

Как это работает:
- пользователь нажимает `Завершить сеанс`;
- фронтенд вызывает `POST /api/system/shutdown`;
- backend переводит активную сессию в безопасное состояние;
- backend пишет событие завершения;
- backend запускает helper-скрипт;
- helper закрывает окна `Backend :43117` и `Frontend :43118`.

Что важно помнить:
- полноценный destructive test этого сценария лучше делать вручную отдельно;
- автоматическая проверка в рамках сессии делалась только через dry-run helper-скрипта.

## 12. Что читать в первую очередь перед новой доработкой

Если нужно быстро войти в проект, порядок такой:
1. [SESSION_CHANGELOG.md](SESSION_CHANGELOG.md)
2. [backend/main.py](backend/main.py)
3. [backend/debate.py](backend/debate.py)
4. [backend/storage.py](backend/storage.py)
5. [backend/chronomancer.py](backend/chronomancer.py)
6. [backend/casting.py](backend/casting.py)
7. [backend/defaults.py](backend/defaults.py)
8. [frontend/src/App.jsx](frontend/src/App.jsx)
9. [frontend/src/components/ControlPanel.jsx](frontend/src/components/ControlPanel.jsx)
10. [frontend/src/components/InventoryDrawer.jsx](frontend/src/components/InventoryDrawer.jsx)
11. [frontend/src/components/RoomsDrawer.jsx](frontend/src/components/RoomsDrawer.jsx)
12. [frontend/src/components/CastingAssistantModal.jsx](frontend/src/components/CastingAssistantModal.jsx)

## 13. Что ещё не доведено до идеала

На момент создания файла стоит иметь в виду:
- в базе могут оставаться старые исторические сообщения на английском, если они были сгенерированы до ужесточения русских промптов;
- полный ручной прогон сценария `Завершить сеанс` ещё желательно сделать отдельно;
- лаборатория персонажей реализована в объёме Фазы 1 (read-only досье: эволюция статов, ачивки, заметки, карьера); впереди Фаза 2 (вкладка памяти: просмотр и сброс профильного графа) и Фаза 3 (клонирование для дуэлей, ДНК-экспорт/импорт);
- экспорт сейчас реализован как Markdown; PDF/проводник сохранения ещё не добавлены.

## 14. Рекомендуемые следующие шаги

Самые разумные следующие задачи:
- вручную прогнать сценарий `Завершить сеанс` до конца;
- Фаза 2 лаборатории: вкладка памяти персонажа (просмотр содержимого профильного графа и осознанный сброс памяти);
- Фаза 3 лаборатории: клонирование персонажа под другую модель для A/B-дуэли за одним столом; ДНК-экспорт/импорт профиля одним файлом;
- сделать более явные карточки персонажей с историей наблюдений;
- добавить экспорт комнаты целиком и, при необходимости, PDF-экспорт;
- расширить тесты на сценарии паузы, восстановления и финального раунда;
- при необходимости вычистить старые англоязычные исторические логи из базы.

## 15. Команды быстрой проверки

Backend:
```powershell
cd backend
venv\Scripts\python.exe -m py_compile main.py debate.py storage.py chronomancer.py casting.py defaults.py agents.py
```

Frontend:
```powershell
cd frontend
npm run build
```

Dry-run shutdown helper:
```powershell
powershell -ExecutionPolicy Bypass -File .\shutdown_round_table.ps1 -DelaySeconds 0 -DryRun
```

## 16. Визуальные ассеты

Подготовленные файлы:
- [assets/github-header.svg](assets/github-header.svg)
- [assets/github-header.png](assets/github-header.png)
- [assets/repo-social-preview.svg](assets/repo-social-preview.svg)
- [assets/repo-social-preview.png](assets/repo-social-preview.png)
- [frontend/public/social-preview.svg](frontend/public/social-preview.svg)
- [frontend/public/social-preview.png](frontend/public/social-preview.png)
- [frontend/public/favicon.svg](frontend/public/favicon.svg)
- [frontend/public/favicon.png](frontend/public/favicon.png)
- [RELEASE_README.md](RELEASE_README.md)
- [RELEASE_v0.1.0.md](RELEASE_v0.1.0.md)
- [CHANGELOG.md](CHANGELOG.md)

## 17. Последнее правило для следующего ИИ

Если вносишь изменения в логику комнат, сессий, паузы, восстановления, выбора моделей или Хрономанта:
- сначала обнови соответствующий раздел в этом файле;
- потом уже считай работу завершённой.
