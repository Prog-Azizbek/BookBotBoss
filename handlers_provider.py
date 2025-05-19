# handlers_provider.py
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from database import get_db, Provider, Service, TimeSlot, Booking

logger = logging.getLogger(__name__)

async def register_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Регистрирует нового поставщика услуг."""
    user = update.effective_user
    args = context.args # Получаем аргументы после команды

    if not args:
        await update.message.reply_text(
            "Пожалуйста, укажите название вашей компании или ваше имя после команды.\n"
            "Пример: `/register_provider Салон Красоты Фея`",
            parse_mode=ParseMode.HTML
        )
        return

    provider_name = " ".join(args) # Объединяем все аргументы в одну строку - это имя провайдера
    db: Session = next(get_db()) # Получаем сессию БД

    try:
        # Проверяем, не зарегистрирован ли уже такой пользователь
        existing_provider = db.query(Provider).filter(Provider.telegram_id == user.id).first()
        if existing_provider:
            await update.message.reply_text(
                f"Вы уже зарегистрированы как поставщик услуг под именем: <b>{existing_provider.name}</b>.",
                parse_mode=ParseMode.HTML
            )
            return

        # Создаем нового поставщика
        new_provider = Provider(telegram_id=user.id, name=provider_name)
        db.add(new_provider)
        db.commit()
        db.refresh(new_provider) # Обновляем объект, чтобы получить provider_id

        await update.message.reply_text(
            f"Поздравляем, <b>{provider_name}</b>! Вы успешно зарегистрированы как поставщик услуг.\n"
            f"Ваш ID поставщика: <code>{new_provider.provider_id}</code> (он может понадобиться позже).\n"
            f"Теперь вы можете добавлять свои услуги и временные слоты.",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Provider registered: {provider_name} (Telegram ID: {user.id}, Provider ID: {new_provider.provider_id})")

    except Exception as e:
        logger.error(f"Error during provider registration for user {user.id}: {e}")
        db.rollback() # Откатываем изменения в БД в случае ошибки
        await update.message.reply_text(
            "Произошла ошибка при регистрации. Пожалуйста, попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()


async def add_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавляет новую услугу для зарегистрированного поставщика."""
    user = update.effective_user
    db: Session = next(get_db())

    try:
        # 1. Проверяем, является ли пользователь зарегистрированным поставщиком
        current_provider = db.query(Provider).filter(Provider.telegram_id == user.id, Provider.is_active == True).first()
        if not current_provider:
            await update.message.reply_text(
                "Эта команда доступна только для зарегистрированных и активных поставщиков услуг.\n"
                "Пожалуйста, сначала зарегистрируйтесь с помощью команды: \n"
                "`/register_provider <Ваше Имя/Название Компании>`",
                parse_mode=ParseMode.HTML # Используем HTML, т.к. в строке есть < >
            )
            return

        # 2. Парсим аргументы
        if not context.args:
            await update.message.reply_text(
                "Пожалуйста, укажите данные для услуги после команды.\n"
                "Формат: `/add_service Название Услуги; Описание; Длительность в минутах; Цена`\n"
                "Пример: `/add_service Стрижка мужская; Классическая стрижка; 60; 500`\n"
                "Описание и Цена являются необязательными. Если цена не указана, она будет 0.\n"
                "Если описание не нужно, оставьте его пустым: `/add_service Стрижка; ; 60; 500`", # или даже /add_service Стрижка;60
                parse_mode=ParseMode.HTML
            )
            return

        full_args_str = " ".join(context.args)
        parts = [p.strip() for p in full_args_str.split(';')]

        if len(parts) < 2 or len(parts) > 4 : # Минимум: Название, Длительность. Максимум + Описание, Цена
            await update.message.reply_text(
                "Неверный формат. Используйте: `/add_service Название; [Описание]; Длительность (мин); [Цена]`\n"
                "Описание и цена - необязательные поля. Разделяйте данные точкой с запятой ';'.\n"
                "Пример только с обязательными полями: `/add_service Экспресс-маникюр; 30` (описание пустое, цена 0)\n"
                "Пример со всеми полями: `/add_service Полный уход; Спа-процедуры для рук; 90; 1500`",
                parse_mode=ParseMode.HTML
            )
            return

        service_name = parts[0]

        # Длительность должна быть в предпоследней или последней позиции
        try:
            duration_minutes_str = ""
            if len(parts) == 2: # Название; Длительность
                duration_minutes_str = parts[1]
            elif len(parts) == 3: # Название; Описание; Длительность ИЛИ Название; Длительность; Цена
                # Пытаемся предпоследний как длительность
                try:
                    duration_minutes = int(parts[1]) # Название; Длительность; Цена
                    duration_minutes_str = parts[1]
                except ValueError: # Значит это Название; Описание; Длительность
                    duration_minutes_str = parts[2]
            elif len(parts) == 4: # Название; Описание; Длительность; Цена
                duration_minutes_str = parts[2]

            duration_minutes = int(duration_minutes_str)
            if duration_minutes <= 0:
                await update.message.reply_text("Длительность услуги должна быть положительным числом минут.")
                return
        except ValueError:
            await update.message.reply_text("Неверный формат длительности. Укажите количество минут (целое число).")
            return
        except IndexError:
            await update.message.reply_text("Ошибка при разборе аргументов. Проверьте формат ввода.")
            return

        # Определение описания и цены на основе количества аргументов
        description = ""
        price = 0.0

        if len(parts) == 2: # Название; Длительность
            pass # description и price остаются по умолчанию
        elif len(parts) == 3:
            # Это может быть (Название; Описание; Длительность) или (Название; Длительность; Цена)
            try: # Проверяем, является ли второй аргумент (parts[1]) числом (длительностью)
                int(parts[1]) # Если да, то это (Название; Длительность; Цена)
                price_str = parts[2]
                try:
                    price = float(price_str)
                    if price < 0:
                        await update.message.reply_text("Цена не может быть отрицательной.")
                        return
                except ValueError:
                    await update.message.reply_text("Неверный формат цены. Укажите число.")
                    return
            except ValueError: # Если второй аргумент не число, то это (Название; Описание; Длительность)
                description = parts[1]
        elif len(parts) == 4: # Название; Описание; Длительность; Цена
            description = parts[1]
            price_str = parts[3]
            try:
                price = float(price_str)
                if price < 0:
                    await update.message.reply_text("Цена не может быть отрицательной.")
                    return
            except ValueError:
                await update.message.reply_text("Неверный формат цены. Укажите число.")
                return

        if not service_name:
            await update.message.reply_text("Название услуги не может быть пустым.")
            return

        # 3. Создаем и сохраняем услугу
        new_service = Service(
            provider_id=current_provider.provider_id,
            name=service_name,
            description=description,
            duration_minutes=duration_minutes,
            price=price
        )
        db.add(new_service)
        db.commit()
        db.refresh(new_service)

        await update.message.reply_text(
            f"Услуга '<b>{new_service.name}</b>' успешно добавлена!\n"
            f"ID услуги: <code>{new_service.service_id}</code>\n"
            f"Длительность: {new_service.duration_minutes} мин.\n"
            f"Описание: {new_service.description if new_service.description else 'не указано'}\n"
            f"Цена: {new_service.price if new_service.price is not None else 'не указана'}",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Service added by provider {current_provider.provider_id}: {new_service.name} (Service ID: {new_service.service_id})")

    except Exception as e:
        logger.error(f"Error during service addition for user {user.id} (Provider ID: {current_provider.provider_id if 'current_provider' in locals() and current_provider else 'N/A'}): {e}")
        db.rollback()
        await update.message.reply_text(
            "Произошла ошибка при добавлении услуги. Пожалуйста, проверьте формат данных или попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()

async def my_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список услуг, добавленных текущим поставщиком."""
    user = update.effective_user
    db: Session = next(get_db())

    try:
        # 1. Проверяем, является ли пользователь зарегистрированным поставщиком
        current_provider = db.query(Provider).filter(Provider.telegram_id == user.id, Provider.is_active == True).first()
        if not current_provider:
            await update.message.reply_text(
                "Эта команда доступна только для зарегистрированных и активных поставщиков услуг.\n"
                "Пожалуйста, сначала зарегистрируйтесь.", # Убрал пример команды, т.к. он уже должен быть зареган
                parse_mode=ParseMode.HTML
            )
            return

        # 2. Получаем все услуги этого поставщика
        services = db.query(Service).filter(Service.provider_id == current_provider.provider_id).all()

        if not services:
            await update.message.reply_text(
                "У вас пока нет добавленных услуг. \n"
                "Используйте команду `/add_service Название; [Описание]; Длительность; [Цена]` для добавления.",
                parse_mode=ParseMode.HTML
            )
            return

        response_text = f"<b>Ваши услуги ({current_provider.name}):</b>\n\n"
        for service in services:
            price_str = f"{service.price:.2f} руб." if service.price is not None and service.price > 0 else "не указана"
            description_str = f" - <i>{service.description}</i>" if service.description else ""
            response_text += (
                f"<b>ID:</b> <code>{service.service_id}</code>\n"
                f"<b>Название:</b> {service.name}\n"
                f"<b>Длительность:</b> {service.duration_minutes} мин.\n"
                f"<b>Цена:</b> {price_str}\n"
                f"<b>Описание:</b> {service.description if service.description else 'нет'}\n"
                f"--------------------\n"
            )
        
        # Ограничение на длину сообщения в Telegram (4096 символов)
        # Если список очень длинный, нужно будет разбивать на несколько сообщений
        if len(response_text) > 4090: # Небольшой запас
            logger.warning(f"Response text for my_services is too long ({len(response_text)} chars) for provider {current_provider.provider_id}. May be truncated by Telegram.")


        await update.message.reply_text(response_text, parse_mode=ParseMode.HTML)
        logger.info(f"Provider {current_provider.provider_id} viewed their services. Count: {len(services)}")

    except Exception as e:
        logger.error(f"Error in my_services for user {user.id} (Provider ID: {current_provider.provider_id if 'current_provider' in locals() and current_provider else 'N/A'}): {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении списка ваших услуг. Пожалуйста, попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()

async def add_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавляет временной слот для указанной услуги поставщика."""
    user = update.effective_user
    db: Session = next(get_db())

    try:
        # 1. Проверяем, является ли пользователь зарегистрированным поставщиком
        current_provider = db.query(Provider).filter(Provider.telegram_id == user.id, Provider.is_active == True).first()
        if not current_provider:
            await update.message.reply_text(
                "Эта команда доступна только для зарегистрированных и активных поставщиков услуг.",
                parse_mode=ParseMode.HTML
            )
            return

        # 2. Парсим аргументы: ID_услуги и ДатаВремя начала слота
        if len(context.args) < 2: # Ожидаем ID и как минимум дату, время может быть через пробел
            await update.message.reply_text(
                "Неверный формат. Используйте: `/add_slot <ID_услуги> <ГГГГ-ММ-ДД> <ЧЧ:ММ>`\n"
                "Пример: `/add_slot 123 2024-07-15 10:00`",
                parse_mode=ParseMode.HTML
            )
            return

        try:
            service_id_to_add_slot = int(context.args[0])
        except ValueError:
            await update.message.reply_text("ID услуги должен быть числом.")
            return

        # Собираем дату и время из оставшихся аргументов
        datetime_str_parts = context.args[1:]
        if len(datetime_str_parts) != 2: # Ожидаем отдельно дату и отдельно время
             await update.message.reply_text(
                "Неверный формат даты и времени. Укажите дату и время раздельно.\n"
                "Пример: `2024-07-15 10:00`",
                parse_mode=ParseMode.HTML
            )
             return
        
        datetime_str = f"{datetime_str_parts[0]} {datetime_str_parts[1]}" # "ГГГГ-ММ-ДД ЧЧ:ММ"

        try:
            start_time_dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(
                "Неверный формат даты или времени. Используйте `ГГГГ-ММ-ДД ЧЧ:ММ`.\n"
                "Пример: `2024-07-15 10:00`",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Проверка, что время не в прошлом
        if start_time_dt < datetime.now():
            await update.message.reply_text(
                "Нельзя добавлять слоты на прошедшее время.",
                parse_mode=ParseMode.HTML
            )
            return

        # 3. Проверяем, существует ли услуга с таким ID у этого поставщика
        service_for_slot = db.query(Service).filter(
            Service.service_id == service_id_to_add_slot,
            Service.provider_id == current_provider.provider_id
        ).first()

        if not service_for_slot:
            await update.message.reply_text(
                f"Услуга с ID <code>{service_id_to_add_slot}</code> не найдена или не принадлежит вам.\n"
                "Вы можете посмотреть ID ваших услуг командой `/my_services`.",
                parse_mode=ParseMode.HTML
            )
            return

        # 4. Рассчитываем время окончания слота
        end_time_dt = start_time_dt + timedelta(minutes=service_for_slot.duration_minutes)

        existing_slot_at_time = db.query(TimeSlot).filter(
            TimeSlot.service_id == service_for_slot.service_id,
            TimeSlot.start_time == start_time_dt
        ).first()

        if existing_slot_at_time:
            status_msg = "забронирован" if not existing_slot_at_time.is_available else "уже существует"
            await update.message.reply_text(
                f"Слот для услуги '<b>{service_for_slot.name}</b>' на <i>{start_time_dt.strftime('%Y-%m-%d %H:%M')}</i> {status_msg}.",
                parse_mode=ParseMode.HTML
            )
            return
        
        overlapping_slots = db.query(TimeSlot).filter(
            TimeSlot.service_id == service_for_slot.service_id,
            TimeSlot.start_time < end_time_dt,
            TimeSlot.end_time > start_time_dt
        ).first()

        if overlapping_slots:
            await update.message.reply_text(
                f"Новый слот пересекается с существующим слотом для услуги '<b>{service_for_slot.name}</b>'.\n"
                f"Существующий слот: {overlapping_slots.start_time.strftime('%H:%M')} - {overlapping_slots.end_time.strftime('%H:%M')}",
                parse_mode=ParseMode.HTML
            )
            return


        # 6. Создаем и сохраняем слот
        new_slot = TimeSlot(
            service_id=service_for_slot.service_id,
            start_time=start_time_dt,
            end_time=end_time_dt,
            is_available=True
        )
        db.add(new_slot)
        db.commit()
        db.refresh(new_slot)

        await update.message.reply_text(
            f"Временной слот для услуги '<b>{service_for_slot.name}</b>' успешно добавлен!\n"
            f"ID слота: <code>{new_slot.slot_id}</code>\n"
            f"Время: {new_slot.start_time.strftime('%Y-%m-%d %H:%M')} - {new_slot.end_time.strftime('%H:%M')}",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Slot added by provider {current_provider.provider_id} for service {service_for_slot.service_id}: {new_slot.start_time} (Slot ID: {new_slot.slot_id})")

    except Exception as e:
        logger.error(f"Error in add_slot for user {user.id} (Provider ID: {current_provider.provider_id if 'current_provider' in locals() and current_provider else 'N/A'}): {e}")
        db.rollback()
        await update.message.reply_text(
            "Произошла ошибка при добавлении временного слота. Пожалуйста, проверьте формат данных или попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()


async def my_slots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список временных слотов, добавленных поставщиком, с их статусом."""
    user = update.effective_user
    db: Session = next(get_db())

    try:
        # 1. Проверяем, является ли пользователь зарегистрированным поставщиком
        current_provider = db.query(Provider).filter(Provider.telegram_id == user.id, Provider.is_active == True).first()
        if not current_provider:
            await update.message.reply_text(
                "Эта команда доступна только для зарегистрированных и активных поставщиков услуг.",
                parse_mode=ParseMode.HTML
            )
            return

        # 2. Получаем все услуги этого поставщика, чтобы потом получить их слоты
        slots_query = db.query(TimeSlot).join(Service).filter(Service.provider_id == current_provider.provider_id)
        
        slots_query = slots_query.order_by(TimeSlot.start_time) # Сортируем по времени начала
        
        all_slots = slots_query.all()


        if not all_slots:
            await update.message.reply_text(
                "У вас пока нет добавленных временных слотов.\n"
                "Используйте команду `/add_slot <ID_услуги> <ГГГГ-ММ-ДД> <ЧЧ:ММ>` для их создания.",
                parse_mode=ParseMode.HTML
            )
            return

        response_text = f"<b>Ваши временные слоты ({current_provider.name}):</b>\n\n"
        
        # Группировка по услугам для лучшей читаемости (опционально, но красиво)
        slots_by_service = {}
        for slot in all_slots:
            if slot.service.name not in slots_by_service:
                slots_by_service[slot.service.name] = {"service_id": slot.service_id, "slots": []}
            slots_by_service[slot.service.name]["slots"].append(slot)
        
        service_chunks = [] # Будем собирать текст по услугам, чтобы не превысить лимит

        for service_name, data in slots_by_service.items():
            service_id = data["service_id"]
            current_service_text = f"<u><b>Услуга: {service_name} (ID: {service_id})</b></u>\n"
            
            if not data["slots"]:
                current_service_text += "  <i>Нет доступных слотов для этой услуги.</i>\n\n"
                service_chunks.append(current_service_text)
                continue

            for slot in data["slots"]:
                status_emoji = "✅" if slot.is_available else "❌"
                status_text = "Свободен" if slot.is_available else "Забронирован"
                
                booking_info = ""
                if not slot.is_available and slot.booking: # Если есть бронирование
                    booking_info = f" (ID брони: <code>{slot.booking.booking_id}</code>, Клиент TG ID: <code>{slot.booking.client_telegram_id}</code>)"
                
                current_service_text += (
                    f"  <b>ID слота:</b> <code>{slot.slot_id}</code>\n"
                    f"  <b>Время:</b> {slot.start_time.strftime('%Y-%m-%d %H:%M')} - {slot.end_time.strftime('%H:%M')}\n"
                    f"  <b>Статус:</b> {status_emoji} {status_text}{booking_info}\n"
                    f"  --------------------\n"
                )
            service_chunks.append(current_service_text + "\n") # Добавляем отступ между услугами
            
        # Сборка и отправка сообщений
        current_message = response_text
        for chunk in service_chunks:
            if len(current_message) + len(chunk) > 4090: # Проверяем перед добавлением нового чанка
                await update.message.reply_text(current_message, parse_mode=ParseMode.HTML)
                current_message = "" # Начинаем новое сообщение
            current_message += chunk
        
        if current_message: # Отправляем остаток, если есть
            await update.message.reply_text(current_message, parse_mode=ParseMode.HTML)

        logger.info(f"Provider {current_provider.provider_id} viewed their slots. Total slots: {len(all_slots)}")

    except Exception as e:
        logger.error(f"Error in my_slots for user {user.id} (Provider ID: {current_provider.provider_id if 'current_provider' in locals() and current_provider else 'N/A'}): {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении списка ваших слотов. Пожалуйста, попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()


async def cancel_booking_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Позволяет поставщику отменить бронирование по его ID."""
    user = update.effective_user
    db: Session = next(get_db())

    try:
        # 1. Проверяем, является ли пользователь зарегистрированным поставщиком
        current_provider = db.query(Provider).filter(Provider.telegram_id == user.id, Provider.is_active == True).first()
        if not current_provider:    
            await update.message.reply_text(
                "Эта команда доступна только для зарегистрированных и активных поставщиков услуг.",
                parse_mode=ParseMode.HTML
            )
            return

        # 2. Парсим аргументы: ID бронирования
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(
                "Пожалуйста, укажите ID бронирования, которое вы хотите отменить.\n"
                "Формат: `/cancel_booking_provider 'ID_брони'`\n"
                "Вы можете посмотреть ID броней в команде `/my_slots`.",
                parse_mode=ParseMode.HTML
            )
            return
        
        try:
            booking_id_to_cancel = int(context.args[0])
        except ValueError:
            await update.message.reply_text(
                "Некорректный формат ID бронирования.\n"
                "Пожалуйста, укажите числовой ID, как в команде `/cancel_booking_provider <ID>`",
                parse_mode=ParseMode.HTML
            )
            return

        # 3. Ищем бронирование и проверяем, что оно принадлежит услуге этого поставщика
        # и что оно еще не отменено
        booking_to_cancel = db.query(Booking).join(TimeSlot).join(Service).filter(
            Booking.booking_id == booking_id_to_cancel,
            Service.provider_id == current_provider.provider_id,
        ).first()

        if not booking_to_cancel:
            await update.message.reply_text(
                f"Бронирование с ID <code>{booking_id_to_cancel}</code> не найдено, уже отменено, "
                "или не относится к вашим услугам.",
                parse_mode=ParseMode.HTML
            )
            return
        
        slot_of_booking = booking_to_cancel.slot
        service_of_booking = slot_of_booking.service
        client_telegram_id_for_notify = booking_to_cancel.client_telegram_id

        # Освобождаем слот
        slot_of_booking.is_available = True
        db.add(slot_of_booking)

        # Удаляем бронирование
        db.delete(booking_to_cancel)
        db.commit()

        # 5. Уведомляем поставщика об успехе
        await update.message.reply_text(
            f"Бронирование ID <code>{booking_id_to_cancel}</code> на услугу "
            f"<b>{service_of_booking.name}</b> ({slot_of_booking.start_time.strftime('%Y-%m-%d %H:%M')}) "
            f"успешно отменено вами и удалено. Слот снова доступен.",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Provider {current_provider.provider_id} cancelled and deleted booking {booking_id_to_cancel}")

        # 6. Уведомляем клиента об отмене
        try:
            await context.bot.send_message(
                chat_id=client_telegram_id_for_notify,
                text=f"⚠️ <b>Ваше бронирование было отменено поставщиком</b> ⚠️\n\n"
                     f"Бронирование ID <code>{booking_id_to_cancel}</code> на услугу "
                     f"<b>{service_of_booking.name}</b>\n"
                     f"Время: {slot_of_booking.start_time.strftime('%Y-%m-%d %H:%M')}\n"
                     f"Поставщик: {current_provider.name}\n\n"
                     f"К сожалению, это бронирование было отменено. "
                     f"Пожалуйста, свяжитесь с поставщиком для уточнения причин или выберите другое время/услугу.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e_notify:
            logger.error(f"Failed to send provider cancellation notification to client {client_telegram_id_for_notify} for booking {booking_id_to_cancel}: {e_notify}")

    except Exception as e:
        logger.error(f"Error in cancel_booking_provider for user {user.id} (Provider ID: {current_provider.provider_id if 'current_provider' in locals() and current_provider else 'N/A'}): {e}")
        db.rollback()
        await update.message.reply_text(
            "Произошла ошибка при отмене бронирования. Пожалуйста, попробуйте позже."
        )
    finally:
        if 'db' in locals() and db: db.close()
