#!/bin/bash
# deploy.sh — деплой с сохранением кэша

BACKUP_KEY=voronov19
SERVER="https://railway-calculator.onrender.com"
CACHE_FILE="cache.json"

echo "📥 Скачиваю кэш с сервера..."
curl -s "$SERVER/backup?key=$BACKUP_KEY" -o "$CACHE_FILE"

if [ -s "$CACHE_FILE" ]; then
    COUNT=$(python3 -c "import json; d=json.load(open('$CACHE_FILE')); print(len(d))" 2>/dev/null || echo "?")
    echo "✅ Кэш скачан ($COUNT маршрутов)"
else
    echo "⚠️  Кэш пустой или не скачался"
fi

echo "📤 Деплою на GitHub..."
git add .
git commit -m "${1:-update}"
git push

echo "✅ Готово! После деплоя кэш восстановится автоматически."
echo "⏳ Подожди 2-3 минуты пока Render пересоберёт."
