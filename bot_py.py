#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import random
import sqlite3
import itertools
from datetime import datetime
from typing import List, Optional, Dict
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.constants import (
    ParseMode,
    ChatMemberStatus
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)


CLUBS_DB = {
    "England": [
        "Newcastle United", "Tottenham Hotspur", "Chelsea", "Arsenal", "Liverpool",
        "Manchester United", "Manchester City", "Aston Villa", "Crystal Palace",
        "Brighton", "West Ham", "Nottingham Forest"
    ],
    "Italy": [
        "AC Milan", "Inter Milan", "Juventus", "Napoli", "Roma", "Atalanta"
    ],
    "Germany": [
        "Leipzig", "Bayer Leverkusen", "Borussia Dortmund", "Bayern Munich",
        "Frankfurt", "Stuttgart"
    ],
    "Spain": [
        "Real Madrid", "Barcelona", "Atletico Madrid", "Athletic Bilbao", "Sevilla",
        "Real Betis", "Real Sociedad", "Girona", "Villarreal"
    ],
    "France": [
        "Lyon", "Paris Saint-Germain", "Olympique de Marseille", "AS Monaco", "OGC Nice"
    ],
    "Netherlands": ["Ajax", "PSV"],
    "Turkey": ["Galatasaray", "Fenerbahçe", "Beşiktaş"],
    "Portugal": ["Benfica", "Sporting"],
    "Saudi Arabia": ["Al Nassr", "Al Hilal", "Al Ittihad"],
    "National teams": [
        "Spain", "Portugal", "Netherlands", "Germany", "Argentina", "France", "England",
        "Italy", "Japan", "South Korea", "Morocco", "Croatia", "Norway", "Sweden", "Denmark"
    ]
}

# Смешные комментарии для результатов
MATCH_COMMENTS = [
    "Голы летели как горох по стене! 🏐",
    "Вратари сегодня явно забыли перчатки дома! 🥅", 
    "Защитники играли как будто их не существует! 👻",
    "Этот матч войдет в историю... или нет 📚",
    "Кто-то явно переборщил с энергетиками! ⚡",
    "Футбол - непредсказуемая игра, особенно когда играют эти двое! 🎲",
    "Голкипер смотрел на мяч как на НЛО! 🛸",
    "Тактика 'все в атаку' сработала на все 100%! 🚀",
    "Защита дырявее чем швейцарский сыр! 🧀",
    "Мяч в воротах чаще чем пицца в пятницу! 🍕",
    "Кажется, кто-то перепутал футбол с хоккеем по голам! 🏒",
    "Вратарь сегодня больше зритель чем игрок! 👀",
    "Голы сыпались как дождь в октябре! ☔",
    "Оборона работала в режиме 'только для красоты'! 💅",
    "Этот счет видали только в FIFA на легком уровне! 🎮"
]

LOW_SCORE_COMMENTS = [
    "Нулевка! Вратари сегодня - стена! 🧱",
    "Скучновато... может быть кофе поможет? ☕",
    "Голов меньше чем пальцев на одной руке! ✋",
    "Классическая английская погода на поле - серо и уныло! 🌫️",
    "Защитники сегодня как крепостные стены! 🏰",
    "Счет как в шахматах - думают долго, результат скромный! ♟️",
    "Мяч в воротах реже чем комплименты от тренера! 😤"
]

HIGH_SCORE_COMMENTS = [
    "Пушки стреляли без перерыва! 💥",
    "Голов больше чем в новогоднюю ночь салютов! 🎆",
    "Вратарь работал как дворник после листопада! 🍂",
    "Сетки рвутся от такой канонады! 🕳️",
    "Кто-то забыл включить защиту в настройках! ⚙️"
]

DRAW_COMMENTS = [
    "Ничья! Справедливость восторжествовала! ⚖️",
    "Поделили очки как хорошие друзья! 🤝",
    "1:1 - счет дипломатов! 🤵",
    "Никто не хотел быть плохим парнем! 😇",
    "Ничья - это когда оба хороши или оба так себе! 🤷‍♂️"
]

TOURNAMENT_NAME, TOURNAMENT_ROUNDS, TOURNAMENT_PRIZE, ADD_PLAYER_NAME, ADD_PLAYERS_LIST = range(5)

