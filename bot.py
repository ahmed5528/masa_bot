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
import json

# Load environment variables from .env file
load_dotenv()

# تكوين الأساسيات
BOT_TOKEN = os.getenv('BOT_TOKEN')        # Get from environment
CHANNEL_ID = int(os.getenv('CHANNEL_ID', -1002248454067)) # Convert to integer
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '1992092583').split(',')] # Convert string list to int list
GOOGLE_FORM_LINK = os.getenv('GOOGLE_FORM_LINK', "https://forms.gle/fb8qA7K4EEWyPqrX9")
DATABASE_NAME = os.getenv('DATABASE_NAME', 'bot_database.db')

# تمكين التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
def init_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        serial TEXT UNIQUE NOT NULL,
        joined_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create messages table for tracking conversations
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        message_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        admin_id INTEGER,
        message_text TEXT NOT NULL,
        direction TEXT NOT NULL, -- 'user_to_admin' or 'admin_to_user'
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Database utility functions
def get_user_by_id(user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'name': user[1],
            'serial': user[2],
            'joined_date': user[3]
        }
    return None

def get_user_by_serial(serial):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE serial = ?', (serial,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'name': user[1],
            'serial': user[2],
            'joined_date': user[3]
        }
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

# Initialize database
init_database()

# دالة لإنشاء رقم تسلسلي فريد
def generate_serial_number():
    prefix = "KCM-"
    characters = string.ascii_uppercase + string.digits
    serial = ''.join(random.choice(characters) for _ in range(8))
    return prefix + serial

# دالة للتحقق من عضوية المستخدم في المجموعة الخاصة
async def is_member(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Forbidden:
        logger.error("البوت ليس مسؤولاً في المجموعة المحددة أو ليس لديه صلاحية الوصول")
        return False
    except BadRequest as e:
        if "Chat not found" in str(e):
            logger.error("لم يتم العثور على المجموعة. تأكد من معرف المجموعة وإضافة البوت كمسؤول")
        else:
            logger.error(f"خطأ في التحقق من العضوية: {e}")
        return False
    except Exception as e:
        logger.error(f"خطأ غير متوقع في التحقق من العضوية: {e}")
        return False

# دالة للحصول على رابط الدعوة للمجموعة
async def get_invite_link(context: ContextTypes.DEFAULT_TYPE):
    try:
        # محاولة إنشاء رابط دعوة إذا كان البوت مسؤولاً
        chat = await context.bot.get_chat(CHANNEL_ID)
        if chat.invite_link:
            return chat.invite_link
        else:
            # إذا لم يكن هناك رابط دعوة، حاول إنشاء واحد
            invite_link = await context.bot.create_chat_invite_link(
                CHANNEL_ID, 
                creates_join_request=True
            )
            return invite_link.invite_link
    except Exception as e:
        logger.error(f"فشل في الحصول على رابط الدعوة: {e}")
        return None

# أمر البدء /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # التحقق من العضوية
    is_member_result = await is_member(user_id, context)
    
    if not is_member_result:
        # الحصول على رابط الدعوة
        invite_link = await get_invite_link(context)
        
        if invite_link:
            keyboard = [
                [InlineKeyboardButton("انضم إلى المجموعة", url=invite_link)],
                [InlineKeyboardButton("تحقق من العضوية", callback_data="check_membership")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("تحقق من العضوية", callback_data="check_membership")]
            ]
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"مرحباً {user_name}!\n\n"
            "للوصول إلى خدمات الدعم، يجب أن تكون عضوًا في مجموعة الكلية.\n"
            "انضم إلى المجموعة أولاً ثم اضغط على 'تحقق من العضوية'.",
            reply_markup=reply_markup
        )
        return
    
    # إذا كان العضو مسجلاً مسبقاً
    user = get_user_by_id(user_id)
    if user:
        keyboard = [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"مرحباً بعودتك {user_name}!\n"
            f"رقمك التسلسلي: {user['serial']}\n\n"
            "يمكنك استخدام هذا الرقم في نموذج جوجل عندما تطلب المساعدة.",
            reply_markup=reply_markup
        )
        return
    
    # إنشاء رقم تسلسلي جديد للمستخدم
    serial = generate_serial_number()
    success = create_user(user_id, user_name, serial)
    
    if not success:
        # Try again if serial collision occurs
        serial = generate_serial_number()
        success = create_user(user_id, user_name, serial)
    
    if success:
        keyboard = [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"مرحباً {user_name}!\n\n"
            f"تم التحقق من عضويتك بنجاح.\n"
            f"رقمك التسلسلي هو: {serial}\n\n"
            "سيتم استخدام هذا الرقم للحفاظ على خصوصيتك أثناء عملية الدعم.\n"
            "احفظ هذا الرقم جيداً وستحتاجه عند ملء النموذج.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "حدث خطأ أثناء التسجيل. يرجى المحاولة مرة أخرى لاحقاً."
        )

