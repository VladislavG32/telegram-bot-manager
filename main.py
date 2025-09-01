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

# Данные из переменных окружения
GITHUB_USERNAME = os.getenv('GITHUB_USERNAME')
RAILWAY_PROJECT_ID = os.getenv('RAILWAY_PROJECT_ID')

TEMPLATES = {
    "RPC": "VladislavG32/telegram-bot-rpc-template",
}

# Инициализируем клиент GitHub с проверкой доступности токена
GITHUB_TOKEN_VALUE = os.getenv('GITHUB_TOKEN') or os.getenv('GITHUB_API_TOKEN')
if not GITHUB_TOKEN_VALUE:
    logger.error("GitHub token is not set! Check GITHUB_TOKEN or GITHUB_API_TOKEN variables")
    raise ValueError("GitHub token is missing - check environment variables")

github_auth = Auth.Token(GITHUB_TOKEN_VALUE)
g = Github(auth=github_auth)

def check_repo_access(template_repo_name: str):
    """Проверка доступа к репозиторию"""
    try:
        print(f"🔍 Проверяю доступ к репозиторию: {template_repo_name}")
        
        # Проверяем существование репозитория
        repo = g.get_repo(template_repo_name)
        print(f"✅ Репозиторий найден: {repo.html_url}")
        print(f"   Видимость: {repo.visibility}")
        print(f"   Владелец: {repo.owner.login}")
        
        # Проверяем права доступа
        user = g.get_user()
        print(f"   Текущий пользователь: {user.login}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка доступа: {e}")
        return False

def create_repo_from_template(template_repo_name: str, new_repo_name: str, bot_token: str) -> Repository:
    try:
        # Диагностика: проверяем доступ перед созданием
        if not check_repo_access(template_repo_name):
            raise Exception("Нет доступа к шаблонному репозиторию")
        
        template_repo = g.get_repo(template_repo_name)
        user = g.get_user()
        
        print(f"🔄 Создаю репозиторий {new_repo_name} из шаблона {template_repo_name}")
        
        new_repo = user.create_repo_from_template(
            name=new_repo_name,
            repo=template_repo,
            private=True,
            description=f"Auto-generated Telegram bot: {new_repo_name}"
        )
        
        logger.info(f"Repository {new_repo_name} created successfully from template {template_repo_name}")
        print(f"✅ Репозиторий создан: {new_repo.html_url}")
        return new_repo
        
    except Exception as e:
        logger.error(f"Error creating repo from template: {e}")
        print(f"❌ Ошибка при создании: {e}")
        raise Exception(f"Ошибка при создании репозитория: {str(e)}")

def deploy_on_railway(repo_name: str, bot_token: str):
    """Упрощенная функция деплоя через Railway API"""
    try:
        # Простой способ: запустить деплой через API
        url = f"https://api.railway.app/v2/projects/{RAILWAY_PROJECT_ID}/deployments"
        headers = {
            "Authorization": f"Bearer {os.getenv('RAILWAY_API_TOKEN')}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "branch": "main",
            "meta": {
                "repo": f"{GITHUB_USERNAME}/{repo_name}",
                "trigger": "bot_creation"
            }
        }
        
        print(f"🚀 Запускаю деплой для {repo_name}")
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 201:
            logger.info(f"Deployment triggered successfully for {repo_name}")
            print("✅ Деплой запущен успешно!")
            return True
        else:
            logger.error(f"Deployment failed: {response.status_code} - {response.text}")
            print(f"❌ Ошибка деплоя: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error deploying to Railway: {e}")
        print(f"❌ Ошибка при деплое: {e}")
        return False

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [list(TEMPLATES.keys())]
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
    bot_token = update.message.text.strip()
    # Правильная валидация токена
    if not bot_token.startswith(('5', '6', '7', '8', '9')) or len(bot_token) < 20:
        await update.message.reply_text("Это не похоже на валидный токен бота. Попробуй еще раз.")
        return GETTING_BOT_TOKEN

    context.user_data['bot_token'] = bot_token
    await update.message.reply_text("Токен принят! Теперь придумай имя для репозитория (только латиница и цифры, без пробелов).")
    return NAMING_BOT

# Обработчик имени репозитория и финальный запуск
async def received_repo_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo_name = update.message.text.strip()
    template_key = context.user_data['chosen_template']
    bot_token = context.user_data['bot_token']

    await update.message.reply_text("Начинаю процесс создания... Это может занять минуту.")

    try:
        # 1. Создаем репозиторий на GitHub
        new_repo = create_repo_from_template(TEMPLATES[template_key], repo_name, bot_token)
        
        # 2. Запускаем деплой на Railway
        deploy_success = deploy_on_railway(repo_name, bot_token)

        if deploy_success:
            await update.message.reply_text(
                f"✅ Готово!\n"
                f"Репозиторий: {new_repo.html_url}\n"
                f"Деплой запущен. Проверить статус можно в панели Railway.\n"
                f"Твой бот должен запуститься в ближайшие несколько минут."
            )
        else:
            await update.message.reply_text(
                f"⚠️ Репозиторий создан: {new_repo.html_url}\n"
                f"Но возникли проблемы с автоматическим деплоем.\n"
                f"Запустите деплой вручную в панели Railway."
            )
            
    except Exception as e:
        logger.error(f"Error during bot creation: {e}")
        error_message = str(e)
        if "404" in error_message:
            await update.message.reply_text("⚠️ Ошибка: Шаблонный репозиторий не найден. Проверьте правильность ссылки на шаблон.")
        elif "401" in error_message:
            await update.message.reply_text("⚠️ Ошибка: Неверный GitHub токен. Проверьте права доступа.")
        else:
            await update.message.reply_text(f"⚠️ Что-то пошло не так: {error_message}")

    # Очищаем данные пользователя
    context.user_data.clear()
    return ConversationHandler.END

# Функция для отмены диалога
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Создание бота отменено.', reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

def main():
    # Проверяем что все переменные окружения загружены
    required_vars = ['MANAGER_BOT_TOKEN', 'RAILWAY_API_TOKEN', 'GITHUB_USERNAME', 'RAILWAY_PROJECT_ID']
    
    # Проверяем наличие хотя бы одного GitHub токена
    github_token_vars = ['GITHUB_TOKEN', 'GITHUB_API_TOKEN']
    has_github_token = any(os.getenv(var) for var in github_token_vars)
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars or not has_github_token:
        missing_message = missing_vars.copy()
        if not has_github_token:
            missing_message.append('GITHUB_TOKEN or GITHUB_API_TOKEN')
        
        logger.error(f"Missing required environment variables: {missing_message}")
        print(f"Ошибка: Отсутствуют переменные окружения: {missing_message}")
        return

    # Диагностика при запуске
    print("🔍 Запускаю диагностику...")
    for template_name in TEMPLATES.values():
        if not check_repo_access(template_name):
            print("❌ Диагностика не пройдена! Проверьте настройки.")
            return
    
    print("✅ Диагностика пройдена успешно!")

    try:
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

        logger.info("Bot started successfully")
        print("🤖 Бот запущен успешно!")
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Ошибка запуска бота: {e}")

if __name__ == '__main__':
    main()