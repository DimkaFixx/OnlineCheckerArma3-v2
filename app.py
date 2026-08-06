from parser import Parser, Player
from sheets import GoogleTableManager
from db import update_table_s1_327, update_table_s2_327
import logging
import time
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
import os

load_dotenv()
MSK_TZ = timezone(timedelta(hours=3))
DB_URL = os.getenv("DB_URL")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def wait_until_next_update() -> None:
    """Подождать до ближайшей границы пяти минут по московскому времени."""

    current_time = datetime.now(MSK_TZ)
    next_update = current_time.replace(second=0, microsecond=0)
    next_update += timedelta(minutes=5 - current_time.minute % 5)
    seconds_to_wait = (next_update - current_time).total_seconds()
    logger.info("Следующее обновление запланировано на %s МСК", next_update.strftime("%H:%M"))
    time.sleep(seconds_to_wait)


def run_update_cycle(sheets_manager, parser_server_1, parser_server_2) -> None:
    """Выполнить один цикл сбора онлайна и обновления отчётов."""

    logger.info("Начинаю форматирование таблицы")
    sheets_manager.update_table()
    logger.info("Форматирование таблицы завершено")

    logger.info("Начинаю парсинг данных S1")
    players_server_1 = parser_server_1.parse_players()
    logger.info("Парсинг S1 завершён: получено игроков — %s", len(players_server_1))

    logger.info("Начинаю парсинг данных S2")
    players_server_2 = parser_server_2.parse_players()
    logger.info("Парсинг S2 завершён: получено игроков — %s", len(players_server_2))

    s1_updated_count = update_table_s1_327(players_server_1)
    s2_updated_count = update_table_s2_327(players_server_2)
    logger.info("Данные записаны в БД: S1 — %s, S2 — %s", s1_updated_count, s2_updated_count)

    logger.info("Начинаю обновление ежедневного и месячного отчётов")
    sheets_manager.update_daily_data()
    sheets_manager.update_mounthly_data()
    logger.info("Отчёты Google Sheets обновлены")


def main():
    sheets_manager = GoogleTableManager(os.getenv("CREDITALS_PATH"), os.getenv("SPREADSHEET_NAME"), os.getenv("LIST_NAME"))
    sheets_manager.connect()

    ranks = sheets_manager.get_ranks()
    jedi_prefixes = sheets_manager.get_jedi_prefixes()

    parser_server_1 = Parser(os.getenv("S1_IP"), int(os.getenv("S1_PORT")), jedi_prefixes, ranks)
    parser_server_2 = Parser(os.getenv("S2_IP"), int(os.getenv("S2_PORT")), jedi_prefixes, ranks)

    logger.info("Начинаю форматирование таблицы")
    sheets_manager.update_table()
    logger.info("Форматирование таблицы завершено")

    while True:
        wait_until_next_update()
        logger.info("Запущен плановый цикл обновления")
        try:
            run_update_cycle(sheets_manager, parser_server_1, parser_server_2)
        except Exception:
            logger.exception("Плановый цикл завершён с ошибкой")
    
if __name__ == "__main__":
    main()
