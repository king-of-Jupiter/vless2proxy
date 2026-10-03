# VLESS → SOCKS5 Dashboard

Локальная LAN-панель без авторизации: добавляете VLESS-ссылки (TCP / XHTTP), выбираете режим и порт — поднимается прокси через Xray. Статус («огонёк») и пинг проверяются автоматически.

Логика парсинга VLESS и генерации `config.json` портирована из [VLESS-to-HTTP](https://github.com/thejohnd0e/VLESS-to-HTTP) (`entrypoint.sh` → `app/vless_parser.py`).

## Запуск

```bash
docker compose up -d --build
```

Откройте в LAN: `http://<ip-хоста>:8123`

Остановка:

```bash
docker compose down
```

## Как пользоваться

1. Нажмите «Добавить», вставьте `vless://…` ссылку целиком.
2. Выберите режим: **SOCKS5** (по умолчанию), **HTTP** или **Оба**.
3. Порт подставляется автоматически: предыдущий + 1 (старт SOCKS5 с `1080`, HTTP с `9000`). Можно поменять вручную.
4. Карточка показывает:
   - зелёный пульсирующий огонёк + `онлайн` / красный `офлайн`,
   - пинг в мс и egress-IP,
   - строки подключения (`socks5://127.0.0.1:PORT`) с кнопкой «копия»,
   - кнопки Старт / Стоп / Рестарт / Проверить / Логи / Удалить.

## Проверка жизни

Каждые 30 с (переменная `CHECK_INTERVAL`) для каждого включённого профиля:

1. TCP-подключение к порту,
2. запрос через прокси к `https://www.google.com/generate_204` (замер ms) и `https://api.ipify.org` (egress IP).

## Проверка вручную

```bash
# SOCKS5
curl --socks5-hostname 127.0.0.1:1080 https://api.ipify.org -m 10 -v
# HTTP
curl -x http://127.0.0.1:9000 https://api.ipify.org -m 10 -v
```

## Файлы

```
app/main.py          FastAPI + API
app/db.py            SQLite (data/profiles.db)
app/vless_parser.py  парсинг VLESS + генерация Xray-конфига
app/xray_manager.py  по одному процессу Xray на профиль
app/health.py        TCP + proxy-пинг
app/templates/      Jinja-шаблон (minimalist-ui)
app/static/         CSS + vanilla JS
tests/test_parser.py тесты парсера (tcp / xhttp)
data/               БД, сгенерированные config-*.json, логи (volume)
```

## Безопасность

Без авторизации — держите строго в домашней LAN, не пробрасывайте порт дашборда наружу.
