"""
Генерация тестовых данных: таблицы, врачи, слоты на 7–14 дней, опционально тестовые записи.
Часовой пояс — Москва; слоты в БД сохраняются в UTC.
Запуск из корня проекта: python -m scripts.seed_db [--with-appointments]
"""
import argparse
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zoneinfo import ZoneInfo

from db.connection import get_connection, init_db

TIMEZONE = ZoneInfo("Europe/Moscow")
UTC = ZoneInfo("UTC")

NUM_DOCTORS = 15
DAYS_AHEAD = 14
SLOT_DURATIONS = (10, 20)
BOOKED_RATIO = 0.5  # доля уже занятых слотов (недоступны для записи)
WORK_START = 9
WORK_END = 18


DOCTORS_DATA = [
    ("Тихомирова А.А.", "Терапевт", "Общая терапия, ОРВИ, хронические заболевания"),
    ("Соколов И.П.", "Кардиолог", "Сердце, давление, ЭКГ"),
    ("Козлова М.В.", "Отоларинголог", "Ухо, горло, нос"),
    ("Новиков Д.С.", "Невролог", "Головные боли, головокружение, боли в спине"),
    ("Морозова Е.А.", "Гастроэнтеролог", "Желудок, кишечник, печень"),
    ("Волков А.И.", "Дерматолог", "Кожа, аллергия, сыпь"),
    ("Федорова О.Л.", "Офтальмолог", "Зрение, глаза"),
    ("Кузнецов Р.Н.", "Уролог", "Мочеполовая система"),
    ("Орлова Т.Г.", "Гинеколог", "Женское здоровье"),
    ("Лебедев П.К.", "Травматолог", "Ушибы, переломы, суставы"),
    ("Смирнова В.Ю.", "Эндокринолог", "Щитовидная железа, гормоны, диабет"),
    ("Попов Н.Д.", "Пульмонолог", "Кашель, бронхит, лёгкие"),
    ("Козлов С.М.", "Ревматолог", "Суставы, соединительная ткань"),
    ("Егорова Л.В.", "Психотерапевт", "Тревога, стресс, сон"),
    ("Павлова И.С.", "Терапевт", "Первичный приём, направление к специалистам"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed DB: doctors, slots, optional test appointments")
    parser.add_argument("--with-appointments", action="store_true", help="Create test users and appointments")
    args = parser.parse_args()

    init_db()
    conn = get_connection()

    try:
        # Врачи
        cur = conn.execute("SELECT COUNT(*) AS c FROM doctors")
        if cur.fetchone()["c"] > 0:
            print("Таблица doctors уже заполнена, пропуск.")
        else:
            for full_name, specialty, description in DOCTORS_DATA[:NUM_DOCTORS]:
                conn.execute(
                    "INSERT INTO doctors (full_name, specialty, description) VALUES (?, ?, ?)",
                    (full_name, specialty, description),
                )
            conn.commit()
            print(f"Добавлено врачей: {len(DOCTORS_DATA[:NUM_DOCTORS])}")

        # Слоты: московское время -> UTC для хранения
        cur = conn.execute("SELECT id FROM doctors")
        doctor_ids = [r["id"] for r in cur.fetchall()]
        now_moscow = datetime.now(TIMEZONE)
        start_date = now_moscow.date()
        slots_added = 0

        for day_offset in range(DAYS_AHEAD):
            day = start_date + timedelta(days=day_offset)
            for doctor_id in doctor_ids:
                for hour in range(WORK_START, WORK_END):
                    for minute in (0, 20, 40):
                        for duration in SLOT_DURATIONS:
                            start_moscow = datetime(day.year, day.month, day.day, hour, minute, 0, tzinfo=TIMEZONE)
                            if start_moscow <= now_moscow:
                                continue
                            if minute + duration > 60:
                                continue
                            start_utc = start_moscow.astimezone(UTC).isoformat()
                            is_booked = 1 if random.random() < BOOKED_RATIO else 0
                            try:
                                conn.execute(
                                    """INSERT INTO doctor_slots (doctor_id, start_utc, duration_minutes, is_booked)
                                       VALUES (?, ?, ?, ?)""",
                                    (doctor_id, start_utc, duration, is_booked),
                                )
                                slots_added += 1
                            except sqlite3.IntegrityError:
                                pass  # UNIQUE (doctor_id, start_utc, duration_minutes)
        conn.commit()
        print(f"Добавлено слотов: {slots_added}")

        if args.with_appointments:
            # Тестовые пользователи и записи
            test_telegram_ids = [111111, 222222]
            for tid in test_telegram_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO users (telegram_id, created_at) VALUES (?, ?)",
                    (tid, now_moscow.isoformat()),
                )
            conn.commit()
            cur = conn.execute("SELECT id, telegram_id FROM users WHERE telegram_id IN (?, ?)", test_telegram_ids)
            user_rows = list(cur.fetchall())
            cur = conn.execute(
                """SELECT id, doctor_id FROM doctor_slots WHERE is_booked = 0 ORDER BY RANDOM() LIMIT 4"""
            )
            free_slots = list(cur.fetchall())
            for i, u in enumerate(user_rows):
                if i < len(free_slots):
                    slot = free_slots[i]
                    conn.execute(
                        """INSERT INTO appointments (user_id, doctor_id, slot_id, description, created_at, reminder_sent, cancelled)
                           VALUES (?, ?, ?, NULL, ?, 0, 0)""",
                        (u["id"], slot["doctor_id"], slot["id"], now_moscow.isoformat()),
                    )
                    conn.execute("UPDATE doctor_slots SET is_booked = 1 WHERE id = ?", (slot["id"],))
            conn.commit()
            print("Добавлены тестовые пользователи и записи (with-appointments).")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
