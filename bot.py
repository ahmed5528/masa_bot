import os
from dotenv import load_dotenv
import logging
import random
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    ContextTypes, 
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from telegram.error import Forbidden, BadRequest
import sqlite3

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', -1002248454067))
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '1992092583').split(',')]
GOOGLE_FORM_LINK = os.getenv('GOOGLE_FORM_LINK', "https://forms.gle/fb8qA7K4EEWyPqrX9")
DATABASE_NAME = os.getenv('DATABASE_NAME', 'bot_database.db')

# 🚦 Make logging lightweight (save CPU/disk)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.WARNING
)
logger = logging.getLogger(__name__)

# Database setup
def init_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        serial TEXT UNIQUE NOT NULL,
        joined_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        admin_id INTEGER,
        message_text TEXT NOT NULL,
        direction TEXT NOT NULL,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

def get_user_by_id(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {'user_id': user[0], 'name': user[1], 'serial': user[2], 'joined_date': user[3]}
    return None

def get_user_by_serial(serial):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE serial = ?', (serial,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {'user_id': user[0], 'name': user[1], 'serial': user[2], 'joined_date': user[3]}
    return None

def create_user(user_id, name, serial):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (user_id, name, serial, joined_date) VALUES (?, ?, ?, ?)',
            (user_id, name, serial, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def add_message(user_id, admin_id, message_text, direction):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO messages (user_id, admin_id, message_text, direction) VALUES (?, ?, ?, ?)',
        (user_id, admin_id, message_text, direction)
    )
    conn.commit()
    conn.close()

def get_user_messages(user_id, limit=10):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?',
        (user_id, limit)
    )
    messages = cursor.fetchall()
    conn.close()
    return messages

init_database()

def generate_serial_number():
    prefix = "KCM-"
    characters = string.ascii_uppercase + string.digits
    return prefix + ''.join(random.choice(characters) for _ in range(8))

# -------- BOT HANDLERS --------

async def is_member(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def get_invite_link(context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = await context.bot.get_chat(CHANNEL_ID)
        if chat.invite_link:
            return chat.invite_link
        invite_link = await context.bot.create_chat_invite_link(
            CHANNEL_ID, creates_join_request=True
        )
        return invite_link.invite_link
    except Exception:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    is_member_result = await is_member(user_id, context)

    if not is_member_result:
        invite_link = await get_invite_link(context)
        keyboard = [[InlineKeyboardButton("تحقق من العضوية", callback_data="check_membership")]]
        if invite_link:
            keyboard.insert(0, [InlineKeyboardButton("انضم إلى المجموعة", url=invite_link)])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"مرحباً {user_name}!\n\n"
            "يجب أن تكون عضوًا في مجموعة الكلية للوصول إلى خدمات الدعم.",
            reply_markup=reply_markup
        )
        return

    user = get_user_by_id(user_id)
    if user:
        keyboard = [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
        await update.message.reply_text(
            f"مرحباً بعودتك {user_name}!\n"
            f"رقمك التسلسلي: {user['serial']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    serial = generate_serial_number()
    if create_user(user_id, user_name, serial):
        keyboard = [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
        await update.message.reply_text(
            f"تم التحقق من عضويتك!\n"
            f"رقمك التسلسلي: {serial}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_membership":
        if await is_member(user_id, context):
            user = get_user_by_id(user_id)
            if not user:
                serial = generate_serial_number()
                create_user(user_id, query.from_user.first_name, serial)
                user = get_user_by_id(user_id)
            await query.edit_message_text(
                f"تم التحقق!\nرقمك التسلسلي: {user['serial']}",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
                )
            )
        else:
            invite_link = await get_invite_link(context)
            keyboard = [[InlineKeyboardButton("تحقق من العضوية", callback_data="check_membership")]]
            if invite_link:
                keyboard.insert(0, [InlineKeyboardButton("انضم إلى المجموعة", url=invite_link)])
            await query.edit_message_text(
                "لم يتم التحقق من عضويتك بعد.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif query.data == "get_form":
        user = get_user_by_id(user_id)
        if user:
            await query.edit_message_text(
                f"رابط النموذج: {GOOGLE_FORM_LINK}\n"
                f"استخدم الرقم التسلسلي: `{user['serial']}`",
                parse_mode="Markdown"
            )

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("الاستخدام: /reply <serial> <message>")
        return
    serial, message = context.args[0], " ".join(context.args[1:])
    user = get_user_by_serial(serial)
    if not user:
        await update.message.reply_text("الرقم غير موجود!")
        return
    await context.bot.send_message(chat_id=user['user_id'], text=f"📩 من الدعم:\n{message}")
    add_message(user['user_id'], update.effective_user.id, message, 'admin_to_user')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user_by_id(update.effective_user.id)
    if not user:
        return
    if update.message.reply_to_message and "من الدعم" in update.message.reply_to_message.text:
        user_message = update.message.text
        add_message(user['user_id'], None, user_message, 'user_to_admin')
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"📩 رد من {user['name']} ({user['serial']}):\n{user_message}"
            )

async def view_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /history <serial>")
        return
    user = get_user_by_serial(context.args[0])
    if not user:
        await update.message.reply_text("الرقم غير موجود!")
        return
    messages = get_user_messages(user['user_id'])
    if not messages:
        await update.message.reply_text("لا توجد رسائل")
        return
    history_text = f"📋 سجل {user['serial']} ({user['name']}):\n\n"
    for msg in reversed(messages):
        history_text += f"{msg[5]} {'👤→🛠️' if msg[4]=='user_to_admin' else '🛠️→👤'}: {msg[3]}\n\n"
    await update.message.reply_text(history_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - بدء\n/help - مساعدة\n"
        "للمسؤولين:\n/reply <serial> <msg>\n/history <serial>"
    )

# -------- MAIN APP (Webhook instead of Polling) --------
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reply", reply_to_user))
    application.add_handler(CommandHandler("history", view_chat_history))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running with Webhooks...")
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=BOT_TOKEN,
        webhook_url=f"https://{os.getenv('RAILWAY_STATIC_URL')}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
