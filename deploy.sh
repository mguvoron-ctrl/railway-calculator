#!/bin/bash
# deploy.sh — деплой с сохранением кэша

BACKUP_KEY=voronov19
SERVER="https://railway-calculator.onrender.com"
CACHE_FILE="cache.json"

# Проверяем что сервер живой перед скачиванием
echo "🔍 Проверяю доступность сервера..."
for i in 1 2 3 4 5; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER/health")
  if [ "$STATUS" = "200" ]; then
    echo "✅ Сервер доступен"
    break
  fi
  echo "⏳ Попытка $i/5 — сервер не отвечает, жду 15 сек..."
  sleep 15
done

if [ "$STATUS" != "200" ]; then
  echo "❌ Сервер недоступен — деплой отменён. Попробуй позже."
  exit 1
fi

echo "📥 Скачиваю кэш с сервера..."
curl -s "$SERVER/backup?key=$BACKUP_KEY" -o "$CACHE_FILE"

if [ -s "$CACHE_FILE" ]; then
    COUNT=$(python3 -c "import json; d=json.load(open('$CACHE_FILE')); print(len(d))" 2>/dev/null || echo "?")
    echo "✅ Кэш скачан ($COUNT маршрутов)"
else
    echo "⚠️  Кэш пустой или не скачался — деплой всё равно продолжится"
    rm -f "$CACHE_FILE"
fi

echo "📤 Деплою на GitHub..."
git add -A -- ':!cache.json'
git commit -m "${1:-update}" 2>/dev/null || echo "Нечего коммитить"
git push

echo "⏳ Жду пока Render пересоберёт..."
sleep 30

# Ждём пока новый сервер поднимется
for i in 1 2 3 4 5 6 7 8 9 10; do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER/health")
  if [ "$STATUS" = "200" ]; then
    echo "✅ Новый сервер поднялся"
    break
  fi
  echo "⏳ Ждём сервер $i/10..."
  sleep 15
done

if [ "$STATUS" != "200" ]; then
  echo "❌ Новый сервер не поднялся. Загрузи кэш вручную:"
  echo "curl -X POST \"$SERVER/upload-cache?key=$BACKUP_KEY\" -H \"Content-Type: application/json\" --data-binary \"@$CACHE_FILE\""
  exit 1
fi

if [ -s "$CACHE_FILE" ]; then
    echo "📤 Загружаю кэш обратно на сервер..."
    RESULT=$(curl -s -X POST "$SERVER/upload-cache?key=$BACKUP_KEY" \
        -H "Content-Type: application/json" \
        --data-binary "@$CACHE_FILE")
    echo "✅ $RESULT"
    rm -f "$CACHE_FILE"
fi

echo "🎉 Готово!"
