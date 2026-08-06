"""Хранение ежедневного онлайна 327-го батальона."""

import os
from datetime import datetime, time as datetime_time, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, create_engine, func, inspect, select, text
from sqlalchemy.orm import Session, declarative_base


load_dotenv()
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("Переменная окружения DB_URL не задана")


MSK_TZ = timezone(timedelta(hours=3))
engine = create_engine(DB_URL, echo=True)
Base = declarative_base()


def create_bat_table(table_name: str):
    """Создать модель ежедневного онлайна для одного игрового сервера."""

    return type(
        f"BatTable_{table_name}",
        (Base,),
        {
            "__tablename__": table_name,
            "id": Column(Integer, primary_key=True),
            "nick": Column(String),
            "bat": Column(String),
            "date": Column(String),
            # Суммарный онлайн игрока за дату из поля date.
            "duration_seconds": Column(Integer, default=0),
            # Начало текущей сессии по данным игрового сервера.
            "last_session_start_time": Column(String),
            # Время последнего опроса, когда игрок был замечен онлайн.
            "last_seen_at": Column(String),
        },
    )


s1_327 = create_bat_table("s1_327")
s2_327 = create_bat_table("s2_327")


def create_tables() -> None:
    """Создать таблицы и добавить last_seen_at в уже существующие таблицы."""

    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    with engine.begin() as connection:
        for table_name in ("s1_327", "s2_327"):
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "last_seen_at" not in columns:
                connection.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN last_seen_at VARCHAR")
                )


def _parse_msk_datetime(value: str | None) -> datetime | None:
    """Преобразовать строку из БД в дату со временем МСК."""

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=MSK_TZ)
    return parsed.astimezone(MSK_TZ)


def _get_daily_record(session: Session, table, nickname: str, day: str):
    record = session.scalar(
        select(table).where(table.nick == nickname, table.date == day)
    )
    if record is None:
        record = table(nick=nickname, bat="327", date=day, duration_seconds=0)
        session.add(record)
    return record


def _add_online_interval(
    session: Session,
    table,
    nickname: str,
    session_start: datetime,
    interval_start: datetime,
    interval_end: datetime,
) -> None:
    """Добавить интервал онлайна, разделяя его на отдельные московские даты."""

    cursor = max(interval_start, session_start)
    while cursor < interval_end:
        next_midnight = datetime.combine(
            cursor.date() + timedelta(days=1), datetime_time.min, tzinfo=MSK_TZ
        )
        segment_end = min(next_midnight, interval_end)
        seconds_to_add = round((segment_end - cursor).total_seconds())

        if seconds_to_add > 0:
            record = _get_daily_record(session, table, nickname, cursor.date().isoformat())
            record.duration_seconds = (record.duration_seconds or 0) + seconds_to_add
            record.bat = "327"
            record.last_session_start_time = session_start.isoformat(timespec="seconds")
            record.last_seen_at = segment_end.isoformat(timespec="seconds")

        cursor = segment_end


def _update_bat_table(players, table) -> int:
    """Обновить ежедневный онлайн для списка игроков одного игрового сервера."""

    current_time = datetime.now(MSK_TZ)
    processed_nicknames = set()
    updated_count = 0

    create_tables()

    with Session(engine) as session:
        for player in players:
            if str(player.bat).strip() != "327" or not player.name:
                continue

            nickname = player.name.strip()
            if not nickname or nickname in processed_nicknames:
                continue
            processed_nicknames.add(nickname)

            session_duration = max(0, int(player.duration_seconds))
            session_start = current_time - timedelta(seconds=session_duration)
            previous_record = session.scalar(
                select(table)
                .where(table.nick == nickname, table.last_seen_at.is_not(None))
                .order_by(table.last_seen_at.desc())
            )

            previous_start = _parse_msk_datetime(
                previous_record.last_session_start_time if previous_record else None
            )
            previous_seen = _parse_msk_datetime(
                previous_record.last_seen_at if previous_record else None
            )

            # Начало текущей сессии от A2S немного плавает из-за округления,
            # поэтому считаем сессии одинаковыми с точностью до одной минуты.
            same_session = (
                previous_start is not None
                and abs((session_start - previous_start).total_seconds()) <= 60
            )
            interval_start = previous_seen if same_session and previous_seen else session_start

            if interval_start < current_time:
                _add_online_interval(
                    session,
                    table,
                    nickname,
                    session_start,
                    interval_start,
                    current_time,
                )
                updated_count += 1

        session.commit()

    return updated_count


