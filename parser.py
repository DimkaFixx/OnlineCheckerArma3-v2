import a2s
import socket
import re

class Player:
    def __init__(self, player_full_nick, duration):
        self.player_full_nick = player_full_nick
        self.duration_seconds = duration
        self.name = None
        self.bat = None
    
    def __str__(self):
        return f"Player(name={self.player_full_nick}, {self.duration_seconds}, {self.bat}, {self.name})"

class Parser:
    def __init__(self, host, port, jedi_prefixes, ranks):
        self.host = host
        self.port = port
        self.jedi_prefixes = jedi_prefixes
        self.ranks = ranks
    
    def find_working_query_address(self, base_host, base_port):
        # Для ряда игр query-порт может отличаться от игрового на +/-1
        candidates = [(base_host, base_port), (base_host, base_port + 1), (base_host, base_port - 1)]
        checked = []

        for candidate in candidates:
            if candidate in checked:
                continue
            checked.append(candidate)
            try:
                info = a2s.info(candidate)
                return candidate, info
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                continue

        return None, None

    def get_data(self, host, port):
        working_address_and_port, server_info = self.find_working_query_address(host, port)

        return a2s.players(working_address_and_port, timeout=100)

    def parse_players(self):
        data = self.get_data(self.host, self.port)

        players = []
        for player in data:
            player_object = Player(player_full_nick=player.name, duration=player.duration)
            try:
                bat, formatted_nick = self.find_bat_for_players(player_object)
                player_object.bat = bat
                player_object.name = formatted_nick
                players.append(player_object)
            except Exception as e:
                print(f"Error occurred while processing player {player.name}, skipping: {e}")
        return players
    
    # -----------------------------------------------------------------------------

    def find_bat_for_players(self, player):
        player_nickname = str(player.player_full_nick)

        #Отсекаем CR, CT
        if not "[" in player_nickname:
            return None, self.format_player_nickname_not_with_bat(player_nickname)
        
        # Проверяем на джедая 
        jedi = False
        for jedi_prefix in self.jedi_prefixes:
            if player_nickname.startswith(f"[{jedi_prefix}"):
                jedi = True
                break
        
        # Если джедай, то находим его подразделение
        if jedi:
            bat = player_nickname.split("|")[-1].replace(" ", "") if "|" in player_nickname else "Jedi"
            # Убираем подразделение
            nick_with_not_bat = player_nickname.split("|")[0] if "|" in player_nickname else player_nickname
            #Осталвяем только ФИ джедая, убираем что он жид
            player_nickname = re.sub(r'\s*\[.*?\]\s*', '', nick_with_not_bat)

            return bat, self.format_player_nickname_not_with_bat(player_nickname)

        # Убираем спецуху, только у джедаев там батальон
        player_nickname = player_nickname.split("|")[0] if "|" in player_nickname else player_nickname
        
        
        # Если не джедай, то проверяем на C-3 (удобно просто)
        if player_nickname.startswith("[C-3"):
            player_nickname = re.sub(r'\s*\[.*?\]\s*', '', player_nickname)
            return "C-3", self.format_player_nickname_not_with_bat(player_nickname)
        
        # Также проверяем на RC
        if player_nickname.startswith("[RC"):
            player_nickname = re.sub(r'\s*\[.*?\]\s*', '', player_nickname)
            return "RC", self.format_player_nickname_not_with_bat(player_nickname)
        
        # Далее проверям на БСО, сразу будем брать легионеров или отрядников, будем брать только нужных нам отрядников, остальные в None
        if "-" in player_nickname.split("]")[0]:
            bat = player_nickname.split("]")[0] 
            bat = bat.split("-")[1] if "-" in bat else bat
            player_nickname = re.sub(r'\s*\[.*?\]\s*', '', player_nickname)
            return bat, self.format_player_nickname_not_with_bat(player_nickname)
        
        #Остались вроде как толкьо тупо [<БАТ>]
        bat = player_nickname.split("]")[0].replace("[", "") if "]" in player_nickname else None
        player_nickname = re.sub(r'\s*\[.*?\]\s*', '', player_nickname)
        return bat, self.format_player_nickname_not_with_bat(player_nickname)

    #Сюда идет звание + позвыной (мб + номер или + ФИ)
    def format_player_nickname_not_with_bat(self, player_nickname):
        if any(rank in player_nickname for rank in self.ranks):
            for rank in self.ranks:
                if rank+" " in player_nickname:
                    player_nickname = player_nickname.replace(rank+" ", "")
                    break
        else:
            player_nickname = player_nickname.strip()
        
        #На этом этапе у нас или ник или номер, или номер + ник или ФИ джедая, 
        
        player_nick_or_num = player_nickname.split(" ")
        if "" in player_nick_or_num:
            player_nick_or_num.remove("")
        # Клон только с номером или только с ником
        if len(player_nick_or_num) == 1:
            return player_nick_or_num[0].replace(" ", "")
        # Клон с номером + ником, номер может быть 01-2345
        if player_nick_or_num[0].isdigit() or any([num.isdigit() for num in player_nick_or_num[0].split("-")]) or any([num.isdigit() for num in player_nick_or_num[0].split("/")]):
            return player_nick_or_num[1].replace(" ", "")

        # ФИ джедая, тут всё идет в тарары
        return player_nickname

parser = Parser(host="195.18.27.19", port=2302, jedi_prefixes=["Jedi", "Jedi Master", "Jedi Knight"], ranks=["Private", "Corporal", "Sergeant", "Lieutenant", "Captain", "Major", "Colonel"])
print(parser.parse_players())