DB_PATH = os.getenv("LEAGUE_DB", "/app/data/league_v3.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def db():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    c = conn.cursor()

    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("PRAGMA foreign_keys=ON;")

    c.execute("""
    CREATE TABLE IF NOT EXISTS tournaments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        prize TEXT,
        rounds INTEGER DEFAULT 2,
        created_at TEXT NOT NULL
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        club TEXT,
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        match_number INTEGER NOT NULL,
        home TEXT NOT NULL,
        away TEXT NOT NULL,
        home_goals INTEGER,
        away_goals INTEGER,
        played INTEGER DEFAULT 0,
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
    );
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_tournaments_chat ON tournaments(chat_id, created_at DESC);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_players_tid ON players(tournament_id);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_matches_tid ON matches(tournament_id);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_matches_tid_played ON matches(tournament_id, played, match_number);")
    
    c.execute("PRAGMA table_info(matches)")
    columns = [row[1] for row in c.fetchall()]
    if 'match_number' not in columns:
        c.execute("ALTER TABLE matches ADD COLUMN match_number INTEGER DEFAULT 0")
        c.execute("""
        UPDATE matches 
        SET match_number = id 
        WHERE match_number IS NULL OR match_number = 0
        """)

    conn.commit()
    conn.close()

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    if chat.type == 'private':
        return True
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
        except Exception:
            return False   

def get_current_tournament(chat_id: int) -> Optional[sqlite3.Row]:
    """Получает текущий выбранный турнир для чата"""
    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT t.* FROM tournaments t
        JOIN chat_current_tournament cct ON t.id = cct.tournament_id
        WHERE cct.chat_id = ?
    """, (chat_id,))
    row = c.fetchone()
    conn.close()
    return row

def set_current_tournament(chat_id: int, tournament_id: int):
    """Устанавливает текущий турнир для чата"""
    conn = db()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO chat_current_tournament (chat_id, tournament_id)
        VALUES (?, ?)
    """, (chat_id, tournament_id))
    conn.commit()
    conn.close()

def get_chat_tournaments(chat_id: int) -> List[sqlite3.Row]:
    """Получает все турниры для чата"""
    conn = db()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM tournaments 
        WHERE chat_id = ? 
        ORDER BY created_at DESC
    """, (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def match_no(row: sqlite3.Row) -> int:
    try:
        n = row['match_number']
        return n if n is not None else row['id']
    except Exception:
        return row['id']

def add_tournament(chat_id: int, name: str, prize: str, rounds: int) -> int:
    conn = db()
    c = conn.cursor()

    c.execute("""
    INSERT INTO tournaments (chat_id, name, prize, rounds, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (chat_id, name, prize, rounds, datetime.now().isoformat()))
    tid = c.lastrowid

    conn.commit()
    conn.close()

    set_current_tournament(chat_id, tid)

    return tid

# -------------------------
# Игроки и клубы
# -------------------------
def add_player(tournament_id: int, name: str):
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO players (tournament_id, name) VALUES (?, ?)", (tournament_id, name))
    conn.commit()
    conn.close()

def assign_club(tournament_id: int, name: str, club: str):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE players SET club=? WHERE tournament_id=? AND name=?", (club, tournament_id, name))
    conn.commit()
    conn.close()

def get_players(tournament_id: int) -> List[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE tournament_id=?", (tournament_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_players_without_clubs(tournament_id: int) -> List[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE tournament_id=? AND (club IS NULL OR club = '')", (tournament_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_player_by_id(player_id: int) -> Optional[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM players WHERE id=?", (player_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_player_club(tournament_id: int, name: str) -> Optional[str]:
    """Получает клуб игрока"""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT club FROM players WHERE tournament_id=? AND name=?", (tournament_id, name))
    row = c.fetchone()
    conn.close()
    return row["club"] if row and row["club"] else None

def assign_random_clubs(tournament_id: int):
    players = get_players(tournament_id)
    all_clubs = [club for clubs in CLUBS_DB.values() for club in clubs]
    random.shuffle(all_clubs)
    conn = db()
    c = conn.cursor()
    for i, player in enumerate(players):
        if i < len(all_clubs):
            c.execute("UPDATE players SET club=? WHERE id=?", (all_clubs[i], player["id"]))
    conn.commit()
    conn.close()

def generate_schedule(tournament_id: int, rounds: int):
    conn = db()
    c = conn.cursor()
    
    c.execute("DELETE FROM matches WHERE tournament_id=?", (tournament_id,))
    
    players = get_players(tournament_id)
    names = [p["name"] for p in players]
    matches = []
    
    # Генерируем все пары для каждого круга
    for r in range(rounds):
        for i in range(len(names)):
            for j in range(i + 1, len(names)):  
                if r % 2 == 0:
                    matches.append((names[i], names[j]))
                else:
                    matches.append((names[j], names[i]))
    
    random.shuffle(matches)
    
    # Добавляем матчи с правильной нумерацией начиная с 1
    for match_num, (home, away) in enumerate(matches, start=1):
        c.execute("INSERT INTO matches (tournament_id, match_number, home, away) VALUES (?, ?, ?, ?)",
                  (tournament_id, match_num, home, away))
    conn.commit()
    conn.close()

def get_schedule(tournament_id: int, limit: int = None) -> List[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT * FROM matches
    WHERE tournament_id=? ORDER BY played ASC, match_number ASC
    """ + ("LIMIT ?" if limit else ""), (tournament_id,) + ((limit,) if limit else ()))
    rows = c.fetchall()
    conn.close()
    return rows

def record_result(tournament_id: int, match_id: int, hg: int, ag: int):
    conn = db()
    c = conn.cursor()
    c.execute("""
    UPDATE matches
    SET home_goals=?, away_goals=?, played=1
    WHERE tournament_id=? AND id=?
    """, (hg, ag, tournament_id, match_id))
    conn.commit()
    conn.close()

def get_standings(tournament_id: int) -> List[tuple]:
    players = get_players(tournament_id)
    table = {p["name"]: {"P":0, "W":0, "D":0, "L":0, "GF":0, "GA":0, "GD":0, "PTS":0} for p in players}

    conn = db()
    c = conn.cursor()
    c.execute("SELECT home, away, home_goals, away_goals, played FROM matches WHERE tournament_id=?", (tournament_id,))
    for home, away, hg, ag, played in c.fetchall():
        if not played or hg is None or ag is None:
            continue
        table[home]["P"] += 1
        table[away]["P"] += 1
        table[home]["GF"] += hg; table[home]["GA"] += ag
        table[away]["GF"] += ag; table[away]["GA"] += hg
        if hg > ag:
            table[home]["W"] += 1; table[away]["L"] += 1
            table[home]["PTS"] += 3
        elif hg < ag:
            table[away]["W"] += 1; table[home]["L"] += 1
            table[away]["PTS"] += 3
        else:
            table[home]["D"] += 1; table[away]["D"] += 1
            table[home]["PTS"] += 1; table[away]["PTS"] += 1
    for n in table:
        table[n]["GD"] = table[n]["GF"] - table[n]["GA"]
    conn.close()

    ordered = sorted(table.items(), key=lambda kv: (-kv[1]["PTS"], -kv[1]["GD"], -kv[1]["GF"], kv[0]))
    return ordered

def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))

