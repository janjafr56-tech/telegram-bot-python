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

    if points >= 50000:
        return 8, "💎👑"

    if points >= 25000:
        return 7, "👑"

    if points >= 12000:
        return 6, "🔥"

    if points >= 6000:
        return 5, "💎"

    if points >= 3000:
        return 4, "🥇"

    if points >= 1500:
        return 3, "🥈"

    if points >= 500:
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


def get_rank_badge(rank):

    if rank == 1:
        return "🥇"

    if rank == 2:
        return "🥈"

    if rank == 3:
        return "🥉"

    if rank <= 10:
        return "🔵"

    return "⚪"


def get_rank_name(rank):

    if rank == 1:
        return "رنگ 1 - طلایی"

    if rank == 2:
        return "رنگ 2 - نقره‌ای"

    if rank == 3:
        return "رنگ 3 - برنزی"

    if rank <= 10:
        return f"رنگ {rank} - آبی"

    return f"رنگ {rank}"


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
# STRICT SCORE 1 - 10
# =========================

def calculate_score(video):

    duration = video.duration or 0
    width = video.width or 0
    height = video.height or 0
    file_size = video.file_size or 0

    # شروع خیلی پایین و سخت‌گیرانه
    score = 1

    # -------------------------
    # RESOLUTION
    # -------------------------

    if width >= 1920 and height >= 1080:
        score += 3

    elif width >= 1280 and height >= 720:
        score += 2

    elif width >= 720 and height >= 480:
        score += 1

    else:
        score -= 1


    # -------------------------
    # DURATION
    # -------------------------

    if 5 <= duration <= 60:
        score += 1

    elif 3 <= duration < 5:
        score += 0

    elif duration > 60:
        score -= 1

    else:
        score -= 1


    # -------------------------
    # FILE SIZE
    # -------------------------

    if file_size >= 5_000_000:
        score += 1

    elif file_size >= 1_000_000:
        score += 0

    else:
        score -= 1


    # -------------------------
    # ASPECT RATIO
    # -------------------------

    if width > 0 and height > 0:

        ratio = width / height

        if 0.5 <= ratio <= 2.2:
            score += 1
        else:
            score -= 1


    # -------------------------
    # FINAL
    # -------------------------

    return max(1, min(score, 10))


# =========================
# SCORE -> POINTS
# =========================

def score_to_points(score):

    points_table = {
        1: 1,
        2: 8,
        3: 18,
        4: 30,
        5: 42,
        6: 55,
        7: 68,
        8: 80,
        9: 92,
        10: 100
    }

    return points_table.get(score, 1)


# =========================
# SCORE BADGE
# =========================

def score_badge(score):

    if score == 10:
        return "💎"

    if score == 9:
        return "🟣"

    if score >= 7:
        return "🔵"

    if score >= 5:
        return "🟡"

    if score >= 3:
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

🎯 نمره: 1 تا 10
🏆 Points: 1 تا 100
🎨 رنگ/رتبه: بر اساس Ranking

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

🎯 نمره ادیت: 1 تا 10
🏆 Points: 1 تا 100

🎨 رنگ/رتبه بر اساس جایگاه Ranking است.

🏆 /points
مشاهده Points و Level و رنگ

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

    level, level_icon = get_level(points)

    rank = get_rank(message.from_user.id)

    rank_badge = get_rank_badge(rank)
    rank_name = get_rank_name(rank)

    bot.reply_to(
        message,
        f"""
👤 {message.from_user.first_name}

🏆 Points: {points}

{level_icon} Level: {level}

{rank_badge} Rank: #{rank}

🎨 {rank_name}

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

        level, level_icon = get_level(points)

        if i <= 3:
            place = medals[i - 1]
        else:
            place = f"{i}."

        rank_badge = get_rank_badge(i)

        text += (
            f"{place} {name}\n"
            f"   {rank_badge} رنگ {i}\n"
            f"   {level_icon} Level {level}\n"
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

    # -------------------------
    # DAILY LIMIT
    # -------------------------

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
        "⏳ ادیت دریافت شد...\n🔍 بررسی سخت‌گیرانه در حال انجام است..."
    )


    try:

        # -------------------------
        # DOWNLOAD
        # -------------------------

        file_info = bot.get_file(
            message.video.file_id
        )

        file_data = bot.download_file(
            file_info.file_path
        )


        # -------------------------
        # DUPLICATE
        # -------------------------

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


        # -------------------------
        # SCORE
        # -------------------------

        score = calculate_score(
            message.video
        )


        # -------------------------
        # POINTS
        # -------------------------

        earned_points = score_to_points(
            score
        )


        # -------------------------
        # OLD LEVEL
        # -------------------------

        old_level, _ = get_level(
            points_before
        )


        # -------------------------
        # SAVE
        # -------------------------

        add_points(
            message.from_user.id,
            earned_points
        )

        add_daily_edit(
            message.from_user.id
        )

        save_edit(
            message.from_user.id,
            file_hash,
            score
        )


        # -------------------------
        # NEW DATA
        # -------------------------

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

        rank_badge = get_rank_badge(rank)
        rank_name = get_rank_name(rank)


        # -------------------------
        # SCORE DISPLAY
        # -------------------------

        score_badge_icon = score_badge(
            score
        )

        remaining = DAILY_LIMIT - new_daily


        # -------------------------
        # LEVEL UP
        # -------------------------

        level_up = ""

        if new_level > old_level:

            level_up = f"""
🎉 LEVEL UP!

{level_icon} Level {new_level}!
"""


        # -------------------------
        # RESULT
        # -------------------------

        text = f"""
🎬 نتیجه بررسی ادیت

{score_badge_icon} نمره: {score}/10

━━━━━━━━━━━━

🏆 +{earned_points} Points

💰 مجموع: {new_points} Points

{level_icon} Level: {new_level}

{rank_badge} Rank: #{rank}

🎨 {rank_name}

📅 ادیت باقی‌مانده امروز: {remaining}

━━━━━━━━━━━━

⚠️ سیستم فعلاً سخت‌گیرانه است.
🤖 تحلیل واقعی تصویر و آهنگ در مرحله AI اضافه می‌شود.

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

لطفاً دوباره امتحان کن.
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
