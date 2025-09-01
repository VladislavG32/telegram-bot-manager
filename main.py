import os
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters
from github import Github, Auth
from github.Repository import Repository
import requests
import json
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
CHOOSING_TEMPLATE, GETTING_BOT_TOKEN, NAMING_BOT = range(3)

# Ваши данные
GITHUB_USERNAME = "VladislavG32"  # Например, "IvanIvanov"
TEMPLATES = {
    "RPC": "VladislavG32/telegram-bot-rpc-template",  # Ссылка на ваш шаблонный репозиторий
    # ... добавьте другие шаблоны
}
RAILWAY_PROJECT_ID = "2babb01d-99f2-47a4-b14b-1f6b3872cafc" # Найти можно в настройках проекта в Railway

# Инициализируем клиент GitHub
github_auth = Auth.Token(os.getenv('GITHUB_TOKEN'))
g = Github(auth=github_auth)

# Функция для создания репозитория из шаблона
def create_repo_from_template(template_repo_name: str, new_repo_name: str, bot_token: str) -> Repository:
    template_repo = g.get_repo(template_repo_name)
    user = g.get_user()

    # Создаем новый репозиторий из шаблона
    new_repo = user.create_repo_from_template(
        name=new_repo_name,
        repo=template_repo,
        private=True,
        description=f"Auto-generated Telegram bot: {new_repo_name}"
    )

    # Здесь можно автоматически заменить токен в файле конфигурации нового репозитория.
    # Например, прочитать файл config.py, заменить placeholder на реальный токен и записать обратно.
    # Это сложный шаг, требующий работы с GitHub API для изменения файлов.
    # Простой вариант: использовать переменные окружения на Railway, а не хардкодить токен в код.

    # !!! Упрощенный подход: мы будем просто передавать токен как переменную окружения при деплое на Railway.
    # А в коде шаблона бота должен быть код, который читает токен из переменной окружения, например:
    # token = os.getenv('BOT_TOKEN')

    return new_repo

# Функция для деплоя на Railway через API
def deploy_on_railway(repo_name: str, bot_token: str):
    url = "https://api.railway.app/graphql/v2"
    api_token = os.getenv('RAILWAY_API_TOKEN')
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    # 1. Создаем новый сервис в проекте Railway, привязывая к нему репозиторий
    query_create_service = """
    mutation {
        serviceCreate(
            input: { name: "%s", projectId: "%s", source: { repo: "%s/%s" } }
        ) {
            id
            name
        }
    }
    """ % (repo_name, RAILWAY_PROJECT_ID, GITHUB_USERNAME, repo_name)

    # 2. Добавляем переменную окружения BOT_TOKEN для этого сервиса
    query_add_variable = """
    mutation {
        variableCreate(
            input: { name: "BOT_TOKEN", value: "%s", serviceId: "%s" }
        ) {
            id
            name
        }
    }
    """ % (bot_token, "$serviceId") # Здесь будет сложнее, нужно получить ID созданного сервиса

    # Реальный код GraphQL запроса будет более сложным и многошаговым.
    # Это псевдокод, иллюстрирующий идею.

    # На практике проще использовать Deployments API от Railway или их CLI.
    # Альтернатива: настроить в шаблоне Webhook на Railway, чтобы деплой запускался автоматически при пуше в репозиторий.
    # Тогда нам нужно лишь создать репо и запустить деплой вручную через API одним запросом.
    response = requests.post(url, json={"query": query_create_service}, headers=headers)
    # ... обработка ответа и второй запрос ...

    logger.info(f"Deployment triggered for {repo_name}. Response: {response.json()}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [list(TEMPLATES.keys())]  # Создаем клавиатуру из ключей нашего словаря шаблонов
    await update.message.reply_text(
        "Привет! Я бот, создающий других ботов.\n"
        "Выбери тип бота, которого хочешь создать:",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True,
            input_field_placeholder="Какой бот тебе нужен?"
        )
    )
    return CHOOSING_TEMPLATE

# Обработчик выбора шаблона
async def chosen_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_choice = update.message.text
    if user_choice not in TEMPLATES:
        await update.message.reply_text("Пожалуйста, выбери вариант из предложенных ниже.")
        return CHOOSING_TEMPLATE

    context.user_data['chosen_template'] = user_choice
    await update.message.reply_text(
        f"Отлично! Ты выбрал {user_choice}.\n"
        f"Теперь пришли мне токен для нового бота. (Получи его у @BotFather)",
        reply_markup=ReplyKeyboardRemove()
    )
    return GETTING_BOT_TOKEN

# Обработчик получения токена
async def received_bot_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_token = update.message.text
    # Простая валидация токена
    if not bot_token.startswith('') or len(bot_token) < 20:
        await update.message.reply_text("Это не похоже на валидный токен бота. Попробуй еще раз.")
        return GETTING_BOT_TOKEN

    context.user_data['bot_token'] = bot_token
    await update.message.reply_text("Токен принят! Теперь придумай имя для репозитория (только латиница и цифры, без пробелов).")
    return NAMING_BOT

# Обработчик имени репозитория и финальный запуск
async def received_repo_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo_name = update.message.text
    template_key = context.user_data['chosen_template']
    bot_token = context.user_data['bot_token']

    await update.message.reply_text("Начинаю процесс создания... Это может занять минуту.")

    try:
        # 1. Создаем репозиторий на GitHub
        new_repo = create_repo_from_template(TEMPLATES[template_key], repo_name, bot_token)
        # 2. Запускаем деплой на Railway
        deploy_on_railway(repo_name, bot_token)

        await update.message.reply_text(
            f"✅ Готово!\n"
            f"Репозиторий: {new_repo.html_url}\n"
            f"Деплой запущен. Проверить статус можно в панели Railway.\n"
            f"Твой бот должен запуститься в ближайшие несколько минут."
        )
    except Exception as e:
        logger.error(f"Error during bot creation: {e}")
        await update.message.reply_text(f"⚠️ Что-то пошло не так: {e}")

    # Очищаем данные пользователя
    context.user_data.clear()
    return ConversationHandler.END

# Функция для отмены диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Создание бота отменено.', reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

def main():
    # Создаем Application и передаем ему токен бота.
    application = Application.builder().token(os.getenv('MANAGER_BOT_TOKEN')).build()

    # Настраиваем обработчик диалога (ConversationHandler)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, chosen_template)],
            GETTING_BOT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_bot_token)],
            NAMING_BOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_repo_name)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)

    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()