def format_table(tournament_id: int, ordered: List[tuple]) -> str:
    # ширины колонок, все числа вправо
    # #  Игрок         И  В  Н  П   ±   О
    header = f"{'#':<2}{'Игрок':<12}{'И':>3}{'В':>3}{'Н':>3}{'П':>3}{'±':>5}{'О':>4}"
    lines = [header, "─" * len(header)]

    for i, (name, st) in enumerate(ordered, start=1):
        club = get_player_club(tournament_id, name)
        short = get_short_club_name(club) if club else ""
        display = f"{name[:8]}({short})" if club else name[:12]
        if len(display) > 12:
            display = display[:11] + "…"

        lines.append(
            f"{i:<2}"
            f"{display:<12}"
            f"{st['P']:>3}{st['W']:>3}{st['D']:>3}{st['L']:>3}"
            f"{st['GD']:>5}{st['PTS']:>4}"
        )

    table = "\n".join(lines)
    return f"<pre>{_html_escape(table)}</pre>"

def get_current_tournament_prize(tournament_id: int) -> str:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT prize FROM tournaments WHERE id=?", (tournament_id,))
    row = c.fetchone()
    conn.close()
    return row["prize"] if row and row["prize"] else "приз"

def get_short_club_name(club: str) -> str:
    """Сокращает название клуба для компактного отображения"""
    short_names = {
        # England
        "Newcastle United": "NEW", "Tottenham Hotspur": "TOT", "Chelsea": "CHE", 
        "Arsenal": "ARS", "Liverpool": "LIV", "Manchester United": "MUN", 
        "Manchester City": "MCI", "Aston Villa": "AVL", "Crystal Palace": "CRY",
        "Brighton": "BRI", "West Ham": "WHU", "Nottingham Forest": "NFO",
        # Italy  
        "AC Milan": "MIL", "Inter Milan": "INT", "Juventus": "JUV", 
        "Napoli": "NAP", "Roma": "ROM", "Atalanta": "ATA",
        # Germany
        "Leipzig": "LEI", "Bayer Leverkusen": "LEV", "Borussia Dortmund": "BVB",
        "Bayern Munich": "BAY", "Frankfurt": "FRA", "Stuttgart": "STU",
        # Spain
        "Real Madrid": "RMA", "Barcelona": "BAR", "Atletico Madrid": "ATM",
        "Athletic Bilbao": "ATH", "Sevilla": "SEV", "Real Betis": "BET",
        "Real Sociedad": "RSO", "Girona": "GIR", "Villarreal": "VIL",
        # France
        "Lyon": "LYO", "Paris Saint-Germain": "PSG", "Olympique de Marseille": "MAR",
        "AS Monaco": "MON", "OGC Nice": "NIC",
        # Other
        "Ajax": "AJX", "PSV": "PSV", "Galatasaray": "GAL", "Fenerbahçe": "FEN",
        "Beşiktaş": "BES", "Benfica": "BEN", "Sporting": "SPO",
        "Al Nassr": "NAS", "Al Hilal": "HIL", "Al Ittihad": "ITT",
        # National teams
        "Spain": "ESP", "Portugal": "POR", "Netherlands": "NED", "Germany": "GER",
        "Argentina": "ARG", "France": "FRA", "England": "ENG", "Italy": "ITA",
        "Japan": "JPN", "South Korea": "KOR", "Morocco": "MAR", "Croatia": "CRO",
        "Norway": "NOR", "Sweden": "SWE", "Denmark": "DEN"
    }
    return short_names.get(club, club[:3].upper())