# معالجة ضغط الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "check_membership":
        is_member_result = await is_member(user_id, context)
        
        if is_member_result:
            user = get_user_by_id(user_id)
            if not user:
                # إنشاء رقم تسلسلي جديد للمستخدم
                serial = generate_serial_number()
                user_name = query.from_user.first_name
                
                success = create_user(user_id, user_name, serial)
                if not success:
                    # Try again if serial collision occurs
                    serial = generate_serial_number()
                    success = create_user(user_id, user_name, serial)
                
                if success:
                    keyboard = [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"تم التحقق من عضويتك بنجاح!\n\n"
                        f"رقمك التسلسلي هو: {serial}\n\n"
                        "سيتم استخدام هذا الرقم للحفاظ على خصوصيتك أثناء عملية الدعم.\n"
                        "احفظ هذا الرقم جيداً وستحتاجه عند ملء النموذج.",
                        reply_markup=reply_markup
                    )
                else:
                    await query.edit_message_text(
                        "حدث خطأ أثناء التسجيل. يرجى المحاولة مرة أخرى لاحقاً."
                    )
            else:
                keyboard = [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"تم التحقق من عضويتك بنجاح!\n\n"
                    f"رقمك التسلسلي هو: {user['serial']}\n\n"
                    "يمكنك استخدام هذا الرقم في نموذج جوجل عندما تطلب المساعدة.",
                    reply_markup=reply_markup
                )
        else:
            # الحصول على رابط الدعوة
            invite_link = await get_invite_link(context)
            
            if invite_link:
                keyboard = [
                    [InlineKeyboardButton("انضم إلى المجموعة", url=invite_link)],
                    [InlineKeyboardButton("تحقق من العضوية", callback_data="check_membership")]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("تحقق من العضوية", callback_data="check_membership")]
                ]
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "لم يتم التحقق من عضويتك بعد.\n"
                "يرجى الانضمام إلى المجموعة أولاً ثم الضغط على 'تحقق من العضوية' مرة أخرى.",
                reply_markup=reply_markup
            )
    
    elif query.data == "get_form":
        user = get_user_by_id(user_id)
        if user:
            await query.edit_message_text(
                f"لطلب الدعم، يرجى ملء النموذج التالي:\n\n"
                f"رابط النموذج: {GOOGLE_FORM_LINK}\n\n"
                f"**تأكد من استخدام الرقم التسلسلي التالي في مكان الاسم:**\n"
                f"`{user['serial']}`\n\n"
                "بعد تقديم النموذج، سيتواصل معك فريق الدعم خلال 24-48 ساعة.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "عذراً، لم يتم العثور على بياناتك. يرجى البدء مرة أخرى باستخدام /start"
            )

# أمر للمسؤولين للرد على المستخدمين
async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("عذراً，你没有权限执行此操作。")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "استخدام خاطئ! يرجى استخدام الصيغة:\n"
            "/reply <الرقم_التسلسلي> <الرسالة>"
        )
        return
    
    serial = context.args[0]
    message = " ".join(context.args[1:])
    
    user = get_user_by_serial(serial)
    if not user:
        await update.message.reply_text("الرقم التسلسلي غير موجود!")
        return
    
    target_user_id = user['user_id']
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📩 لديك رسالة من فريق الدعم:\n\n{message}\n\n"
                 "يمكنك الرد مباشرة على هذه الرسالة للتواصل مع الفريق."
        )
        # Save the message to database
        add_message(target_user_id, user_id, message, 'admin_to_user')
        await update.message.reply_text("تم إرسال الرسالة بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"فشل في إرسال الرسالة: {e}")

# معالجة الرسائل العادية (للرد من المستخدم إلى المسؤول)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    user = get_user_by_id(user_id)
    if not user:
        await update.message.reply_text("يرجى البدء أولاً باستخدام /start")
        return
    
    # إذا كان المستخدم يرد على رسالة من البوت
    if update.message.reply_to_message and "لديك رسالة من فريق الدعم" in update.message.reply_to_message.text:
        user_message = update.message.text
        
        # Save the message to database
        add_message(user_id, None, user_message, 'user_to_admin')
        
        # إرسال الرسالة إلى جميع المسؤولين
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 رد من المستخدم:\n"
                         f"الرقم التسلسلي: {user['serial']}\n"
                         f"الاسم: {user['name']}\n\n"
                         f"الرسالة: {user_message}"
                )
            except Exception as e:
                logger.error(f"فشل في إرسال الرسالة إلى المسؤول {admin_id}: {e}")
        
        await update.message.reply_text("تم إرسال رسالتك إلى فريق الدعم. سنرد عليك قريباً.")

# أمر لرؤية سجل المحادثات (للمسؤولين)
async def view_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("عذراً，你没有权限执行此操作。")
        return
    
    if not context.args:
        await update.message.reply_text(
            "استخدام خاطئ! يرجى استخدام الصيغة:\n"
            "/history <الرقم_التسلسلي>"
        )
        return
    
    serial = context.args[0]
    user = get_user_by_serial(serial)
    
    if not user:
        await update.message.reply_text("الرقم التسلسلي غير موجود!")
        return
    
    messages = get_user_messages(user['user_id'])
    
    if not messages:
        await update.message.reply_text(f"لا توجد رسائل مسجلة للمستخدم {serial}")
        return
    
    history_text = f"📋 سجل المحادثة للمستخدم {serial} ({user['name']}):\n\n"
    
    for msg in reversed(messages):  # Show in chronological order
        timestamp = datetime.strptime(msg[5], "%Y-%m-%d %H:%M:%S.%f").strftime("%Y-%m-%d %H:%M")
        direction = "👤 → 🛠️" if msg[4] == 'user_to_admin' else "🛠️ → 👤"
        history_text += f"{timestamp} {direction}:\n{msg[3]}\n\n"
    
    await update.message.reply_text(history_text)

# أمر المساعدة
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً! أنا بوت الدعم النفسي لمجتمع الكلية.\n\n"
        "الأوامر المتاحة:\n"
        "/start - بدء استخدام البوت والتحقق من العضوية\n"
        "/help - عرض هذه الرسالة\n\n"
        "للمسؤولين فقط:\n"
        "/reply <الرقم_التسلسلي> <الرسالة> - إرسال رسالة إلى مستخدم\n"
        "/history <الرقم_التسلسلي> - عرض سجل المحادثة مع مستخدم"
    )

# دالة رئيسية
def main():
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reply", reply_to_user))
    application.add_handler(CommandHandler("history", view_chat_history))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    print("البوت يعمل...")
    application.run_polling()

if __name__ == "__main__":
    main()
