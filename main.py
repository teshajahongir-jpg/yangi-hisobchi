import os
import math
import logging
import asyncio
from datetime import datetime, time
import sqlite3
import pandas as pd

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from fastapi import FastAPI
import uvicorn

# 1. TIZIM SOZLAMALARI (CONFIG)
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Bu yerga bot tokenini qo'ying
ADMIN_ID = 123456789  # Jahongir aka, bu yerga o'zingizning shaxsiy Telegram ID-angizni qo'ying

# Ofis koordinatalari (Geofence) va ruxsat etilgan radius (metrda)
OFFICE_LAT = 39.7747
OFFICE_LON = 64.4286
ALLOWED_RADIUS_METERS = 50.0

# Ish vaqti standartlari
WORK_START_TIME = time(9, 0)  # 09:00
OBED_LIMIT_MINUTES = 60  # 1 soat obed

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)

# 2. MA'LUMOTLAR BAZASI (SQLITE) OPERATSIYALARI
DB_FILE = "attendance_system.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Xodimlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            tg_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            monthly_salary REAL NOT NULL,
            daily_rate REAL NOT NULL,
            minute_rate REAL NOT NULL,
            status TEXT DEFAULT 'inactive'
        )
    ''')
    
    # Davomat va kunlik hisobotlar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            date TEXT,
            arrival_time TEXT,
            departure_time TEXT,
            lunch_start TEXT,
            lunch_end TEXT,
            late_minutes INTEGER DEFAULT 0,
            lunch_over_minutes INTEGER DEFAULT 0,
            earned_today REAL DEFAULT 0,
            status TEXT,
            FOREIGN KEY(tg_id) REFERENCES employees(tg_id)
        )
    ''')
    
    # Dam olish kunlari jadvali (Admin o'zgartira oladi)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS off_days (
            day_name TEXT PRIMARY KEY,
            is_off INTEGER DEFAULT 0
        )
    ''')
    
    # Standart dam olish kunini (masalan Yakshanba) kiritish
    days = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
    for day in days:
        is_off_val = 1 if day == 'Yakshanba' else 0
        cursor.execute("INSERT OR IGNORE INTO off_days (day_name, is_off) VALUES (?, ?)", (day, is_off_val))
        
    conn.commit()
    conn.close()

init_db()

# Haversine formulasi — Lokatsiyalar orasidagi masofani aniq hisoblash (metrda)
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Yer radiusi metrlarda
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# 3. TELEGRAM BOT (AIOGRAM 3.X) ISHLASHI
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# FSM Davlatlari (Xodim qo'shish uchun)
class EmployeeForm(StatesGroup):
    tg_id = State()
    full_name = State()
    salary = State()

# Klaviaturalar (Keyboards)
def get_admin_keyboard():
    kb = [
        [KeyboardButton(text="👥 Xodimlar Ro'yxati"), KeyboardButton(text="➕ Xodim Qo'shish")],
        [KeyboardButton(text="📊 Excel Hisobot Yuklash"), KeyboardButton(text="⚙ Dam olish kunlari")],
        [KeyboardButton(text="🔄 Tizimni Yangilash")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_employee_keyboard(status):
    if status == 'inactive':
        kb = [[KeyboardButton(text="🟢 Ishni boshlash", request_location=True)]]
    elif status == 'working':
        kb = [
            [KeyboardButton(text="🍽 Obedga chiqish"), KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
        ]
    elif status == 'lunch':
        kb = [[KeyboardButton(text="↩ Obeddan qaytish", request_location=True)]]
    else:
        kb = [[KeyboardButton(text="📴 Bugun sizga dam yoki ish yakunlangan")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ADMIN HANDLERS ---
@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def admin_start(message: types.Message):
    await message.answer("Xush kelibsiz, Jahongir aka! Boshqaruv paneliga xush kelibsiz.", reply_markup=get_admin_keyboard())

@dp.message(F.text == "➕ Xodim Qo'shish", F.from_user.id == ADMIN_ID)
async def add_employee_start(message: types.Message, state: FSMContext):
    await message.answer("Xodimning Telegram ID raqamini kiriting:")
    await state.set_state(EmployeeForm.tg_id)

@dp.message(EmployeeForm.tg_id, F.from_user.id == ADMIN_ID)
async def add_employee_id(message: types.Message, state: FSMContext):
    try:
        tg_id = int(message.text)
        await state.update_data(tg_id=tg_id)
        await message.answer("Xodimning F.I.Sh (Ismi va Familiyasi)ni kiriting:")
        await state.set_state(EmployeeForm.full_name)
    except ValueError:
        await message.answer("Iltimos, faqat raqamlardan iborat ID kiriting:")

@dp.message(EmployeeForm.full_name, F.from_user.id == ADMIN_ID)
async def add_employee_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Xodimning oylik maoshini kiriting (so'mda, masalan: 5000000):")
    await state.set_state(EmployeeForm.salary)

@dp.message(EmployeeForm.salary, F.from_user.id == ADMIN_ID)
async def add_employee_salary(message: types.Message, state: FSMContext):
    try:
        salary = float(message.text)
        data = await state.get_data()
        
        # Oylik, kunlik va daqiqalik stavkalarni hisoblash (26 ish kuniga bo'lingan holda)
        daily_rate = salary / 26
        minute_rate = daily_rate / 540  # 9 soatlik ish kuni = 540 daqiqa
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO employees (tg_id, full_name, monthly_salary, daily_rate, minute_rate) VALUES (?, ?, ?, ?, ?)",
            (data['tg_id'], data['full_name'], salary, daily_rate, minute_rate)
        )
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ Xodim muvaffaqiyatli qo'shildi!\n👤 {data['full_name']}\n💰 Kunlik stavka: {daily_rate:.2f} so'm", reply_markup=get_admin_keyboard())
        await state.clear()
    except ValueError:
        await message.answer("Iltimos, maoshni to'g'ri raqamda kiriting:")

@dp.message(F.text == "👥 Xodimlar Ro'yxati", F.from_user.id == ADMIN_ID)
async def list_employees(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, full_name, monthly_salary, status FROM employees")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await message.answer("Hozircha hech qanday xodim qo'shilmagan.")
        return
        
    text = "📋 **Xodimlar ro'yxati va joriy holati:**\n\n"
    for r in rows:
        text += f"🆔 {r[0]} | 👤 {r[1]} | 💰 {r[2]:,.0f} so'm | Holat: {r[3]}\n"
    await message.answer(text)

@dp.message(F.text == "⚙ Dam olish kunlari", F.from_user.id == ADMIN_ID)
async def manage_off_days(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT day_name, is_off FROM off_days")
    rows = cursor.fetchall()
    conn.close()
    
    inline_kb = []
    for day, is_off in rows:
        status_str = "🟢 Dam olish kuni" if is_off == 1 else "🔴 Ish kuni"
        inline_kb.append([InlineKeyboardButton(text=f"{day}: {status_str}", callback_data=f"toggle_{day}")])
        
    reply_markup = InlineKeyboardMarkup(inline_keyboard=inline_kb)
    await message.answer("Haftalik kunlar sozlamasi. O'zgartirmoqchi bo'lgan kuningizni bosing:", reply_markup=reply_markup)

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_day_callback(callback: types.CallbackQuery):
    day_name = callback.data.split("_")[1]
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_off FROM off_days WHERE day_name = ?", (day_name,))
    current = cursor.fetchone()[0]
    new_val = 0 if current == 1 else 1
    cursor.execute("UPDATE off_days SET is_off = ? WHERE day_name = ?", (new_val, day_name))
    conn.commit()
    
    cursor.execute("SELECT day_name, is_off FROM off_days")
    rows = cursor.fetchall()
    conn.close()
    
    inline_kb = []
    for day, is_off in rows:
        status_str = "🟢 Dam olish kuni" if is_off == 1 else "🔴 Ish kuni"
        inline_kb.append([InlineKeyboardButton(text=f"{day}: {status_str}", callback_data=f"toggle_{day}")])
        
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb))
    await callback.answer(f"{day_name} holati o'zgartirildi!")

@dp.message(F.text == "📊 Excel Hisobot Yuklash", F.from_user.id == ADMIN_ID)
async def export_excel(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    
    # 1-Varoq: Kunlik batafsil jadval
    df_daily = pd.read_sql_query("SELECT * FROM attendance", conn)
    
    # 2-Varoq: Oylik yakuniy hisob-kitoblar
    query_monthly = '''
        SELECT 
            e.full_name AS [Xodim F.I.Sh],
            COUNT(CASE WHEN a.status = 'completed' THEN 1 END) AS [Kelgan kunlari],
            SUM(a.late_minutes) AS [Jami kechikish (daqiqa)],
            SUM(a.lunch_over_minutes) AS [Jami obeddan kechikish],
            SUM(a.earned_today) AS [Jami hisoblangan maosh (so'm)]
        FROM employees e
        LEFT JOIN attendance a ON e.tg_id = a.tg_id
        GROUP BY e.tg_id
    '''
    df_monthly = pd.read_sql_query(query_monthly, conn)
    conn.close()
    
    file_path = "Hisobot_Sherin_Bakery.xlsx"
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df_daily.to_excel(writer, sheet_name='Kunlik Batafsil', index=False)
        df_monthly.to_excel(writer, sheet_name='Oylik Yakuniy Hisobot', index=False)
        
    file = types.FSInputFile(file_path)
    await message.answer_document(file, caption="📋 Sherin Bakery uchun tayyorlangan 2 varoqli (Kunlik va Oylik) yakuniy Excel hisoboti.")
    os.remove(file_path)

# --- XODIM HANDLERS ---
@dp.message(Command("start"), F.from_user.id != ADMIN_ID)
async def employee_start(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status, full_name FROM employees WHERE tg_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer("❌ Kechirasiz, siz tizimga xodim sifatida kiritilmagansiz. Adminga murojaat qiling.")
        return
        
    await message.answer(f"Salom {row[1]}! Tizimga xush kelibsiz. Quyidagi tugmalardan foydalaning.", reply_markup=get_employee_keyboard(row[0]))

@dp.message(F.location)
async def handle_location(message: types.Message):
    # Geofence tekshiruvi
    dist = calculate_distance(message.location.latitude, message.location.longitude, OFFICE_LAT, OFFICE_LON)
    if dist > ALLOWED_RADIUS_METERS:
        await message.answer(f"❌ Siz ofis hududida emassiz! (Masofa: {dist:.1f} metr). Ofisga kelib qaytadan urinib ko'ring.")
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status, daily_rate, minute_rate, full_name FROM employees WHERE tg_id = ?", (message.from_user.id,))
    emp = cursor.fetchone()
    
    if not emp:
        conn.close()
        return
        
    status, daily_rate, minute_rate, full_name = emp
    now_str = datetime.now().strftime("%H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if status == 'inactive':
        # ISHNI BOSHLASH
        now_time = datetime.now().time()
        late_minutes = 0
        
        # Kechikish mantiqi: 09:01 dan boshlab har bir daqiqa hisoblanadi
        if now_time > WORK_START_TIME:
            fmt = '%H:%M:%S'
            d1 = datetime.strptime(now_str, fmt)
            d2 = datetime.strptime("09:00:00", fmt)
            late_minutes = int((d1 - d2).total_seconds() / 60)
            
        # Agar xodim kechikkan bo'lsa, o'sha kunlik stavkadan minus qilinadi (Jahongir aka sharti bo'yicha kunidan minus qilish)
        earned_today = daily_rate - (late_minutes * minute_rate)
        if earned_today < 0: 
            earned_today = 0
            
        cursor.execute(
            "INSERT INTO attendance (tg_id, date, arrival_time, late_minutes, earned_today, status) VALUES (?, ?, ?, ?, ?, 'working')",
            (message.from_user.id, today_str, now_str, late_minutes, earned_today)
        )
        cursor.execute("UPDATE employees SET status = 'working' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        
        await message.answer(f"✅ Ish muvaffaqiyatli boshlandi!\n⏰ Vaqt: {now_str}\n⚠️ Kechikish: {late_minutes} daqiqa.", reply_markup=get_employee_keyboard('working'))
        # Adminga shaxsiy xabar
        await bot.send_message(ADMIN_ID, f"🟢 Xodim **{full_name}** {now_str} da ishni boshladi.\nKechikish: {late_minutes} daqiqa.")
        
    elif status == 'working':
        # ISHNI YAKUNLASH
        cursor.execute("UPDATE attendance SET departure_time = ?, status = 'completed' WHERE tg_id = ? AND date = ?", (now_str, message.from_user.id, today_str))
        cursor.execute("UPDATE employees SET status = 'inactive' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        
        await message.answer(f"🔴 Ish kuningiz yakunlandi. Rahmat!\n⏰ Vaqt: {now_str}", reply_markup=get_employee_keyboard('inactive'))
        await bot.send_message(ADMIN_ID, f"🔴 Xodim **{full_name}** {now_str} da ishni yakunladi.")
        
    elif status == 'lunch':
        # OBEDDAN QAYTISH
        cursor.execute("SELECT lunch_start, earned_today FROM attendance WHERE tg_id = ? AND date = ?", (message.from_user.id, today_str))
        row_attendance = cursor.fetchone()
        
        lunch_over_minutes = 0
        new_earned = row_attendance[1] if row_attendance else daily_rate
        
        if row_attendance and row_attendance[0]:
            fmt = '%H:%M:%S'
            d1 = datetime.strptime(now_str, fmt)
            d2 = datetime.strptime(row_attendance[0], fmt)
            total_lunch_minutes = int((d1 - d2).total_seconds() / 60)
            
            if total_lunch_minutes > OBED_LIMIT_MINUTES:
                lunch_over_minutes = total_lunch_minutes - OBED_LIMIT_MINUTES
                # Obeddan kechikilgan har bir daqiqa uchun oylikdan chegirib tashlanadi (Jahongir aka sharti)
                new_earned = new_earned - (lunch_over_minutes * minute_rate)
                if new_earned < 0: 
                    new_earned = 0
                    
        cursor.execute(
            "UPDATE attendance SET lunch_end = ?, lunch_over_minutes = ?, earned_today = ? WHERE tg_id = ? AND date = ?",
            (now_str, lunch_over_minutes, new_earned, message.from_user.id, today_str)
        )
        cursor.execute("UPDATE employees SET status = 'working' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        
        await message.answer(f"↩ Obeddan qaytdingiz. Ish davom etadi.\n⚠️ Obeddan oshib ketgan vaqt: {lunch_over_minutes} daqiqa.", reply_markup=get_employee_keyboard('working'))
        await bot.send_message(ADMIN_ID, f"↩ Xodim **{full_name}** obeddan qaytdi. Oshib ketgan vaqt: {lunch_over_minutes} daqiqa.")
        
    conn.close()

@dp.message(F.text == "🍽 Obedga chiqish")
async def handle_lunch_start(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status, full_name FROM employees WHERE tg_id = ?", (message.from_user.id,))
    emp = cursor.fetchone()
    
    if emp and emp[0] == 'working':
        now_str = datetime.now().strftime("%H:%M:%S")
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute("UPDATE attendance SET lunch_start = ? WHERE tg_id = ? AND date = ?", (now_str, message.from_user.id, today_str))
        cursor.execute("UPDATE employees SET status = 'lunch' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        
        await message.answer(f"🍽 Obed vaqti boshlandi. Yoqimli ishtaha!\nLimit: {OBED_LIMIT_MINUTES} daqiqa.", reply_markup=get_employee_keyboard('lunch'))
        await bot.send_message(ADMIN_ID, f"🍽 Xodim **{emp[1]}** {now_str} da obedga chiqdi.")
        
    conn.close()

# 4. AVTOMATIK KUN YAKUNI VA JAZOLASH TIZIMI (SOAT 23:00 DA ISHLAYDI)
async def auto_daily_cron():
    while True:
        now = datetime.now()
        # Har kuni soat 23:00 da tekshiradi
        if now.hour == 23 and now.minute == 0:
            current_day_name = now.strftime('%A')
            # Kun nomini o'zbekchaga o'girish
            days_uz = {
                'Monday': 'Dushanba', 'Tuesday': 'Seshanba', 'Wednesday': 'Chorshanba',
                'Thursday': 'Payshanba', 'Friday': 'Juma', 'Saturday': 'Shanba', 'Sunday': 'Yakshanba'
            }
            uz_day = days_uz.get(current_day_name, 'Yakshanba')
            
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            
            # Bugun dam olish kunimi tekshirish
            cursor.execute("SELECT is_off FROM off_days WHERE day_name = ?", (uz_day,))
            is_off_row = cursor.fetchone()
            
            if is_off_row and is_off_row[0] == 1:
                # Agar bugun dam olish kuni bo'lsa, tizim hech kimni jazolamaydi
                conn.close()
                await asyncio.sleep(60)
                continue
                
            today_str = now.strftime("%Y-%m-%d")
            cursor.execute("SELECT tg_id, full_name, daily_rate FROM employees")
            all_employees = cursor.fetchall()
            
            for emp in all_employees:
                tg_id, full_name, daily_rate = emp
                cursor.execute("SELECT id FROM attendance WHERE tg_id = ? AND date = ?", (tg_id, today_str))
                attendance_row = cursor.fetchone()
                
                # Agar xodim umuman kelmagan yoki kunni yopmagan bo'lsa (Jahongir aka sharti - B variant)
                if not attendance_row:
                    cursor.execute(
                        "INSERT INTO attendance (tg_id, date, status, earned_today) VALUES (?, ?, 'absent', 0)",
                        (tg_id, today_str)
                    )
                    # Xodimning statusini qayta inactive holatga tushiramiz
                    cursor.execute("UPDATE employees SET status = 'inactive' WHERE tg_id = ?", (tg_id,))
                    
                    try:
                        await bot.send_message(tg_id, "⚠️ Siz bugun ishga kelmadingiz yoki tizimda kunni yakunlamadingiz. Bugungi kun uchun ish haqi yozilmadi.")
                    except Exception:
                        pass
                        
            conn.commit()
            conn.close()
            await bot.send_message(ADMIN_ID, "🌙 Kun yakunlandi. Kelmagan yoki ishni yakunlamagan xodimlarga avtomatic 'Kelmagan' (absent) status berildi va kunlik maosh yozilmadi.")
            
        await asyncio.sleep(60)  # Har minutda tekshirib turadi

# 5. RENDER UCHUN FASTAPI WEB SERVER (PING SYSTEM & LIVE DASHBOARD)
app = FastAPI()

@app.get("/")
def read_root():
    # Jonli dashboard ma'lumotlarini bazadan o'qib brauzerda ko'rsatish
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT e.full_name, e.status, a.arrival_time, a.late_minutes, a.earned_today 
        FROM employees e
        LEFT JOIN attendance a ON e.tg_id = a.tg_id AND a.date = date('now')
    ''')
    rows = cursor.fetchall()
    conn.close()
    
    html_content = "<html><head><title>Sherin Bakery - Live Dashboard</title></head><body style='font-family:sans-serif; padding:20px; background:#f4f6f9;'>"
    html_content += "<h1 style='color:#333;'>🧁 Sherin Bakery - Jonli Dashboard</h1>"
    html_content += "<p>Render server holati: 🟢 Faol (Bot o'chib qolmaydi)</p>"
    html_content += "<table border='1' cellpadding='10' style='border-collapse:collapse; background:#fff; width:100%; max-width:800px;'>"
    html_content += "<tr style='background:#007bff; color:#fff;'><th>Xodim</th><th>Holat</th><th>Kelgan vaqti</th><th>Kechikish (min)</th><th>Bugungi daromad</th></tr>"
    
    for r in rows:
        arrival = r[2] if r[2] else "-"
        late = r[3] if r[3] is not None else "-"
        earned = f"{r[4]:,.2f} so'm" if r[4] is not None else "-"
        html_content += f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{arrival}</td><td>{late}</td><td>{earned}</td></tr>"
        
    html_content += "</table></body></html>"
    return types.Response(content=html_content, media_type="text/html")

async def run_bot():
    asyncio.create_task(auto_daily_cron())  # Kunlik jazo cronini parallel ishga tushirish
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Server portini olish (Render talabi bo'yicha)
    port = int(os.environ.get("PORT", 8000))
    
    # Botni FastAPI bilan birga asynchronous ishga tushirish
    loop = asyncio.get_event_loop()
    loop.create_task(run_bot())
    
    uvicorn.run(app, host="0.0.0.0", port=port)
