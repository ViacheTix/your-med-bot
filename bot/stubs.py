"""Заглушки: подбор врачей по симптомам и список вопросов анамнеза. Часовой пояс — Москва."""
from db.crud import get_doctors_by_ids, get_therapist
from db.connection import get_connection

TIMEZONE = "Europe/Moscow"


def pick_doctors_by_symptoms(symptom_description: str, limit: int = 3) -> list[dict]:
    """
    Заглушка: по описанию симптомов вернуть до limit врачей (или терапевта).
    Сейчас: случайные врачи из БД; если ни одного — один терапевт.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT id, full_name, specialty, description FROM doctors ORDER BY RANDOM() LIMIT ?",
            (limit,),
        )
        doctors = [dict(r) for r in cur.fetchall()]
        if not doctors:
            t = get_therapist()
            if t:
                doctors = [t]
        return doctors
    finally:
        conn.close()


def get_anamnesis_questions(doctor_specialty: str | None = None) -> list[str]:
    """
    Заглушка: список вопросов для умного анамнеза (10–20 штук).
    doctor_specialty не используется в заглушке.
    """
    return [
        "Когда впервые появились симптомы?",
        "Симптомы постоянные или приходят приступами?",
        "Что усиливает или ослабляет проявления?",
        "Была ли температура? Какая максимальная?",
        "Принимаете ли вы сейчас какие-то лекарства?",
        "Есть ли аллергия на лекарства или другие вещества?",
        "Были ли похожие жалобы раньше?",
        "Есть ли хронические заболевания?",
        "Курите ли вы? Как давно и сколько?",
        "Как бы вы оценили интенсивность симптомов от 1 до 10?",
        "Симптомы мешают работе или повседневным делам?",
        "Были ли контакты с больными или переохлаждение?",
    ]
