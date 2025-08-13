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
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# -------------------------
# Встроенная база клубов
# -------------------------
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

# -------------------------
# States for conversation
# -------------------------
TOURNAMENT_NAME, TOURNAMENT_ROUNDS, TOURNAMENT_PRIZE, ADD_PLAYER_NAME, ADD_PLAYERS_LIST = range(5)

# -------------------------
# Подключение к базе данных
# -------------------------
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
    # Игроки
    c.execute("""
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        club TEXT,
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id)
    );
    """)
    # Матчи
    c.execute("""
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        home TEXT NOT NULL,
        away TEXT NOT NULL,
        home_goals INTEGER,
        away_goals INTEGER,
        played INTEGER DEFAULT 0,
        FOREIGN KEY(tournament_id) REFERENCES tournaments(id)
    );
    """)
    conn.commit()
    conn.close()

# -------------------------
# Утилиты
# -------------------------
def get_active_tournament(chat_id: int) -> Optional[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM tournaments WHERE chat_id=? AND active=1 ORDER BY id DESC LIMIT 1", (chat_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_tournament(chat_id: int, name: str, prize: str, rounds: int) -> int:
    conn = db()
    c = conn.cursor()
    
    # Сначала завершаем все старые турниры в этом чате
    c.execute("UPDATE tournaments SET active=0 WHERE chat_id=?", (chat_id,))
    
    # Удаляем все старые матчи и игроков из предыдущих турниров этого чата
    tournament_ids = c.execute("SELECT id FROM tournaments WHERE chat_id=?", (chat_id,)).fetchall()
    for tid in tournament_ids:
        c.execute("DELETE FROM matches WHERE tournament_id=?", (tid['id'],))
        c.execute("DELETE FROM players WHERE tournament_id=?", (tid['id'],))
    
    # Сбрасываем автоинкремент для таблицы matches
    c.execute("DELETE FROM sqlite_sequence WHERE name='matches'")
    
    # Создаем новый турнир
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

# -------------------------
# Генерация расписания
# -------------------------
def generate_schedule(tournament_id: int, rounds: int):
    conn = db()
    c = conn.cursor()
    
    # Удаляем все старые матчи этого турнира перед генерацией новых
    c.execute("DELETE FROM matches WHERE tournament_id=?", (tournament_id,))
    
    players = get_players(tournament_id)
    names = [p["name"] for p in players]
    matches = []
    
    # Генерируем все пары для каждого круга
    for r in range(rounds):
        for i in range(len(names)):
            for j in range(i + 1, len(names)):  # Только уникальные пары
                if r % 2 == 0:
                    matches.append((names[i], names[j]))
                else:
                    matches.append((names[j], names[i]))
    
    random.shuffle(matches)
    
    for home, away in matches:
        c.execute("INSERT INTO matches (tournament_id, home, away) VALUES (?, ?, ?)",
                  (tournament_id, home, away))
    conn.commit()
    conn.close()

def get_schedule(tournament_id: int, limit: int = None) -> List[sqlite3.Row]:
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT * FROM matches
    WHERE tournament_id=? ORDER BY played ASC, id ASC
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

# -------------------------
# Таблица
# -------------------------
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
    header = f"{'#':>2} {'Игрок':<12} {'И':>2} {'В':>2} {'Н':>2} {'П':>2} {'З':>2} {'П':>2} {'±':>3} {'О':>2}"
    lines.append(header)
    lines.append("-"*len(header))
    for i, (name, st) in enumerate(ordered, start=1):
        club = get_player_club(tournament_id, name)
        
        short_club = get_short_club_name(club) if club else ""
        display_name = f"{name}({short_club})" if short_club else name
        
        if len(display_name) > 12:
            display_name = display_name[:11] + "."
        lines.append(f"{i:>2} {display_name:<12} {st['P']:>2} {st['W']:>2} {st['D']:>2} {st['L']:>2} {st['GF']:>2} {st['GA']:>2} {st['GD']:>3} {st['PTS']:>2}")
    return "```\n" + "\n".join(lines) + "\n```"

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

# -------------------------
# Шутки про приз
# -------------------------
def get_funny_message(ordered: List[tuple], prize: str) -> Optional[str]:
    if not ordered:
        return None
    top_score = ordered[0][1]['PTS']
    leaders = [name for name, st in ordered if st['PTS'] == top_score]
    if len(leaders) == 1:
        return f"⚡ {leaders[0]} лидирует и уже чует запах победы за {prize}!"
    elif len(leaders) == 2:
        return f"🤝 {leaders[0]} и {leaders[1]} делят лидерство! Может, {prize} будет на двоих?"
    else:
        return f"🔥 Борьба за {prize} накаляется!"

# -------------------------
# UI кнопки
# -------------------------
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🆕 Новый турнир", callback_data="new_tournament")],
        [InlineKeyboardButton("👥 Добавить игрока", callback_data="add_player"),
         InlineKeyboardButton("👥+ Добавить списком", callback_data="add_players_list")],
        [InlineKeyboardButton("⚽ Назначить клубы", callback_data="assign_clubs_menu")],
        [InlineKeyboardButton("📅 Генерировать расписание", callback_data="generate_schedule")],
        [InlineKeyboardButton("📋 Расписание", callback_data="show_schedule"),
         InlineKeyboardButton("⚽ Записать результат", callback_data="record_result")],
        [InlineKeyboardButton("📊 Таблица", callback_data="show_table")],
        [InlineKeyboardButton("🏆 Завершить турнир", callback_data="end_tournament")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_players_keyboard(tournament_id: int):
    """Клавиатура для выбора игрока для назначения клуба"""
    keyboard = []
    players_without_clubs = get_players_without_clubs(tournament_id)
    
    # Разбиваем на строки по 2 кнопки
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
    # Разбиваем на строки по 2 кнопки
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
    # Разбиваем на строки по 2 кнопки
    for i in range(0, len(clubs), 2):
        row = []
        for j in range(i, min(i + 2, len(clubs))):
            club = clubs[j]
            row.append(InlineKeyboardButton(club, callback_data=f"assign_club_{country}_{club}"))
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("◀️ Назад к странам", callback_data="select_country")])
    return InlineKeyboardMarkup(keyboard)

