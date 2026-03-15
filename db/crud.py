"""CRUD для users, doctors, slots, appointments, anamnesis_drafts. Время слотов в БД — UTC; логика «сейчас» и 3 дня — по Москве."""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db.connection import get_connection

TIMEZONE = ZoneInfo("Europe/Moscow")
UTC = ZoneInfo("UTC")


def _now_moscow() -> datetime:
    return datetime.now(TIMEZONE)


def _now_utc() -> datetime:
    return datetime.now(UTC)


# --- users ---

def create_or_get_user(telegram_id: int) -> int:
    """Возвращает user.id (создаёт пользователя при первом обращении)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        now = _now_moscow().isoformat()
        cur = conn.execute(
            "INSERT INTO users (telegram_id, created_at) VALUES (?, ?)",
            (telegram_id, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


# --- doctors ---

def get_doctors_by_ids(doctor_ids: list[int]) -> list[dict]:
    """Список врачей по id."""
    if not doctor_ids:
        return []
    conn = get_connection()
    try:
        placeholders = ",".join("?" * len(doctor_ids))
        cur = conn.execute(
            f"SELECT id, full_name, specialty, description FROM doctors WHERE id IN ({placeholders})",
            doctor_ids,
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_doctors_for_secondary(user_id: int) -> list[dict]:
    """Врачи, к которым пользователь был на приёме за последние 6 месяцев (без отменённых)."""
    conn = get_connection()
    try:
        six_months_ago = (_now_moscow() - timedelta(days=180)).astimezone(UTC).isoformat()
        cur = conn.execute("""
            SELECT DISTINCT d.id, d.full_name, d.specialty, d.description
            FROM doctors d
            JOIN appointments a ON a.doctor_id = d.id
            JOIN doctor_slots s ON s.id = a.slot_id
            WHERE a.user_id = ? AND a.cancelled = 0 AND s.start_utc >= ?
            ORDER BY d.full_name
        """, (user_id, six_months_ago))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_all_doctors() -> list[dict]:
    """Все врачи для выбора «знаю врача»."""
    conn = get_connection()
    try:
        cur = conn.execute("SELECT id, full_name, specialty, description FROM doctors ORDER BY full_name")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_therapist() -> dict | None:
    """Один врач с специальностью «Терапевт» для подстановки при отсутствии подбора."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, full_name, specialty, description FROM doctors WHERE specialty = ? LIMIT 1",
            ("Терапевт",),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_doctors_by_specialty(specialty: str) -> list[dict]:
    """Список врачей по специальности (точное совпадение)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, full_name, specialty, description FROM doctors WHERE specialty = ? ORDER BY full_name",
            (specialty,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# --- slots (в БД хранятся в UTC) ---

def get_available_slots(
    doctor_id: int,
    duration_minutes: int,
    prefer_3_days: bool = True,
) -> list[dict]:
    """
    Свободные слоты врача с длительностью duration_minutes.
    prefer_3_days: сначала слоты за 3 календарных дня (Москва); если их < 10 — ближайшие 10 без ограничения.
    """
    now_utc = _now_utc()
    now_moscow = _now_moscow()
    end_3_days_moscow = (now_moscow.date() + timedelta(days=3))
    end_3_days_utc = datetime.combine(end_3_days_moscow, datetime.max.time(), tzinfo=TIMEZONE).astimezone(UTC)
    now_utc_s = now_utc.isoformat()
    end_3_days_utc_s = end_3_days_utc.isoformat()

    conn = get_connection()
    try:
        if prefer_3_days:
            cur = conn.execute("""
                SELECT id, doctor_id, start_utc, duration_minutes
                FROM doctor_slots
                WHERE doctor_id = ? AND duration_minutes = ? AND is_booked = 0
                  AND start_utc >= ? AND start_utc <= ?
                ORDER BY start_utc
                LIMIT 10
            """, (doctor_id, duration_minutes, now_utc_s, end_3_days_utc_s))
            rows = cur.fetchall()
            if len(rows) >= 10:
                return [dict(r) for r in rows]
        cur = conn.execute("""
            SELECT id, doctor_id, start_utc, duration_minutes
            FROM doctor_slots
            WHERE doctor_id = ? AND duration_minutes = ? AND is_booked = 0 AND start_utc >= ?
            ORDER BY start_utc
            LIMIT 10
        """, (doctor_id, duration_minutes, now_utc_s))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def book_slot(slot_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE doctor_slots SET is_booked = 1 WHERE id = ?", (slot_id,))
        conn.commit()
    finally:
        conn.close()


def free_slot(slot_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE doctor_slots SET is_booked = 0 WHERE id = ?", (slot_id,))
        conn.commit()
    finally:
        conn.close()


# --- appointments ---

def create_appointment(
    user_id: int,
    doctor_id: int,
    slot_id: int,
    description: str | None = None,
) -> int:
    now = _now_moscow().isoformat()
    conn = get_connection()
    try:
        cur = conn.execute("""
            INSERT INTO appointments (user_id, doctor_id, slot_id, description, created_at, reminder_sent, cancelled)
            VALUES (?, ?, ?, ?, ?, 0, 0)
        """, (user_id, doctor_id, slot_id, description or None, now))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_appointments_count(user_id: int) -> int:
    """Количество записей пользователя (без отменённых), для выбора первичный/вторичный."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM appointments WHERE user_id = ? AND cancelled = 0",
            (user_id,),
        )
        return cur.fetchone()["c"]
    finally:
        conn.close()


