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

DB_PATH = os.getenv("LEAGUE_DB", "league_v3.db")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    c = conn.cursor()
    # Таблица турниров
    c.execute("""
    CREATE TABLE IF NOT EXISTS tournaments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        prize TEXT,
        rounds INTEGER DEFAULT 2,
        created_at TEXT NOT NULL,
        active INTEGER DEFAULT 1
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        club TEXT,
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id)
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
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id)
    );
    """)
    
    c.execute("PRAGMA table_info(matches)")
    columns = [row[1] for row in c.fetchall()]
    if 'match_number' not in columns:
        c.execute("ALTER TABLE matches ADD COLUMN match_number INTEGER DEFAULT 0")
        # Обновляем существующие записи
        c.execute("""
        UPDATE matches 
        SET match_number = id 
        WHERE match_number IS NULL OR match_number = 0
        """)
    
    conn.commit()
    conn.close()

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == 'private':
        return True

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False

def get_active_tournament(chat_id: int) -> Optional[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM tournaments WHERE chat_id=? AND active=1 ORDER BY id DESC LIMIT 1", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row

def match_no(row: sqlite3.Row) -> int:
    try:
        n = row['match_number']
        return n if n is not None else row['id']
    except Exception:
        return row['id']

def add_tournament(chat_id: int, name: str, prize: str, rounds: int) -> int:
    conn = db()
    c = conn.cursor()
    
    c.execute("UPDATE tournaments SET active=0 WHERE chat_id=?", (chat_id,))
    
    tournament_ids = c.execute("SELECT id FROM tournaments WHERE chat_id=?", (chat_id,)).fetchall()
    for tid in tournament_ids:
        c.execute("DELETE FROM matches WHERE tournament_id=?", (tid['id'],))
        c.execute("DELETE FROM players WHERE tournament_id=?", (tid['id'],))
    
    
    c.execute("""
    INSERT INTO tournaments (chat_id, name, prize, rounds, created_at, active)
    VALUES (?, ?, ?, ?, ?, 1)
    """, (chat_id, name, prize, rounds, datetime.now().isoformat()))
    tid = c.lastrowid
    conn.commit()
    conn.close()
    return tid

def end_tournament(tournament_id: int):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE tournaments SET active=0 WHERE id=?", (tournament_id,))
    conn.commit()
    conn.close()

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

def format_table(tournament_id: int, ordered: List[tuple]) -> str:
    lines = []
    header = f"{'#':<2}{'Игрок':<10}{'И':<3}{'В':<3}{'Н':<3}{'П':<3}{'±':<5}{'О':<3}"
    lines.append(header)
    lines.append("─" * len(header))
    for i, (name, st) in enumerate(ordered, start=1):
        club = get_player_club(tournament_id, name)
        short_club = get_short_club_name(club) if club else ""
        if club:
            display_name = f"{name[:6]}({short_club})" if len(name) > 6 else f"{name}({short_club})"
        else:
            display_name = name[:9]
        if len(display_name) > 10:
            display_name = display_name[:9] + "."
        lines.append(f"{i:<2}{display_name:<10}{st['P']:<3}{st['W']:<3}{st['D']:<3}{st['L']:<3}{st['GD']:<4}{st['PTS']:<3}")
    # ВАЖНО: возвращаем HTML <pre>, НИКАКИХ бэктиков
    table = "\n".join(lines)
    # Экранируем спецсимволы для HTML
    table = (table
             .replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;"))
    return f"<pre>{table}</pre>"

def get_active_tournament_prize(tournament_id: int) -> str:
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

def get_main_menu_keyboard(is_admin: bool = True):
    """Клавиатура с учетом прав пользователя"""
    keyboard = []
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("🆕 Новый турнир", callback_data="new_tournament")])
    
    keyboard.extend([
        [InlineKeyboardButton("👥 Добавить игрока", callback_data="add_player"),
         InlineKeyboardButton("👥+ Добавить списком", callback_data="add_players_list")],
        [InlineKeyboardButton("⚽ Назначить клубы", callback_data="assign_clubs_menu")],
        [InlineKeyboardButton("📅 Генерировать расписание", callback_data="generate_schedule")],
        [InlineKeyboardButton("📋 Расписание", callback_data="show_schedule"),
         InlineKeyboardButton("⚽ Записать результат", callback_data="record_result")],
        [InlineKeyboardButton("📊 Таблица", callback_data="show_table")]
    ])
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("🏆 Завершить турнир", callback_data="end_tournament")])
    
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

