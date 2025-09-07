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

# Load environment variables from .env file
load_dotenv()

# تكوين الأساسيات
BOT_TOKEN = os.getenv('BOT_TOKEN')        # Get from environment
CHANNEL_ID = int(os.getenv('CHANNEL_ID', -1002248454067)) # Convert to integer
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '1992092583').split(',')] # Convert string list to int list
GOOGLE_FORM_LINK = os.getenv('GOOGLE_FORM_LINK', "https://forms.gle/fb8qA7K4EEWyPqrX9")
# تمكين التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# قاموس لتخزين البيانات (في تطبيق حقيقي، استخدم قاعدة بيانات)
user_data = {}
serial_to_user = {}

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
    if user_id in user_data:
        serial = user_data[user_id]['serial']
        keyboard = [[InlineKeyboardButton("الحصول على النموذج", callback_data="get_form")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"مرحباً بعودتك {user_name}!\n"
            f"رقمك التسلسلي: {serial}\n\n"
            "يمكنك استخدام هذا الرقم في نموذج جوجل عندما تطلب المساعدة.",
            reply_markup=reply_markup
        )
        return
    
    # إنشاء رقم تسلسلي جديد للمستخدم
    serial = generate_serial_number()
    user_data[user_id] = {
        'name': user_name,
        'serial': serial,
        'joined_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    serial_to_user[serial] = user_id
    
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

# معالجة ضغط الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "check_membership":
        is_member_result = await is_member(user_id, context)
        
        if is_member_result:
            # إنشاء رقم تسلسلي جديد للمستخدم
            serial = generate_serial_number()
            user_name = query.from_user.first_name
            
            user_data[user_id] = {
                'name': user_name,
                'serial': serial,
                'joined_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            serial_to_user[serial] = user_id
            
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
        if user_id in user_data:
            serial = user_data[user_id]['serial']
            await query.edit_message_text(
                f"لطلب الدعم، يرجى ملء النموذج التالي:\n\n"
                f"رابط النموذج: {GOOGLE_FORM_LINK}\n\n"
                f"**تأكد من استخدام الرقم التسلسلي التالي في مكان الاسم:**\n"
                f"`{serial}`\n\n"
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
        await update.message.reply_text("عذراً،你没有权限执行此操作。")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "استخدام خاطئ! يرجى استخدام الصيغة:\n"
            "/reply <الرقم_التسلسلي> <الرسالة>"
        )
        return
    
    serial = context.args[0]
    message = " ".join(context.args[1:])
    
    if serial not in serial_to_user:
        await update.message.reply_text("الرقم التسلسلي غير موجود!")
        return
    
    target_user_id = serial_to_user[serial]
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"📩 لديك رسالة من فريق الدعم:\n\n{message}\n\n"
                 "يمكنك الرد مباشرة على هذه الرسالة للتواصل مع الفريق."
        )
        await update.message.reply_text("تم إرسال الرسالة بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"فشل في إرسال الرسالة: {e}")

# معالجة الرسائل العادية (للرد من المستخدم إلى المسؤول)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        await update.message.reply_text("يرجى البدء أولاً باستخدام /start")
        return
    
    # إذا كان المستخدم يرد على رسالة من البوت
    if update.message.reply_to_message and "لديك رسالة من فريق الدعم" in update.message.reply_to_message.text:
        user_serial = user_data[user_id]['serial']
        user_name = user_data[user_id]['name']
        user_message = update.message.text
        
        # إرسال الرسالة إلى جميع المسؤولين
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 رد من المستخدم:\n"
                         f"الرقم التسلسلي: {user_serial}\n"
                         f"الاسم: {user_name}\n\n"
                         f"الرسالة: {user_message}"
                )
            except Exception as e:
                logger.error(f"فشل في إرسال الرسالة إلى المسؤول {admin_id}: {e}")
        
        await update.message.reply_text("تم إرسال رسالتك إلى فريق الدعم. سنرد عليك قريباً.")

# أمر المساعدة
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً! أنا بوت الدعم النفسي لمجتمع الكلية.\n\n"
        "الأوامر المتاحة:\n"
        "/start - بدء استخدام البوت والتحقق من العضوية\n"
        "/help - عرض هذه الرسالة\n\n"
        "للمسؤولين فقط:\n"
        "/reply <الرقم_التسلسلي> <الرسالة> - إرسال رسالة إلى مستخدم"
    )

# دالة رئيسية
def main():
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reply", reply_to_user))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    print("البوت يعمل...")
    application.run_polling()

if __name__ == "__main__":
    main()
