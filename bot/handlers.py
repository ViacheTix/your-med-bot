# noqa: E501
"""Обработчики: /start, первичный/вторичный, врачи, анамнез, слоты, подтверждение."""
import json
import logging
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards import (
    start_choice_kb,
    yes_no_kb,
    doctors_kb,
    slots_kb,
    confirm_booking_kb,
)
from bot.states import (
    StartChoice,
    PrimaryBranch,
    PrimaryKnowsDoctor,
    PrimaryNoDoctor,
    Secondary,
)
from bot.stubs import pick_doctors_by_symptoms, get_anamnesis_questions
from db import (
    create_or_get_user,
    get_all_doctors,
    get_doctors_for_secondary,
    get_available_slots,
    book_slot,
    create_appointment,
    get_user_appointments_count,
    get_draft,
    save_draft,
    delete_draft,
    get_doctors_by_ids,
    slot_start_moscow,
    get_connection,
    cancel_appointment,
    free_slot,
)

logger = logging.getLogger(__name__)
router = Router()

# Длительность слотов: с анамнезом / вторичный — 10 мин, без анамнеза — 20 мин
DURATION_MIN_WITH_ANAMNESIS = 10
DURATION_MIN_WITHOUT_ANAMNESIS = 20

TEXT_START = "Здравствуйте! Я помогу записаться на приём.\n\nВыберите тип приёма:"
TEXT_SECONDARY_EXPLAIN = "Вторичный приём — визит к тому же врачу, к которому вы обращались в последние 6 месяцев."
TEXT_PRIMARY_KNOW_DOCTOR = "К какому врачу хотите записаться? Выберите из списка:"
TEXT_ANAMNESIS_OFFER = (
    "Умный анамнез — короткий опрос перед приёмом. Ответы помогут врачу подготовиться. Заполнить?"
)
TEXT_SYMPTOMS_PRIMARY = "Опишите, что вас беспокоит (симптомы, жалобы). По описанию подберём врача."
TEXT_SYMPTOMS_ANAMNESIS = "Кратко опишите симптомы для анамнеза:"
TEXT_CHOOSE_DOCTOR = "По вашему описанию подходят эти специалисты. Выберите врача:"
TEXT_ALL_CORRECT = "Всё верно?"
TEXT_FIX_QUESTION = "Введите номер вопроса и новый ответ (например: 3 Новый ответ)."
TEXT_SLOT_CHOOSE = "Выберите удобное время (по Москве):"
TEXT_CONFIRM_BOOKING = "Подтвердите запись:"
TEXT_BOOKED = "Запись оформлена. За 24 часа до приёма пришлём напоминание с возможностью отменить."
TEXT_NO_SLOTS = "К сожалению, свободных слотов пока нет. Попробуйте позже."


# --- /start ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = create_or_get_user(message.from_user.id)
    count = get_user_appointments_count(user_id)
    has_visits = count > 0
    await state.set_state(StartChoice.choosing_type)
    await state.update_data(user_id=user_id)
    text = TEXT_START
    if has_visits:
        text += "\n\n" + TEXT_SECONDARY_EXPLAIN
    await message.answer(text, reply_markup=start_choice_kb(has_visits))


# --- Первичный: знаете врача? ---

