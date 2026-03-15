"""Конфигурация: токен из окружения, часовой пояс Москва."""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = ZoneInfo("Europe/Moscow")