def get_matches_keyboard(tournament_id: int, unplayed_only: bool = True):
    keyboard = []
    matches = get_schedule(tournament_id, 100)

    if unplayed_only:
        matches = [m for m in matches if not m['played']]

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

        keyboard.append([InlineKeyboardButton(text_full, callback_data=f"select_match_{match['id']}")])

    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_score_keyboard(match_id: int, player_name: str):
    """Клавиатура для выбора количества голов"""
    keyboard = []
    
    for i in range(0, 21, 5): 
        row = []
        for j in range(i, min(i + 5, 11)):
            row.append(InlineKeyboardButton(str(j), callback_data=f"score_{match_id}_{player_name}_{j}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="record_result")])
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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_is_admin = await is_admin(update, context)
    await update.message.reply_text(
        "⚽ Добро пожаловать в Tournament Manager!\n\n"
        "Управляйте турниром с помощью кнопок ниже:",
        reply_markup=get_main_menu_keyboard(user_is_admin)
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_is_admin = await is_admin(update, context)
    await update.message.reply_text(
        "⚽ Меню управления турниром:",
        reply_markup=get_main_menu_keyboard(user_is_admin)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    # ИСПРАВЛЕНО: проверяем права админа при каждом нажатии кнопки
    user_is_admin = await is_admin(update, context)
    
    if data == "main_menu":
        await query.edit_message_text(
            "⚽ Меню управления турниром:",
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )
    
    elif data == "new_tournament":
        if not user_is_admin:
            await query.edit_message_text(
                "❌ Только администраторы группы могут создавать турниры.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        await query.edit_message_text("Введите название турнира:")
        context.user_data['stage'] = 'tournament_name'
    
    elif data == "add_players_list":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира. Создайте новый турнир.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        await query.edit_message_text("Введите имена игроков через запятую:\nПример: Амир, Диас, Влад")
        context.user_data['stage'] = 'add_players_list'
    
    elif data == "record_result":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        await query.edit_message_text(
            "⚽ Выберите матч для записи результата:\n\n"
            "⚽ - не сыгран, ✅ - завершен",
            reply_markup=get_matches_keyboard(t['id'], unplayed_only=True)
        )
    
    elif data.startswith("select_match_"):
        match_id = int(data[13:])
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text("❌ Нет активного турнира.", reply_markup=get_main_menu_keyboard(user_is_admin))
            return

        match = get_match_by_id(t['id'], match_id)
        if not match:
            await query.edit_message_text("❌ Матч не найден.", reply_markup=get_main_menu_keyboard(user_is_admin))
            return

        # Проверяем только один раз при выборе матча
        if match['played']:
            await query.edit_message_text(
                f"❌ Результат этого матча уже записан: {match['home']} {match['home_goals']}:{match['away_goals']} {match['away']}",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return

        context.user_data['selected_match_id'] = match_id
        context.user_data['selected_match'] = dict(match)  # Сохраняем как обычный dict
        context.user_data['match_scores'] = {}

        no = match_no(match)
        await query.edit_message_text(
            f"⚽ Матч #{no}: {match['home']} vs {match['away']}\n\n"
            f"Сколько голов забил {match['home']}?",
            reply_markup=get_score_keyboard(match_id, match['home'])
        )
    
    elif data.startswith("score_"):
        parts = data[6:].split("_", 3)
        if len(parts) < 3:
            await query.edit_message_text("❌ Ошибка формата данных.", reply_markup=get_main_menu_keyboard(user_is_admin))
            return
            
        match_id = int(parts[0])
        player_name = parts[1]
        goals = int(parts[2])

        match = context.user_data.get('selected_match')
        if not match:
            await query.edit_message_text("❌ Ошибка: матч не выбран.", reply_markup=get_main_menu_keyboard(user_is_admin))
            return

        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text("❌ Нет активного турнира.", reply_markup=get_main_menu_keyboard(user_is_admin))
            return

        context.user_data.setdefault('match_scores', {})
        context.user_data['match_scores'][player_name] = goals

        no = match_no(match)

        if len(context.user_data['match_scores']) == 1:
            # Первый игрок - показываем форму для второго
            other_player = match['away'] if player_name == match['home'] else match['home']
            await query.edit_message_text(
                f"⚽ Матч #{no}: {match['home']} vs {match['away']}\n"
                f"✅ {player_name}: {goals} голов\n\n"
                f"Сколько голов забил {other_player}?",
                reply_markup=get_score_keyboard(match_id, other_player)
            )
        else:
            # Второй игрок - записываем результат и показываем итог
            home_goals = context.user_data['match_scores'].get(match['home'], 0)
            away_goals = context.user_data['match_scores'].get(match['away'], 0)

            # ИСПРАВЛЕНО: убрали повторную проверку played статуса
            # Записываем результат сразу
            record_result(t['id'], match_id, home_goals, away_goals)

            match_comment = get_funny_match_comment(home_goals, away_goals)

            ordered = get_standings(t['id'])
            prize = get_active_tournament_prize(t['id'])
            msg = format_table(t['id'], ordered)
            fun = get_funny_message(ordered, prize)

            result_text = (
                f"✅ Результат записан!\n"
                f"⚽ Матч #{no}: {match['home']} {home_goals}:{away_goals} {match['away']}\n\n"
                f"{match_comment}\n\n"
                f"{msg}"
            )

            await query.edit_message_text(
                result_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )

            if fun:
                await query.message.reply_text(fun)
            
            # Очищаем данные
            context.user_data.pop('selected_match_id', None)
            context.user_data.pop('selected_match', None)
            context.user_data.pop('match_scores', None)
    
    elif data == "add_player":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира. Создайте новый турнир.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        await query.edit_message_text("Введите имя игрока:")
        context.user_data['stage'] = 'add_player_name'
    
    elif data == "assign_clubs_menu":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        players_without_clubs = get_players_without_clubs(t['id'])
        if not players_without_clubs:
            await query.edit_message_text(
                "✅ Всем игрокам уже назначены клубы!",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        await query.edit_message_text(
            f"⚽ Назначение клубов игрокам\n\n"
            f"👥 Игроков без клубов: {len(players_without_clubs)}\n\n"
            "Выберите игрока:",
            reply_markup=get_players_keyboard(t['id'])
        )
    
    elif data.startswith("select_player_"):
        player_id = int(data[14:])  # убираем "select_player_"
        player = get_player_by_id(player_id)
        if not player:
            await query.edit_message_text(
                "❌ Игрок не найден.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        context.user_data['selected_player_id'] = player_id
        context.user_data['selected_player_name'] = player['name']
        
        await query.edit_message_text(
            f"👤 Выбран игрок: {player['name']}\n\n"
            "🌍 Выберите страну для назначения клуба:",
            reply_markup=get_countries_keyboard()
        )
    
    elif data == "select_country":
        # Возвращаемся к выбору стран для текущего игрока
        player_name = context.user_data.get('selected_player_name', 'игрок')
        await query.edit_message_text(
            f"👤 Выбран игрок: {player_name}\n\n"
            "🌍 Выберите страну для назначения клуба:",
            reply_markup=get_countries_keyboard()
        )
    
    elif data.startswith("country_"):
        country = data[8:]  
        player_name = context.user_data.get('selected_player_name', 'игрок')
        context.user_data['selected_country'] = country
        
        await query.edit_message_text(
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
            await query.edit_message_text(
                "❌ Ошибка: игрок не выбран.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        # Назначаем клуб выбранному игроку
        assign_club(t['id'], player_name, club)
        
        # Очищаем данные о выбранном игроке
        context.user_data.pop('selected_player_id', None)
        context.user_data.pop('selected_player_name', None)
        context.user_data.pop('selected_country', None)
        
        # Проверяем, остались ли игроки без клубов
        remaining_players = get_players_without_clubs(t['id'])
        if remaining_players:
            await query.edit_message_text(
                f"✅ {player_name} назначен клуб {get_country_flag(country)} {club}!\n\n"
                f"👥 Игроков без клубов осталось: {len(remaining_players)}\n\n"
                "Выберите следующего игрока:",
                reply_markup=get_players_keyboard(t['id'])
            )
        else:
            await query.edit_message_text(
                f"✅ {player_name} назначен клуб {get_country_flag(country)} {club}!\n\n"
                "🎉 Всем игрокам назначены клубы! Можете генерировать расписание.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
    
    elif data == "assign_random":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        assign_random_clubs(t['id'])
        await query.edit_message_text(
            "🎲 Клубы назначены случайно!",
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )
    
    elif data == "generate_schedule":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        generate_schedule(t['id'], t['rounds'])
        await query.edit_message_text(
            "📅 Расписание сгенерировано!",
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )
    
    elif data == "show_schedule":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text("❌ Нет активного турнира.", reply_markup=get_main_menu_keyboard(user_is_admin))
            return
        sched = get_schedule(t['id'])
        if not sched:
            await query.edit_message_text("📋 Нет матчей. Сгенерируйте расписание.", reply_markup=get_main_menu_keyboard(user_is_admin))
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

        await query.edit_message_text("\n".join(lines), reply_markup=get_main_menu_keyboard(user_is_admin))
    
    elif data == "show_table":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        ordered = get_standings(t['id'])
        msg = format_table(t['id'], ordered)
        await query.edit_message_text(
            f"📊 ТУРНИРНАЯ ТАБЛИЦА:\n\n{msg}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )
    
    elif data == "end_tournament":
        if not user_is_admin:
            await query.edit_message_text(
                "❌ Только администраторы группы могут завершать турниры.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
            
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        ordered = get_standings(t['id'])
        end_tournament(t['id'])
        winner = ordered[0][0] if ordered else "никто"
        prize = get_active_tournament_prize(t['id'])
        msg = format_table(t['id'], ordered)
        
        winner_messages = [
            f"🎊 Барабанная дробь... Победитель — {winner}!",
            f"👑 {winner} — новый король турнира!",
            f"🏆 {winner} забирает {prize} домой!",
            f"⚡ {winner} — гений футбола!"
        ]
        
        winner_msg = random.choice(winner_messages)
        
        await query.edit_message_text(
            f"🏆 Турнир '{t['name']}' окончен!\n"
            f"{winner_msg}\n\n{msg}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'stage' not in context.user_data:
        return

    stage = context.user_data['stage']
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_is_admin = await is_admin(update, context)

    if stage == 'tournament_name':
        # Проверяем права только для создания турнира
        if not user_is_admin:
            context.user_data['stage'] = None
            await update.message.reply_text(
                "❌ Только администраторы группы могут создавать турниры.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
            
        context.user_data['new_tournament'] = {'name': text}
        context.user_data['stage'] = 'tournament_rounds'
        await update.message.reply_text("Сколько кругов? (по умолчанию 2):")
    
    elif stage == 'tournament_rounds':
        # Здесь уже не нужно проверять права, так как процесс уже начат
        rounds = int(text) if text.isdigit() else 2
        context.user_data['new_tournament']['rounds'] = rounds
        context.user_data['stage'] = 'tournament_prize'
        await update.message.reply_text("Какой приз?")
    
    elif stage == 'tournament_prize':
        # И здесь тоже не нужно проверять права
        prize = text if text else "приз"
        context.user_data['new_tournament']['prize'] = prize
        
        tid = add_tournament(
            chat_id,
            context.user_data['new_tournament']['name'],
            prize,
            context.user_data['new_tournament']['rounds']
        )
        context.user_data['stage'] = None
        
        await update.message.reply_text(
            f"✅ Турнир '{context.user_data['new_tournament']['name']}' создан!\n"
            f"🏆 Приз: {prize}\n"
            f"🔄 Кругов: {context.user_data['new_tournament']['rounds']}\n\n"
            "Теперь добавляйте игроков и назначайте им клубы:",
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )
    
    elif stage == 'add_player_name':
        t = get_active_tournament(chat_id)
        if not t:
            context.user_data['stage'] = None
            await update.message.reply_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        add_player(t['id'], text)
        context.user_data['stage'] = None
        
        await update.message.reply_text(
            f"✅ Игрок {text} добавлен в турнир!",
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )
    
    elif stage == 'add_players_list':
        t = get_active_tournament(chat_id)
        if not t:
            context.user_data['stage'] = None
            await update.message.reply_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return

        player_names = [name.strip() for name in text.split(',') if name.strip()]
        
        if not player_names:
            await update.message.reply_text(
                "❌ Не найдено имен игроков. Попробуйте еще раз.\n"
                "Пример: Амир, Диас, Влад",
                reply_markup=get_main_menu_keyboard(user_is_admin)
            )
            return
        
        added_count = 0
        for name in player_names:
            if len(name) > 0 and len(name) <= 50: 
                add_player(t['id'], name)
                added_count += 1
        
        context.user_data['stage'] = None
        
        await update.message.reply_text(
            f"✅ Добавлено игроков: {added_count}\n"
            f"👥 Список: {', '.join(player_names[:10])}{'...' if len(player_names) > 10 else ''}",
            reply_markup=get_main_menu_keyboard(user_is_admin)
        )

# Команда для записи результата (остается текстовой для удобства)
async def cmd_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = get_active_tournament(update.effective_chat.id)
    if not t:
        await update.message.reply_text("❌ Нет активного турнира.")
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
        record_result(t['id'], match_id, hg, ag)
        
        # Добавляем смешной комментарий
        match_comment = get_funny_match_comment(hg, ag)
        
        ordered = get_standings(t['id'])
        prize = get_active_tournament_prize(t['id'])
        msg = format_table(t['id'], ordered)
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
    app.add_handler(CommandHandler("result", cmd_result))
    
    # Обработчики кнопок и текста
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    app.run_polling()

if __name__ == "__main__":
    main()