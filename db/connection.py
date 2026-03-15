"""Подключение к SQLite и инициализация схемы. Слоты в БД хранятся в UTC."""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("DB_PATH", Path(__file__).resolve().parent.parent / "bot.db"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. Миграция: пересоздаёт doctor_slots с UNIQUE(doctor_id, start_utc, duration_minutes)."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                specialty TEXT NOT NULL,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS doctor_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                start_utc TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                is_booked INTEGER NOT NULL DEFAULT 0,
                UNIQUE(doctor_id, start_utc, duration_minutes)
            );

            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                slot_id INTEGER NOT NULL REFERENCES doctor_slots(id),
                description TEXT,
                created_at TEXT NOT NULL,
                reminder_sent INTEGER NOT NULL DEFAULT 0,
                cancelled INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS anamnesis_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                doctor_id INTEGER REFERENCES doctors(id),
                symptom_description TEXT,
                current_question_index INTEGER NOT NULL DEFAULT 0,
                answers_json TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER);
            INSERT OR IGNORE INTO _schema_version (version) VALUES (1);
        """)
        conn.commit()

        cur = conn.execute("SELECT version FROM _schema_version LIMIT 1")
        row = cur.fetchone()
        version = row[0] if row else 1
        if version < 2:
            conn.executescript("""
                DROP TABLE IF EXISTS appointments;
                DROP TABLE IF EXISTS doctor_slots;
                CREATE TABLE doctor_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
                    start_utc TEXT NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    is_booked INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(doctor_id, start_utc, duration_minutes)
                );
                UPDATE _schema_version SET version = 2;
            """)
            conn.commit()
    finally:
        conn.close()
