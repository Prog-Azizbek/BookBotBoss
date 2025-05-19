# main.py
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import CallbackQueryHandler 

# Импортируем хендлеры
from handlers_common import start, help_command
from handlers_provider import (
    register_provider, add_service, my_services, 
    add_slot, my_slots, cancel_booking_provider
)
from handlers_client import list_available_services, my_bookings_client
# Импортируем токен из config.py
from config import BOT_TOKEN
# Импортируем функции для работы с БД и сами модели (пока не используем, но понадобятся)
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Provider, Service, TimeSlot, Booking, create_db_tables, get_db
# Настройка логирования для отладки
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на инлайн-кнопки."""
    query = update.callback_query
    await query.answer() # Важно ответить на колбек, чтобы кнопка перестала "грузиться"

    callback_data = query.data
    user_telegram_id = query.from_user.id
    db: Session = next(get_db())

    try:
        if callback_data.startswith("view_slots_"):
            service_id = int(callback_data.split("_")[2]) # Извлекаем ID услуги
            
            service_info = db.query(Service).filter(Service.service_id == service_id).first()
            if not service_info:
                await query.edit_message_text(text="Ошибка: Услуга не найдена.") # Редактируем исходное сообщение кнопки
                return

            # Ищем доступные слоты для этой услуги (только будущие и is_available=True)
            now = datetime.now()
            available_slots = db.query(TimeSlot).filter(
                TimeSlot.service_id == service_id,
                TimeSlot.is_available == True,
                TimeSlot.start_time > now # Только будущие слоты
            ).order_by(TimeSlot.start_time).limit(10).all() # Ограничим вывод 10 слотами для начала (пагинация потом)

            if not available_slots:
                await query.edit_message_text(
                    text=f"Для услуги '<b>{service_info.name}</b>' сейчас нет свободных слотов.\n"
                         f"Попробуйте проверить позже или выберите другую услугу.",
                    parse_mode=ParseMode.HTML
                )
                return

            slots_keyboard = []
            slots_text = f"<b>Доступные слоты для '{service_info.name}':</b>\n\n"
            
            # Если редактируем сообщение, где была кнопка "Показать слоты", то старый текст и кнопки исчезнут
            # Это нормальное поведение для edit_message_text
            
            for slot in available_slots:
                slots_text += f"🗓️ {slot.start_time.strftime('%Y-%m-%d %H:%M')} - {slot.end_time.strftime('%H:%M')}\n"
                slots_keyboard.append([
                    InlineKeyboardButton(
                        f"Забронировать на {slot.start_time.strftime('%H:%M %d.%m')}",
                        callback_data=f"book_slot_{slot.slot_id}" # Новый callback_data для бронирования
                    )
                ])
            
            # Кнопка "Назад к списку услуг" (если нужно)
            # slots_keyboard.append([InlineKeyboardButton("⬅️ Назад к услугам", callback_data="back_to_services")])
            # Для этого потребуется сохранить состояние или просто вызывать /services снова

            reply_markup_slots = InlineKeyboardMarkup(slots_keyboard)
            await query.edit_message_text(text=slots_text, reply_markup=reply_markup_slots, parse_mode=ParseMode.HTML)
            logger.info(f"User {user_telegram_id} viewed slots for service {service_id}")
        
        elif callback_data.startswith("book_slot_"):
            slot_id_to_book = int(callback_data.split("_")[2])
            
            # --- ЛОГИКА БРОНИРОВАНИЯ ---
            slot_to_book = db.query(TimeSlot).filter(
                TimeSlot.slot_id == slot_id_to_book,
                TimeSlot.is_available == True, # Убедимся, что слот все еще доступен
                TimeSlot.start_time > datetime.now() # И что он не в прошлом
            ).first()

            if not slot_to_book:
                await query.edit_message_text(text="К сожалению, этот слот уже занят или недоступен. Пожалуйста, выберите другой.")
                # Можно предложить вернуться к выбору слотов для этой услуги или к общему списку услуг
                return

            # Проверяем, нет ли у этого клиента уже бронирования на это же время (для других услуг/провайдеров)
            # Это более сложная проверка, для MVP можно опустить, но в реальной системе важна.
            # existing_client_booking_at_time = db.query(Booking).join(TimeSlot)\
            # .filter(Booking.client_telegram_id == user_telegram_id,
            # TimeSlot.start_time < slot_to_book.end_time,
            # TimeSlot.end_time > slot_to_book.start_time,
            # Booking.status == 'confirmed' # или другие активные статусы
            # ).first()
            # if existing_client_booking_at_time:
            # await query.edit_message_text(text="У вас уже есть другое бронирование на это время. Пожалуйста, отмените его или выберите другое время.")
            # return


            # Создаем бронирование
            new_booking = Booking(
                slot_id=slot_to_book.slot_id,
                client_telegram_id=user_telegram_id,
                status="confirmed" # Статус по умолчанию 'confirmed'
            )
            slot_to_book.is_available = False # Делаем слот недоступным

            db.add(new_booking)
            db.add(slot_to_book) # SQLAlchemy отследит изменения в slot_to_book
            db.commit()
            db.refresh(new_booking)
            # db.refresh(slot_to_book) # Не обязательно, если не используем его поля ниже

            # Получаем информацию об услуге и провайдере для уведомления
            service_booked = slot_to_book.service # Через relationship
            provider_of_service = service_booked.provider # Через relationship

            confirmation_text = (
                f"🎉 <b>Вы успешно забронировали услугу!</b> 🎉\n\n"
                f"<b>Услуга:</b> {service_booked.name}\n"
                f"<b>Мастер/Компания:</b> {provider_of_service.name}\n"
                f"<b>Время:</b> {slot_to_book.start_time.strftime('%Y-%m-%d %H:%M')}\n"
                f"<b>ID вашего бронирования:</b> <code>{new_booking.booking_id}</code> (сохраните его)\n\n"
                f"Мы также уведомим поставщика услуг."
            )
            await query.edit_message_text(text=confirmation_text, parse_mode=ParseMode.HTML)
            logger.info(f"User {user_telegram_id} booked slot {slot_id_to_book} for service {service_booked.service_id}. Booking ID: {new_booking.booking_id}")

            # --- Отправка уведомления Поставщику ---
            provider_telegram_id = provider_of_service.telegram_id
            try:
                await context.bot.send_message(
                    chat_id=provider_telegram_id,
                    text=f"🔔 <b>Новое бронирование!</b> 🔔\n\n"
                         f"<b>Услуга:</b> {service_booked.name}\n"
                         f"<b>Время:</b> {slot_to_book.start_time.strftime('%Y-%m-%d %H:%M')}\n"
                         f"<b>Клиент Telegram ID:</b> <code>{user_telegram_id}</code>\n"
                         f"<b>ID бронирования:</b> <code>{new_booking.booking_id}</code>",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Notification sent to provider {provider_telegram_id} for booking {new_booking.booking_id}")
            except Exception as e_notify:
                logger.error(f"Failed to send notification to provider {provider_telegram_id} for booking {new_booking.booking_id}: {e_notify}")
                # Ошибку уведомления не показываем клиенту, но логируем

        # elif callback_data == "back_to_services":
        # # Нужно либо заново вызвать list_available_services, либо как-то "откатить" сообщение
        # # Проще всего - попросить пользователя снова ввести /services
        # await query.message.reply_text("Для просмотра списка всех услуг, пожалуйста, используйте команду /services")
        # await query.delete_message() # Удаляем сообщение с кнопками слотов

        elif callback_data.startswith("cancel_booking_client_"):
            booking_id_to_cancel = int(callback_data.split("_")[3]) 

            booking_to_cancel = db.query(Booking).filter(
                Booking.booking_id == booking_id_to_cancel,
                Booking.client_telegram_id == user_telegram_id,
                # Booking.status == "confirmed" # Уже не важно, если мы просто удаляем
            ).first()

            if not booking_to_cancel:
                await query.edit_message_text(text="Бронирование не найдено или вы не можете его отменить.")
                return
            
            slot_to_free = booking_to_cancel.slot
            service_name_for_message = slot_to_free.service.name
            slot_time_for_message = slot_to_free.start_time.strftime('%Y-%m-%d %H:%M')
            provider_telegram_id_for_notify = slot_to_free.service.provider.telegram_id


            # Освобождаем слот
            slot_to_free.is_available = True
            db.add(slot_to_free) # Отмечаем слот как измененный

            # Удаляем бронирование
            db.delete(booking_to_cancel) 
            db.commit()

            # Уведомляем клиента
            await query.edit_message_text(
                text=f"Бронирование ID <code>{booking_id_to_cancel}</code> на услугу "
                     f"<b>{service_name_for_message}</b> ({slot_time_for_message}) "
                     f"успешно отменено. Слот снова доступен.",
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Client {user_telegram_id} cancelled and deleted booking {booking_id_to_cancel}")

            # Уведомляем поставщика
            try:
                await context.bot.send_message(
                    chat_id=provider_telegram_id_for_notify,
                    text=f"ℹ️ <b>Отмена бронирования клиентом</b> ℹ️\n\n"
                         f"Бронирование ID <code>{booking_id_to_cancel}</code> на услугу "
                         f"<b>{service_name_for_message}</b>\n"
                         f"Время: {slot_time_for_message}\n"
                         f"было отменено клиентом (TG ID: <code>{user_telegram_id}</code>). Слот снова доступен.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e_notify:
                logger.error(f"Failed to send cancellation notification to provider {provider_telegram_id_for_notify} for booking {booking_id_to_cancel}: {e_notify}")
               
        else:
            await query.edit_message_text(text=f"Неизвестный колбек: {callback_data}")
            logger.warning(f"Received unknown callback_data: {callback_data} from user {user_telegram_id}")

    except Exception as e:
        logger.error(f"Error in button_callback_handler (callback_data: {query.data if query else 'N/A'}) for user {user_telegram_id if query else 'N/A'}: {e}")
        # В случае ошибки можно попробовать отправить сообщение в чат, если edit_message_text не сработает
        try:
            await query.edit_message_text("Произошла непредвиденная ошибка при обработке вашего запроса.")
        except Exception as e_edit_fallback:
             logger.error(f"Fallback edit_message_text also failed: {e_edit_fallback}")
             # Если и это не сработало, можно попробовать context.bot.send_message, если есть query.message.chat_id
             if query and query.message:
                 await context.bot.send_message(chat_id=query.message.chat_id, text="Произошла ошибка. Попробуйте снова.")
    except Exception as e:
        # ...
        pass
    finally:
        db.close()


def main() -> None:
    """Запуск бота."""
    create_db_tables()
    logger.info("Database tables checked/created.")

    application = Application.builder().token(BOT_TOKEN).build()

    # Общие команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Команды Поставщика
    application.add_handler(CommandHandler("register_provider", register_provider))
    application.add_handler(CommandHandler("add_service", add_service))
    application.add_handler(CommandHandler("my_services", my_services))
    application.add_handler(CommandHandler("add_slot", add_slot))
    application.add_handler(CommandHandler("my_slots", my_slots))
    application.add_handler(CommandHandler("cancel_booking_provider", cancel_booking_provider))

    # Команды Клиента
    application.add_handler(CommandHandler("services", list_available_services))
    application.add_handler(CommandHandler("my_bookings", my_bookings_client))
    
    # Обработчик колбеков
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot is starting...")
    application.run_polling()
    logger.info("Bot has stopped.")

if __name__ == "__main__":
    main()