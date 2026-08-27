import os
import sqlite3
import hashlib
from datetime import datetime, date

import telebot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN تنظیم نشده است.")

bot = telebot.TeleBot(TOKEN)

DB_FILE = "bot.db"
DAILY_LIMIT = 3


# =========================
# DATABASE
# =========================

def get_db():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            points INTEGER NOT NULL DEFAULT 0,
            daily_count INTEGER NOT NULL DEFAULT 0,
            daily_date TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# USER
# =========================

def register_user(user):
    today = str(date.today())

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO users
        (user_id, username, first_name, points, daily_count, daily_date)
        VALUES (?, ?, ?, 0, 0, ?)
    """, (
        user.id,
        user.username,
        user.first_name,
        today
    ))

    cur.execute("""
        UPDATE users
        SET username = ?, first_name = ?
        WHERE user_id = ?
    """, (
        user.username,
        user.first_name,
        user.id
    ))

    conn.commit()
    conn.close()


def reset_daily(user_id):
    today = str(date.today())

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT daily_date
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    result = cur.fetchone()

    if result and result[0] != today:
        cur.execute("""
            UPDATE users
            SET daily_count = 0,
                daily_date = ?
            WHERE user_id = ?
        """, (today, user_id))

        conn.commit()

    conn.close()


def get_user(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT points, daily_count, daily_date
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    result = cur.fetchone()
    conn.close()

    return result


def add_points(user_id, amount):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET points = points + ?
        WHERE user_id = ?
    """, (amount, user_id))

    conn.commit()
    conn.close()


def add_daily_edit(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET daily_count = daily_count + 1
        WHERE user_id = ?
    """, (user_id,))

    conn.commit()
    conn.close()


# =========================
# LEVEL
# =========================

def get_level(points):

    if points >= 10000:
        return 8, "💎👑"

    if points >= 5000:
        return 7, "👑"

    if points >= 2000:
        return 6, "🔥"

    if points >= 1000:
        return 5, "💎"

    if points >= 500:
        return 4, "🥇"

    if points >= 250:
        return 3, "🥈"

    if points >= 100:
        return 2, "🥉"

    return 1, "🪵"


# =========================
# RANK
# =========================

def get_rank(user_id):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT points
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    result = cur.fetchone()

    if not result:
        conn.close()
        return 0

    points = result[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE points > ?
    """, (points,))

    rank = cur.fetchone()[0] + 1

    conn.close()

    return rank


def top_users():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT username, first_name, points
        FROM users
        ORDER BY points DESC
        LIMIT 10
    """)

    result = cur.fetchall()

    conn.close()

    return result


# =========================
# DUPLICATE
# =========================

def make_hash(file_data):
    return hashlib.sha256(file_data).hexdigest()


def is_duplicate(file_hash):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id
        FROM edits
        WHERE file_hash = ?
    """, (file_hash,))

    result = cur.fetchone()

    conn.close()

    return result is not None


