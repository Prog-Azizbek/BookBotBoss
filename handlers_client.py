# handlers_client.py
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import get_db, Provider, Service, TimeSlot, Booking

logger = logging.getLogger(__name__)

async def list_available_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает клиенту список доступных услуг с кнопками для просмотра слотов."""
    db: Session = next(get_db())
    user = update.effective_user # Для логирования, если нужно

    try:
        # Получаем все активные услуги от активных поставщиков,
        # у которых есть доступные слоты в будущем
        # Это сложный запрос, разобьем его для ясности или упростим для MVP
        
        # Вариант 1: Простой - все активные услуги активных провайдеров
        # active_services_query = db.query(Service).join(Provider).filter(
        #     Provider.is_active == True,
        #     # Service.is_deleted == False # если бы было поле is_deleted у услуги
        # )
        
        # Вариант 2: Более сложный, но правильный - только те услуги, где ЕСТЬ доступные слоты в будущем
        # Для этого нужно будет проверить наличие таких слотов для каждой услуги.
        # Это может быть накладно, если услуг много.
        # Пока сделаем проще: покажем все услуги, а проверку слотов - на следующем шаге.

        # Для MVP: показываем все услуги от активных провайдеров.
        # Позже можно добавить фильтр, чтобы показывать только услуги с доступными слотами.
        # И сразу подгружаем информацию о провайдере, чтобы не делать лишних запросов в цикле
        services_with_providers = db.query(Service, Provider.name.label("provider_name"))\
            .join(Provider, Service.provider_id == Provider.provider_id)\
            .filter(Provider.is_active == True)\
            .order_by(Provider.name, Service.name)\
            .all()

        if not services_with_providers:
            await update.message.reply_text("К сожалению, на данный момент нет доступных услуг для бронирования.")
            return

        response_text = "<b>Доступные услуги для бронирования:</b>\n\n"
        keyboard = [] # Список для кнопок

        
        if len(services_with_providers) > 30: # Произвольное ограничение для примера
            await update.message.reply_text(
                "Найдено слишком много услуг. Пожалуйста, используйте фильтры (будут добавлены позже) "
                "или свяжитесь с администратором для уточнения." # Заглушка для пагинации
            )
            logger.warning(f"Too many services ({len(services_with_providers)}) to display without pagination for /services command.")
            return

        for service, provider_name_tuple in services_with_providers:
            provider_name = provider_name_tuple # т.к. provider_name.label("provider_name") возвращает строку

            price_str = f"{service.price:.2f} руб." if service.price is not None and service.price > 0 else "не указана"
            response_text += (
                f"<b>Услуга:</b> {service.name}\n"
                f"<i>От:</i> {provider_name}\n"
                f"<i>Длительность:</i> {service.duration_minutes} мин.\n"
                f"<i>Цена:</i> {price_str}\n"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"➡️ Показать слоты для: {service.name} (от {provider_name})", 
                    callback_data=f"view_slots_{service.service_id}"
                )
            ])
            response_text += "--------------------\n"
            
        # Если клавиатура пуста (хотя мы проверили services_with_providers), на всякий случай
        if not keyboard:
             await update.message.reply_text("Не удалось сформировать список услуг с кнопками.")
             return

        reply_markup = InlineKeyboardMarkup(keyboard)
        

        if len(response_text) > 4000 :
            logger.warning(f"Long service list text for /services: {len(response_text)} chars. May be truncated.")

        
        if not services_with_providers:
            await update.message.reply_text("К сожалению, на данный момент нет доступных услуг для бронирования.")
            return

        await update.message.reply_text("<b>Доступные услуги для бронирования:</b>", parse_mode=ParseMode.HTML)

        for service, provider_name_tuple in services_with_providers:
            provider_name = provider_name_tuple
            price_str = f"{service.price:.2f} руб." if service.price is not None and service.price > 0 else "не указана"
            
            service_details_text = (
                f"<b>Услуга:</b> {service.name}\n"
                f"<i>От:</i> {provider_name}\n"
                f"<i>Длительность:</i> {service.duration_minutes} мин.\n"
                f"<i>Цена:</i> {price_str}\n"
            )
            if service.description:
                 service_details_text += f"<i>Описание:</i> {service.description[:100] + '...' if len(service.description) > 100 else service.description}\n"
            
            service_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"🗓️ Показать слоты", 
                    callback_data=f"view_slots_{service.service_id}"
                )]
            ])
            await update.message.reply_text(service_details_text, reply_markup=service_keyboard, parse_mode=ParseMode.HTML)
        
        logger.info(f"User {user.id if user else 'N/A'} viewed available services. Count: {len(services_with_providers)}")


    except Exception as e:
        logger.error(f"Error in list_available_services for user {user.id if user else 'N/A'}: {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении списка услуг. Пожалуйста, попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()


async def my_bookings_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает клиенту список его активных бронирований."""
    user = update.effective_user
    db: Session = next(get_db())

    try:
        # Ищем активные (статус 'confirmed') и будущие бронирования для текущего клиента
        now = datetime.now()
        client_bookings = db.query(Booking).join(TimeSlot).filter(
            Booking.client_telegram_id == user.id,
            Booking.status == "confirmed", # Только подтвержденные
            TimeSlot.start_time > now      # Только будущие
        ).order_by(TimeSlot.start_time).all()

        if not client_bookings:
            await update.message.reply_text(
                "У вас нет активных предстоящих бронирований.\n"
                "Чтобы найти и забронировать услугу, используйте команду /services."
            )
            return

        response_text = "<b>Ваши предстоящие бронирования:</b>\n\n"
        
        for booking in client_bookings:
            slot = booking.slot
            service = slot.service
            provider = service.provider

            response_text += (
                f"<b>ID Брони:</b> <code>{booking.booking_id}</code>\n"
                f"<b>Услуга:</b> {service.name}\n"
                f"<b>Мастер/Компания:</b> {provider.name}\n"
                f"<b>Время:</b> {slot.start_time.strftime('%Y-%m-%d %H:%M')} - {slot.end_time.strftime('%H:%M')}\n"
            )
            keyboard_booking = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"❌ Отменить бронь ID: {booking.booking_id}",
                    callback_data=f"cancel_booking_client_{booking.booking_id}"
                )
            ]])
            await update.message.reply_text(response_text, reply_markup=keyboard_booking, parse_mode=ParseMode.HTML)
            response_text = "" # Очищаем для следующего бронирования, чтобы каждое было отдельным сообщением с кнопкой

        logger.info(f"User {user.id} viewed their bookings. Count: {len(client_bookings)}")

    except Exception as e:
        logger.error(f"Error in my_bookings_client for user {user.id}: {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении списка ваших бронирований. Пожалуйста, попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()