def get_match_by_id(tournament_id: int, match_id: int) -> Optional[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM matches WHERE tournament_id=? AND id=?", (tournament_id, match_id))
    row = c.fetchone()
    conn.close()
    return row

def get_funny_match_comment(home_goals: int, away_goals: int) -> str:
    """Генерирует смешной комментарий по результату матча"""
    total_goals = home_goals + away_goals
    
    if home_goals == away_goals:
        return random.choice(DRAW_COMMENTS)
    elif total_goals >= 6:
        return random.choice(HIGH_SCORE_COMMENTS)
    elif total_goals <= 1:
        return random.choice(LOW_SCORE_COMMENTS)
    else:
        return random.choice(MATCH_COMMENTS)

def get_funny_message(ordered: List[tuple], prize: str) -> Optional[str]:
    """Обновленная функция с более интересными комментариями"""
    if not ordered:
        return None
    
    top_score = ordered[0][1]['PTS']
    leaders = [name for name, st in ordered if st['PTS'] == top_score]
    
    leader_messages = [
        f"👑 {leaders[0]} правит балом! {prize} уже пахнет победой!",
        f"🔥 {leaders[0]} в огне! Остальные курят в сторонке!",
        f"⚡ {leaders[0]} на коне! {prize} почти в кармане!",
        f"🚀 {leaders[0]} летит к {prize} как ракета!",
        f"👏 {leaders[0]} показывает класс! {prize} ждет своего героя!"
    ]
    
    tie_messages = [
        f"🤝 {leaders[0]} и {leaders[1]} не могут определиться! {prize} в подвешенном состоянии!",
        f"⚔️ {leaders[0]} против {leaders[1]}! Битва за {prize} накаляется!",
        f"🎭 {' VS '.join(leaders)} - драма достойная Оскара! {prize} ждет!",
        f"🔥 Дуэль века: {' и '.join(leaders)}! {prize} дрожит от напряжения!"
    ]
    
    chaos_messages = [
        f"🌪️ Полный хаос в турнире! {len(leaders)} претендентов на {prize}!",
        f"🎪 Цирк продолжается! {len(leaders)} клоунов борются за {prize}!",
        f"🍯 {prize} привлекает {len(leaders)} пчел! Кто первый доберется?",
        f"🎲 Кубик брошен! {len(leaders)} игроков в игре за {prize}!"
    ]
    
    if len(leaders) == 1:
        return random.choice(leader_messages)
    elif len(leaders) == 2:
        return random.choice(tie_messages)
    else:
        return random.choice(chaos_messages)

def get_main_menu_keyboard(is_admin: bool = True, has_tournament: bool = False):
    """Клавиатура с учетом прав пользователя и наличия турнира"""
    keyboard = []
    
    # Кнопки для работы с турнирами
    keyboard.append([InlineKeyboardButton("🏆 Выбрать турнир", callback_data="select_tournament")])
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("🆕 Создать турнир", callback_data="new_tournament")])
    
    # Кнопки для работы с текущим турниром (показываем только если турнир выбран)
    if has_tournament:
        keyboard.extend([
            [InlineKeyboardButton("👥 Добавить игрока", callback_data="add_player"),
             InlineKeyboardButton("👥+ Добавить списком", callback_data="add_players_list")],
            [InlineKeyboardButton("⚽ Назначить клубы", callback_data="assign_clubs_menu")],
            [InlineKeyboardButton("📊 Таблица", callback_data="show_table"),
             InlineKeyboardButton("📋 Расписание", callback_data="show_schedule")],
            [InlineKeyboardButton("⚽ Записать результат", callback_data="record_result"),
             InlineKeyboardButton("✏️ Изменить результат", callback_data="edit_result")]
        ])
        
        if is_admin:
            keyboard.append([InlineKeyboardButton("📅 Генерировать расписание", callback_data="generate_schedule")])
    
    return InlineKeyboardMarkup(keyboard)

def get_tournaments_keyboard(tournaments: List[sqlite3.Row], current_tournament_id: int = None):
    """Клавиатура для выбора турнира"""
    keyboard = []
    
    if not tournaments:
        keyboard.append([InlineKeyboardButton("❌ Нет турниров", callback_data="no_tournaments")])
    else:
        for tournament in tournaments:
            # Показываем статус текущего турнира
            status = "🟢" if tournament['id'] == current_tournament_id else "⚪"
            text = f"{status} {tournament['name'][:20]}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"choose_tournament_{tournament['id']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_players_keyboard(tournament_id: int):
    """Клавиатура для выбора игрока для назначения клуба"""
    keyboard = []
    players_without_clubs = get_players_without_clubs(tournament_id)
    
    for i in range(0, len(players_without_clubs), 2):
        row = []
        for j in range(i, min(i + 2, len(players_without_clubs))):
            player = players_without_clubs[j]
            row.append(InlineKeyboardButton(f"👤 {player['name']}", callback_data=f"select_player_{player['id']}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🎲 Случайно всем", callback_data="assign_random")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_countries_keyboard():
    keyboard = []
    countries = list(CLUBS_DB.keys())
    
    for i in range(0, len(countries), 2):
        row = []
        for j in range(i, min(i + 2, len(countries))):
            country = countries[j]
            flag_emoji = get_country_flag(country)
            row.append(InlineKeyboardButton(f"{flag_emoji} {country}", callback_data=f"country_{country}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀️ Назад к игрокам", callback_data="assign_clubs_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_clubs_keyboard(country: str, player_name: str):
    keyboard = []
    clubs = CLUBS_DB.get(country, [])
    
    for i in range(0, len(clubs), 2):
        row = []
        for j in range(i, min(i + 2, len(clubs))):
            club = clubs[j]
            row.append(InlineKeyboardButton(club, callback_data=f"assign_club_{country}_{club}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀️ Назад к странам", callback_data="select_country")])
    return InlineKeyboardMarkup(keyboard)

def get_matches_keyboard(tournament_id: int, unplayed_only: bool = True, for_edit: bool = False):
    keyboard = []
    matches = get_schedule(tournament_id, 100)

    if unplayed_only:
        matches = [m for m in matches if not m['played']]
    elif for_edit:
        matches = [m for m in matches if m['played']]  # Для редактирования только сыгранные

    if not matches:
        return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]])

    for match in matches:
        status = "⚽" if not match['played'] else "✅"
        hg = match['home_goals'] if match['home_goals'] is not None else "-"
        ag = match['away_goals'] if match['away_goals'] is not None else "-"
        no = match_no(match)

        text_full = f"{status} #{no}: {match['home']} vs {match['away']} [{hg}:{ag}]"
        if len(text_full) > 40:
            home_short = match['home'][:7] if len(match['home']) > 7 else match['home']
            away_short = match['away'][:7] if len(match['away']) > 7 else match['away']
            text_full = f"{status} #{no}: {home_short}-{away_short} [{hg}:{ag}]"

        callback_prefix = "edit_match_" if for_edit else "select_match_"
        keyboard.append([InlineKeyboardButton(text_full, callback_data=f"{callback_prefix}{match['id']}")])

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_score_keyboard(match_id: int, player_name: str, is_edit: bool = False):
    """Клавиатура для выбора количества голов"""
    keyboard = []
    
    for i in range(0, 21, 5): 
        row = []
        for j in range(i, min(i + 5, 11)):
            callback_prefix = "edit_score_" if is_edit else "score_"
            row.append(InlineKeyboardButton(str(j), callback_data=f"{callback_prefix}{match_id}_{player_name}_{j}"))
        keyboard.append(row)
    
    back_callback = "edit_result" if is_edit else "record_result"
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)

