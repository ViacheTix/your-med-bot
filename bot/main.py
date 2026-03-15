"""Точка входа бота: aiogram, FSM, напоминания за 24 ч (APScheduler). Часовой пояс — Москва."""
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, TIMEZONE
from db import init_db, get_appointments_for_reminder, mark_reminder_sent, get_doctors_by_ids
from bot.handlers import router
from bot.keyboards import cancel_reminder_kb

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")
REMINDER_INTERVAL_MINUTES = 15
REMINDER_WINDOW_HOURS = (23, 25)  # напоминать, если приём через 23–25 ч


async def send_reminders(bot: Bot) -> None:
    """Найти записи с приёмом через ~24 ч, отправить напоминание, пометить reminder_sent."""
    now_utc = datetime.now(UTC)
    from_utc = now_utc + timedelta(hours=REMINDER_WINDOW_HOURS[0])
    to_utc = now_utc + timedelta(hours=REMINDER_WINDOW_HOURS[1])
    appointments = get_appointments_for_reminder(from_utc, to_utc)
    for apt in appointments:
        try:
            doctor_id = apt["doctor_id"]
            doctors = get_doctors_by_ids([doctor_id])
            doctor_name = doctors[0]["full_name"] if doctors else "врач"
            start_utc = datetime.fromisoformat(apt["start_utc"].replace("Z", "+00:00"))
            if start_utc.tzinfo is None:
                start_utc = start_utc.replace(tzinfo=UTC)
            start_moscow = start_utc.astimezone(TIMEZONE)
            time_str = start_moscow.strftime("%d.%m.%Y в %H:%M")
            text = f"Напоминание: завтра у вас приём у {doctor_name} в {time_str} (Мск). Можно отменить запись кнопкой ниже."
            await bot.send_message(
                apt["telegram_id"],
                text,
                reply_markup=cancel_reminder_kb(apt["id"]),
            )
            mark_reminder_sent(apt["id"])
        except Exception as e:
            logger.exception("Reminder send failed for appointment %s: %s", apt.get("id"), e)


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("Задайте BOT_TOKEN в .env")

    init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        send_reminders,
        "interval",
        minutes=REMINDER_INTERVAL_MINUTES,
        args=(bot,),
        id="reminders",
    )

    async def run() -> None:
        scheduler.start()
        try:
            await dp.start_polling(bot)
        finally:
            scheduler.shutdown(wait=False)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
