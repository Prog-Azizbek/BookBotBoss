# handlers_common.py
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при команде /start с HTML форматированием."""
    user = update.effective_user
    welcome_message = (
        f"Привет, {user.first_name}!\n"
        f"Я бот для бронирования услуг. Что бы вы хотели сделать?\n\n"
        f"<b>Основные команды:</b>\n"
        f"/help - Показать это сообщение\n\n"
        
        f"<b>Для Поставщиков Услуг:</b>\n"
        f"/register_provider <i>Ваше Имя/Название Компании</i> - Регистрация как поставщик\n"
        f"  <i>Пример: /register_provider Салон Красоты Фея</i>\n"
        f"/add_service <i>Название;Описание;Длительность_мин;Цена</i> - Добавить услугу\n"
        f"  <i>Пример: /add_service Стрижка;Модельная;60;500</i>\n"
        f"/my_services - Просмотреть ваши услуги\n"
        f"/add_slot <i>ID_услуги ГГГГ-ММ-ДД ЧЧ:ММ</i> - Добавить временной слот\n"
        f"  <i>Пример: /add_slot 123 2024-10-20 14:00</i>\n"
        f"/my_slots - Просмотреть ваши слоты и их бронирования\n"
        f"/cancel_booking_provider <i>ID_брони</i> - Отменить бронирование на вашу услугу\n"
        f"  <i>Пример: /cancel_booking_provider 45</i>\n\n"
        
        f"<b>Для Клиентов:</b>\n"
        f"/services - Посмотреть доступные услуги и забронировать\n"
        f"/my_bookings - Посмотреть ваши бронирования (и отменить их)\n"
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.HTML)
    logger.info(f"User {user.id} ({user.username}) started the bot.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с помощью по командам с HTML форматированием."""
    help_text = (
        f"Привет! Я бот для бронирования услуг.\n\n"
        f"<b>Основные команды:</b>\n"
        f"/help - Показать это сообщение\n\n"
        
        f"<b>Для Поставщиков Услуг:</b>\n"
        f"<b>/register_provider</b> <i>Ваше Имя/Название Компании</i>\n"
        f"  <i>Регистрация нового поставщика услуг. Укажите имя или название после команды.</i>\n"
        f"  <i>Пример: /register_provider Салон Красоты Фея</i>\n\n"
        
        f"<b>/add_service</b> <i> Название; Описание; Длительность_в_минутах; Цена</i>\n"
        f"  <i>Добавляет новую услугу. Параметры указываются через точку с запятой (<b>;</b>).</i>\n"
        f"  <i>Описание и Цена не обязательны.</i>\n"
        f"  <i>Пример (все поля): /add_service Стрижка мужская;Классическая стрижка;60;500</i>\n"
        f"  <i>Пример (без описания): /add_service Маникюр;;45;700</i>\n\n"
        
        f"<b>/my_services</b>\n"
        f"  <i>Показывает список ваших услуг и их ID.</i>\n\n"
        
        f"<b>/add_slot</b> <i>ID_услуги ГГГГ-ММ-ДД ЧЧ:ММ</i>\n"
        f"  <i>Добавляет временной слот. Укажите ID услуги, дату и время через пробел.</i>\n"
        f"  <i>ID услуги можно узнать из /my_services.</i>\n"
        f"  <i>Пример: /add_slot 123 2024-10-20 14:00</i>\n\n"
        
        f"<b>/my_slots</b>\n"
        f"  <i>Показывает ваши слоты, сгруппированные по услугам, и кто их забронировал.</i>\n\n"
        
        f"<b>/cancel_booking_provider</b> <i>ID_брони</i>\n"
        f"  <i>Отменяет бронирование на вашу услугу. Укажите ID брони после команды.</i>\n"
        f"  <i>ID брони можно увидеть в /my_slots.</i>\n"
        f"  <i>Пример: /cancel_booking_provider 45</i>\n\n"
        
        f"<b>Для Клиентов:</b>\n"
        f"<b>/services</b>\n"
        f"  <i>Показывает список доступных услуг. Выберите услугу кнопками, чтобы увидеть слоты и забронировать.</i>\n\n"
        
        f"<b>/my_bookings</b>\n"
        f"  <i>Показывает ваши предстоящие бронирования. Кнопками можно отменить бронь.</i>\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)