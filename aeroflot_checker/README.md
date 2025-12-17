# Aeroflot Subsidized Ticket Checker

Этот скрипт проверяет наличие субсидированных билетов Аэрофлота (Калининград -> Санкт-Петербург) на указанные даты и отправляет уведомление в Telegram.

## Запуск через Docker (Рекомендуется)

Это самый простой способ запуска, так как он автоматически устанавливает все зависимости, включая Google Chrome.

### Требования
- Docker
- Docker Compose

### Инструкция

1. **Настройка:**
   Откройте файл `docker-compose.yml` и раскомментируйте строки с переменными окружения, подставив свои значения:
   ```yaml
   environment:
     - TELEGRAM_BOT_TOKEN=ваш_токен
     - TELEGRAM_CHAT_ID=ваш_chat_id
   ```
   *Либо* отредактируйте файл `main.py` напрямую.

2. **Запуск:**
   ```bash
   docker-compose up -d --build
   ```
   Флаг `-d` запускает контейнер в фоновом режиме.

3. **Просмотр логов:**
   ```bash
   docker-compose logs -f
   ```

4. **Остановка:**
   ```bash
   docker-compose down
   ```

---

## Установка вручную на Ubuntu Server (без Docker)

Если вы не хотите использовать Docker, следуйте этой инструкции.

1. **Обновите систему и установите необходимые пакеты:**

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip wget unzip
   ```

2. **Установите Google Chrome:**

   ```bash
   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
   sudo apt install -y ./google-chrome-stable_current_amd64.deb
   ```

3. **Установите зависимости Python:**

   Перейдите в папку со скриптом и выполните:

   ```bash
   pip3 install -r requirements.txt
   ```

4. **Настройка:**
   Откройте файл `main.py` и вставьте ваш `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.

5. **Запуск:**
   ```bash
   python3 main.py
   ```
   
   Для запуска в фоне:
   ```bash
   nohup python3 main.py > output.log 2>&1 &
   ```

## Как это работает

Скрипт использует Selenium для запуска браузера Chrome в "безголовом" (headless) режиме. Это позволяет обойти простые проверки на ботов, так как запросы выполняются из реального браузерного окружения.

1. Скрипт открывает страницу поиска субсидированных билетов.
2. Ждет загрузки страницы и инициализации сессии.
3. Выполняет JavaScript-код внутри браузера для отправки API-запроса на поиск билетов.
4. Если билеты найдены, отправляет сообщение в Telegram.
5. Повторяет проверку каждый час.
