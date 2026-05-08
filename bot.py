import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
from datetime import time
import json
import httpx
from datetime import timezone, timedelta
import signal
import sys
import os
from flask import Flask
import threading

MOSCOW_TZ = timezone(timedelta(hours=3))
import os
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.0-flash-001"
# Токен от BotFather (храни его в секрете!)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
diary = {}
DATA_FILE = "diary.json"

# Простой веб-сервер для Render (чтобы не ругался на отсутствие порта)
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "BotiK жив и работает!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

#Сохранение данных
def save_on_exit(sig, frame):
    save_diary()
    print("Данные сохранены. Пока!")
    sys.exit(0)


#Для получения НОРМАЛЬНОГО РУСского дня недели
def get_weekday():
    days_ru = {
        "Monday": "☕ Понедельник",
        "Tuesday": "📅 Вторник",
        "Wednesday": "☂︎ Среда",
        "Thursday": "😎 Четверг",
        "Friday": "🥳 Пятница",
        "Saturday": "🥞 Суббота",
        "Sunday": "🌻 Воскресенье"
    }
    eng_day = datetime.now(MOSCOW_TZ).strftime("%A")
    return days_ru[eng_day]

#Ловец ошибок для консоли
async def error_handler(update, context):
    print(f"Ошибка (не страшно, бот работает дальше): {context.error}")

# Команда /start — бот здоровается
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name  # Берём имя пользователя из Telegram
    await update.message.reply_text(
        f"Привет, {user_name}! Я Создатель Саммари☀️ - твой дневник \n"
        "Просто пиши мне в течение дня всё, что происходит, а в воскресенье я пришлю тебе саммари недели!\n"
        "Напиши /help, чтобы узнать, что я умею."
    )

# Команда /help — подсказка
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Я запоминаю всё, что ты мне пишешь.\n"
        "🗓 Каждое воскресенье в 21:00 я пришлю тебе краткое саммари недели.\n"
        "📃С помощью команды /stats ты сможешь увидеть количество записей за каждый день!\n"
        "📌Если нажмешь /about, то подробнее узнаешь зачем я нужен и что я делаю)\n"
        "📊 Также ты можешь написать /summary в любой момент, чтобы получить итоги прямо сейчас."
    )

# Команда /about — информация о боте
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "☀️Я Создатель Саммари — твой личный дневник-ассистент.\n"
        "Моя задача — запоминать события твоей жизни и подводить итоги недели.\n\n"
        "🗓️Каждое воскресенье я буду присылать тебе 🕯️саммари(краткую выдержку твоих похождений), чтобы ты мог следить за прогрессом в своих начинаниях и видел, насколько много ты на самом деле делаешь!💎\n\n"
        "Все что тебе нужно, это в течении дня или перед сном присылать мне пару предложений о том, как прошел твой день☀️\n"
        "Я напоминаю тебе о том, какой ты молодец на самом деле\n\n"
        "Если потребуется вспомнить команды, пиши /help\n\n"
        "🏷️Версия: 1.1\n"
    )

#Записывает сообщения в дневник
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = str(update.effective_chat.id)  # Получаем уникальный ID чата
    day = get_weekday()

    # Если этого пользователя ещё нет — создаём пустой словарь
    if chat_id not in diary:
        diary[chat_id] = {}

    # Если этого дня ещё нет у пользователя — создаём пустой список
    if day not in diary[chat_id]:
        diary[chat_id][day] = []

    diary[chat_id][day].append(text)
    count = len(diary[chat_id][day])
    await update.message.reply_text(f"Сообщение записано на день недели {day}! Сегодня записей: {count}")

    save_diary()

#Функция stats - выводит количество записей за каждый день
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_diary = diary.get(chat_id, {})

    all_days = ["☕ Понедельник", "📅 Вторник", "☂︎ Среда", "😎 Четверг", "🥳 Пятница", "🥞 Суббота", "🌻 Воскресенье"]
    lines = ["📊 Статистика за неделю:"]
    for day in all_days:
        count = len(user_diary.get(day, []))
        if count > 0:
            lines.append(f"{day}: {count} зап.")
        else:
            lines.append(f"{day}: пусто")

    await update.message.reply_text("\n".join(lines))

#Функции сохранения и загрузки
def load_diary():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}  # Если файла нет или он сломан — возвращаем пустой словарь

