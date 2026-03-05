# 🚂 ЖД Калькулятор

Калькулятор железнодорожных расстояний между станциями России.
Данные берутся с alta.ru.

---

## Ссылки

| Назначение | Ссылка |
|---|---|
| Сайт | https://railway-calculator.onrender.com |
| Проверка кэша | https://railway-calculator.onrender.com/health |
| Скачать бэкап | https://railway-calculator.onrender.com/backup?key=ТВОЙ_ПАРОЛЬ |

---

## Архитектура

```
Браузер (index.html)
    ↓
Render.com — FastAPI сервер (main.py)
    ↓ гонка (прямой запрос + 2 прокси)
alta.ru — источник данных о расстояниях
```

---

## Сервисы

### Render.com
- Хостинг Python сервера (бесплатно)
- URL: https://dashboard.render.com
- Сервис: railway-calculator
- Регион: Oregon (США)
- Бесплатный тариф засыпает после 15 минут без запросов

### GitHub
- Хранение кода
- URL: https://github.com/mguvoron-ctrl/railway-calculator
- Каждый git push автоматически деплоит новую версию на Render

### cron-job.org
- Пингует сервер каждые 15 минут чтобы не засыпал
- URL: https://cron-job.org
- Задание: ping railway-calculator → /health каждые 15 минут

---

## Переменные окружения на Render

| Переменная | Назначение |
|---|---|
| BACKUP_KEY | Пароль для скачивания и загрузки бэкапа кэша |

---

## Файлы проекта

| Файл | Назначение |
|---|---|
| main.py | FastAPI сервер |
| index.html | Фронтенд |
| requirements.txt | Python зависимости |
| deploy.sh | Скрипт деплоя с сохранением кэша |
| .gitignore | Исключает cache.json из GitHub |
| cache.json | Кэш маршрутов (не попадает в GitHub) |

---

## Как деплоить изменения

```bash
cd /Users/jack/Desktop/калькулятор
bash deploy.sh "описание изменений"
```

Скрипт автоматически:
1. Скачивает кэш с сервера
2. Пушит новый код на GitHub
3. Ждёт 90 секунд пока Render пересоберёт
4. Загружает кэш обратно на сервер

ВАЖНО: Никогда не делай просто git push — кэш сбросится!

---

## Как работает кэш

1. Пользователь запрашивает маршрут А→Б
2. Сервер проверяет кэш — если есть, отдаёт мгновенно (0с)
3. Если нет — гонка: запрос напрямую на alta.ru + 2 прокси (~2-3с)
4. Автоматически кэшируются все промежуточные подмаршруты
5. Кэш сохраняется в файл cache.json на сервере

---

## Как восстановить кэш вручную

```bash
curl -X POST "https://railway-calculator.onrender.com/upload-cache?key=ТВОЙ_ПАРОЛЬ" \
  -H "Content-Type: application/json" \
  --data-binary "@cache.json"
```
