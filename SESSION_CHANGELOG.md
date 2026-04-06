# Журнал изменений этой сессии

Этот файл фиксирует изменения, которые были внесены в проект в рамках текущей длинной сессии до момента создания документации.

Важно:
- репозиторий в текущей папке не инициализирован как Git-репозиторий;
- поэтому журнал ниже является ручным техническим логом изменений;
- для последующих доработок лучше опираться одновременно на этот файл и на [README_AI.md](C:\REPO\circletable\README_AI.md).

## 1. Исправления живого чата и визуального ритма

Сделано в ранней части сессии:
- устранено дублирование сообщений в чате;
- исправлен жизненный цикл WebSocket и повторные переподключения;
- добавлена защита от повторного применения одинаковых событий через `event_id`;
- анимация печати и появления реплик сделана спокойнее;
- пузыри реплик приведены к более стабильной горизонтальной форме;
- интерфейс переведён на русский язык;
- расширены базовые роли и визуальные тексты управления.

Основные затронутые файлы:
- [backend/main.py](C:\REPO\circletable\backend\main.py)
- [backend/debate.py](C:\REPO\circletable\backend\debate.py)
- [frontend/src/App.jsx](C:\REPO\circletable\frontend\src\App.jsx)
- [frontend/src/hooks/useWebSocket.js](C:\REPO\circletable\frontend\src\hooks\useWebSocket.js)
- [frontend/src/hooks/useTypewriter.js](C:\REPO\circletable\frontend\src\hooks\useTypewriter.js)
- [frontend/src/components/SpeechBubble.jsx](C:\REPO\circletable\frontend\src\components\SpeechBubble.jsx)
- [frontend/src/index.css](C:\REPO\circletable\frontend\src\index.css)

## 2. Расширение ролей и специализаций персонажей

Добавлена двухосевая модель персонажа:
- `характер`;
- `профессиональный профиль / специализация`.

Что появилось:
- большой каталог профессиональных специализаций;
- расширенный набор характеров;
- поддержка более серьёзных и более игровых архетипов;
- показ специализации в интерфейсе;
- включение специализации в системный промпт агента.

Затронутые файлы:
- [frontend/src/constants/roles.js](C:\REPO\circletable\frontend\src\constants\roles.js)
- [frontend/src/constants/specialties.js](C:\REPO\circletable\frontend\src\constants\specialties.js)
- [frontend/src/components/ControlPanel.jsx](C:\REPO\circletable\frontend\src\components\ControlPanel.jsx)
- [frontend/src/components/ChatPanel.jsx](C:\REPO\circletable\frontend\src\components\ChatPanel.jsx)
- [frontend/src/components/Mascot.jsx](C:\REPO\circletable\frontend\src\components\Mascot.jsx)
- [backend/agents.py](C:\REPO\circletable\backend\agents.py)
- [backend/debate.py](C:\REPO\circletable\backend\debate.py)
- [backend/context.py](C:\REPO\circletable\backend\context.py)
- [backend/main.py](C:\REPO\circletable\backend\main.py)

## 3. Поддержка Ollama и запуск проекта на другом компьютере

Добавлен комплект сценариев запуска и обслуживания:
- [00_check_ollama.bat](C:\REPO\circletable\00_check_ollama.bat)
- [01_prepare_ollama_models.bat](C:\REPO\circletable\01_prepare_ollama_models.bat)
- [02_refresh_project_models.bat](C:\REPO\circletable\02_refresh_project_models.bat)
- [03_start_round_table.bat](C:\REPO\circletable\03_start_round_table.bat)
- [start_core.bat](C:\REPO\circletable\start_core.bat)
- [start.bat](C:\REPO\circletable\start.bat)
- [refresh_project_models.ps1](C:\REPO\circletable\refresh_project_models.ps1)

Что изменилось по смыслу:
- проект умеет автоматически читать локальный список моделей `Ollama` через API `/api/tags`;
- для пользователя появился более удобный сценарий запуска через `start.bat`;
- появилась возможность вручную обновить список моделей проекта без ручного редактирования файлов.

## 4. Переход от бесконечного чата к комнатам и сессиям

Самый крупный блок изменений этой сессии.

В проект добавлены новые сущности:
- комнаты;
- сессии;
- раунды;
- хроника сессии;
- профили персонажей;
- активные участники и скамейка;
- наблюдатель `Хрономант`.

Новая постоянная база:
- SQLite на пути [backend/data/circletable.db](C:\REPO\circletable\backend\data\circletable.db)

Создана и встроена новая серверная инфраструктура:
- [backend/storage.py](C:\REPO\circletable\backend\storage.py)
- [backend/chronomancer.py](C:\REPO\circletable\backend\chronomancer.py)
- [backend/debate.py](C:\REPO\circletable\backend\debate.py)
- [backend/main.py](C:\REPO\circletable\backend\main.py)

Что теперь умеет проект:
- хранить комнаты и переключаться между ними;
- сохранять текущую сессию;
- ставить беседу на паузу в безопасной точке;
- продолжать после паузы;
- завершать сессию;
- добавлять персонажа из инвентаря;
- создавать нового персонажа и сажать за стол;
- отправлять персонажа на скамейку и возвращать обратно;
- принимать пользовательский вопрос прямо в текущую комнату;
- работать в режимах `Бесконечный`, `С подсказками`, `Автофинал`;
- проводить межраундовый обзор через `Хрономанта`;
- обновлять видимые характеристики персонажей.

## 5. Новый интерфейс управления комнатой

На фронтенде переработан сценарий управления:
- отдельный drawer комнат;
- отдельный drawer инвентаря персонажей;
- обновлённая нижняя панель управления сессией;
- поддержка паузы, финального раунда и пользовательских вопросов;
- отображение рекомендаций и активности наблюдателя;
- отображение инвентаря, скамейки и активных участников.