def save_diary():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(diary, f, ensure_ascii=False, indent=2)

#Проверка на день недели и отправка саммари по воскресеньям
async def check_summary(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(MOSCOW_TZ)
    day = get_weekday()

    if day == "🌻 Воскресенье" and now.time() >= time(21, 0):
        for chat_id, user_diary in diary.items():
            if user_diary:  # Если у пользователя есть записи
                summary = await generate_summary(user_diary)
                await context.bot.send_message(chat_id=chat_id, text=summary)

        # Очищаем дневник для новой недели (всем пользователям)
        diary = {}
        save_diary()

#Команда /summary — позволяет получить саммари в любой момент
async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    # Проверяем, есть ли записи у этого пользователя
    user_diary = diary.get(chat_id, {})
    if not user_diary:
        await update.message.reply_text("У тебя пока нет записей за эту неделю 😢")
        return

    await update.message.reply_text("Секунду, генерирую саммари... ✍️")
    summary = await generate_summary(user_diary)
    await update.message.reply_text(summary)

#Функция для генерации саммари
async def generate_summary(week_data):
    # Формируем текст из записей
    lines = []
    for day, entries in week_data.items():
        if entries:
            lines.append(f"{day}: {', '.join(entries)}")

    if not lines:
        return "На этой неделе не было записей 😢"

    user_text = "\n".join(lines)

    # Отправляем запрос к нейросети
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Ты — дружелюбный и заботливый ассистент, который подводит итоги недели. "
                            "Твой тон — как у мудрого друга, который всегда поддержит и найдёт повод для гордости. "
                            "Пиши на русском языке, живым и тёплым языком, без сухости и шаблонов.\n\n"

                            "Формат ответа:\n"
                            "• Для каждого дня сделай отдельный блок с эмодзи дня (пн-вс). "
                            "• В каждом дне — 5-8 предложений(можно меньше, если совсем мало записей): что было сделано, что важного случилось. "
                            "• Не просто перечисляй события, а показывай прогресс: "
                            "'В понедельник ты начал с малого — всего 30 минут учёбы, но это уже победа над ленью!'\n\n"

                            "Работа с мыслями и цитатами:\n"
                            "• Если среди записей есть размышления, цитаты или идеи — выдели их особо. "
                            "• Дай краткий фидбек: согласен ли ты с мыслью, как её можно применить в жизни. "
                            "• Можешь добавить свою фразу-поддержку в духе: 'Как говорится, дорогу осилит идущий — и ты идёшь!'\n\n"

                            "Главная цель:\n"
                            "• Показать, что неделя прошла не зря. Даже если кажется, что ничего не сделано — "
                            "найди маленькие победы и подсвети их. "
                            "• Напомни, что отдых и забота о себе — тоже важная часть продуктивной недели. "
                            "• Закончи саммари тёплым пожеланием на следующую неделю.\n\n"

                            "Ограничения:\n"
                            "• Не выдумывай события, которых нет в записях. "
                            "• Не будь токсично-позитивным — если неделя была тяжёлой, признай это. "
                            "• Укладывайся в 30-50 предложений на всё саммари(можно меньше, если совсем мало записей)."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Вот мои записи за неделю:\n{user_text}"
                    }
                ]
            }
        )

    data = response.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    else:
        print("Ошибка OpenRouter:", data)  # Покажет в терминале, если что не так
        return "Извини, не смог сгенерировать саммари. Попробуй позже 🙏"

# Главная функция — запускает бота
def main():
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()

    global diary
    diary = load_diary()

    # Регистрируем обработчик сообщений — все текстовые сообщения будут обрабатываться функцией handle_message
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


    # Регистрируем команды: когда пользователь пишет /start — вызывается функция start
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_error_handler(error_handler)

    # Проверяем необходимость саммари каждый час (3600 секунд)
    app.job_queue.run_repeating(check_summary, interval=3600, first=10)

    signal.signal(signal.SIGINT, save_on_exit)  # Ctrl+C

    # Запускаем веб-сервер в фоновом потоке
    threading.Thread(target=run_web, daemon=True).start()

    # Запускаем бота (будет работать, пока не нажмём Ctrl+C)
    print("Ботик проснулся и готов работать!")
    app.run_polling()

# Эта строчка говорит: "Если файл запущен напрямую — выполняй main()"
if __name__ == "__main__":
    main()