def save_edit(user_id, file_hash, score):

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO edits
        (user_id, file_hash, score, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        file_hash,
        score,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


# =========================
# SCORE
# =========================

def calculate_score(video):

    score = 70

    duration = video.duration or 0

    if duration >= 5:
        score += 5

    if duration >= 10:
        score += 5

    if video.width and video.height:

        if video.width >= 720 and video.height >= 720:
            score += 5

    if video.file_size:

        if video.file_size >= 1_000_000:
            score += 5

    return min(score, 100)


def score_icon(score):

    if score >= 90:
        return "🟢"

    if score >= 80:
        return "🔵"

    if score >= 70:
        return "🟡"

    if score >= 60:
        return "🟠"

    return "🔴"


# =========================
# START
# =========================

@bot.message_handler(commands=["start"])
def start(message):

    register_user(message.from_user)

    bot.reply_to(
        message,
        """
🎬 به مهندس ادیت خوش آمدی!

🎥 ادیتت را بفرست.

🏆 Points
📈 Level
🥇 Ranking
🔁 ضد ادیت تکراری

📅 روزانه ۳ ادیت

دستورات:

/points
/rank
/help
"""
    )


# =========================
# HELP
# =========================

@bot.message_handler(commands=["help"])
def help_command(message):

    bot.reply_to(
        message,
        """
📚 راهنمای مهندس ادیت

🎬 یک ویدیو بفرست تا بررسی شود.

🏆 /points
مشاهده Points و Level

🥇 /rank
مشاهده Top 10

📅 هر کاربر روزانه ۳ ادیت دارد.

🔁 ادیت تکراری دوباره Point نمی‌گیرد.

👥 ربات در گروه هم کار می‌کند.
"""
    )


# =========================
# POINTS
# =========================

@bot.message_handler(commands=["points"])
def points_command(message):

    register_user(message.from_user)
    reset_daily(message.from_user.id)

    user = get_user(message.from_user.id)

    points = user[0]
    daily = user[1]

    level, icon = get_level(points)

    rank = get_rank(message.from_user.id)

    bot.reply_to(
        message,
        f"""
👤 {message.from_user.first_name}

🏆 Points: {points}

{icon} Level: {level}

🥇 Rank: #{rank}

📅 ادیت امروز: {daily}/{DAILY_LIMIT}
"""
    )


# =========================
# RANKING
# =========================

@bot.message_handler(commands=["rank"])
def rank_command(message):

    users = top_users()

    if not users:

        bot.reply_to(
            message,
            "🏆 هنوز کسی Point ندارد."
        )

        return

    text = "🏆 TOP 10 EDITORS\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, user in enumerate(users, start=1):

        username = user[0]
        first_name = user[1]
        points = user[2]

        name = first_name or username or "User"

        level, icon = get_level(points)

        if i <= 3:
            place = medals[i - 1]
        else:
            place = f"{i}."

        text += (
            f"{place} {name}\n"
            f"   {icon} Level {level}\n"
            f"   🏆 {points} Points\n\n"
        )

    bot.reply_to(message, text)


# =========================
# VIDEO
# =========================

@bot.message_handler(content_types=["video"])
def receive_video(message):

    register_user(message.from_user)

    reset_daily(message.from_user.id)

    user = get_user(message.from_user.id)

    points_before = user[0]
    daily = user[1]

    # محدودیت روزانه
    if daily >= DAILY_LIMIT:

        bot.reply_to(
            message,
            """
⛔ سهم امروزت تمام شده.

📅 حداکثر ۳ ادیت در روز داری.

فردا دوباره می‌توانی ادیت بفرستی. 🎬
"""
        )

        return

    processing = bot.reply_to(
        message,
        "⏳ ادیت دریافت شد...\n🔍 در حال بررسی..."
    )

    try:

        # دریافت فایل
        file_info = bot.get_file(
            message.video.file_id
        )

        file_data = bot.download_file(
            file_info.file_path
        )

        # ضد تکرار
        file_hash = make_hash(file_data)

        if is_duplicate(file_hash):

            bot.edit_message_text(
                """
❌ این ادیت قبلاً ثبت شده است.

🔁 ادیت تکراری Point نمی‌گیرد.
""",
                message.chat.id,
                processing.message_id
            )

            return

        # نمره
        score = calculate_score(
            message.video
        )

        # Level قبل
        old_level, _ = get_level(
            points_before
        )

        # ثبت اطلاعات
        add_points(
            message.from_user.id,
            score
        )

        add_daily_edit(
            message.from_user.id
        )

        save_edit(
            message.from_user.id,
            file_hash,
            score
        )

        # اطلاعات جدید
        updated = get_user(
            message.from_user.id
        )

        new_points = updated[0]
        new_daily = updated[1]

        new_level, level_icon = get_level(
            new_points
        )

        rank = get_rank(
            message.from_user.id
        )

        score_color = score_icon(score)

        remaining = DAILY_LIMIT - new_daily

        level_up = ""

        if new_level > old_level:

            level_up = f"""
🎉 LEVEL UP!

{level_icon} Level {new_level}
"""

        text = f"""
🎬 نتیجه ادیت

{score_color} نمره: {score}/100

━━━━━━━━━━━━

🏆 +{score} Points

💰 مجموع: {new_points} Points

{level_icon} Level: {new_level}

🥇 Rank: #{rank}

📅 ادیت باقی‌مانده امروز: {remaining}

{level_up}
"""

        bot.edit_message_text(
            text,
            message.chat.id,
            processing.message_id
        )

    except Exception as error:

        print("ERROR:", error)

        bot.edit_message_text(
            """
❌ هنگام بررسی ادیت مشکلی پیش آمد.

دوباره امتحان کن.
""",
            message.chat.id,
            processing.message_id
        )


# =========================
# RUN
# =========================

print("🎬 Mohandes Edit Bot started.")

bot.infinity_polling(
    skip_pending=True
)
