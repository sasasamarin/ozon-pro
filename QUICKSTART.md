# 🚀 БЫСТРЫЙ СТАРТ — заливка кода в GitHub

## Шаг 1: Скачай архив
Архив `ozon-pro-mvp.tar.gz` уже готов (он в наших выходных файлах).

## Шаг 2: На твоём Mac открой Terminal и выполни:

```bash
# 1. Распакуй архив
cd ~/Downloads
tar -xzf ozon-pro-mvp.tar.gz
cd ozon-pro

# 2. Инициализируй git и залей в твой репо
git init
git add .
git commit -m "Initial commit: MVP скелет"
git branch -M main
git remote add origin https://github.com/sasasamarin/ozon-pro.git
git push -u origin main

# 3. Готово!
# Открой https://github.com/sasasamarin/ozon-pro - там будет весь код
```

## Если git ругается на авторизацию:

```bash
# Установи GitHub CLI (один раз)
brew install gh

# Авторизуйся
gh auth login

# Повтори push
git push -u origin main
```