def get_country_flag(country: str) -> str:
    flags = {
        "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "Italy": "🇮🇹",
        "Germany": "🇩🇪", 
        "Spain": "🇪🇸",
        "France": "🇫🇷",
        "Netherlands": "🇳🇱",
        "Turkey": "🇹🇷",
        "Portugal": "🇵🇹",
        "Saudi Arabia": "🇸🇦",
        "National teams": "🌍"
    }
    return flags.get(country, "⚽")

async def send_new_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    """Отправляет новое меню (удаляет старое сообщение и отправляет новое)"""
    chat_id = update.effective_chat.id
    user_is_admin = await is_admin(update, context)
    current_tournament = get_current_tournament(chat_id)
    
    # Определяем клавиатуру по умолчанию
    default_markup = get_main_menu_keyboard(user_is_admin, bool(current_tournament))
    reply_markup = kwargs.get('reply_markup', default_markup)
    parse_mode = kwargs.get('parse_mode', None)
    
    try:
        # Удаляем старое сообщение если это callback query
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.delete()
    except Exception:
        pass
    
    # Отправляем новое сообщение
    if hasattr(update, 'callback_query') and update.callback_query:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_is_admin = await is_admin(update, context)
    current_tournament = get_current_tournament(update.effective_chat.id)
    
    text = "⚽ Добро пожаловать в Tournament Manager!\n\n"
    if current_tournament:
        text += f"🏆 Текущий турнир: {current_tournament['name']}\n\n"
    text += "Управляйте турниром с помощью кнопок ниже:"
    
    await send_new_menu(update, context, text)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_is_admin = await is_admin(update, context)
    current_tournament = get_current_tournament(update.effective_chat.id)
    
    text = "⚽ Меню управления турниром:"
    if current_tournament:
        text += f"\n🏆 Текущий турнир: {current_tournament['name']}"
    
    await send_new_menu(update, context, text)

