import asyncio
import logging
import sqlite3
import requests
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, 
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

BOT_TOKEN = "9235835555:AAEKF62n8SXvjlemeZjVLg3-Q7D0wXrdk9w"
API_KEY = "d0de5669-cae8-4a03-ad66-98dd5b58b330"

# كلمة المرور السرية للمدير
ADMIN_PASSWORD = "Z2244"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

class AdminStates(StatesGroup):
    waiting_for_recharge_input = State()

def init_db():
    conn = sqlite3.connect("reports_cache.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            vin TEXT PRIMARY KEY,
            report_text TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            phone_number TEXT UNIQUE,
            reports_left INTEGER DEFAULT 0,
            expiry_date TEXT,
            is_admin INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_cached_report(vin):
    conn = sqlite3.connect("reports_cache.db")
    cursor = conn.cursor()
    cursor.execute("SELECT report_text FROM reports WHERE vin = ?", (vin,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def save_report_to_cache(vin, report_text):
    conn = sqlite3.connect("reports_cache.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO reports (vin, report_text) VALUES (?, ?)", (vin, report_text))
    conn.commit()
    conn.close()

def get_user_by_telegram(user_id):
    conn = sqlite3.connect("reports_cache.db")
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number, reports_left, expiry_date, is_admin FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def is_user_admin(user_id):
    user = get_user_by_telegram(user_id)
    return user and user[3] == 1

def deduct_user_report_by_telegram(user_id):
    conn = sqlite3.connect("reports_cache.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET reports_left = reports_left - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

async def check_and_alert_site_balance():
    try:
        balance_url = f"http://vinscan.top/api/balance?apikey={API_KEY}"
        response = requests.get(balance_url, timeout=15)
        if response.status_code == 200:
            text = response.text.strip()
            digits = "".join(filter(str.isdigit, text))
            if digits:
                balance = int(digits)
                if balance <= 20:
                    conn = sqlite3.connect("reports_cache.db")
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id FROM users WHERE is_admin = 1")
                    admins = cursor.fetchall()
                    conn.close()
                    for admin in admins:
                        await bot.send_message(
                            admin[0],
                            f"🚨 **تنبيه عاجل لمدير البوت!**\n\n"
                            f"رصيدك المتبقي في موقع `vinscan` أصبح قليلاً جداً!\n"
                            f"💰 الرصيد الحالي بالموقع: `{balance}` تقريراً.",
                            parse_mode="Markdown"
                        )
    except Exception as e:
        print(f"Error checking balance: {e}")

async def show_admin_panel(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ شحن رصيد لزبون", callback_data="admin_recharge")],
        [InlineKeyboardButton(text="💰 فحص رصيد الموقع الفعلي", callback_data="admin_site_balance")],
        [InlineKeyboardButton(text="👥 عرض قائمة الزبائن", callback_data="admin_list_users")]
    ])
    await message.answer("👑 **لوحة تحكم المدير المتقدمة:**", reply_markup=keyboard, parse_mode="Markdown")

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if is_user_admin(user_id):
        await show_admin_panel(message)
        return

    user = get_user_by_telegram(user_id)
    if user and user[0] and user[0] != "ADMIN":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 التحقق من رصيدي", callback_data="user_balance")]
        ])
        await message.answer(
            f"مرحباً بك مجدداً في خدمة تقارير السيارات 🚗\n\n"
            f"📱 رقم الهاتف المرتبط: `{user[0]}`\n"
            f"📊 التقارير المتبقية: `{user[1]}`\n\n"
            f"أرسل لي **رقم الشاصي (VIN)** المكون من 17 خانة لجلب التقرير.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 اضغط هنا لمشاركة رقم هاتفك للتفعيل", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(
            "مرحباً بك في خدمة تقارير السيارات 🚗\n\n"
            "للاستفادة من الخدمة وتفعيل حسابك، يرجى مشاركة رقم هاتفك بالضغط على الزر أدناه:",
            reply_markup=kb
        )

@dp.message(Command("admin"))
async def admin_panel_cmd(message: Message, state: FSMContext):
    await state.clear()
    if is_user_admin(message.from_user.id):
        await show_admin_panel(message)
    else:
        await message.answer("⚠️ يرجى إرسال كلمة المرور السرية لتسجيل الدخول كمدير.", parse_mode="Markdown")

@dp.callback_query()
async def callback_handler(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = callback.data

    if data == "user_balance":
        user = get_user_by_telegram(user_id)
        if user and user[0]:
            await callback.message.answer(f"📊 **حالة حسابك:**\n- الهاتف: `{user[0]}`\n- التقارير المتبقية: `{user[1]}`", parse_mode="Markdown")
        else:
            await callback.message.answer("⚠️ يرجى تفعيل حسابك برقم الهاتف أولاً.")
        await callback.answer()

    elif is_user_admin(user_id):
        if data == "admin_site_balance":
            try:
                balance_url = f"http://vinscan.top/api/balance?apikey={API_KEY}"
                response = requests.get(balance_url, timeout=30)
                if response.status_code == 200:
                    await callback.message.answer(f"💰 رصيدك الفعلي في موقع vinscan:\n`{response.text}`", parse_mode="Markdown")
                else:
                    await callback.message.answer("⚠️ تعذر جلب رصيد الموقع.")
            except Exception as e:
                await callback.message.answer(f"❌ خطأ: {str(e)}")
            await callback.answer()

        elif data == "admin_recharge":
            await state.set_state(AdminStates.waiting_for_recharge_input)
            await callback.message.answer(
                "➕ **شحن رصيد لزبون:**\n\n"
                "أرسل الآن: **رقم الهاتف ثم مسافة ثم عدد التقارير**\n"
                "(مثال: `07504500863 10`)",
                parse_mode="Markdown"
            )
            await callback.answer()

        elif data == "admin_list_users":
            conn = sqlite3.connect("reports_cache.db")
            cursor = conn.cursor()
            cursor.execute("SELECT phone_number, reports_left, expiry_date FROM users WHERE phone_number != 'ADMIN' AND phone_number != 'غير محدد'")
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                await callback.message.answer("⚠️ لا يوجد زبائن مسجلون حتى الآن.")
            else:
                text = "👥 **قائمة الزبائن المسجلين:**\n\n"
                for row in rows:
                    text += f"📱 `{row[0]}` ➔ المتبقي: `{row[1]}` (صالح حتى: {row[2]})\n"
                await callback.message.answer(text, parse_mode="Markdown")
            await callback.answer()

@dp.message(F.contact)
async def handle_contact(message: Message):
    if message.contact:
        user_id = message.from_user.id
        phone = message.contact.phone_number.strip()
        
        conn = sqlite3.connect("reports_cache.db")
        cursor = conn.cursor()
        cursor.execute("SELECT reports_left, expiry_date FROM users WHERE phone_number = ?", (phone,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("UPDATE users SET user_id = ? WHERE phone_number = ?", (user_id, phone))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, phone_number, reports_left, expiry_date)
                VALUES (?, ?, 0, 'غير محدد')
            """, (user_id, phone))
        
        conn.commit()
        conn.close()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 التحقق من رصيدي", callback_data="user_balance")]
        ])
        await message.answer(
            f"✅ تم تسجيل رقم هاتفك بنجاح: `{phone}`\n\n"
            "تواصل مع الإدارة لشحن رصيدك.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@dp.message(F.text)
async def handle_messages(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # التحقق المباشر إذا كتب المستخدم كلمة المرور Z2244 كرسالة عادية
    if text == ADMIN_PASSWORD:
        conn = sqlite3.connect("reports_cache.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, phone_number, reports_left, expiry_date, is_admin)
            VALUES (?, 'ADMIN', 9999, 'دائم', 1)
        """, (user_id,))
        conn.commit()
        conn.close()
        
        await message.answer("✅ تم تفعيل صلاحيات المدير بنجاح!")
        await show_admin_panel(message)
        return

    current_state = await state.get_state()
    # حالة استقبال الشحن بعد الضغط على زر الشحن
    if is_user_admin(user_id) and current_state == AdminStates.waiting_for_recharge_input.state:
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            phone = parts[0].strip()
            reports_count = int(parts[1])
            expiry_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            
            try:
                conn = sqlite3.connect("reports_cache.db")
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE phone_number = ?", (phone,))
                row = cursor.fetchone()
                
                if row:
                    cursor.execute("""
                        UPDATE users SET reports_left = reports_left + ?, expiry_date = ? WHERE phone_number = ?
                    """, (reports_count, expiry_date, phone))
                else:
                    cursor.execute("""
                        INSERT INTO users (user_id, phone_number, reports_left, expiry_date)
                        VALUES (0, ?, ?, ?)
                    """, (phone, reports_count, expiry_date))
                    
                conn.commit()
                conn.close()
                
                await state.clear()
                await message.answer(f"✅ تمت إضافة `{reports_count}` تقريراً بنجاح لرقم الهاتف `{phone}`.")
                return
            except Exception as e:
                await message.answer(f"❌ حدث خطأ أثناء الشحن: {str(e)}")
                return
        else:
            await message.answer("⚠️ صيغة غير صحيحة. أرسل الرقم والعدد هكذا: `07504500863 10`", parse_mode="Markdown")
            return

    # شحن مباشر من قبل المدير بدون ضغط الزر (رقم الهاتف والعدد)
    if is_user_admin(user_id):
        parts = text.split()
        if len(parts) == 2 and parts[1].isdigit():
            phone = parts[0].strip()
            reports_count = int(parts[1])
            expiry_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            
            try:
                conn = sqlite3.connect("reports_cache.db")
                cursor = conn.cursor()
                cursor.execute("SELECT user_id FROM users WHERE phone_number = ?", (phone,))
                row = cursor.fetchone()
                
                if row:
                    cursor.execute("""
                        UPDATE users SET reports_left = reports_left + ?, expiry_date = ? WHERE phone_number = ?
                    """, (reports_count, expiry_date, phone))
                else:
                    cursor.execute("""
                        INSERT INTO users (user_id, phone_number, reports_left, expiry_date)
                        VALUES (0, ?, ?, ?)
                    """, (phone, reports_count, expiry_date))
                    
                conn.commit()
                conn.close()
                
                await message.answer(f"✅ تمت إضافة `{reports_count}` تقريراً بنجاح لرقم الهاتف `{phone}`.")
                return
            except Exception as e:
                await message.answer(f"❌ حدث خطأ: {str(e)}")
                return

    # التحقق من رقم الشاصي للزبائن
    vin_number = text.upper()
    if len(vin_number) != 17:
        await message.answer("⚠️ رقم الشاصي غير صحيح. يجب أن يتكون من 17 خانة بالضبط:")
        return

    user = get_user_by_telegram(user_id)
    if not user or not user[0] or user[0] == "ADMIN":
        await message.answer("⚠️ يرجى إرسال /start ومشاركة رقم هاتفك لتفعيل حسابك أولاً.")
        return
        
    phone, reports_left, expiry = user[0], user[1], user[2]
    if reports_left <= 0:
        await message.answer("❌ عذراً، رصيدك من التقارير انتهى. يرجى التواصل مع الإدارة لشحن رصيدك.")
        return

    cached_report = get_cached_report(vin_number)
    if cached_report:
        deduct_user_report_by_telegram(user_id)
        await message.answer(f"✅ إليك نتيجة التقرير (من الأرشيف):\n\n{cached_report}")
        return

    wait_msg = await message.answer("🔄 جاري سحب التقرير، يرجى الانتظار...")

    try:
        api_url = f"http://vinscan.top/carfax?apikey={API_KEY}&vin={vin_number}&lang=ar"
        response = requests.get(api_url, timeout=90)
        
        await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        
        if response.status_code == 200:
            result_text = response.text.strip()
            
            if result_text and "error" not in result_text.lower():
                save_report_to_cache(vin_number, result_text)
                deduct_user_report_by_telegram(user_id)
                await message.answer(f"✅ إليك نتيجة التقرير:\n\n{result_text}")
                
                await check_and_alert_site_balance()
            else:
                await message.answer("❌ لم يتم العثور على تقرير لهذا الرقم في النظام.")
        else:
            await message.answer("⚠️ حدث خطأ أثناء الاتصال بالخادم. حاول لاحقاً.")
            
    except Exception as e:
        await bot.delete_message(chat_id=message.chat.id, message_id=wait_msg.message_id)
        await message.answer(f"❌ حدث خطأ فني: {str(e)}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())