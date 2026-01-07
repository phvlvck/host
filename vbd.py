import telebot
from telebot import types
import subprocess
import os
import re
import sys
import logging
import time
import threading
from datetime import datetime, timedelta
import json
import signal
import platform

TOKEN = '7289881542:AAGmDZB08PX1NzM3zxXd5dEGd9k6fOMta1A'
bot = telebot.TeleBot(TOKEN)

required_channel = None

bot_scripts = {}
admin_id = 1786031358  # id
uploaded_files_dir = "uploaded_files"
user_upload_dates = {}  
upload_dates_file = "upload_dates.json"
blocked_users_file = "blocked_users.json"
users_file = 'users.json'
trusted_users = set()

# تعريف متغير العمليات النشطة
active_processes = {}

def is_process_running(process):
    """التحقق مما إذا كانت العملية لا تزال تعمل"""
    if process is None:
        return False
    
    try:
        # التحقق من حالة العملية
        return process.poll() is None
    except:
        return False

def terminate_process_tree(process):
    """إنهاء العملية وشجرة العمليات التابعة لها"""
    try:
        if process is None:
            return
            
        # إنهاء العملية الرئيسية
        if platform.system() == "Windows":
            process.terminate()
        else:
            # على أنظمة Unix نستخدم مجموعة الإشارات
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        
        # الانتظار لفترة ثم إجبار الإنهاء إذا لزم الأمر
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if platform.system() == "Windows":
                process.kill()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception as e:
        logging.error(f"Error terminating process: {e}")

def get_system_info():
    """الحصول على معلومات النظام"""
    info = {
        'platform': platform.system(),
        'platform_release': platform.release(),
        'platform_version': platform.version(),
        'architecture': platform.machine(),
        'processor': platform.processor(),
        'cpu_count': os.cpu_count(),
        'memory': os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') if hasattr(os, 'sysconf') else None
    }
    return info

# تحميل وحفظ المستخدمين
def load_users():
    if os.path.exists(users_file):
        with open(users_file, 'r') as file:
            return set(json.load(file))
    return set()

def save_users(users_set):
    with open(users_file, 'w') as file:
        json.dump(list(users_set), file)

users = load_users()

# تحميل وحفظ المستخدمين الموثوقين
def load_trusted_users():
    if os.path.exists('trusted_users.json'):
        with open('trusted_users.json', 'r') as file:
            return set(json.load(file))
    return set()

def save_trusted_users():
    with open('trusted_users.json', 'w') as file:
        json.dump(list(trusted_users), file)

trusted_users.update(load_trusted_users())

# تحميل وحفظ الاشتراكات غير المحدودة
def load_unlimited_subscriptions():
    if os.path.exists('unlimited_subscriptions.json'):
        with open('unlimited_subscriptions.json', 'r') as file:
            return set(json.load(file))
    return set()

def save_unlimited_subscriptions():
    with open('unlimited_subscriptions.json', 'w') as file:
        json.dump(list(unlimited_subscriptions), file)

unlimited_subscriptions = load_unlimited_subscriptions()

# تحميل وحفظ تواريخ الرفع
def load_upload_dates():
    if os.path.exists(upload_dates_file):
        with open(upload_dates_file, 'r') as file:
            data = json.load(file)
            # تحويل المفاتيح إلى أعداد صحيحة
            return {int(k): v for k, v in data.items()}
    return {}

def save_upload_dates():
    with open(upload_dates_file, 'w') as file:
        json.dump(user_upload_dates, file, default=str)

# تحميل وحفظ المستخدمين المحظورين
def load_blocked_users():
    if os.path.exists('blocked_users.json'):
        with open('blocked_users.json', 'r') as file:
            data = json.load(file)
            # تحويل القائمة إلى مجموعة مع تحويل القيم إلى أعداد صحيحة
            return set(int(user_id) for user_id in data)
    return set()

def save_blocked_users():
    with open('blocked_users.json', 'w') as file:
        json.dump(list(blocked_users), file)

# تحميل البيانات عند بدء التشغيل
blocked_users = load_blocked_users()
user_upload_dates = load_upload_dates()

