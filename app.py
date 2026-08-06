from parser import Parser, Player
from sheets import GoogleTableManager
import time
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
import os

MSK_TZ = timezone(timedelta(hours=3))

load_dotenv()


def main():
    sheets_manager = GoogleTableManager()
    sheets_manager.connect()

    ranks = sheets_manager.get_ranks()
    jedi_prefixes = sheets_manager.get_jedi_prefixes()

    parser_server_1 = Parser(os.getenv("S1_IP"), int(os.getenv("S1_PORT")), jedi_prefixes, ranks)
    parser_server_2 = Parser(os.getenv("S2_IP"), int(os.getenv("S2_PORT")), jedi_prefixes, ranks)

    players_server_1 = parser_server_1.parse_players()
    players_server_2 = parser_server_2.parse_players()
    for player in players_server_1:
        print(player)
    print("--------------------------------------------------")
    for player in players_server_2:
        print(player)
    
if __name__ == "__main__":
    main()