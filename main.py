import os
import threading
import requests
import time
import re
import random
from loreofJun import lore
from loreofJun import random_thoughts
#from dotenv import load_dotenv
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# Токены
#load_dotenv()

TELEGRAM_TOKEN = '7580851736:AAFwJYN1Jsdj2LwnaKt0rYbwkqTtP6tYBsI'
CHATGPT_API_KEY = 'sk-NHbJXSoqrgySlxs0IjEQmHxZCnClQIUUqhhVpWb82LT3BlbkFJFGZW2-sifjC8n5hM9_iEbFNHsQJGsD-hc5sECvpccA'
OPENAI_API_KEY = 'sk-NHbJXSoqrgySlxs0IjEQmHxZCnClQIUUqhhVpWb82LT3BlbkFJFGZW2-sifjC8n5hM9_iEbFNHsQJGsD-hc5sECvpccA'

# Глобальный словарь для хранения состояний пользователей
user_memory = {}

MAX_MEMORY_LENGTH = 100
MEMORY_TTL = 30000

# Функция для отправки запроса к ChatGPT API
def get_chatgpt_response(user_id: int, message: str, max_tokens: int = 250, temperature: float = 0.9) -> str:
    current_time = time.time()

    # Используем память пользователя, если она есть, и фильтруем старые сообщения
    user_context = [
        msg for msg in user_memory.get(user_id, [])
        if current_time - msg['timestamp'] < MEMORY_TTL
    ]

    # Добавляем новое сообщение пользователя в контекст с меткой времени
    user_context.append({
        "role": "user",
        "content": message,
        "timestamp": current_time
    })

    # Оставляем только последние MAX_MEMORY_LENGTH сообщений в контексте
    if len(user_context) > MAX_MEMORY_LENGTH:
        user_context = user_context[-MAX_MEMORY_LENGTH:]

    # Формируем запрос к ChatGPT с лором бота
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CHATGPT_API_KEY}",
    }
    data = {
        "model": "gpt-4o-mini",  # Исправляем модель на gpt-4 или gpt-3.5-turbo
        "messages": [
            {"role": "system", "content": lore}  # Убираем лишний пробел
        ] + [{"role": msg["role"], "content": msg["content"]} for msg in user_context],
        "max_tokens": max_tokens,  # Добавляем параметр max_tokens
        "temperature": temperature
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()  # Эта строка выбросит исключение, если статус код не 200

        response_json = response.json()
        reply = response_json['choices'][0]['message']['content']

        # Добавляем ответ ChatGPT в контекст с меткой времени
        user_context.append({
            "role": "assistant",
            "content": reply,
            "timestamp": current_time
        })

        # Сохраняем обновленный контекст, оставляя только последние сообщения
        if len(user_context) > MAX_MEMORY_LENGTH:
            user_context = user_context[-MAX_MEMORY_LENGTH:]

        if random.random() < 0.1:
            reply += f" Кстати, {random.choice(random_thoughts)}"

        user_memory[user_id] = user_context

        return reply
    except requests.exceptions.RequestException as e:
        return f"Ошибка при обращении к ChatGPT API: {str(e)}"


# Улучшенная функция для генерации изображения с использованием DALL-E 3
def generate_image(prompt):
    try:
        response = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            },
            json={
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024"  # Можно также указать другие размеры
            }
        )
        response_json = response.json()
        if response.status_code == 200:
            return response_json['data'][0]['url']
        else:
            return None
    except Exception as e:
        return None


# Улучшенная функция для определения, требуется ли генерация изображения
def requires_image_generation(text):
    # Список ключевых слов для генерации изображений
    image_keywords = ['нарисуй', 'сгенерируй изображение', 'покажи картинку', 'визуализируй', 'draw', 'visualize',
                     'нарисуй картинку', 'изобрази', 'create an image']

    # Ищем ключевые слова в тексте
    for keyword in image_keywords:
        if keyword in text.lower():
            return True
    return False


# Функция для извлечения запроса изображения из текста
def extract_image_description(text):
    # Примитивный анализ текста для получения конкретных описаний изображения
    image_description_match = re.search(r'нарисуй (.+)|сгенерируй изображение (.+)', text.lower())
    if image_description_match:
        return image_description_match.group(1) or image_description_match.group(2)

    # Альтернативные случаи
    image_keywords = ['изобрази', 'draw', 'create an image of', 'visualize', 'show an image of']
    for keyword in image_keywords:
        if keyword in text.lower():
            # Убираем ключевое слово и пытаемся найти, о чем идет речь
            return text.lower().replace(keyword, '').strip()

    return "картинка"  # Возвращаем нейтральное описание, если не нашли ничего конкретного


TRIGGER_WORDS = ["Люцифер", "Luсifer", "Lucie", "Люци", "Дьявол", "Diablo", "Ад", "Ангел"]

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.text:
        user_message = update.message.text
        chat_id = update.message.chat_id

        # Проверка на наличие триггерных слов или если бот упомянут через reply
        if any(word in user_message.lower() for word in TRIGGER_WORDS) or \
           (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id):

            # Если сообщение - ответ на сообщение бота
            if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
                user_message = update.message.text

            # Проверка на необходимость генерации изображения
            if requires_image_generation(user_message):
                image_description = extract_image_description(user_message)  # Извлекаем описание изображения
                image_url = generate_image(image_description)
                if image_url:
                    await context.bot.send_photo(chat_id=chat_id, photo=image_url)
                else:
                    await context.bot.send_message(chat_id=chat_id, text="Не удалось сгенерировать изображение.")
            else:
                # Генерация ответа от ChatGPT
                chatgpt_response = get_chatgpt_response(chat_id, user_message)
                # Отправка ответа
                await context.bot.send_message(chat_id=chat_id, text=chatgpt_response)

    else:
        return

def run_telegram_bot():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()


def run_health_check_server():
    class HealthCheckHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"Health Check OK")

    port = int(os.getenv('PORT', 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Starting health check server on port {port}")
    server.serve_forever()


if __name__ == '__main__':
    # Запускаем HTTP-сервер для health-check в отдельном потоке
    threading.Thread(target=run_health_check_server).start()

    # Запускаем Telegram бота
    run_telegram_bot()