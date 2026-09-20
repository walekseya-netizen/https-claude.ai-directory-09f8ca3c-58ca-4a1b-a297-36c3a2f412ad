# Развёртывание сервиса

Сервис упакован в Docker-образ, слушает порт из переменной `PORT` (по умолчанию 8000)
и отвечает на `GET /health`. Ниже три готовых пути: от самого быстрого к самому
самостоятельному.

## Переменные окружения

| Переменная | Назначение | По умолчанию |
| --- | --- | --- |
| `KS_DATABASE_PATH` | Путь к файлу базы SQLite | `data/ks.sqlite3` |
| `KS_DATABASE_URL` | Подключение к PostgreSQL; если задано, SQLite не используется | пусто |
| `KS_API_KEY` | Ключ доступа к `/api/**`. Пустое значение — доступ без ключа | пусто |
| `PORT` | Порт HTTP-сервера | `8000` |

Если `KS_API_KEY` задан, каждый запрос к `/api/**` должен нести заголовок
`X-API-Key`. Эндпоинты `/health`, `/docs` и `/openapi.json` остаются открытыми,
а в Swagger UI появляется кнопка **Authorize** для подстановки ключа.
Ключ передаётся HTTP-заголовком, поэтому используйте только латиницу и цифры.

## 1. Render — быстрее всего, есть бесплатный план

1. Откройте <https://dashboard.render.com/blueprints> → **New Blueprint Instance**.
2. Подключите этот репозиторий и выберите ветку с сервисом.
3. Render прочитает `render.yaml`, соберёт `Dockerfile` и поднимет веб-сервис.
   Нажмите **Apply** и подождите первую сборку (около 5 минут).
4. Адрес вида `https://ks-service-xxxx.onrender.com` появится на странице сервиса.
5. Сгенерированный ключ доступа — в разделе **Environment**, переменная `KS_API_KEY`.

Проверка:

```bash
curl https://<ваш-адрес>/health
curl -H "X-API-Key: <ключ>" https://<ваш-адрес>/api/v1/ks2
```

Особенности бесплатного плана: сервис засыпает после 15 минут простоя, и первый
запрос после сна выполняется около минуты; диск недоступен, поэтому база лежит
в `/tmp` и очищается при перезапуске — для первого знакомства этого хватает.

### Постоянное хранение на Render

Документы переживут перезапуски, если подключить PostgreSQL — это работает
и на бесплатном плане:

```bash
cp deploy/render-postgres.yaml render.yaml
git commit -am "Постоянное хранение документов в PostgreSQL" && git push
```

Render увидит изменение блюпринта, создаст базу `ks-db` и сам подставит строку
подключения в переменную `KS_DATABASE_URL`. Бесплатная база Render живёт 30 дней;
дальше — план starter у базы либо внешний PostgreSQL (Neon, Supabase, свой сервер):
в этом случае блок `databases` не нужен, достаточно вписать строку подключения
в `KS_DATABASE_URL` на вкладке Environment.

Альтернатива без PostgreSQL — диск для SQLite: план **starter** у веб-сервиса,
`KS_DATABASE_PATH=/data/ks.sqlite3` и раскомментированный блок `disk` в `render.yaml`.

Документы, созданные до перехода, не потеряются — перенесите их выгрузкой
(см. «Резервные копии и перенос» ниже).

## 2. Fly.io — постоянный диск, оплата по потреблению

```bash
fly auth login
fly launch --no-deploy            # подхватит существующий fly.toml
fly volumes create ks_data --size 1 --region fra
fly secrets set KS_API_KEY=$(openssl rand -hex 16)
fly deploy
fly open /docs
```

База лежит на томе `ks_data`, смонтированном в `/data`, и переживает
перезапуски и выкатки новых версий.

## 3. Свой сервер — Docker Compose

```bash
git clone <адрес репозитория> ks && cd ks
echo "KS_API_KEY=$(openssl rand -hex 16)" > .env
docker compose up -d
curl http://localhost:8000/health
```

Документы хранятся в именованном томе `ks-data`. Наружу сервис лучше выставлять
через nginx или Caddy с TLS — своего HTTPS у контейнера нет.

Резервная копия и восстановление базы:

```bash
docker compose exec ks-service sh -c 'cat /data/ks.sqlite3' > ks-backup.sqlite3
```

## Резервные копии и перенос

Все документы выгружаются в один JSON-файл и загружаются обратно — в том числе
в другое хранилище, так что этим же способом переезжают с SQLite на PostgreSQL:

```bash
# выгрузить из локальной базы
python -m app.cli dump --output backup.json

# загрузить в PostgreSQL (адрес базы — со вкладки Environment в Render)
python -m app.cli load --input backup.json --database-url "postgresql://..."
```

Без `--database-path` и `--database-url` команды работают с тем хранилищем,
которое задано переменными окружения. Загрузка перезаписывает документы
с совпадающими идентификаторами, поэтому её можно повторять.

## Что проверить после развёртывания

```bash
BASE=https://<ваш-адрес>
KEY=<ключ>

curl -s $BASE/health

# Акт КС-2 из примера
ID=$(curl -s -X POST $BASE/api/v1/ks2 -H "X-API-Key: $KEY" \
  -H 'Content-Type: application/json' -d @examples/ks2_request.json |
  python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')

# Справка КС-3 по этому акту
curl -s -X POST $BASE/api/v1/ks3/from-acts -H "X-API-Key: $KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"act_ids\": [\"$ID\"], \"document_number\": \"1\", \"document_date\": \"2026-03-31\"}"

# Готовый бланк в XLSX
curl -OJ -H "X-API-Key: $KEY" $BASE/api/v1/ks2/$ID/xlsx
```
