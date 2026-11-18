# Adrobot · Campaign desk

Веб-обёртка для управления кампаниями Keitaro: создание кампании с GEO-фильтром и двумя потоками, список кампаний и редактор состава офферов.

## Возможности

- Создание кампании: название, ISO-код страны, ID оффера, домен, группа и источник.
- Два потока: указанное GEO отправляется на Google; остальной трафик уходит на оффер.
- Редактирование списка офферов в потоке Keitaro: добавить, удалить, изменить порядок основного оффера.
- Поиск, фильтр по статусу, пауза/возобновление и архивирование кампании в Keitaro.
- Переходы, конверсии, выручка и расход загружаются из отчёта Keitaro за всё время; CR и ROI рассчитываются на этих данных.
- API ключ Keitaro хранится только на сервере.
- Локальный режим для демонстрации без доступа к Keitaro: SQLite и примеры офферов.

## Запуск локально

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Откройте <http://127.0.0.1:8000>. Интерактивная документация API доступна по адресу <http://127.0.0.1:8000/docs>.

## Проверка

```bash
python -m pytest -q
```

Тесты проверяют CRUD кампаний, валидацию названий, импорт отчёта Keitaro и payload создания/редактирования потоков через изолированный HTTP mock. Они не обращаются к реальному трекеру.

## Настройка Keitaro

Создайте API-ключ с доступом к кампаниям и справочникам в Keitaro, затем укажите адрес инсталляции и ключ в `.env`:

```dotenv
KEITARO_BASE_URL=https://tracker.example.com
KEITARO_API_KEY=your-server-side-api-key
```

`KEITARO_BASE_URL` указывается без `/admin_api/v1`. Ключ не передаётся в браузер и не должен коммититься. Если параметры пусты, приложение остаётся в локальном демо-режиме. Справочники доменов, групп, источников и офферов загружаются из Admin API, когда соединение настроено.

Для миграции схемы используйте Alembic:

```bash
alembic upgrade head
alembic downgrade -1
```

SQLite-файл по умолчанию — `adrobot.db` в корне проекта. Для другого окружения задайте `DATABASE_URL`, например `postgresql+psycopg://user:pass@localhost/adrobot` и добавьте драйвер PostgreSQL в зависимости.

## Структура

```text
app/
  main.py          FastAPI endpoints
  models.py        SQLAlchemy модели
  schemas.py       Pydantic валидация
  keitaro.py       серверный клиент Keitaro Admin API
  static/          интерфейс без сборки фронтенда
migrations/        Alembic миграции
```

## API

- `GET /api/campaigns` — список, поддерживает `?q=`.
- `POST /api/campaigns` — создать кампанию и два потока.
- `GET /api/campaigns/{id}` / `PATCH /api/campaigns/{id}` — просмотр и изменение статуса/названия.
- `PUT /api/campaigns/{id}/offers` — сохранить набор офферов.
- `DELETE /api/campaigns/{id}` — удалить запись из рабочего пространства.
- `GET /api/offers`, `GET /api/resources/{domains|groups|sources}` — справочники.

## Примечание по Keitaro API

Интеграция использует Keitaro Admin API v1 для кампаний, потоков, справочников и отчёта `report/build`. Типы потоков, схема `offers` и фильтр страны соответствуют полям Admin API. Перед подключением к конкретному трекеру сверьте доступность Admin API для установленной редакции Keitaro. Локальный режим работает независимо от подключения.