def update_table_s1_327(players_server_1) -> int:
    """Обновить ежедневный онлайн 327-го батальона на сервере S1."""

    return _update_bat_table(players_server_1, s1_327)


def update_table_s2_327(players_server_2) -> int:
    """Обновить ежедневный онлайн 327-го батальона на сервере S2."""

    return _update_bat_table(players_server_2, s2_327)


def _check_last_online_of_the_players(nicks, table) -> dict:
    """Вернуть последнюю дату и дневной онлайн каждого ника из списка."""

    result = {}
    today = datetime.now(MSK_TZ).date()
    unique_nicks = dict.fromkeys(
        nick.strip() for nick in nicks if isinstance(nick, str) and nick.strip()
    )

    with Session(engine) as session:
        for nickname in unique_nicks:
            last_record = session.scalar(
                select(table)
                .where(table.nick == nickname)
                .order_by(table.date.desc(), table.id.desc())
            )

            if last_record is None:
                result[nickname] = {"days_ago": None, "duration": None}
                continue

            try:
                last_online_date = datetime.fromisoformat(last_record.date).date()
            except (TypeError, ValueError):
                result[nickname] = {"days_ago": None, "duration": None}
                continue

            result[nickname] = {
                "days_ago": max(0, (today - last_online_date).days),
                "duration": last_record.duration_seconds or 0,
            }

    return result


def check_last_online_of_the_players_s1(nicks) -> dict:
    """Вернуть последний онлайн игроков 327-го батальона на сервере S1.

    Результат имеет вид ``{"Nick": {"days_ago": 2, "duration": 7200}}``.
    Для ника без записей оба значения равны ``None``.
    """

    return _check_last_online_of_the_players(nicks, s1_327)


def check_last_online_of_the_players_s2(nicks) -> dict:
    """Вернуть последний онлайн игроков 327-го батальона на сервере S2.

    Результат имеет вид ``{"Nick": {"days_ago": 2, "duration": 7200}}``.
    Для ника без записей оба значения равны ``None``.
    """

    return _check_last_online_of_the_players(nicks, s2_327)


def _get_online_last_30_days(nicks, table) -> dict:
    """Вернуть ежедневный онлайн списка игроков за 30 последних дней по МСК."""

    ordered_nicks = list(
        dict.fromkeys(
            nick.strip() for nick in nicks if isinstance(nick, str) and nick.strip()
        )
    )
    today = datetime.now(MSK_TZ).date()
    first_day = today - timedelta(days=29)
    result = {
        (first_day + timedelta(days=offset)).strftime("%d.%m"): {
            nickname: 0 for nickname in ordered_nicks
        }
        for offset in range(30)
    }

    if not ordered_nicks:
        return result

    with Session(engine) as session:
        rows = session.execute(
            select(table.date, table.nick, func.sum(table.duration_seconds))
            .where(
                table.nick.in_(ordered_nicks),
                table.date >= first_day.isoformat(),
                table.date <= today.isoformat(),
            )
            .group_by(table.date, table.nick)
        )

        for day, nickname, duration in rows:
            try:
                day_key = datetime.fromisoformat(day).strftime("%d.%m")
            except (TypeError, ValueError):
                continue

            if day_key in result and nickname in result[day_key]:
                result[day_key][nickname] = duration or 0

    return result


def get_online_last_30_days_s1(nicks) -> dict:
    """Вернуть онлайн игроков за 30 дней из таблицы ``s1_327``.

    Формат: ``{"06.06": {"Fox": 3230, "Rex": 0}}``.
    """

    return _get_online_last_30_days(nicks, s1_327)


def get_online_last_30_days_s2(nicks) -> dict:
    """Вернуть онлайн игроков за 30 дней из таблицы ``s2_327``.

    Формат: ``{"06.06": {"Fox": 3230, "Rex": 0}}``.
    """

    return _get_online_last_30_days(nicks, s2_327)
