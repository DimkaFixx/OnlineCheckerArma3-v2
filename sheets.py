import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from db import (
    check_last_online_of_the_players_s1,
    check_last_online_of_the_players_s2,
    get_online_last_30_days_s1,
    get_online_last_30_days_s2,
)
import os

load_dotenv()
MSK_TZ = timezone(timedelta(hours=3))

class GoogleTableManager:
    def __init__(self, creditals_path, spreadsheet_url, list_name):
        self.scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"
        ]
        self.url = spreadsheet_url
        self.list_name = list_name
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(creditals_path, self.scope)
        self.client = gspread.authorize(self.creds)
        self.sheet = None
        self.spreadsheet = None

    def connect(self):
        self.spreadsheet = self.client.open_by_url(self.url)
        self.sheet = self.spreadsheet.worksheet(self.list_name)
    
    def get_data_of_users(self): 
        #Получить значения с диапазона ячеек 
        return self.sheet.get_values('B1:B100')
    
    def update_table(self):
        temp_sheet = self.sheet
        self.sheet = self.spreadsheet.worksheet("Состав")
        rows_count = self.sheet.row_count
        cols_count = self.sheet.col_count
        sort_range = f'{os.getenv("ROWSTOSORT_FROM")}3:{os.getenv("ROWSTOSORT_TO")}{rows_count}'
        self.sheet.sort((1, 'asc'), range=sort_range)
        full_range = f"A1:{gspread.utils.rowcol_to_a1(rows_count, cols_count)}"
        border_style = {
            "style": "SOLID",
            "color": {
                "red": 1.0,
                "green": 1.0,
                "blue": 1.0
            }
        }
        self.sheet.format(full_range, {
            "borders": {
                "top": border_style,
                "bottom": border_style,
                "left": border_style,
                "right": border_style
            }
        })
        self.sheet = temp_sheet
    
    def get_ranks(self):
        ranks = self.sheet.get_values('C1:C100')
        for i in range(len(ranks)):
            ranks[i] = ranks[i][0]
        return ranks
    
    def get_jedi_prefixes(self):
        jedi_prefixes = self.sheet.get_values('D1:D100')
        for i in range(len(jedi_prefixes)):
            jedi_prefixes[i] = jedi_prefixes[i][0]
        return jedi_prefixes

    def update_daily_data(self):
        """Заполнить I2:K101 последним онлайном игроков из B1:B100."""
        users = self.get_data_of_users()
        nicks = [row[0].strip() for row in users if row and row[0].strip()]
        server1_data = check_last_online_of_the_players_s1(nicks)
        server2_data = check_last_online_of_the_players_s2(nicks)

        def format_last_online(data, nickname):
            player_data = data.get(nickname)
            if not player_data or player_data["days_ago"] is None:
                return ""

            duration = player_data["duration"] or 0
            hours, remainder = divmod(duration, 3600)
            minutes = remainder // 60
            return f"{player_data['days_ago']} ({hours}:{minutes:02d})"

        rows = [
            [
                f"`{nickname}`",
                format_last_online(server1_data, nickname),
                format_last_online(server2_data, nickname),
            ]
            for nickname in nicks[:100]
        ]
        rows.extend([["", "", ""]] * (100 - len(rows)))
        self.sheet.update("I2:K101", rows)

    def update_mounthly_data(self):
        """Заполнить 30-дневный отчёт в столбцах L:BT.

        Для каждой даты создаётся пара столбцов: первый хранит онлайн S1,
        второй — онлайн S2.
        """
        users = self.get_data_of_users()
        nicks = [row[0].strip() for row in users if row and row[0].strip()][:100]
        server1_data = get_online_last_30_days_s1(nicks)
        server2_data = get_online_last_30_days_s2(nicks)
        dates = list(server1_data)

        def format_duration(duration):
            hours, remainder = divmod(duration or 0, 3600)
            return f"{hours}:{remainder // 60:02d}"

        headers = []
        for day in dates:
            headers.extend([day, day])

        rows = []
        for nickname in nicks:
            row = [f"`{nickname}`"]
            for day in dates:
                row.append(format_duration(server1_data[day].get(nickname, 0)))
                row.append(format_duration(server2_data[day].get(nickname, 0)))
            rows.append(row)

        rows.extend([[""] * 61] * (100 - len(rows)))
        self.sheet.update("M1:BT1", [headers])
        self.sheet.update("L2:BT101", rows)
    