# إعدادات التسجيل
logging.basicConfig(filename='bot_errors.log', level=logging.ERROR)

# إنشاء مجلد الملفات المرفوعة
if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir)

# إدارة حالة البوت
state_file = "bot_state.json"

def save_state():
    state_data = {}
    for script_name, script_info in bot_scripts.items():
        state_data[script_name] = {
            'name': script_info['name'],
            'path': script_info['path'],
            'start_time': script_info['start_time'].isoformat() if script_info['start_time'] else None,
            'running': is_process_running(script_info.get('process'))
        }
    
    with open(state_file, 'w') as file:
        json.dump(state_data, file)

def load_state():
    if os.path.exists(state_file):
        with open(state_file, 'r') as file:
            return json.load(file)
    else:
        with open(state_file, 'w') as file:
            json.dump({}, file)
        return {}

# تحضير النصوص البرمجية
def get_imports(script_path):
    imports = set()
    try:
        with open(script_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if line.startswith('import ') or line.startswith('from '):
                    parts = line.split()
                    if len(parts) > 1:
                        module = parts[1].split('.')[0]
                        imports.add(module)
    except Exception as e:
        logging.error(f"Error reading imports from {script_path}: {e}")
    return imports

def install_packages(packages):
    for package in packages:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                logging.warning(f"Failed to install {package}: {result.stderr}")
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout installing {package}")
        except Exception as e:
            logging.error(f"Error installing package {package}: {e}")

def prepare_script(script_path):
    try:
        imports = get_imports(script_path)
        install_packages(imports)
    except Exception as e:
        logging.error(f"Error preparing script {script_path}: {e}")

# وظائف الاشتراك الإجباري
def is_subscribed(user_id):
    if not required_channel:
        return True
    try:
        member = bot.get_chat_member(required_channel, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Error checking subscription: {e}")
        return False

# معالجة جميع الرسائل من المستخدمين المحظورين
@bot.message_handler(func=lambda message: message.from_user.id in blocked_users)
def handle_blocked_user(message):
    try:
        bot.reply_to(message, "⚠️ تم حظرك من استخدام هذا البوت.")
    except Exception as e:
        logging.error(f"Error handling blocked user message: {e}")

# معالجة الإجراءات من الأدمن على المستخدمين
@bot.message_handler(func=lambda message: message.text and message.text.isdigit() and message.from_user.id == admin_id)
def handle_admin_user_action(message):
    try:
        user_id = int(message.text)
        
        if message.reply_to_message:
            reply_text = message.reply_to_message.text
            
            if "يرجى إرسال معرف المستخدم الذي تريد حظره" in reply_text:
                blocked_users.add(user_id)
                save_blocked_users()
                bot.send_message(message.chat.id, f"✅ تم حظر المستخدم {user_id} بنجاح.")
            
            elif "يرجى إرسال معرف المستخدم الذي تريد إلغاء حظره" in reply_text:
                if user_id in blocked_users:
                    blocked_users.remove(user_id)
                    save_blocked_users()
                    bot.send_message(message.chat.id, f"✅ تم إلغاء حظر المستخدم {user_id} بنجاح.")
                else:
                    bot.send_message(message.chat.id, f"المستخدم {user_id} ليس محظورًا.")
            
            elif "يرجى إرسال معرف المستخدم الذي تريد تفعيل اشتراك بلا حدود له" in reply_text:
                unlimited_subscriptions.add(user_id)
                save_unlimited_subscriptions()
                bot.send_message(message.chat.id, f"✅ تم تفعيل اشتراك بلا حدود للمستخدم {user_id}.")
            
            elif "يرجى إرسال معرف المستخدم الذي تريد إلغاء اشتراك بلا حدود له" in reply_text:
                if user_id in unlimited_subscriptions:
                    unlimited_subscriptions.remove(user_id)
                    save_unlimited_subscriptions()
                    bot.send_message(message.chat.id, f"✅ تم إلغاء اشتراك بلا حدود للمستخدم {user_id}.")
                else:
                    bot.send_message(message.chat.id, f"المستخدم {user_id} ليس لديه اشتراك بلا حدود.")
            
            elif "يرجى إرسال معرف المستخدم الذي تريد إضافته كموثوق" in reply_text:
                trusted_users.add(user_id)
                save_trusted_users()
                bot.send_message(message.chat.id, f"✅ تم إضافة المستخدم {user_id} كموثوق.")
            
            elif "يرجى إرسال معرف المستخدم الذي تريد إزالته من قائمة الموثوقين" in reply_text:
                if user_id in trusted_users:
                    trusted_users.remove(user_id)
                    save_trusted_users()
                    bot.send_message(message.chat.id, f"✅ تم إزالة المستخدم {user_id} من قائمة الموثوقين.")
                else:
                    bot.send_message(message.chat.id, f"المستخدم {user_id} غير موجود في قائمة الموثوقين.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال معرف مستخدم صحيح (أرقام فقط).")
    except Exception as e:
        logging.error(f"Error in handle_admin_user_action: {e}")
        bot.send_message(message.chat.id, f"حدث خطأ: {e}")

# وظائف القائمة الرئيسية
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    # التحقق من الحظر أولاً
    if user_id in blocked_users:
        bot.reply_to(message, "⚠️ تم حظرك من استخدام هذا البوت.")
        return

    if required_channel and not is_subscribed(user_id):
        bot.send_message(message.chat.id, f"يجب عليك الاشتراك في القناة أولاً: {required_channel}")
        return

    if user_id not in users:
        users.add(user_id)
        save_users(users)
        print(f"User {user_id} added to users list")

    markup = types.InlineKeyboardMarkup()

    # أزرار المستخدمين العاديين
    upload_button = types.InlineKeyboardButton("رفع ملف 📁", callback_data='upload')
    files_count_button = types.InlineKeyboardButton(f"عدد الملفات : {len(bot_scripts)}", callback_data='files_count')
    show_files_button = types.InlineKeyboardButton("عرض الملفات", callback_data='show_files')

    markup.row(upload_button)
    markup.row(files_count_button, show_files_button)

    # أزرار الأدمن فقط
    if message.from_user.id == admin_id:
        stop_bot_button = types.InlineKeyboardButton("إيقاف بوت", callback_data='stop_bot')
        block_user_button = types.InlineKeyboardButton("حظر شخص", callback_data='block_user')
        unblock_user_button = types.InlineKeyboardButton("إلغاء حظر", callback_data='unblock_user')
        show_blocked_users_button = types.InlineKeyboardButton("عرض المحظورين", callback_data='show_blocked_users')
        unlimited_button = types.InlineKeyboardButton("بلا حدود", callback_data='unlimited_upload')
        cancel_unlimited_button = types.InlineKeyboardButton("إلغاء بلا حدود", callback_data='cancel_unlimited')
        add_trusted_button = types.InlineKeyboardButton("إضافة موثوق", callback_data='add_trusted')
        show_trusted_button = types.InlineKeyboardButton("عرض الموثوقين", callback_data='show_trusted')
        remove_trusted_button = types.InlineKeyboardButton("إزالة موثوق", callback_data='remove_trusted')
        add_subscription_button = types.InlineKeyboardButton("اضف اشتراك إجباري", callback_data='add_subscription')
        delete_subscription_button = types.InlineKeyboardButton("مسح قناة الاشتراك", callback_data='delete_subscription')
        clear_blocked_users_button = types.InlineKeyboardButton("مسح المحظورين", callback_data='clear_blocked_users')
        bot_stats_button = types.InlineKeyboardButton("إحصائيات البوت", callback_data='bot_stats')

        markup.row(stop_bot_button)
        markup.row(block_user_button, unblock_user_button)
        markup.row(show_blocked_users_button)
        markup.row(unlimited_button, cancel_unlimited_button)
        markup.row(add_trusted_button)
        markup.row(show_trusted_button, remove_trusted_button)
        markup.row(add_subscription_button)
        markup.row(delete_subscription_button, clear_blocked_users_button)
        markup.row(bot_stats_button)

    bot.send_message(
        message.chat.id,
        "مرحبًا بك في بوت رفع وتشغيل ملفات بايثون.",
        reply_markup=markup
    )

# معالجة الإحصائيات
@bot.callback_query_handler(func=lambda call: call.data == 'bot_stats')
def handle_bot_stats(call):
    if call.from_user.id == admin_id:
        try:
            num_users = len(users)
            num_files = len(bot_scripts)
            running_files = sum(1 for info in bot_scripts.values() if is_process_running(info.get('process')))
            system_info = get_system_info()
            
            stats_text = f"""
📊 إحصائيات البوت:
👥 عدد المستخدمين: {num_users}
📁 عدد الملفات: {num_files}
⚡ الملفات النشطة: {running_files}
🖥️ النظام: {system_info['platform']} {system_info['platform_release']}
💾 المعالج: {system_info['processor'] or 'غير معروف'}
🎯 النواة: {system_info['cpu_count']}
            """
            bot.send_message(call.message.chat.id, stats_text)
        except Exception as e:
            logging.error(f"Error retrieving bot stats: {e}")
            bot.send_message(call.message.chat.id, "حدث خطأ في استرجاع الإحصائيات.")
    else:
        bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

# إدارة المستخدمين المحظورين
@bot.callback_query_handler(func=lambda call: call.data == 'clear_blocked_users')
def handle_clear_blocked_users(call):
    if call.from_user.id == admin_id:
        blocked_users.clear()
        save_blocked_users()
        bot.answer_callback_query(call.id, "✅ تم مسح قائمة المحظورين.")
    else:
        bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

# إدارة الاشتراك الإجباري
@bot.callback_query_handler(func=lambda call: call.data == 'add_subscription')
def handle_add_subscription(call):
    if call.from_user.id == admin_id:
        msg = bot.send_message(call.message.chat.id, "أرسل رابط القناة التي تريد استخدامها (يمكن أن تكون عامة أو خاصة).")
        bot.register_next_step_handler(msg, save_channel_link)
    else:
        bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

@bot.callback_query_handler(func=lambda call: call.data == 'delete_subscription')
def handle_delete_subscription(call):
    global required_channel
    if call.from_user.id == admin_id:
        required_channel = None
        bot.answer_callback_query(call.id, "✅ تم مسح قناة الاشتراك الإجباري.")
    else:
        bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

def save_channel_link(message):
    global required_channel
    required_channel = message.text.strip()
    bot.reply_to(message, f"✅ تم تعيين قناة الاشتراك الإجباري: {required_channel}")

# إدارة المستخدمين الموثوقين
@bot.callback_query_handler(func=lambda call: call.data == 'show_trusted')
def handle_show_trusted(call):
    if call.from_user.id == admin_id:
        if trusted_users:
            trusted_users_list = "\n".join(str(user_id) for user_id in trusted_users)
            bot.send_message(call.message.chat.id, f"المستخدمون الموثوقون:\n{trusted_users_list}")
        else:
            bot.send_message(call.message.chat.id, "لا يوجد مستخدمون موثوقون.")
    else:
        bot.send_message(call.message.chat.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

@bot.callback_query_handler(func=lambda call: call.data == 'remove_trusted')
def handle_remove_trusted(call):
    if call.from_user.id == admin_id:
        bot.send_message(call.message.chat.id, "يرجى إرسال معرف المستخدم الذي تريد إزالته من قائمة الموثوقين.")
        bot.register_next_step_handler(call.message, process_remove_trusted)
    else:
        bot.send_message(call.message.chat.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

@bot.callback_query_handler(func=lambda call: call.data == 'add_trusted')
def handle_add_trusted(call):
    if call.from_user.id == admin_id:
        bot.send_message(call.message.chat.id, "يرجى إرسال معرف المستخدم الذي تريد إضافته كموثوق.")
        bot.register_next_step_handler(call.message, process_add_trusted)
    else:
        bot.send_message(call.message.chat.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

def process_add_trusted(message):
    user_id = message.text
    try:
        user_id = int(user_id)
        trusted_users.add(user_id)
        save_trusted_users()
        bot.send_message(message.chat.id, f"✅ تم إضافة المستخدم {user_id} كموثوق.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال معرف مستخدم صحيح.")

def process_remove_trusted(message):
    user_id = message.text
    try:
        user_id = int(user_id)
        if user_id in trusted_users:
            trusted_users.remove(user_id)
            save_trusted_users()
            bot.send_message(message.chat.id, f"✅ تم إزالة المستخدم {user_id} من قائمة الموثوقين.")
        else:
            bot.send_message(message.chat.id, "المستخدم غير موجود في قائمة الموثوقين.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال معرف مستخدم صحيح.")

# عرض الملفات
@bot.callback_query_handler(func=lambda call: call.data == 'show_files')
def handle_show_files(call):
    if call.from_user.id == admin_id:
        running_files = []
        for script_name, info in bot_scripts.items():
            if is_process_running(info.get('process')) and info.get('start_time'):
                runtime = datetime.now() - info['start_time']
                running_files.append(f"{info['name']} بدأ التشغيل منذ: {str(runtime).split('.')[0]}")
        
        if running_files:
            response = "الملفات التي تعمل حاليًا:\n" + "\n".join(running_files)
        else:
            response = "لا توجد ملفات تعمل حاليًا."
        bot.send_message(call.message.chat.id, response)
    else:
        bot.answer_callback_query(call.id, "هذه الميزة متاحة فقط للأدمن.")

# إدارة الاشتراكات غير المحدودة
@bot.callback_query_handler(func=lambda call: call.data == 'unlimited_upload')
def handle_unlimited_upload(call):
    if call.from_user.id == admin_id:
        bot.send_message(call.message.chat.id, "يرجى إرسال معرف المستخدم الذي تريد تفعيل اشتراك بلا حدود له.")
    else:
        bot.send_message(call.message.chat.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_unlimited')
def handle_cancel_unlimited(call):
    if call.from_user.id == admin_id:
        bot.send_message(call.message.chat.id, "يرجى إرسال معرف المستخدم الذي تريد إلغاء اشتراك بلا حدود له.")
    else:
        bot.send_message(call.message.chat.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

# معالجة رفع الملفات
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    
    # التحقق من الحظر
    if user_id in blocked_users:
        bot.reply_to(message, "⚠️ تم حظرك من استخدام هذا البوت.")
        return

    if required_channel and not is_subscribed(user_id):
        bot.reply_to(message, f"يجب عليك الاشتراك في القناة أولاً: {required_channel}")
        return

    current_date = datetime.now().date().isoformat()

    is_admin = user_id == admin_id
    is_unlimited = user_id in unlimited_subscriptions
    
    if not is_admin and not is_unlimited:
        last_upload_date = user_upload_dates.get(user_id)
        if last_upload_date == current_date:
            bot.reply_to(message, "❌ لا يمكنك رفع أكثر من ملف واحد في اليوم.")
            return

    try:
        file_id = message.document.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # تحميل الملف مباشرة بدون فحص
        bot_script_name = message.document.file_name
        script_path = os.path.join(uploaded_files_dir, bot_script_name)
        
        with open(script_path, 'wb') as new_file:
            new_file.write(downloaded_file)

        # إعداد السكربت
        prepare_script(script_path)

        # إضافة المعلومات للذاكرة
        bot_scripts[bot_script_name] = {
            'name': bot_script_name,
            'path': script_path,
            'process': None,
            'start_time': None
        }

        # استخراج التوكن
        bot_token = get_bot_token(script_path)
        
        # إنشاء الأزرار
        markup = types.InlineKeyboardMarkup()
        start_button = types.InlineKeyboardButton("تشغيل الملف", callback_data=f'start_{bot_script_name}')
        stop_button = types.InlineKeyboardButton("ايقاف الملف", callback_data=f'stop_{bot_script_name}')
        delete_button = types.InlineKeyboardButton("حذف الملف", callback_data=f'delete_{bot_script_name}')
        markup.row(start_button)
        markup.row(stop_button, delete_button)

        # إرسال الرسالة
        bot.reply_to(
            message, 
            f"✅ تم رفع ملف بوتك بنجاح\n\n📄 اسم الملف المرفوع: {bot_script_name}\n🔑 توكن البوت المرفوع: {bot_token}", 
            reply_markup=markup
        )

        # إرسال نسخة للأدمن
        send_to_admin(script_path)
        
        # تشغيل الملف تلقائياً
        start_file(script_path, message.chat.id)
        
        # تحديث تاريخ الرفع للمستخدم
        if not is_admin and not is_unlimited:
            user_upload_dates[user_id] = current_date
            save_upload_dates()

    except Exception as e:
        logging.error(f"Error handling file: {e}")
        bot.reply_to(message, f"❌ حدث خطأ: {str(e)}")

# عرض المستخدمين المحظورين
@bot.callback_query_handler(func=lambda call: call.data == 'show_blocked_users')
def show_blocked_users(call):
    if call.from_user.id == admin_id:
        if blocked_users:
            blocked_users_list = "\n".join(str(user_id) for user_id in blocked_users)
            bot.send_message(call.message.chat.id, f"👥 المستخدمون المحظورون:\n{blocked_users_list}")
        else:
            bot.send_message(call.message.chat.id, "✅ لا يوجد مستخدمون محظورون.")
    else:
        bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.")

# إرسال الملف للأدمن
def send_to_admin(file_name):
    try:
        with open(file_name, 'rb') as file:
            bot.send_document(admin_id, file, caption=f"📁 ملف تم رفعه: {os.path.basename(file_name)}")
    except Exception as e:
        logging.error(f"Error sending file to admin: {e}")

# تشغيل الملف
def start_file(script_path, chat_id):
    try:
        script_name = os.path.basename(script_path)
        
        # التحقق مما إذا كان الملف يعمل بالفعل
        if script_name in bot_scripts and is_process_running(bot_scripts[script_name].get('process')):
            bot.send_message(chat_id, f"⚠️ الملف {script_name} يعمل بالفعل.")
            return
        
        # إنشاء العملية
        if platform.system() == "Windows":
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # على أنظمة Unix نستخدم مجموعة العمليات
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid
            )
        
        # تحديث المعلومات
        bot_scripts[script_name]['process'] = process
        bot_scripts[script_name]['start_time'] = datetime.now()
        active_processes[script_name] = process
        
        # حفظ الحالة
        save_state()
        
        # بدء مراقبة العملية في الخلفية
        threading.Thread(target=monitor_process_output, args=(process, script_name, chat_id), daemon=True).start()
        
        bot.send_message(chat_id, f"✅ تم تشغيل {script_name} بنجاح.")
        
    except Exception as e:
        logging.error(f"Error starting bot: {e}")
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء تشغيل {os.path.basename(script_path)}: {str(e)}")

# مراقبة إخراج العملية
def monitor_process_output(process, script_name, chat_id):
    try:
        # مراقبة الإخراج القياسي
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                if line:
                    logging.info(f"[{script_name}] {line.strip()}")
        
        # مراقبة أخطاء الإخراج
        if process.stderr:
            for line in iter(process.stderr.readline, ''):
                if line:
                    logging.error(f"[{script_name} ERROR] {line.strip()}")
                    # إرسال الأخطاء للأدمن
                    try:
                        bot.send_message(admin_id, f"⚠️ خطأ في {script_name}: {line.strip()[:100]}")
                    except:
                        pass
        
        # انتظار انتهاء العملية
        process.wait()
        
    except Exception as e:
        logging.error(f"Error monitoring process {script_name}: {e}")

# استخراج توكن البوت من الملف
def get_bot_token(file_name):
    try:
        with open(file_name, 'r', encoding='utf-8') as file:
            content = file.read()
            
            # البحث عن التوكن بأنماط مختلفة
            patterns = [
                r'TOKEN\s*=\s*[\'"]([^\'"]*)[\'"]',
                r'token\s*=\s*[\'"]([^\'"]*)[\'"]',
                r'bot_token\s*=\s*[\'"]([^\'"]*)[\'"]',
                r'api_id\s*=\s*[\'"]([^\'"]*)[\'"]',
                r'api_hash\s*=\s*[\'"]([^\'"]*)[\'"]'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    token = match.group(1)
                    # إخفاء جزء من التوكن للأمان
                    if len(token) > 8:
                        return token[:4] + "****" + token[-4:]
                    return token
            
            return "تعذر العثور على التوكن"
            
    except Exception as e:
        logging.error(f"Error getting bot token: {e}")
        return "تعذر العثور على التوكن"

# معالجة الأزرار
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    
    # التحقق من الحظر
    if user_id in blocked_users:
        allowed_actions = ['files_count', 'show_files']
        if call.data not in allowed_actions:
            bot.answer_callback_query(call.id, "⚠️ تم حظرك من استخدام هذا البوت.", show_alert=True)
            return

    if call.data == 'upload':
        bot.send_message(call.message.chat.id, "📤 ارسل الملف الآن.")
    
    elif call.data == 'files_count':
        bot.answer_callback_query(call.id, f"📊 عدد الملفات المرفوعة: {len(bot_scripts)}")
    
    elif call.data == 'block_user':
        if call.from_user.id == admin_id:
            bot.send_message(call.message.chat.id, "يرجى إرسال معرف المستخدم الذي تريد حظره.")
        else:
            bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.", show_alert=True)
    
    elif call.data == 'unblock_user':
        if call.from_user.id == admin_id:
            bot.send_message(call.message.chat.id, "يرجى إرسال معرف المستخدم الذي تريد إلغاء حظره.")
        else:
            bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.", show_alert=True)
    
    elif call.data == 'stop_bot':
        if call.from_user.id == admin_id:
            bot.send_message(call.message.chat.id, "يرجى إرسال اسم الملف الذي تريد إيقافه.")
        else:
            bot.answer_callback_query(call.id, "ليس لديك صلاحيات لتنفيذ هذا الأمر.", show_alert=True)
    
    elif call.data.startswith('delete_') or call.data.startswith('stop_') or call.data.startswith('start_'):
        # استخراج الإجراء واسم الملف
        parts = call.data.split('_')
        action = parts[0]
        script_name = '_'.join(parts[1:])
        
        if script_name not in bot_scripts:
            bot.answer_callback_query(call.id, f"❌ الملف {script_name} غير موجود.", show_alert=True)
            return
        
        script_path = bot_scripts[script_name]['path']
        
        if action == 'delete':
            try:
                stop_bot(script_path, call.message.chat.id, delete=True)
                if script_name in bot_scripts:
                    del bot_scripts[script_name]
                save_state()
                bot.send_message(call.message.chat.id, f"✅ تم حذف ملف {script_name} بنجاح.")
            except Exception as e:
                logging.error(f"Error deleting script: {e}")
                bot.send_message(call.message.chat.id, f"❌ حدث خطأ: {str(e)}")
        
        elif action == 'stop':
            try:
                stop_bot(script_path, call.message.chat.id)
                save_state()
            except Exception as e:
                logging.error(f"Error stopping script: {e}")
                bot.send_message(call.message.chat.id, f"❌ حدث خطأ: {str(e)}")
        
        elif action == 'start':
            try:
                start_file(script_path, call.message.chat.id)
            except Exception as e:
                logging.error(f"Error starting script: {e}")
                bot.send_message(call.message.chat.id, f"❌ حدث خطأ: {str(e)}")

# إيقاف البوت
def stop_bot(script_path, chat_id, delete=False):
    try:
        script_name = os.path.basename(script_path)
        
        if script_name not in bot_scripts:
            bot.send_message(chat_id, f"❌ الملف {script_name} غير موجود.")
            return
        
        process = bot_scripts[script_name].get('process')
        
        if is_process_running(process):
            # إنهاء العملية
            terminate_process_tree(process)
            bot_scripts[script_name]['process'] = None
            bot_scripts[script_name]['start_time'] = None
            
            # حذف من العمليات النشطة
            if script_name in active_processes:
                del active_processes[script_name]
            
            save_state()
            
            if delete:
                try:
                    os.remove(script_path)
                    bot.send_message(chat_id, f"✅ تم حذف {script_name} من الاستضافة.")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ حدث خطأ أثناء حذف الملف: {str(e)}")
            else:
                bot.send_message(chat_id, f"✅ تم إيقاف {script_name} بنجاح.")
        else:
            bot.send_message(chat_id, f"ℹ️ {script_name} غير نشط حالياً.")
            
    except Exception as e:
        logging.error(f"Error stopping bot: {e}")
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء إيقاف {script_name}: {str(e)}")

# معالجة إيقاف البوت بالاسم
@bot.message_handler(func=lambda message: message.reply_to_message and "يرجى إرسال اسم الملف الذي تريد إيقافه" in message.reply_to_message.text)
def handle_stop_bot_name(message):
    if message.from_user.id == admin_id:
        bot_name = message.text
        stop_bot_by_name(bot_name, message.chat.id)

def stop_bot_by_name(bot_name, chat_id):
    if bot_name in bot_scripts:
        script_path = bot_scripts[bot_name]['path']
        stop_bot(script_path, chat_id)
    else:
        bot.send_message(chat_id, f"❌ لم يتم العثور على ملف باسم {bot_name}.")

# مراقبة العمليات
def monitor_processes():
    while True:
        try:
            for script_name, script_info in list(bot_scripts.items()):
                process = script_info.get('process')
                
                # التحقق مما إذا كانت العملية لا تزال تعمل
                if process and not is_process_running(process):
                    bot.send_message(
                        admin_id, 
                        f"⚠️ العملية الخاصة بالملف {script_name} توقفت، سيتم إعادة تشغيلها."
                    )
                    
                    script_path = script_info['path']
                    
                    # حذف العملية القديمة
                    if script_name in active_processes:
                        del active_processes[script_name]
                    
                    # إعادة التشغيل
                    start_file(script_path, admin_id)
            
            # تنظيف الملفات غير النشطة
            clean_inactive_files()
            
            time.sleep(60)
            
        except Exception as e:
            logging.error(f"Error in monitor_processes: {e}")
            time.sleep(60)

# تنظيف الملفات غير النشطة
def clean_inactive_files():
    current_time = datetime.now()
    for script_name, info in list(bot_scripts.items()):
        process = info.get('process')
        
        # إذا كانت العملية غير نشطة
        if not is_process_running(process):
            if info.get('start_time') and (current_time - info['start_time']) > timedelta(hours=2):
                file_path = info['path']
                try:
                    os.remove(file_path)
                    del bot_scripts[script_name]
                    
                    # حذف من العمليات النشطة
                    if script_name in active_processes:
                        del active_processes[script_name]
                    
                    save_state()
                    bot.send_message(admin_id, f"🗑️ تم حذف الملف {script_name} لأنه توقّف عن العمل لأكثر من ساعتين.")
                except Exception as e:
                    logging.error(f"Error deleting inactive file {script_name}: {e}")

# التنظيف الدوري
def periodic_cleaner():
    while True:
        clean_inactive_files()
        time.sleep(3600)  # ساعة واحدة

# استطلاع البوت
def bot_polling():
    while True:
        try:
            print("Starting bot polling...")
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            logging.error(f"Error in bot.polling: {e}")
            print(f"Polling error: {e}")
            time.sleep(10)

# البداية
if __name__ == "__main__":
    print("Bot starting...")
    print(f"Admin ID: {admin_id}")
    print(f"Upload directory: {uploaded_files_dir}")
    
    # تحميل الحالة السابقة
    saved_state = load_state()
    
    for script_name, script_info in saved_state.items():
        script_path = script_info.get('path')
        
        if script_path and os.path.exists(script_path):
            bot_scripts[script_name] = {
                'name': script_info['name'],
                'path': script_path,
                'process': None,
                'start_time': datetime.fromisoformat(script_info['start_time']) if script_info.get('start_time') else None
            }
            
            # إعادة تشغيل الملفات التي كانت تعمل
            if script_info.get('running'):
                print(f"Restarting previously running script: {script_name}")
                threading.Thread(target=start_file, args=(script_path, admin_id), daemon=True).start()
                time.sleep(1)  # تأخير بسيط بين كل تشغيل

    # بدء الخيوط
    monitoring_thread = threading.Thread(target=monitor_processes, daemon=True)
    cleaner_thread = threading.Thread(target=periodic_cleaner, daemon=True)
    
    monitoring_thread.start()
    cleaner_thread.start()

    # بدء البوت
    print("Starting bot polling thread...")
    polling_thread = threading.Thread(target=bot_polling, daemon=True)
    polling_thread.start()
    
    # إبقاء البرنامج الرئيسي يعمل
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nBot stopping...")