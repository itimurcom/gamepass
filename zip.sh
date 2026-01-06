#!/bin/bash

# --- НАЛАШТУВАННЯ ---

# 1. Отримуємо поточну дату та час
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")

# 2. Формуємо назву архіву
OUTPUT_ARCHIVE="backup_${TIMESTAMP}.zip"

# 3. Вкажіть файли та папки для архівації (через пробіл)
# Зверніть увагу: без лапок навколо змінної $FILES_TO_ZIP у команді zip
FILES_TO_ZIP="gamepass.py core/*.py core/*.html catalog/index.html catalog/*"

# 4. ЩО ВИКЛЮЧИТИ (через пробіл)
# Приклад: виключити кеш пітона, логи або конкретний файл
# Якщо виключати нічого не треба, залиште лапки пустими ""
EXCLUDE_LIST="core/__init__.py catalog/data.js"


# --- ВИКОНАННЯ ---

echo "Створення архіву: $OUTPUT_ARCHIVE"

# Створення zip архіву
# -r : рекурсивно
# -x : виключити файли зі списку $EXCLUDE_LIST
zip -r "$OUTPUT_ARCHIVE" $FILES_TO_ZIP -x $EXCLUDE_LIST

# Перевірка результату
if [ $? -eq 0 ]; then
    echo "✅ Готово! Файл збережено як: $OUTPUT_ARCHIVE"
else
    echo "❌ Помилка при архівації."
fi