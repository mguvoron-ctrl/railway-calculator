#!/bin/bash
# deploy.sh — деплой с сохранением кэша

BACKUP_KEY="ТВОЙ_ПАРОЛЬ"
SERVER="https://railway-calculator.onrender.com"
CACHE_FILE="cache.json"

echo "📥 Скачиваю кэш с сервера..."
curl -s "$SERVER/backup?key=$BACKUP_KEY" -o "$CACHE_FILE"

if [ -s "$CACHE_FILE" ]; then
    COUNT=$(python3 -c "import json; d=json.load(open('$CACHE_FILE')); print(len(d))" 2>/dev/null || echo "?")
    echo "✅ Кэш скачан ($COUNT маршрутов)"
else
    echo "⚠️  Кэш пустой или не скачался"
    rm -f "$CACHE_FILE"
fi

echo "📤 Деплою на GitHub..."
git add -A -- ':!cache.json'
git commit -m "${1:-update}" 2>/dev/null || echo "Нечего коммитить"
git push

echo "⏳ Жду пока Render пересоберёт (90 сек)..."
sleep 90

if [ -s "$CACHE_FILE" ]; then
    echo "📤 Загружаю кэш обратно на сервер..."
    RESULT=$(curl -s -X POST "$SERVER/upload-cache?key=$BACKUP_KEY" \
        -H "Content-Type: application/json" \
        --data-binary "@$CACHE_FILE")
    echo "✅ $RESULT"
    rm -f "$CACHE_FILE"
fi

echo "🎉 Готово!"