@router.callback_query(StartChoice.choosing_type, F.data == "primary")
async def primary_start(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    user_id = create_or_get_user(cq.from_user.id)
    await state.update_data(user_id=user_id)
    await state.set_state(PrimaryBranch.choosing_know_doctor)
    await cq.message.edit_text(
        "Знаете ли вы врача, к которому хотите записаться?",
        reply_markup=yes_no_kb("know_doctor_yes", "know_doctor_no"),
    )


@router.callback_query(PrimaryBranch.choosing_know_doctor, F.data == "know_doctor_yes")
async def primary_knows_doctor(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(PrimaryKnowsDoctor.choosing_doctor)
    doctors = get_all_doctors()
    await cq.message.edit_text(TEXT_PRIMARY_KNOW_DOCTOR, reply_markup=doctors_kb(doctors, "p_doc"))


@router.callback_query(PrimaryBranch.choosing_know_doctor, F.data == "know_doctor_no")
async def primary_no_doctor(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(PrimaryNoDoctor.symptom_description)
    await cq.message.edit_text(TEXT_SYMPTOMS_PRIMARY)


# --- Вторичный ---

@router.callback_query(StartChoice.choosing_type, F.data == "secondary")
async def secondary_start(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    user_id = create_or_get_user(cq.from_user.id)
    await state.update_data(user_id=user_id)
    doctors = get_doctors_for_secondary(user_id)
    if not doctors:
        await cq.message.edit_text("Нет записей за последние 6 месяцев. Выберите «Первичный приём».")
        await state.set_state(StartChoice.choosing_type)
        await cq.message.answer(TEXT_START, reply_markup=start_choice_kb(True))
        return
    await state.set_state(Secondary.choosing_doctor)
    await cq.message.edit_text("К какому врачу записываемся? (вторичный приём)", reply_markup=doctors_kb(doctors, "s_doc"))


@router.callback_query(Secondary.choosing_doctor, F.data.startswith("s_doc:"))
async def secondary_doctor_chosen(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    doctor_id = int(cq.data.split(":")[1])
    await state.update_data(doctor_id=doctor_id)
    await state.set_state(Secondary.choosing_slot)
    slots = get_available_slots(doctor_id, DURATION_MIN_WITH_ANAMNESIS, prefer_3_days=True)
    if not slots:
        await cq.message.edit_text(TEXT_NO_SLOTS)
        return
    await cq.message.edit_text(TEXT_SLOT_CHOOSE, reply_markup=slots_kb(slots, "s_slot"))


@router.callback_query(Secondary.choosing_slot, F.data.startswith("s_slot:"))
async def secondary_slot_chosen(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    slot_id = int(cq.data.split(":")[1])
    data = await state.get_data()
    slots = get_available_slots(data["doctor_id"], DURATION_MIN_WITH_ANAMNESIS, prefer_3_days=True)
    slot = next((s for s in slots if s["id"] == slot_id), None)
    if not slot:
        await cq.answer("Слот занят. Выберите другое время.", show_alert=True)
        return
    conn = get_connection()
    cur = conn.execute("SELECT full_name FROM doctors WHERE id = ?", (data["doctor_id"],))
    doctor_name = cur.fetchone()["full_name"]
    conn.close()
    start = slot_start_moscow(slot)
    time_str = start.strftime("%d.%m.%Y в %H:%M (Мск)")
    await state.update_data(slot_id=slot_id)
    await state.set_state(Secondary.confirm_booking)
    await cq.message.edit_text(
        f"Врач: {doctor_name}\nВремя: {time_str}\n\n" + TEXT_CONFIRM_BOOKING,
        reply_markup=confirm_booking_kb(),
    )


@router.callback_query(Secondary.confirm_booking, F.data == "confirm_booking")
async def secondary_confirm_booking(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    book_slot(data["slot_id"])
    create_appointment(data["user_id"], data["doctor_id"], data["slot_id"], None)
    await state.clear()
    await cq.message.edit_text(TEXT_BOOKED)


# --- Первичный, знает врача: врач -> анамнез да/нет -> слоты или вопросы ---

@router.callback_query(PrimaryKnowsDoctor.choosing_doctor, F.data.startswith("p_doc:"))
async def primary_knows_doctor_chosen(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    doctor_id = int(cq.data.split(":")[1])
    await state.update_data(doctor_id=doctor_id)
    await state.set_state(PrimaryKnowsDoctor.choosing_anamnesis)
    data = await state.get_data()
    user_id = data["user_id"]
    draft = get_draft(user_id, doctor_id)
    if draft:
        await cq.message.edit_text(
            "У вас есть незавершённый анамнез. Продолжить?",
            reply_markup=yes_no_kb("draft_continue", "draft_new"),
        )
        return
    await cq.message.edit_text(TEXT_ANAMNESIS_OFFER, reply_markup=yes_no_kb("anamnesis_yes", "anamnesis_no"))


def _format_summary(questions: list[str], answers: list[str]) -> str:
    return "\n\n".join(f"{i}. {q}\n   {a}" for i, (q, a) in enumerate(zip(questions, answers), 1))


async def _go_to_anamnesis_confirm(message: Message, state: FSMContext, questions: list, answers: list, state_group):
    """Показать сводку ответов. Используем answer(), т.к. при вызове из message-хендлера message — от пользователя (edit_text нельзя)."""
    text = "Проверьте ответы:\n\n" + _format_summary(questions, answers) + "\n\n" + TEXT_ALL_CORRECT
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Всё верно", callback_data="anamnesis_ok"),
        InlineKeyboardButton(text="Исправить", callback_data="anamnesis_fix"),
    )
    await message.answer(text, reply_markup=builder.as_markup())
    await state.set_state(state_group.anamnesis_confirm)


@router.callback_query(PrimaryKnowsDoctor.choosing_anamnesis, F.data == "draft_continue")
async def draft_continue(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    draft = get_draft(data["user_id"], data["doctor_id"])
    if not draft:
        await cq.message.edit_text(TEXT_ANAMNESIS_OFFER, reply_markup=yes_no_kb("anamnesis_yes", "anamnesis_no"))
        return
    answers = json.loads(draft["answers_json"])
    questions = get_anamnesis_questions(None)
    await state.update_data(questions=questions, answers=answers, current_index=draft["current_question_index"])
    await _go_to_anamnesis_confirm(cq.message, state, questions, answers, PrimaryKnowsDoctor)


@router.callback_query(PrimaryKnowsDoctor.choosing_anamnesis, F.data == "draft_new")
async def draft_new(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await cq.message.edit_text(TEXT_ANAMNESIS_OFFER, reply_markup=yes_no_kb("anamnesis_yes", "anamnesis_no"))


@router.callback_query(PrimaryKnowsDoctor.choosing_anamnesis, F.data == "anamnesis_no")
async def anamnesis_no(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await _show_slots_primary_knows(cq.message, state, DURATION_MIN_WITHOUT_ANAMNESIS, with_description=False)


@router.callback_query(PrimaryKnowsDoctor.choosing_anamnesis, F.data == "anamnesis_yes")
async def anamnesis_yes(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(PrimaryKnowsDoctor.symptom_description)
    await cq.message.edit_text(TEXT_SYMPTOMS_ANAMNESIS)


@router.message(PrimaryKnowsDoctor.symptom_description, F.text)
async def primary_symptom_for_anamnesis(msg: Message, state: FSMContext):
    data = await state.get_data()
    doctors = get_doctors_by_ids([data["doctor_id"]]) if data.get("doctor_id") else []
    specialty = doctors[0].get("specialty") if doctors else None
    questions = get_anamnesis_questions(specialty)
    await state.update_data(symptom_description=msg.text, questions=questions, answers=[], current_index=0)
    await state.set_state(PrimaryKnowsDoctor.anamnesis_questions)
    await msg.answer(f"Вопрос 1 из {len(questions)}:\n\n{questions[0]}")


@router.message(PrimaryKnowsDoctor.anamnesis_questions, F.text)
async def anamnesis_answer(msg: Message, state: FSMContext):
    data = await state.get_data()
    questions = data["questions"]
    answers = data.get("answers", [])
    current_index = data.get("current_index", 0)
    answers.append(msg.text.strip())
    next_index = current_index + 1
    user_id, doctor_id = data["user_id"], data.get("doctor_id")
    save_draft(user_id, next_index, json.dumps(answers, ensure_ascii=False), doctor_id, data.get("symptom_description"))
    await state.update_data(answers=answers, current_index=next_index)

    if next_index >= len(questions):
        await _go_to_anamnesis_confirm(msg, state, questions, answers, PrimaryKnowsDoctor)
        return
    await msg.answer(f"Вопрос {next_index + 1} из {len(questions)}:\n\n{questions[next_index]}")


@router.callback_query(PrimaryKnowsDoctor.anamnesis_confirm, F.data == "anamnesis_ok")
async def anamnesis_confirm_ok(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await _show_slots_primary_knows(cq.message, state, DURATION_MIN_WITH_ANAMNESIS, with_description=True)


@router.callback_query(PrimaryKnowsDoctor.anamnesis_confirm, F.data == "anamnesis_fix")
async def anamnesis_fix(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(PrimaryKnowsDoctor.anamnesis_fix_number)
    await cq.message.edit_text(TEXT_FIX_QUESTION)


@router.message(PrimaryKnowsDoctor.anamnesis_fix_number, F.text)
async def anamnesis_fix_number_msg(msg: Message, state: FSMContext):
    parts = msg.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await msg.answer("Формат: номер и новый текст (например: 3 Стало лучше).")
        return
    try:
        num = int(parts[0])
    except ValueError:
        await msg.answer("Первое слово — номер вопроса (число).")
        return
    data = await state.get_data()
    questions, answers = data["questions"], data["answers"].copy()
    if num < 1 or num > len(answers):
        await msg.answer(f"Номер от 1 до {len(answers)}.")
        return
    answers[num - 1] = parts[1]
    await state.update_data(answers=answers)
    await state.set_state(PrimaryKnowsDoctor.anamnesis_confirm)
    await _go_to_anamnesis_confirm(msg, state, questions, answers, PrimaryKnowsDoctor)


async def _show_slots_primary_knows(message: Message, state: FSMContext, duration_minutes: int, with_description: bool):
    data = await state.get_data()
    slots = get_available_slots(data["doctor_id"], duration_minutes, prefer_3_days=True)
    if not slots:
        await message.answer(TEXT_NO_SLOTS)
        return
    await state.update_data(slot_duration=duration_minutes, with_description=with_description)
    await state.set_state(PrimaryKnowsDoctor.choosing_slot)
    await message.answer(TEXT_SLOT_CHOOSE, reply_markup=slots_kb(slots, "p_slot"))


@router.callback_query(PrimaryKnowsDoctor.choosing_slot, F.data.startswith("p_slot:"))
async def primary_slot_chosen(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    slot_id = int(cq.data.split(":")[1])
    data = await state.get_data()
    slots = get_available_slots(data["doctor_id"], data["slot_duration"], prefer_3_days=True)
    slot = next((s for s in slots if s["id"] == slot_id), None)
    if not slot:
        await cq.answer("Слот занят. Выберите другое время.", show_alert=True)
        return
    conn = get_connection()
    cur = conn.execute("SELECT full_name FROM doctors WHERE id = ?", (data["doctor_id"],))
    doctor_name = cur.fetchone()["full_name"]
    conn.close()
    time_str = slot_start_moscow(slot).strftime("%d.%m.%Y в %H:%M (Мск)")
    desc = ""
    if data.get("with_description") and data.get("questions") and data.get("answers"):
        desc = _format_summary(data["questions"], data["answers"])
    await state.update_data(slot_id=slot_id, confirm_description=desc)
    await state.set_state(PrimaryKnowsDoctor.confirm_booking)
    await cq.message.edit_text(
        f"Врач: {doctor_name}\nВремя: {time_str}\n\n" + TEXT_CONFIRM_BOOKING,
        reply_markup=confirm_booking_kb(),
    )


@router.callback_query(PrimaryKnowsDoctor.confirm_booking, F.data == "confirm_booking")
async def primary_confirm_booking(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    book_slot(data["slot_id"])
    create_appointment(data["user_id"], data["doctor_id"], data["slot_id"], data.get("confirm_description"))
    delete_draft(data["user_id"], data["doctor_id"])
    await state.clear()
    await cq.message.edit_text(TEXT_BOOKED)


# --- Первичный, не знает врача: симптомы -> подбор врачей -> врач -> анамнез -> слоты ---

@router.message(PrimaryNoDoctor.symptom_description, F.text)
async def primary_no_doctor_symptoms(msg: Message, state: FSMContext):
    doctors = pick_doctors_by_symptoms(msg.text.strip(), limit=3)
    if not doctors:
        await msg.answer("Не удалось подобрать врача. Попробуйте описать симптомы иначе или выберите «Первичный» и укажите врача вручную.")
        return
    await state.update_data(symptom_description=msg.text.strip())
    await state.set_state(PrimaryNoDoctor.choosing_doctor)
    await msg.answer(TEXT_CHOOSE_DOCTOR, reply_markup=doctors_kb(doctors, "pn_doc"))


@router.callback_query(PrimaryNoDoctor.choosing_doctor, F.data.startswith("pn_doc:"))
async def primary_no_doctor_chosen(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    doctor_id = int(cq.data.split(":")[1])
    await state.update_data(doctor_id=doctor_id)
    await state.set_state(PrimaryNoDoctor.choosing_anamnesis)
    data = await state.get_data()
    draft = get_draft(data["user_id"], doctor_id)
    if draft:
        await cq.message.edit_text(
            "Есть незавершённый анамнез. Продолжить?",
            reply_markup=yes_no_kb("pn_draft_continue", "pn_draft_new"),
        )
        return
    await cq.message.edit_text(TEXT_ANAMNESIS_OFFER, reply_markup=yes_no_kb("pn_anamnesis_yes", "pn_anamnesis_no"))


@router.callback_query(PrimaryNoDoctor.choosing_anamnesis, F.data == "pn_draft_continue")
async def pn_draft_continue(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    draft = get_draft(data["user_id"], data["doctor_id"])
    if not draft:
        await cq.message.edit_text(TEXT_ANAMNESIS_OFFER, reply_markup=yes_no_kb("pn_anamnesis_yes", "pn_anamnesis_no"))
        return
    answers = json.loads(draft["answers_json"])
    questions = get_anamnesis_questions(None)
    await state.update_data(questions=questions, answers=answers, current_index=draft["current_question_index"])
    await _go_to_anamnesis_confirm(cq.message, state, questions, answers, PrimaryNoDoctor)


@router.callback_query(PrimaryNoDoctor.choosing_anamnesis, F.data == "pn_draft_new")
async def pn_draft_new(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await cq.message.edit_text(TEXT_ANAMNESIS_OFFER, reply_markup=yes_no_kb("pn_anamnesis_yes", "pn_anamnesis_no"))


@router.callback_query(PrimaryNoDoctor.choosing_anamnesis, F.data == "pn_anamnesis_no")
async def pn_anamnesis_no(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await _show_slots_primary_no(cq.message, state, DURATION_MIN_WITHOUT_ANAMNESIS, with_description=False)


@router.callback_query(PrimaryNoDoctor.choosing_anamnesis, F.data == "pn_anamnesis_yes")
async def pn_anamnesis_yes(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(PrimaryNoDoctor.symptom_description_after_doctor)
    await cq.message.edit_text(TEXT_SYMPTOMS_ANAMNESIS)


@router.message(PrimaryNoDoctor.symptom_description_after_doctor, F.text)
async def pn_symptom_anamnesis(msg: Message, state: FSMContext):
    data = await state.get_data()
    doctors = get_doctors_by_ids([data["doctor_id"]]) if data.get("doctor_id") else []
    specialty = doctors[0].get("specialty") if doctors else None
    questions = get_anamnesis_questions(specialty)
    await state.update_data(symptom_description=msg.text, questions=questions, answers=[], current_index=0)
    await state.set_state(PrimaryNoDoctor.anamnesis_questions)
    await msg.answer(f"Вопрос 1 из {len(questions)}:\n\n{questions[0]}")


@router.message(PrimaryNoDoctor.anamnesis_questions, F.text)
async def pn_anamnesis_answer(msg: Message, state: FSMContext):
    data = await state.get_data()
    questions, answers = data["questions"], data.get("answers", [])
    current_index = data.get("current_index", 0)
    answers.append(msg.text.strip())
    next_index = current_index + 1
    save_draft(data["user_id"], next_index, json.dumps(answers, ensure_ascii=False), data["doctor_id"], data.get("symptom_description"))
    await state.update_data(answers=answers, current_index=next_index)
    if next_index >= len(questions):
        await _go_to_anamnesis_confirm(msg, state, questions, answers, PrimaryNoDoctor)
        return
    await msg.answer(f"Вопрос {next_index + 1} из {len(questions)}:\n\n{questions[next_index]}")


@router.callback_query(PrimaryNoDoctor.anamnesis_confirm, F.data == "anamnesis_ok")
async def pn_anamnesis_confirm_ok(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await _show_slots_primary_no(cq.message, state, DURATION_MIN_WITH_ANAMNESIS, with_description=True)


@router.callback_query(PrimaryNoDoctor.anamnesis_confirm, F.data == "anamnesis_fix")
async def pn_anamnesis_fix(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    await state.set_state(PrimaryNoDoctor.anamnesis_fix_number)
    await cq.message.edit_text(TEXT_FIX_QUESTION)


@router.message(PrimaryNoDoctor.anamnesis_fix_number, F.text)
async def pn_anamnesis_fix_msg(msg: Message, state: FSMContext):
    parts = msg.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await msg.answer("Формат: номер и новый текст.")
        return
    try:
        num = int(parts[0])
    except ValueError:
        await msg.answer("Первое слово — номер вопроса.")
        return
    data = await state.get_data()
    questions, answers = data["questions"], data["answers"].copy()
    if num < 1 or num > len(answers):
        await msg.answer(f"Номер от 1 до {len(answers)}.")
        return
    answers[num - 1] = parts[1]
    await state.update_data(answers=answers)
    await state.set_state(PrimaryNoDoctor.anamnesis_confirm)
    await _go_to_anamnesis_confirm(msg, state, questions, answers, PrimaryNoDoctor)


async def _show_slots_primary_no(message: Message, state: FSMContext, duration_minutes: int, with_description: bool):
    data = await state.get_data()
    slots = get_available_slots(data["doctor_id"], duration_minutes, prefer_3_days=True)
    if not slots:
        await message.answer(TEXT_NO_SLOTS)
        return
    await state.update_data(slot_duration=duration_minutes, with_description=with_description)
    await state.set_state(PrimaryNoDoctor.choosing_slot)
    await message.answer(TEXT_SLOT_CHOOSE, reply_markup=slots_kb(slots, "pn_slot"))


@router.callback_query(PrimaryNoDoctor.choosing_slot, F.data.startswith("pn_slot:"))
async def pn_slot_chosen(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    slot_id = int(cq.data.split(":")[1])
    data = await state.get_data()
    slots = get_available_slots(data["doctor_id"], data["slot_duration"], prefer_3_days=True)
    slot = next((s for s in slots if s["id"] == slot_id), None)
    if not slot:
        await cq.answer("Слот занят.", show_alert=True)
        return
    conn = get_connection()
    cur = conn.execute("SELECT full_name FROM doctors WHERE id = ?", (data["doctor_id"],))
    doctor_name = cur.fetchone()["full_name"]
    conn.close()
    time_str = slot_start_moscow(slot).strftime("%d.%m.%Y в %H:%M (Мск)")
    desc = _format_summary(data["questions"], data["answers"]) if data.get("with_description") and data.get("questions") and data.get("answers") else ""
    await state.update_data(slot_id=slot_id, confirm_description=desc)
    await state.set_state(PrimaryNoDoctor.confirm_booking)
    await cq.message.edit_text(
        f"Врач: {doctor_name}\nВремя: {time_str}\n\n" + TEXT_CONFIRM_BOOKING,
        reply_markup=confirm_booking_kb(),
    )


@router.callback_query(PrimaryNoDoctor.confirm_booking, F.data == "confirm_booking")
async def pn_confirm_booking(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    data = await state.get_data()
    book_slot(data["slot_id"])
    create_appointment(data["user_id"], data["doctor_id"], data["slot_id"], data.get("confirm_description"))
    delete_draft(data["user_id"], data["doctor_id"])
    await state.clear()
    await cq.message.edit_text(TEXT_BOOKED)


# --- Отмена записи (из напоминания) ---

@router.callback_query(F.data.startswith("cancel_app:"))
async def cancel_appointment_cb(cq: CallbackQuery, state: FSMContext):
    await cq.answer()
    appointment_id = int(cq.data.split(":")[1])
    slot_id = cancel_appointment(appointment_id)
    if slot_id is not None:
        free_slot(slot_id)
    await cq.message.edit_text("Запись отменена.")
