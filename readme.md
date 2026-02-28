<div style="display: flex; align-items: center; gap: 20px;">
  <img src="https://bgitu-compass.ru/assets/compass_logo_big_old.png" width="100" alt="BGITU Compass Logo">
  <div>
    <h1><a href="https://bgitu-compass.ru">БГИТУ Компас</a> (Telegram-бот)</h1>
    <p>Telegram-бот для студентов ФГБОУ ВО "Брянский государственный инженерно-технологический университет". Предоставляет актуальное расписание занятий и информацию о преподавателях.</p>
    <p>🤖 <a href="https://t.me/bgitu_compass_bot">Telegram-бот</a> | 🌐 <a href="https://bgitu-compass.ru">Приложение для Android</a> | 🔌 <a href="https://github.com/koespe/bgitu_compass_api">Backend API</a></p>
  </div>
</div>

## Функциональность

### Основные возможности:

- **Просмотр расписания** — ежедневное и еженедельное отображение в том числе для преподавателей
- **Избранные группы** — добавление нескольких групп для быстрого доступа
- **Поиск преподавателя** — быстро узнать местонахождение преподавателя в университете

## Требования

- **Python 3.9+**
- **PostgreSQL** — база данных
- **Redis** — кэширование и FSM

## Технологии

- **aiogram 3** — фреймворк для Telegram Bot API
- **SQLAlchemy (async)** — ORM для работы с БД
- **PostgreSQL + asyncpg** — база данных
- **Redis** — хранилище состояний FSM и кэширование

## Установка

1. Клонировать репозиторий

2. Установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Создать `.env` файл на основе `.env.example`:
   ```bash
   cp .env.example .env
   ```

## Запуск

```bash
python main.py
```

## Структура проекта

```
bgitu_bot/
├── handlers/        # Обработчики сообщений и callback-запросов
│   ├── users/
│   └── managment/
├── database/        # Модели данных и работа с БД (SQLAlchemy)
├── keyboards/       # Inline и reply клавиатуры
├── middlewares/     # Rate-limiting для сообщений
├── modules/         # Дополнительные модули (парсер расписания)
├── states/          # Состояния FSM
├── config_reader.py # Конфигурация приложения
├── main.py          # Точка входа
└── requirements.txt # Зависимости
```
