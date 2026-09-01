import os
import sqlite3
import hashlib
import base64
import json
import tempfile
from datetime import datetime, date

import cv2
import telebot
from openai import OpenAI


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN تنظیم نشده است.")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY تنظیم نشده است.")

bot = telebot.TeleBot(TOKEN)
ai = OpenAI(api_key=OPENAI_API_KEY)

DB_FILE = "bot.db"
DAILY_LIMIT = 3
AI_MODEL = "gpt-5.6-luna"


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
# USERS
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

    cur.execute(
        "SELECT daily_date FROM users WHERE user_id = ?",
        (user_id,)
    )

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

    cur.execute(
        "SELECT points FROM users WHERE user_id = ?",
        (user_id,)
    )

    result = cur.fetchone()

    if not result:
        conn.close()
        return 0

    points = result[0]

    cur.execute(
        "SELECT COUNT(*) FROM users WHERE points > ?",
        (points,)
    )

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

    cur.execute(
        "SELECT id FROM edits WHERE file_hash = ?",
        (file_hash,)
    )

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
# VIDEO FRAMES
# =========================

def extract_frames(video_path, max_frames=6):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError("ویدیو قابل خواندن نیست.")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total <= 0:
        cap.release()
        raise RuntimeError("فریم ویدیو پیدا نشد.")

    frames = []

    positions = [
        int(i * (total - 1) / (max_frames - 1))
        for i in range(max_frames)
    ]

    for position in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, position)

        ok, frame = cap.read()

        if not ok:
            continue

        height, width = frame.shape[:2]

        if width > 1280:
            scale = 1280 / width
            frame = cv2.resize(
                frame,
                (
                    int(width * scale),
                    int(height * scale)
                )
            )

        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 80]
        )

        if ok:
            frames.append(
                base64.b64encode(
                    encoded.tobytes()
                ).decode("utf-8")
            )

    cap.release()

    return frames


# =========================
# AI
# =========================

def analyze_video_with_ai(video_path):

    frames = extract_frames(video_path)

    if not frames:
        raise RuntimeError("فریم برای تحلیل پیدا نشد.")

    content = [{
        "type": "input_text",
        "text": """
تو یک داور بسیار سخت‌گیر حرفه‌ای ادیت ویدیو هستی.

فریم‌های این ویدیو را بررسی کن.

موارد مهم:

- کیفیت تصویر
- نور و وضوح
- ترکیب‌بندی
- تدوین و کات
- هماهنگی بین فریم‌ها
- خلاقیت
- حرفه‌ای بودن کلی

نمره را الکی بالا نده.

10 فقط برای یک ادیت واقعاً استثنایی است.
9 بسیار سخت باشد.
8 برای ادیت خیلی خوب است.
6 یا 7 برای ادیت متوسط تا خوب است.
5 و پایین‌تر برای ادیت ضعیف‌تر است.

فقط JSON برگردان:

{
  "score": 1,
  "reason": "دلیل کوتاه"
}

score حتماً عدد صحیح بین 1 و 10 باشد.
"""
    }]

    for frame in frames:
        content.append({
            "type": "input_image",
            "image_url": (
                "data:image/jpeg;base64,"
                + frame
            )
        })

    response = ai.responses.create(
        model=AI_MODEL,
        input=[{
            "role": "user",
            "content": content
        }]
    )

    text = response.output_text.strip()

    try:
        data = json.loads(text)

        score = int(data["score"])
        reason = str(data.get("reason", ""))

        score = max(1, min(10, score))

        return score, reason

    except Exception:
        raise RuntimeError(
            "پاسخ AI قابل پردازش نبود."
        )


# =========================
# POINTS
# =========================

def score_to_points(score):
    table = {
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

    return table[score]


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

🤖 AI ادیت را بررسی می‌کند.

🎯 نمره: 1 تا 10
🏆 Points: 1 تا 100
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

🎬 یک ویدیو بفرست.

🤖 AI کیفیت تصویر و تدوین را بررسی می‌کند.

🎯 نمره: 1 تا 10
🏆 Points: 1 تا 100

🏆 /points
🥇 /rank

📅 روزانه ۳ ادیت
🔁 ادیت تکراری Point نمی‌گیرد.
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
# RANK
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

    for i, user in enumerate(users, 1):

        username = user[0]
        first_name = user[1]
        points = user[2]

        name = first_name or username or "User"

        level, icon = get_level(points)

        place = medals[i - 1] if i <= 3 else f"{i}."

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

    if daily >= DAILY_LIMIT:

        bot.reply_to(
            message,
            """
⛔ سهم امروزت تمام شده.

📅 حداکثر ۳ ادیت در روز داری.
"""
        )

        return

    processing = bot.reply_to(
        message,
        """
⏳ ادیت دریافت شد...

🤖 AI در حال بررسی است...
🎥 کیفیت
✂️ تدوین
✨ خلاقیت
"""
    )

    temp_path = None

    try:

        file_info = bot.get_file(
            message.video.file_id
        )

        file_data = bot.download_file(
            file_info.file_path
        )

        file_hash = make_hash(file_data)

        if is_duplicate(file_hash):

            bot.edit_message_text(
                "❌ این ادیت قبلاً ثبت شده است.",
                message.chat.id,
                processing.message_id
            )

            return

        with tempfile.NamedTemporaryFile(
            suffix=".mp4",
            delete=False
        ) as temp:

            temp.write(file_data)
            temp_path = temp.name

        score, reason = analyze_video_with_ai(
            temp_path
        )

        earned = score_to_points(score)

        old_level, _ = get_level(points_before)

        add_points(
            message.from_user.id,
            earned
        )

        add_daily_edit(
            message.from_user.id
        )

        save_edit(
            message.from_user.id,
            file_hash,
            score
        )

        updated = get_user(
            message.from_user.id
        )

        new_points = updated[0]
        new_daily = updated[1]

        new_level, icon = get_level(
            new_points
        )

        rank = get_rank(
            message.from_user.id
        )

        remaining = DAILY_LIMIT - new_daily

        level_up = ""

        if new_level > old_level:
            level_up = (
                f"\n🎉 LEVEL UP!\n"
                f"{icon} Level {new_level}\n"
            )

        bot.edit_message_text(
            f"""
🎬 نتیجه AI

🎯 نمره: {score}/10

🧠 نظر AI:
{reason}

━━━━━━━━━━━━

🏆 +{earned} Points
💰 مجموع: {new_points} Points

{icon} Level: {new_level}

🥇 Rank: #{rank}

📅 باقی‌مانده امروز: {remaining}

{level_up}
""",
            message.chat.id,
            processing.message_id
        )

    except Exception as error:

        print("AI ERROR:", repr(error))

        bot.edit_message_text(
            """
❌ در بررسی AI مشکلی پیش آمد.

دوباره امتحان کن.
""",
            message.chat.id,
            processing.message_id
        )

    finally:

        if temp_path:

            try:
                os.remove(temp_path)
            except Exception:
                pass


# =========================
# RUN
# =========================

print("🎬 Mohandes Edit Bot started.")

bot.infinity_polling(
    skip_pending=True
)
