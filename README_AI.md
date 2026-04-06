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
- [backend/main.py](C:\REPO\circletable\backend\main.py)
- [backend/debate.py](C:\REPO\circletable\backend\debate.py)
- [backend/storage.py](C:\REPO\circletable\backend\storage.py)
- [backend/chronomancer.py](C:\REPO\circletable\backend\chronomancer.py)
- [backend/defaults.py](C:\REPO\circletable\backend\defaults.py)

Frontend:
- [frontend/src/App.jsx](C:\REPO\circletable\frontend\src\App.jsx)
- [frontend/src/components/ControlPanel.jsx](C:\REPO\circletable\frontend\src\components\ControlPanel.jsx)
- [frontend/src/components/RoomsDrawer.jsx](C:\REPO\circletable\frontend\src\components\RoomsDrawer.jsx)
- [frontend/src/components/InventoryDrawer.jsx](C:\REPO\circletable\frontend\src\components\InventoryDrawer.jsx)
- [frontend/src/components/ChatPanel.jsx](C:\REPO\circletable\frontend\src\components\ChatPanel.jsx)
- [frontend/src/index.css](C:\REPO\circletable\frontend\src\index.css)
- [frontend/index.html](C:\REPO\circletable\frontend\index.html)

## 3. Как запускать проект

Основной пользовательский сценарий:
- [start.bat](C:\REPO\circletable\start.bat)

Что он делает:
- проверяет `Ollama`;
- пытается подготовить стартовую локальную модель;
- запускает backend и frontend через [start_core.bat](C:\REPO\circletable\start_core.bat).

Полезные вспомогательные сценарии:
- [00_check_ollama.bat](C:\REPO\circletable\00_check_ollama.bat) — проверка `Ollama`
- [01_prepare_ollama_models.bat](C:\REPO\circletable\01_prepare_ollama_models.bat) — установка стартовой локальной модели
- [02_refresh_project_models.bat](C:\REPO\circletable\02_refresh_project_models.bat) — обновление списка моделей в проекте
- [03_start_round_table.bat](C:\REPO\circletable\03_start_round_table.bat) — алиас запуска
- [04_shutdown_round_table.bat](C:\REPO\circletable\04_shutdown_round_table.bat) — ручное завершение dev-сеанса

Обычные адреса:
- backend: `http://localhost:8000`
- frontend: `http://localhost:5173`

## 4. Где хранится состояние

Постоянная база:
- [backend/data/circletable.db](C:\REPO\circletable\backend\data\circletable.db)

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
- `GET /api/characters`
- `POST /api/characters`
- `PATCH /api/characters/{characterId}`
- `DELETE /api/characters/{characterId}`
- `GET /api/rooms/{roomId}/inventory`

### WebSocket-команды

Поддерживаются:
- `get_providers`
- `load_room`
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
- [frontend/src/components/RoomsDrawer.jsx](C:\REPO\circletable\frontend\src\components\RoomsDrawer.jsx)

Функции:
- создание комнаты;
- выбор комнаты;
- переименование;
- удаление.

### Drawer инвентаря

Файл:
- [frontend/src/components/InventoryDrawer.jsx](C:\REPO\circletable\frontend\src\components\InventoryDrawer.jsx)

Функции:
- активные участники;
- скамейка;
- все сохранённые профили;
- добавление за стол;
- отправка на скамейку;
- возврат;
- сохранение/обновление профиля;
- удаление профиля.

### Панель управления

Файл:
- [frontend/src/components/ControlPanel.jsx](C:\REPO\circletable\frontend\src\components\ControlPanel.jsx)

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
- ручное обновление списка моделей.

## 8. Текущая стратегия по моделям

### Главное правило

Для тестов и дефолтов больше нельзя опираться на тяжёлые локальные модели, которые висят на CPU и съедают много ОЗУ.

Текущее поведение:
- приоритет отдан быстрым `Ollama Cloud`-моделям;
- основной дефолт: `gemini-3-flash-preview:cloud`.

Ключевой файл:
- [backend/defaults.py](C:\REPO\circletable\backend\defaults.py)

Дополнительно:
- bootstrap базы обновляет системных персонажей на быстрый дефолт;
- observer provider/model тоже подхватываются из быстрого набора;
- фронтенд-билдер новых персонажей использует тот же дефолт.

### Важный нюанс

Сценарии `00/01/start.bat` по-прежнему умеют готовить локальную `Ollama`-модель как запасной сценарий. Но это не отменяет того, что внутренняя стратегия по умолчанию теперь ориентирована на быстрый cloud-вариант.

## 9. Хрономант

Файл:
- [backend/chronomancer.py](C:\REPO\circletable\backend\chronomancer.py)

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
- [backend/debate.py](C:\REPO\circletable\backend\debate.py)
- [backend/storage.py](C:\REPO\circletable\backend\storage.py)
- [backend/main.py](C:\REPO\circletable\backend\main.py)