Ключевые файлы:
- [frontend/src/App.jsx](C:\REPO\circletable\frontend\src\App.jsx)
- [frontend/src/components/ControlPanel.jsx](C:\REPO\circletable\frontend\src\components\ControlPanel.jsx)
- [frontend/src/components/RoomsDrawer.jsx](C:\REPO\circletable\frontend\src\components\RoomsDrawer.jsx)
- [frontend/src/components/InventoryDrawer.jsx](C:\REPO\circletable\frontend\src\components\InventoryDrawer.jsx)
- [frontend/src/components/ChatPanel.jsx](C:\REPO\circletable\frontend\src\components\ChatPanel.jsx)
- [frontend/src/index.css](C:\REPO\circletable\frontend\src\index.css)

## 6. Хрономант

Добавлен отдельный наблюдатель:
- файл: [backend/chronomancer.py](C:\REPO\circletable\backend\chronomancer.py)

Его роль:
- читать хронику и полный лог только завершённого раунда;
- строить краткую сводку раунда;
- обновлять хронику сессии;
- выдавать рекомендации пользователю;
- обновлять 5 характеристик персонажей;
- выдавать ачивки и оценку полезности;
- предлагать продолжать, финализировать или завершать разговор.

Если модель наблюдателя недоступна:
- включается эвристический fallback-режим.

## 7. Миграция на быстрый дефолт для тестов

После проблем с тяжёлыми локальными моделями по умолчанию была изменена стратегия выбора:
- теперь приоритет отдан быстрым `Ollama Cloud`-моделям;
- основной приоритет для тестов: `gemini-3-flash-preview:cloud`.

Ключевые файлы:
- [backend/defaults.py](C:\REPO\circletable\backend\defaults.py)
- [backend/storage.py](C:\REPO\circletable\backend\storage.py)
- [frontend/src/components/ControlPanel.jsx](C:\REPO\circletable\frontend\src\components\ControlPanel.jsx)

Что дополнительно сделано:
- bootstrap обновляет системных персонажей на быстрый дефолт;
- bootstrap подтягивает быстрый observer provider/model в комнаты;
- новые персонажи во фронтенде создаются с тем же быстрым дефолтом.

## 8. Восстановление незавершённых сессий

Исправлено поведение после перезапуска приложения:
- незавершённые комнаты больше не выглядят как “зависшие активные”;
- при старте они нормализуются в состояние `На паузе`;
- команды `Закругляться`, `Финальный раунд` и пользовательский вопрос теперь умеют работать и для восстановленной паузы.

Основные файлы:
- [backend/storage.py](C:\REPO\circletable\backend\storage.py)
- [backend/main.py](C:\REPO\circletable\backend\main.py)
- [backend/debate.py](C:\REPO\circletable\backend\debate.py)

## 9. Кнопка «Завершить сеанс»

Добавлено управление мягким завершением dev-сеанса из интерфейса:
- кнопка рядом со статусом `На связи`;
- backend-маршрут `POST /api/system/shutdown`;
- helper-скрипт закрытия окон запуска;
- отдельный `.bat` для ручного вызова.

Файлы:
- [frontend/src/App.jsx](C:\REPO\circletable\frontend\src\App.jsx)
- [frontend/src/index.css](C:\REPO\circletable\frontend\src\index.css)
- [backend/main.py](C:\REPO\circletable\backend\main.py)
- [shutdown_round_table.ps1](C:\REPO\circletable\shutdown_round_table.ps1)
- [04_shutdown_round_table.bat](C:\REPO\circletable\04_shutdown_round_table.bat)

Текущее поведение:
- маршрут сохраняет активную сессию в безопасное состояние;
- пишет событие завершения;
- нормализует незавершённые сессии;
- запускает PowerShell helper, который закрывает окна `Backend :8000` и `Frontend :5173`.

## 10. Что было проверено в течение сессии

Многократно проверялось:
- сборка фронтенда через `npm run build`;
- базовая компиляция backend через `python -m py_compile`;
- живое открытие приложения в браузере;
- загрузка комнат;
- видимость и работа паузы;
- выбор быстрого cloud-дефолта вместо тяжёлого локального.

Отдельно проверено:
- dry-run для [shutdown_round_table.ps1](C:\REPO\circletable\shutdown_round_table.ps1)

Не выполнялось автоматически:
- реальный клик по кнопке `Завершить сеанс`, потому что он завершает dev-сеанс и закрывает окна.

## 11. Известные оговорки на момент создания этого файла

- Часть старых сообщений в базе может оставаться на английском, если они были сгенерированы до ужесточения русских промптов.
- В корне проекта сейчас нет Git-истории; этот журнал нужен как ручная замена истории коммитов.
- Полный destructive test кнопки `Завершить сеанс` желательно выполнить отдельно вручную.
- После последних патчей по восстановленной паузе стоит повторно прогнать быстрые технические проверки перед следующей большой доработкой.

## 12. Что читать дальше

Для продолжения работы следующему ИИ сначала открыть:
- [README_AI.md](C:\REPO\circletable\README_AI.md)
- [backend/main.py](C:\REPO\circletable\backend\main.py)
- [backend/debate.py](C:\REPO\circletable\backend\debate.py)
- [backend/storage.py](C:\REPO\circletable\backend\storage.py)
- [backend/chronomancer.py](C:\REPO\circletable\backend\chronomancer.py)
- [frontend/src/App.jsx](C:\REPO\circletable\frontend\src\App.jsx)
- [frontend/src/components/ControlPanel.jsx](C:\REPO\circletable\frontend\src\components\ControlPanel.jsx)
