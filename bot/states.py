"""Состояния FSM для сценариев записи к врачу. Aiogram 3."""
from aiogram.fsm.state import State, StatesGroup


class StartChoice(StatesGroup):
    """После /start: выбор первичный/вторичный или сразу первичный."""
    choosing_type = State()


class PrimaryBranch(StatesGroup):
    """Ветка после выбора «Первичный»: знает врача или нет."""
    choosing_know_doctor = State()


class PrimaryKnowsDoctor(StatesGroup):
    """Первичный, пользователь знает врача."""
    choosing_doctor = State()
    choosing_anamnesis = State()
    symptom_description = State()
    anamnesis_questions = State()
    anamnesis_confirm = State()
    anamnesis_fix_number = State()
    choosing_slot = State()
    confirm_booking = State()


class PrimaryNoDoctor(StatesGroup):
    """Первичный, не знает врача: описание симптомов -> подбор врачей."""
    symptom_description = State()
    choosing_doctor = State()
    choosing_anamnesis = State()
    symptom_description_after_doctor = State()
    anamnesis_questions = State()
    anamnesis_confirm = State()
    anamnesis_fix_number = State()
    choosing_slot = State()
    confirm_booking = State()


class Secondary(StatesGroup):
    """Вторичный приём: выбор врача из списка за 6 мес -> слоты 10 мин."""
    choosing_doctor = State()
    choosing_slot = State()
    confirm_booking = State()