def get_appointments_for_reminder(
    from_utc: datetime,
    to_utc: datetime,
) -> list[dict]:
    """Записи для напоминания: reminder_sent = 0, slot.start_utc в [from_utc, to_utc]. Возвращает id, telegram_id, start_utc, doctor_id."""
    conn = get_connection()
    try:
        cur = conn.execute("""
            SELECT a.id, u.telegram_id, s.start_utc, a.doctor_id
            FROM appointments a
            JOIN doctor_slots s ON s.id = a.slot_id
            JOIN users u ON u.id = a.user_id
            WHERE a.reminder_sent = 0 AND a.cancelled = 0
              AND s.start_utc >= ? AND s.start_utc <= ?
        """, (from_utc.isoformat(), to_utc.isoformat()))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def mark_reminder_sent(appointment_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE appointments SET reminder_sent = 1 WHERE id = ?", (appointment_id,))
        conn.commit()
    finally:
        conn.close()


def cancel_appointment(appointment_id: int) -> int | None:
    """Отменяет запись, возвращает slot_id для освобождения слота."""
    conn = get_connection()
    try:
        cur = conn.execute("SELECT slot_id FROM appointments WHERE id = ?", (appointment_id,))
        row = cur.fetchone()
        if not row:
            return None
        slot_id = row["slot_id"]
        conn.execute("UPDATE appointments SET cancelled = 1 WHERE id = ?", (appointment_id,))
        conn.commit()
        return slot_id
    finally:
        conn.close()


# --- anamnesis_drafts ---

def get_draft(user_id: int, doctor_id: int | None = None) -> dict | None:
    """Черновик анамнеза: для user_id и при необходимости для выбранного doctor_id (None = черновик до выбора врача)."""
    conn = get_connection()
    try:
        if doctor_id is None:
            cur = conn.execute("""
                SELECT id, user_id, doctor_id, symptom_description, current_question_index, answers_json, updated_at
                FROM anamnesis_drafts WHERE user_id = ? AND doctor_id IS NULL
            """, (user_id,))
        else:
            cur = conn.execute("""
                SELECT id, user_id, doctor_id, symptom_description, current_question_index, answers_json, updated_at
                FROM anamnesis_drafts WHERE user_id = ? AND doctor_id = ?
            """, (user_id, doctor_id))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_draft(
    user_id: int,
    current_question_index: int,
    answers_json: str,
    doctor_id: int | None = None,
    symptom_description: str | None = None,
) -> None:
    """Обновляет или создаёт черновик."""
    now = _now_moscow().isoformat()
    conn = get_connection()
    try:
        if doctor_id is None:
            cur = conn.execute("SELECT id FROM anamnesis_drafts WHERE user_id = ? AND doctor_id IS NULL", (user_id,))
        else:
            cur = conn.execute("SELECT id FROM anamnesis_drafts WHERE user_id = ? AND doctor_id = ?", (user_id, doctor_id))
        row = cur.fetchone()
        if row:
            conn.execute("""
                UPDATE anamnesis_drafts
                SET current_question_index = ?, answers_json = ?, updated_at = ?,
                    doctor_id = ?, symptom_description = ?
                WHERE id = ?
            """, (current_question_index, answers_json, now, doctor_id, symptom_description, row["id"]))
        else:
            conn.execute("""
                INSERT INTO anamnesis_drafts (user_id, doctor_id, symptom_description, current_question_index, answers_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, doctor_id, symptom_description, current_question_index, answers_json, now))
        conn.commit()
    finally:
        conn.close()


def delete_draft(user_id: int, doctor_id: int | None = None) -> None:
    """Удаляет черновик после успешной записи."""
    conn = get_connection()
    try:
        if doctor_id is None:
            conn.execute("DELETE FROM anamnesis_drafts WHERE user_id = ? AND doctor_id IS NULL", (user_id,))
        else:
            conn.execute("DELETE FROM anamnesis_drafts WHERE user_id = ? AND doctor_id = ?", (user_id, doctor_id))
        conn.commit()
    finally:
        conn.close()


# --- helpers для бота: слот в московском времени для отображения ---

def slot_start_moscow(slot_row: dict) -> datetime:
    """start_utc из слота перевести в Москву."""
    start_utc = datetime.fromisoformat(slot_row["start_utc"].replace("Z", "+00:00"))
    if start_utc.tzinfo is None:
        start_utc = start_utc.replace(tzinfo=UTC)
    return start_utc.astimezone(TIMEZONE)