async def cmd_new_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return await update.message.reply_text("❌ Только админы.")
    args = " ".join(context.args)
    parts = [p.strip() for p in args.split("|")]
    if not parts or not parts[0]:
        return await update.message.reply_text("Формат: /newtournament Название | [кругов] | [приз]")
    name = parts[0]
    rounds = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
    prize = parts[2] if len(parts) > 2 else "приз"
    tid = add_tournament(update.effective_chat.id, name, prize, rounds)
    
    await send_new_menu(
        update, context,
        f"✅ Турнир '{_html_escape(name)}' создан и выбран как текущий.\n"
        f"Кругов: {rounds}\nПриз: {_html_escape(prize)}",
        parse_mode=ParseMode.HTML
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    user_is_admin = await is_admin(update, context)
    current_tournament = get_current_tournament(chat_id)
    
    if data == "main_menu":
        text = "⚽ Меню управления турниром:"
        if current_tournament:
            text += f"\n🏆 Текущий турнир: {current_tournament['name']}"
        await send_new_menu(update, context, text)
    
    elif data == "select_tournament":
        tournaments = get_chat_tournaments(chat_id)
        current_id = current_tournament['id'] if current_tournament else None
        
        await send_new_menu(
            update, context,
            "🏆 Выберите турнир:\n\n🟢 - текущий турнир\n⚪ - другие турниры",
            reply_markup=get_tournaments_keyboard(tournaments, current_id)
        )
    
    elif data.startswith("choose_tournament_"):
        tournament_id = int(data[18:])
        set_current_tournament(chat_id, tournament_id)
        
        # Получаем информацию о выбранном турнире
        conn = db()
        c = conn.cursor()
        c.execute("SELECT * FROM tournaments WHERE id=?", (tournament_id,))
        tournament = c.fetchone()
        conn.close()
        
        if tournament:
            await send_new_menu(
                update, context,
                f"✅ Выбран турнир: {tournament['name']}\n\n⚽ Меню управления турниром:"
            )
        else:
            await send_new_menu(update, context, "❌ Ошибка выбора турнира")
    
    elif data == "new_tournament":
        if not user_is_admin:
            await send_new_menu(update, context, "❌ Только администраторы группы могут создавать турниры.")
            return
        await query.edit_message_text("Введите название турнира:")
        context.user_data['stage'] = 'tournament_name'
    
    elif data == "add_players_list":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира. Выберите турнир.")
            return
        await query.edit_message_text("Введите имена игроков через запятую:\nПример: Амир, Диас, Влад")
        context.user_data['stage'] = 'add_players_list'
    
    elif data == "record_result":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
        
        await send_new_menu(
            update, context,
            "⚽ Выберите матч для записи результата:\n\n⚽ - не сыгран, ✅ - завершен",
            reply_markup=get_matches_keyboard(current_tournament['id'], unplayed_only=True)
        )
    
    elif data == "edit_result":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
        
        await send_new_menu(
            update, context,
            "✏️ Выберите матч для изменения результата:\n\n✅ - завершенные матчи",
            reply_markup=get_matches_keyboard(current_tournament['id'], unplayed_only=False, for_edit=True)
        )
    
    elif data.startswith("edit_match_"):
        match_id = int(data[11:])
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return

        match = get_match_by_id(current_tournament['id'], match_id)
        if not match:
            await send_new_menu(update, context, "❌ Матч не найден.")
            return

        context.user_data['edit_match_id'] = match_id
        context.user_data['edit_match'] = dict(match)
        context.user_data['edit_match_scores'] = {}

        no = match_no(match)
        await send_new_menu(
            update, context,
            f"✏️ Редактирование матча #{no}: {match['home']} vs {match['away']}\n"
            f"Текущий счет: {match['home_goals']}:{match['away_goals']}\n\n"
            f"Новое количество голов для {match['home']}?",
            reply_markup=get_score_keyboard(match_id, match['home'], is_edit=True)
        )
    
    elif data.startswith("edit_score_"):
        parts = data[11:].split("_", 3)
        if len(parts) < 3:
            await send_new_menu(update, context, "❌ Ошибка формата данных.")
            return
            
        match_id = int(parts[0])
        player_name = parts[1]
        goals = int(parts[2])

        match = context.user_data.get('edit_match')
        if not match:
            await send_new_menu(update, context, "❌ Ошибка: матч не выбран.")
            return

        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return

        context.user_data.setdefault('edit_match_scores', {})
        context.user_data['edit_match_scores'][player_name] = goals

        no = match_no(match)

        if len(context.user_data['edit_match_scores']) == 1:
            # Первый игрок - показываем форму для второго
            other_player = match['away'] if player_name == match['home'] else match['home']
            await send_new_menu(
                update, context,
                f"✏️ Редактирование матча #{no}: {match['home']} vs {match['away']}\n"
                f"✅ {player_name}: {goals} голов\n\n"
                f"Новое количество голов для {other_player}?",
                reply_markup=get_score_keyboard(match_id, other_player, is_edit=True)
            )
        else:
            # Второй игрок - записываем результат и показываем итог
            home_goals = context.user_data['edit_match_scores'].get(match['home'], 0)
            away_goals = context.user_data['edit_match_scores'].get(match['away'], 0)

            # Записываем новый результат
            record_result(current_tournament['id'], match_id, home_goals, away_goals)

            match_comment = get_funny_match_comment(home_goals, away_goals)
            ordered = get_standings(current_tournament['id'])
            prize = get_current_tournament_prize(current_tournament['id'])
            msg = format_table(current_tournament['id'], ordered)

            home = _html_escape(match['home'])
            away = _html_escape(match['away'])
            comment = _html_escape(match_comment)
            old_score = f"{match['home_goals']}:{match['away_goals']}"

            result_text = (
                f"✅ Результат изменен!\n"
                f"⚽ Матч #{no}: {home} {home_goals}:{away_goals} {away}\n"
                f"📝 Было: {old_score} → Стало: {home_goals}:{away_goals}\n\n"
                f"{comment}\n\n"
                f"{msg}"
            )

            await send_new_menu(update, context, result_text, parse_mode=ParseMode.HTML)

            fun = get_funny_message(ordered, prize)
            if fun:
                await context.bot.send_message(chat_id=chat_id, text=fun)

            # Чистим состояние
            context.user_data.pop('edit_match_id', None)
            context.user_data.pop('edit_match', None)
            context.user_data.pop('edit_match_scores', None)
    
    elif data.startswith("select_match_"):
        match_id = int(data[13:])
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return

        match = get_match_by_id(current_tournament['id'], match_id)
        if not match:
            await send_new_menu(update, context, "❌ Матч не найден.")
            return

        if match['played']:
            await send_new_menu(
                update, context,
                f"❌ Результат этого матча уже записан: {match['home']} {match['home_goals']}:{match['away_goals']} {match['away']}"
            )
            return

        context.user_data['selected_match_id'] = match_id
        context.user_data['selected_match'] = dict(match)
        context.user_data['match_scores'] = {}

        no = match_no(match)
        await send_new_menu(
            update, context,
            f"⚽ Матч #{no}: {match['home']} vs {match['away']}\n\n"
            f"Сколько голов забил {match['home']}?",
            reply_markup=get_score_keyboard(match_id, match['home'])
        )
    
    elif data.startswith("score_"):
        parts = data[6:].split("_", 3)
        if len(parts) < 3:
            await send_new_menu(update, context, "❌ Ошибка формата данных.")
            return
            
        match_id = int(parts[0])
        player_name = parts[1]
        goals = int(parts[2])

        match = context.user_data.get('selected_match')
        if not match:
            await send_new_menu(update, context, "❌ Ошибка: матч не выбран.")
            return

        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return

        context.user_data.setdefault('match_scores', {})
        context.user_data['match_scores'][player_name] = goals

        no = match_no(match)

        if len(context.user_data['match_scores']) == 1:
            # Первый игрок - показываем форму для второго
            other_player = match['away'] if player_name == match['home'] else match['home']
            await send_new_menu(
                update, context,
                f"⚽ Матч #{no}: {match['home']} vs {match['away']}\n"
                f"✅ {player_name}: {goals} голов\n\n"
                f"Сколько голов забил {other_player}?",
                reply_markup=get_score_keyboard(match_id, other_player)
            )
        else:
            # Второй игрок - записываем результат и показываем итог
            home_goals = context.user_data['match_scores'].get(match['home'], 0)
            away_goals = context.user_data['match_scores'].get(match['away'], 0)

            # Записываем результат
            record_result(current_tournament['id'], match_id, home_goals, away_goals)

            match_comment = get_funny_match_comment(home_goals, away_goals)
            ordered = get_standings(current_tournament['id'])
            prize = get_current_tournament_prize(current_tournament['id'])
            msg = format_table(current_tournament['id'], ordered)

            home = _html_escape(match['home'])
            away = _html_escape(match['away'])
            comment = _html_escape(match_comment)

            result_text = (
                f"✅ Результат записан!\n"
                f"⚽ Матч #{no}: {home} {home_goals}:{away_goals} {away}\n\n"
                f"{comment}\n\n"
                f"{msg}"
            )

            await send_new_menu(update, context, result_text, parse_mode=ParseMode.HTML)

            fun = get_funny_message(ordered, prize)
            if fun:
                await context.bot.send_message(chat_id=chat_id, text=fun)

            # Чистим состояние
            context.user_data.pop('selected_match_id', None)
            context.user_data.pop('selected_match', None)
            context.user_data.pop('match_scores', None)
    
    elif data == "add_player":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира. Выберите турнир.")
            return
        await query.edit_message_text("Введите имя игрока:")
        context.user_data['stage'] = 'add_player_name'
    
    elif data == "assign_clubs_menu":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
        
        players_without_clubs = get_players_without_clubs(current_tournament['id'])
        if not players_without_clubs:
            await send_new_menu(update, context, "✅ Всем игрокам уже назначены клубы!")
            return
        
        await send_new_menu(
            update, context,
            f"⚽ Назначение клубов игрокам\n\n"
            f"👥 Игроков без клубов: {len(players_without_clubs)}\n\n"
            "Выберите игрока:",
            reply_markup=get_players_keyboard(current_tournament['id'])
        )
    
    elif data.startswith("select_player_"):
        player_id = int(data[14:])
        player = get_player_by_id(player_id)
        if not player:
            await send_new_menu(update, context, "❌ Игрок не найден.")
            return
        
        context.user_data['selected_player_id'] = player_id
        context.user_data['selected_player_name'] = player['name']
        
        await send_new_menu(
            update, context,
            f"👤 Выбран игрок: {player['name']}\n\n"
            "🌍 Выберите страну для назначения клуба:",
            reply_markup=get_countries_keyboard()
        )
    
    elif data == "select_country":
        # Возвращаемся к выбору стран для текущего игрока
        player_name = context.user_data.get('selected_player_name', 'игрок')
        await send_new_menu(
            update, context,
            f"👤 Выбран игрок: {player_name}\n\n"
            "🌍 Выберите страну для назначения клуба:",
            reply_markup=get_countries_keyboard()
        )
    
    elif data.startswith("country_"):
        country = data[8:]  
        player_name = context.user_data.get('selected_player_name', 'игрок')
        context.user_data['selected_country'] = country
        
        await send_new_menu(
            update, context,
            f"👤 Игрок: {player_name}\n"
            f"🌍 Страна: {get_country_flag(country)} {country}\n\n"
            f"⚽ Выберите клуб:",
            reply_markup=get_clubs_keyboard(country, player_name)
        )
    
    elif data.startswith("assign_club_"):
        parts = data[12:].split("_", 1)  
        country = parts[0]
        club = parts[1]
        
        player_id = context.user_data.get('selected_player_id')
        player_name = context.user_data.get('selected_player_name')
        
        if not player_id or not player_name:
            await send_new_menu(update, context, "❌ Ошибка: игрок не выбран.")
            return
        
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
        
        # Назначаем клуб выбранному игроку
        assign_club(current_tournament['id'], player_name, club)
        
        # Очищаем данные о выбранном игроке
        context.user_data.pop('selected_player_id', None)
        context.user_data.pop('selected_player_name', None)
        context.user_data.pop('selected_country', None)
        
        # Проверяем, остались ли игроки без клубов
        remaining_players = get_players_without_clubs(current_tournament['id'])
        if remaining_players:
            await send_new_menu(
                update, context,
                f"✅ {player_name} назначен клуб {get_country_flag(country)} {club}!\n\n"
                f"👥 Игроков без клубов осталось: {len(remaining_players)}\n\n"
                "Выберите следующего игрока:",
                reply_markup=get_players_keyboard(current_tournament['id'])
            )
        else:
            await send_new_menu(
                update, context,
                f"✅ {player_name} назначен клуб {get_country_flag(country)} {club}!\n\n"
                "🎉 Всем игрокам назначены клубы! Можете генерировать расписание."
            )
    
    elif data == "assign_random":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
        assign_random_clubs(current_tournament['id'])
        await send_new_menu(update, context, "🎲 Клубы назначены случайно!")
    
    elif data == "generate_schedule":
        if not user_is_admin:
            await send_new_menu(update, context, "❌ Только администраторы могут генерировать расписание.")
            return
            
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
        
        # Проверяем есть ли уже матчи
        existing_matches = get_schedule(current_tournament['id'])
        if existing_matches:
            await send_new_menu(
                update, context,
                "⚠️ В турнире уже есть матчи!\n\n"
                "🚨 Генерация нового расписания удалит все текущие результаты!\n\n"
                "Вы уверены?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Да, сгенерировать", callback_data="confirm_generate_schedule")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
                ])
            )
        else:
            generate_schedule(current_tournament['id'], current_tournament['rounds'])
            await send_new_menu(update, context, "📅 Расписание сгенерировано!")
    
    elif data == "confirm_generate_schedule":
        if not user_is_admin:
            await send_new_menu(update, context, "❌ Только администраторы могут генерировать расписание.")
            return
            
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
            
        generate_schedule(current_tournament['id'], current_tournament['rounds'])
        await send_new_menu(update, context, "📅 Расписание сгенерировано! Все предыдущие результаты удалены.")
    
    elif data == "show_schedule":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
            
        sched = get_schedule(current_tournament['id'])
        if not sched:
            await send_new_menu(update, context, "📋 Нет матчей. Сгенерируйте расписание.")
            return

        lines = ["📅 РАСПИСАНИЕ МАТЧЕЙ:\n"]
        for m in sched:
            status = "✅" if m['played'] else "⏳"
            hg = m['home_goals'] if m['home_goals'] is not None else "-"
            ag = m['away_goals'] if m['away_goals'] is not None else "-"
            no = match_no(m)

            home_short = m['home'][:8] if len(m['home']) > 8 else m['home']
            away_short = m['away'][:8] if len(m['away']) > 8 else m['away']

            lines.append(f"{status} #{no}: {home_short} vs {away_short} [{hg}:{ag}]")

        await send_new_menu(update, context, "\n".join(lines))
    
    elif data == "show_table":
        if not current_tournament:
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return
            
        ordered = get_standings(current_tournament['id'])
        msg = format_table(current_tournament['id'], ordered)
        await send_new_menu(
            update, context,
            f"📊 ТУРНИРНАЯ ТАБЛИЦА:\n\n{msg}",
            parse_mode=ParseMode.HTML
        )

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'stage' not in context.user_data or not context.user_data['stage']:
        return

    stage = context.user_data['stage']
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_is_admin = await is_admin(update, context)

    if stage == 'tournament_name':
        if not user_is_admin:
            context.user_data['stage'] = None
            await send_new_menu(update, context, "❌ Только администраторы группы могут создавать турниры.")
            return

        context.user_data['new_tournament'] = {'name': text}
        context.user_data['stage'] = 'tournament_rounds'
        await update.message.reply_text("Сколько кругов? Введите число (по умолчанию 2).")

    elif stage == 'tournament_rounds':
        if text and not text.isdigit():
            await update.message.reply_text("Пожалуйста, введите число кругов (например, 2).")
            return

        rounds = int(text) if text.isdigit() else 2
        context.user_data['new_tournament']['rounds'] = rounds
        context.user_data['stage'] = 'tournament_prize'
        await update.message.reply_text("Какой приз? (можно текстом)")

    elif stage == 'tournament_prize':
        prize = text if text else "приз"
        nt = context.user_data.get('new_tournament', {})
        name = nt.get('name', 'Турнир')
        rounds = nt.get('rounds', 2)

        try:
            add_tournament(chat_id, name, prize, rounds)
        except Exception as e:
        
            context.user_data['stage'] = None
            await update.message.reply_text(f"❌ Не удалось создать турнир: {e}")
            return

        context.user_data['stage'] = None
        context.user_data.pop('new_tournament', None)
        await send_new_menu(
            update, context,
            f"✅ Турнир '{_html_escape(name)}' создан и выбран!\n"
            f"🏆 Приз: {_html_escape(prize)}\n"
            f"🔄 Кругов: {rounds}\n\n"
            "Теперь добавляйте игроков и назначайте им клубы:",
            parse_mode=ParseMode.HTML
        )

    elif stage == 'add_player_name':
        current_tournament = get_current_tournament(chat_id)
        if not current_tournament:
            context.user_data['stage'] = None
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return

        add_player(current_tournament['id'], text)
        context.user_data['stage'] = None
        await send_new_menu(update, context, f"✅ Игрок {text} добавлен в турнир!")

    elif stage == 'add_players_list':
        current_tournament = get_current_tournament(chat_id)
        if not current_tournament:
            context.user_data['stage'] = None
            await send_new_menu(update, context, "❌ Нет выбранного турнира.")
            return

        player_names = [name.strip() for name in text.split(',') if name.strip()]
        if not player_names:
            await update.message.reply_text(
                "❌ Не найдено имен игроков. Попробуйте еще раз.\n"
                "Пример: Амир, Диас, Влад"
            )
            return

        added_count = 0
        for name in player_names:
            if 0 < len(name) <= 50:
                add_player(current_tournament['id'], name)
                added_count += 1

        context.user_data['stage'] = None
        await send_new_menu(
            update, context,
            f"✅ Добавлено игроков: {added_count}\n"
            f"👥 Список: {', '.join(player_names[:10])}{'...' if len(player_names) > 10 else ''}"
        )