def get_matches_keyboard(tournament_id: int, unplayed_only: bool = True):
    """Клавиатура для выбора матча"""
    keyboard = []
    matches = get_schedule(tournament_id, 100)  # Показываем до 100 матчей (все матчи)
    
    if unplayed_only:
        matches = [m for m in matches if not m['played']]
    
    if not matches:
        return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="main_menu")]])
    
    for match in matches:
        status = "⚽" if not match['played'] else "✅"
        hg = match['home_goals'] if match['home_goals'] is not None else "-"
        ag = match['away_goals'] if match['away_goals'] is not None else "-"
        
        match_text = f"{status} {match['home']} vs {match['away']} [{hg}:{ag}]"
        if len(match_text) > 35:  # Обрезаем длинный текст
            home_short = match['home'][:8] if len(match['home']) > 8 else match['home']
            away_short = match['away'][:8] if len(match['away']) > 8 else match['away']
            match_text = f"{status} {home_short} vs {away_short} [{hg}:{ag}]"
        
        keyboard.append([InlineKeyboardButton(match_text, callback_data=f"select_match_{match['id']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_score_keyboard(match_id: int, player_name: str):
    """Клавиатура для выбора количества голов"""
    keyboard = []
    # Добавляем кнопки с числами голов от 0 до 10
    for i in range(0, 11, 5):  # Разбиваем по 5 кнопок в ряд
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

# -------------------------
# Telegram команды и обработчики
# -------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Добро пожаловать в Tournament Manager!\n\n"
        "Управляйте турниром с помощью кнопок ниже:",
        reply_markup=get_main_menu_keyboard()
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Меню управления турниром:",
        reply_markup=get_main_menu_keyboard()
    )

# Обработчик кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    
    if data == "main_menu":
        await query.edit_message_text(
            "⚽ Меню управления турниром:",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif data == "new_tournament":
        await query.edit_message_text("Введите название турнира:")
        context.user_data['stage'] = 'tournament_name'
    
    elif data == "add_players_list":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира. Создайте новый турнир.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        await query.edit_message_text("Введите имена игроков через запятую:\nПример: Амир, Диас, Влад")
        context.user_data['stage'] = 'add_players_list'
    
    elif data == "record_result":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        await query.edit_message_text(
            "⚽ Выберите матч для записи результата:\n\n"
            "⚽ - не сыгран, ✅ - завершен",
            reply_markup=get_matches_keyboard(t['id'], unplayed_only=True)
        )
    
    elif data.startswith("select_match_"):
        match_id = int(data[13:])  # убираем "select_match_"
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        match = get_match_by_id(t['id'], match_id)
        if not match:
            await query.edit_message_text(
                "❌ Матч не найден.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        context.user_data['selected_match_id'] = match_id
        context.user_data['selected_match'] = match
        context.user_data['match_scores'] = {}
        
        await query.edit_message_text(
            f"⚽ Матч: {match['home']} vs {match['away']}\n\n"
            f"Сколько голов забил {match['home']}?",
            reply_markup=get_score_keyboard(match_id, match['home'])
        )
    
    elif data.startswith("score_"):
        parts = data[6:].split("_", 3)  # убираем "score_" и разделяем
        match_id = int(parts[0])
        player_name = parts[1]
        goals = int(parts[2])
        
        match = context.user_data.get('selected_match')
        if not match:
            await query.edit_message_text(
                "❌ Ошибка: матч не выбран.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Сохраняем количество голов для игрока
        if 'match_scores' not in context.user_data:
            context.user_data['match_scores'] = {}
        context.user_data['match_scores'][player_name] = goals
        
        # Проверяем, нужно ли спросить про второго игрока
        if len(context.user_data['match_scores']) == 1:
            # Спрашиваем про второго игрока
            other_player = match['away'] if player_name == match['home'] else match['home']
            await query.edit_message_text(
                f"⚽ Матч: {match['home']} vs {match['away']}\n"
                f"✅ {player_name}: {goals} голов\n\n"
                f"Сколько голов забил {other_player}?",
                reply_markup=get_score_keyboard(match_id, other_player)
            )
        else:
            # У нас есть результат для обоих игроков
            home_goals = context.user_data['match_scores'].get(match['home'], 0)
            away_goals = context.user_data['match_scores'].get(match['away'], 0)
            
            t = get_active_tournament(chat_id)
            if t:
                record_result(t['id'], match_id, home_goals, away_goals)
                
                # Очищаем данные
                context.user_data.pop('selected_match_id', None)
                context.user_data.pop('selected_match', None)
                context.user_data.pop('match_scores', None)
                
                # Показываем обновленную таблицу
                ordered = get_standings(t['id'])
                prize = get_active_tournament_prize(t['id'])
                msg = format_table(t['id'], ordered)
                fun = get_funny_message(ordered, prize)
                
                result_text = (
                    f"✅ Результат записан!\n"
                    f"⚽ {match['home']} {home_goals}:{away_goals} {match['away']}\n\n"
                    f"{msg}"
                )
                
                await query.edit_message_text(
                    result_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_main_menu_keyboard()
                )
                
                if fun:
                    await query.message.reply_text(fun)
    
    elif data == "add_player":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира. Создайте новый турнир.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        await query.edit_message_text("Введите имя игрока:")
        context.user_data['stage'] = 'add_player_name'
    
    elif data == "assign_clubs_menu":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        players_without_clubs = get_players_without_clubs(t['id'])
        if not players_without_clubs:
            await query.edit_message_text(
                "✅ Всем игрокам уже назначены клубы!",
                reply_markup=get_main_menu_keyboard()
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
                reply_markup=get_main_menu_keyboard()
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
        country = data[8:]  # убираем "country_"
        player_name = context.user_data.get('selected_player_name', 'игрок')
        context.user_data['selected_country'] = country
        
        await query.edit_message_text(
            f"👤 Игрок: {player_name}\n"
            f"🌍 Страна: {get_country_flag(country)} {country}\n\n"
            f"⚽ Выберите клуб:",
            reply_markup=get_clubs_keyboard(country, player_name)
        )
    
    elif data.startswith("assign_club_"):
        parts = data[12:].split("_", 1)  # убираем "assign_club_" и разделяем
        country = parts[0]
        club = parts[1]
        
        player_id = context.user_data.get('selected_player_id')
        player_name = context.user_data.get('selected_player_name')
        
        if not player_id or not player_name:
            await query.edit_message_text(
                "❌ Ошибка: игрок не выбран.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
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
                reply_markup=get_main_menu_keyboard()
            )
    
    elif data == "assign_random":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        assign_random_clubs(t['id'])
        await query.edit_message_text(
            "🎲 Клубы назначены случайно!",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif data == "generate_schedule":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        generate_schedule(t['id'], t['rounds'])
        await query.edit_message_text(
            "📅 Расписание сгенерировано!",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif data == "show_schedule":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        sched = get_schedule(t['id'])
        if not sched:
            await query.edit_message_text(
                "📋 Нет матчей. Сгенерируйте расписание.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        lines = ["📅 РАСПИСАНИЕ МАТЧЕЙ:\n"]
        for m in sched:
            status = "✅" if m['played'] else "⏳"
            hg = m['home_goals'] if m['home_goals'] is not None else "-"
            ag = m['away_goals'] if m['away_goals'] is not None else "-"
            lines.append(f"{status} {m['id']}: {m['home']} vs {m['away']} [{hg}:{ag}]")
        
        message_text = "\n".join(lines)
        await query.edit_message_text(message_text, reply_markup=get_main_menu_keyboard())
    
    elif data == "show_table":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        ordered = get_standings(t['id'])
        msg = format_table(t['id'], ordered)
        await query.edit_message_text(
            f"📊 ТУРНИРНАЯ ТАБЛИЦА:\n\n{msg}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard()
        )
    
    elif data == "end_tournament":
        t = get_active_tournament(chat_id)
        if not t:
            await query.edit_message_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        ordered = get_standings(t['id'])
        end_tournament(t['id'])
        winner = ordered[0][0] if ordered else "никто"
        prize = get_active_tournament_prize(t['id'])
        msg = format_table(t['id'], ordered)
        await query.edit_message_text(
            f"🏆 Турнир '{t['name']}' окончен!\n"
            f"Победитель — {winner}! {prize} достается ему!\n\n{msg}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu_keyboard()
        )

# Обработчик текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'stage' not in context.user_data:
        return

    stage = context.user_data['stage']
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if stage == 'tournament_name':
        context.user_data['new_tournament'] = {'name': text}
        context.user_data['stage'] = 'tournament_rounds'
        await update.message.reply_text("Сколько кругов? (по умолчанию 2):")
    
    elif stage == 'tournament_rounds':
        rounds = int(text) if text.isdigit() else 2
        context.user_data['new_tournament']['rounds'] = rounds
        context.user_data['stage'] = 'tournament_prize'
        await update.message.reply_text("Какой приз?")
    
    elif stage == 'tournament_prize':
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
            reply_markup=get_main_menu_keyboard()
        )
    
    elif stage == 'add_player_name':
        t = get_active_tournament(chat_id)
        if not t:
            await update.message.reply_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        add_player(t['id'], text)
        context.user_data['stage'] = None
        
        await update.message.reply_text(
            f"✅ Игрок {text} добавлен в турнир!",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif stage == 'add_players_list':
        t = get_active_tournament(chat_id)
        if not t:
            await update.message.reply_text(
                "❌ Нет активного турнира.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Разделяем имена по запятой и очищаем от пробелов
        player_names = [name.strip() for name in text.split(',') if name.strip()]
        
        if not player_names:
            await update.message.reply_text(
                "❌ Не найдено имен игроков. Попробуйте еще раз.\n"
                "Пример: Амир, Диас, Влад",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        # Добавляем всех игроков
        added_count = 0
        for name in player_names:
            if len(name) > 0 and len(name) <= 50:  # Проверяем длину имени
                add_player(t['id'], name)
                added_count += 1
        
        context.user_data['stage'] = None
        
        await update.message.reply_text(
            f"✅ Добавлено игроков: {added_count}\n"
            f"👥 Список: {', '.join(player_names[:10])}{'...' if len(player_names) > 10 else ''}",
            reply_markup=get_main_menu_keyboard()
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
        
        ordered = get_standings(t['id'])
        prize = get_active_tournament_prize(t['id'])
        msg = format_table(t['id'], ordered)
        fun = get_funny_message(ordered, prize)
        
        await update.message.reply_text(
            f"✅ Результат записан!\n\n{msg}",
            parse_mode=ParseMode.MARKDOWN
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