Текущая логика:
- пауза не рвёт поток в середине сообщения;
- реальная остановка происходит в безопасной точке;
- после перезапуска незавершённые сессии переводятся в `paused`;
- UI показывает такие комнаты как `На паузе`;
- сигналы `Закругляться`, `Финальный раунд` и пользовательский вопрос поддерживаются и для восстановленной паузы.

## 11. Завершение dev-сеанса

Файлы:
- [backend/main.py](C:\REPO\circletable\backend\main.py)
- [shutdown_round_table.ps1](C:\REPO\circletable\shutdown_round_table.ps1)
- [04_shutdown_round_table.bat](C:\REPO\circletable\04_shutdown_round_table.bat)
- [frontend/src/App.jsx](C:\REPO\circletable\frontend\src\App.jsx)

Как это работает:
- пользователь нажимает `Завершить сеанс`;
- фронтенд вызывает `POST /api/system/shutdown`;
- backend переводит активную сессию в безопасное состояние;
- backend пишет событие завершения;
- backend запускает helper-скрипт;
- helper закрывает окна `Backend :8000` и `Frontend :5173`.

Что важно помнить:
- полноценный destructive test этого сценария лучше делать вручную отдельно;
- автоматическая проверка в рамках сессии делалась только через dry-run helper-скрипта.

## 12. Что читать в первую очередь перед новой доработкой

Если нужно быстро войти в проект, порядок такой:
1. [SESSION_CHANGELOG.md](C:\REPO\circletable\SESSION_CHANGELOG.md)
2. [backend/main.py](C:\REPO\circletable\backend\main.py)
3. [backend/debate.py](C:\REPO\circletable\backend\debate.py)
4. [backend/storage.py](C:\REPO\circletable\backend\storage.py)
5. [backend/chronomancer.py](C:\REPO\circletable\backend\chronomancer.py)
6. [backend/defaults.py](C:\REPO\circletable\backend\defaults.py)
7. [frontend/src/App.jsx](C:\REPO\circletable\frontend\src\App.jsx)
8. [frontend/src/components/ControlPanel.jsx](C:\REPO\circletable\frontend\src\components\ControlPanel.jsx)
9. [frontend/src/components/InventoryDrawer.jsx](C:\REPO\circletable\frontend\src\components\InventoryDrawer.jsx)
10. [frontend/src/components/RoomsDrawer.jsx](C:\REPO\circletable\frontend\src\components\RoomsDrawer.jsx)

## 13. Что ещё не доведено до идеала

На момент создания файла стоит иметь в виду:
- в базе могут оставаться старые исторические сообщения на английском, если они были сгенерированы до ужесточения русских промптов;
- полный ручной прогон сценария `Завершить сеанс` ещё желательно сделать отдельно;
- у проекта пока нет Git-истории в этой папке, поэтому ручной журнал изменений обязателен;
- лаборатория персонажей, более глубокая meta-игра и расширенная долговременная RPG-эволюция пока не реализованы до конца.

## 14. Рекомендуемые следующие шаги

Самые разумные следующие задачи:
- вручную прогнать сценарий `Завершить сеанс` до конца;
- добавить отдельный экран/режим лаборатории персонажей;
- сделать более явные карточки персонажей с историей наблюдений;
- добавить экспорт комнаты или сессии в файл;
- расширить тесты на сценарии паузы, восстановления и финального раунда;
- при необходимости вычистить старые англоязычные исторические логи из базы.

## 15. Команды быстрой проверки

Backend:
```powershell
cd C:\REPO\circletable\backend
venv\Scripts\python.exe -m py_compile main.py debate.py storage.py chronomancer.py defaults.py agents.py
```

Frontend:
```powershell
cd C:\REPO\circletable\frontend
npm run build
```

Dry-run shutdown helper:
```powershell
powershell -ExecutionPolicy Bypass -File C:\REPO\circletable\shutdown_round_table.ps1 -DelaySeconds 0 -DryRun
```

## 16. Визуальные ассеты

Подготовленные файлы:
- [assets/github-header.svg](C:\REPO\circletable\assets\github-header.svg)
- [assets/repo-social-preview.svg](C:\REPO\circletable\assets\repo-social-preview.svg)
- [frontend/public/social-preview.svg](C:\REPO\circletable\frontend\public\social-preview.svg)
- [frontend/public/favicon.svg](C:\REPO\circletable\frontend\public\favicon.svg)
- [RELEASE_README.md](C:\REPO\circletable\RELEASE_README.md)

## 17. Последнее правило для следующего ИИ

Если вносишь изменения в логику комнат, сессий, паузы, восстановления, выбора моделей или Хрономанта:
- сначала обнови соответствующий раздел в этом файле;
- потом уже считай работу завершённой.