# Команда для записи результата (остается текстовой для удобства)
async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_tournament = get_current_tournament(update.effective_chat.id)
    if not current_tournament:
        await update.message.reply_text("❌ Нет выбранного турнира.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("📝 Формат: /result ID X-Y\nПример: /result 1 2-1")
        return
    
    try:
        match_id = int(context.args[0])
        score = context.args[1].split("-")
        if len(score) != 2:
            await update.message.reply_text("❌ Неверный формат счёта. Используйте X-Y")
            return
        hg, ag = int(score[0]), int(score[1])
        record_result(current_tournament['id'], match_id, hg, ag)
        
        # Добавляем смешной комментарий
        match_comment = get_funny_match_comment(hg, ag)
        
        ordered = get_standings(current_tournament['id'])
        prize = get_current_tournament_prize(current_tournament['id'])
        msg = format_table(current_tournament['id'], ordered)
        fun = get_funny_message(ordered, prize)
        
        await update.message.reply_text(
            f"✅ Результат записан!\n{match_comment}\n\n{msg}",
            parse_mode=ParseMode.HTML
        )
        if fun:
            await update.message.reply_text(fun)
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используйте: /result ID X-Y")

# -------------------------
# Запуск бота
# -------------------------
def main():
    init_db()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Установите BOT_TOKEN")
    
    app = Application.builder().token(token).build()
    
    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("newtournament", cmd_new_tournament))
    app.add_handler(CommandHandler("result", cmd_result))
    
    # Обработчики кнопок и текста
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    app.run_polling()

if __name__ == "__main__":
    main()