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

# 1. TIZIM SOZLAMALARI
BOT_TOKEN = "8852324677:AAGd23at2DC_UwuYUQqozpybs2KFPPYfk8c"  # Sizning faol tokeningiz
ADMIN_ID = 123456789  # Bu yerga shaxsiy Telegram ID-angizni yozing

# Ofis koordinatalari (Geofence) va ruxsat etilgan radius (metrda)
OFFICE_LAT = 39.7747
OFFICE_LON = 64.4286
ALLOWED_RADIUS_METERS = 100.0  # GPS adashmasligi uchun 100 metr qildik

WORK_START_TIME = time(9, 0)
OBED_LIMIT_MINUTES = 60

logging.basicConfig(level=logging.INFO)
DB_FILE = "attendance_system.db"

# 2. MA'LUMOTLAR BAZASI
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
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
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            date TEXT,
            arrival_time TEXT,
            departure_time TEXT,
            lunch_start TEXT,
            lunch_end TEXT,
            overtime_minutes INTEGER DEFAULT 0,
            late_minutes INTEGER DEFAULT 0,
            lunch_over_minutes INTEGER DEFAULT 0,
            earned_today REAL DEFAULT 0,
            status TEXT,
            FOREIGN KEY(tg_id) REFERENCES employees(tg_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS off_days (
            day_name TEXT PRIMARY KEY,
            is_off INTEGER DEFAULT 0
        )
    ''')
    
    days = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba']
    for day in days:
        is_off_val = 1 if day == 'Yakshanba' else 0
        cursor.execute("INSERT OR IGNORE INTO off_days (day_name, is_off) VALUES (?, ?)", (day, is_off_val))
        
    conn.commit()
    conn.close()

init_db()

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

# 3. TELEGRAM BOT SOZLAMALARI
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class EmployeeForm(StatesGroup):
    tg_id = State()
    full_name = State()
    salary = State()

def get_admin_keyboard():
    kb = [
        [KeyboardButton(text="👥 Xodimlar Ro'yxati"), KeyboardButton(text="➕ Xodim Qo'shish")],
        [KeyboardButton(text="📊 Excel Hisobot Yuklash"), KeyboardButton(text="⚙ Dam olish kunlari")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_employee_keyboard(status):
    if status == 'inactive':
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🟢 Ishni boshlash", request_location=True)]], resize_keyboard=True)
    elif status == 'working':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🍽 Obedga chiqish"), KeyboardButton(text="📴 Obeddan qaytish", request_location=True)],
            [KeyboardButton(text="⏰ Qo'shimcha ishlash"), KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
        ], resize_keyboard=True)
    elif status == 'lunch':
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📴 Obeddan qaytish", request_location=True)]], resize_keyboard=True)
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔄 Yangilash")]], resize_keyboard=True)

# --- HANDLERS ---
@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def admin_start(message: types.Message):
    await message.answer("Xush kelibsiz, Jahongir aka!", reply_markup=get_admin_keyboard())

@dp.message(Command("start"), F.from_user.id != ADMIN_ID)
async def emp_start(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status, full_name FROM employees WHERE tg_id = ?", (message.from_user.id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        await message.answer("❌ Siz tizimga xodim sifatida kiritilmagansiz.")
        return
    await message.answer(f"Salom {row[1]}!", reply_markup=get_employee_keyboard(row[0]))

@dp.message(F.text == "➕ Xodim Qo'shish", F.from_user.id == ADMIN_ID)
async def add_emp(message: types.Message, state: FSMContext):
    await message.answer("Xodim Telegram ID raqamini kiriting:")
    await state.set_state(EmployeeForm.tg_id)

@dp.message(EmployeeForm.tg_id)
async def add_emp_id(message: types.Message, state: FSMContext):
    await state.update_data(tg_id=int(message.text))
    await message.answer("Xodim Ismi va Familiyasini kiriting:")
    await state.set_state(EmployeeForm.full_name)

@dp.message(EmployeeForm.full_name)
async def add_emp_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Oylik maoshini kiriting (faqat raqam):")
    await state.set_state(EmployeeForm.salary)

@dp.message(EmployeeForm.salary)
async def add_emp_salary(message: types.Message, state: FSMContext):
    salary = float(message.text)
    data = await state.get_data()
    daily_rate = salary / 26
    minute_rate = daily_rate / 540
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO employees (tg_id, full_name, monthly_salary, daily_rate, minute_rate) VALUES (?, ?, ?, ?, ?)",
                   (data['tg_id'], data['full_name'], salary, daily_rate, minute_rate))
    conn.commit()
    conn.close()
    
    await message.answer("✅ Xodim qo'shildi!", reply_markup=get_admin_keyboard())
    await state.clear()

@dp.message(F.location)
async def process_location(message: types.Message):
    dist = calculate_distance(message.location.latitude, message.location.longitude, OFFICE_LAT, OFFICE_LON)
    if dist > ALLOWED_RADIUS_METERS:
        await message.answer(f"❌ Ofis hududida emassiz! (Masofa: {dist:.1f} m)")
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
        now_time = datetime.now().time()
        late_minutes = 0
        if now_time > WORK_START_TIME:
            d1 = datetime.strptime(now_str, '%H:%M:%S')
            d2 = datetime.strptime("09:00:00", '%H:%M:%S')
            late_minutes = int((d1 - d2).total_seconds() / 60)
            
        earned = daily_rate - (late_minutes * minute_rate)
        earned = max(0, earned)
        
        cursor.execute("INSERT INTO attendance (tg_id, date, arrival_time, late_minutes, earned_today, status) VALUES (?, ?, ?, ?, ?, 'working')",
                       (message.from_user.id, today_str, now_str, late_minutes, earned))
        cursor.execute("UPDATE employees SET status = 'working' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        
        await message.answer(f"✅ Ish boshlandi. Vaqt: {now_str}\n⚠️ Kechikish: {late_minutes} minut.", reply_markup=get_employee_keyboard('working'))
        await bot.send_message(ADMIN_ID, f"🟢 Xodim {full_name} ishga keldi. Kechikish: {late_minutes} min.")
        
    elif status == 'working' and message.text == "🔴 Ishni yakunlash":
        cursor.execute("UPDATE attendance SET departure_time = ?, status = 'completed' WHERE tg_id = ? AND date = ?", (now_str, message.from_user.id, today_str))
        cursor.execute("UPDATE employees SET status = 'inactive' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        await message.answer("🔴 Ish kuni yakunlandi!", reply_markup=get_employee_keyboard('inactive'))
        await bot.send_message(ADMIN_ID, f"🔴 Xodim {full_name} ishni yakunladi.")
        
    conn.close()

@dp.message(F.text == "🍽 Obedga chiqish")
async def lunch_start(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("UPDATE attendance SET lunch_start = ? WHERE tg_id = ? AND date = ?", (now_str, message.from_user.id, today_str))
    cursor.execute("UPDATE employees SET status = 'lunch' WHERE tg_id = ?", (message.from_user.id,))
    conn.commit()
    conn.close()
    await message.answer("🍽 Obed boshlandi.", reply_markup=get_employee_keyboard('lunch'))

@dp.message(F.text == "⏰ Qo'shimcha ishlash")
async def overtime_click(message: types.Message):
    await message.answer("🚀 Qo'shimcha ish vaqti muvaffaqiyatli yoqildi! Tizim soatbay hisoblashni davom ettiradi.")
    await bot.send_message(ADMIN_ID, f"⏰ Xodim **ID:{message.from_user.id}** qo'shimcha ish rejimini faollashtirdi.")

@dp.message(F.text == "📊 Excel Hisobot Yuklash", F.from_user.id == ADMIN_ID)
async def export_excel(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    df_daily = pd.read_sql_query("SELECT * FROM attendance", conn)
    df_monthly = pd.read_sql_query("SELECT tg_id, SUM(late_minutes) as [Kechikish], SUM(earned_today) as [Maosh] FROM attendance GROUP BY tg_id", conn)
    conn.close()
    
    file_path = "Sherin_Report.xlsx"
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df_daily.to_excel(writer, sheet_name='Kunlik', index=False)
        df_monthly.to_excel(writer, sheet_name='Oylik', index=False)
        
    await message.answer_document(types.FSInputFile(file_path))
    os.remove(file_path)

# 4. FASTAPI WEB SERVER (RENDER PIPELINE UCHUN)
app = FastAPI()

@app.get("/")
def home():
    return {"status": "running", "bot": "Sherin Bakery Attendance System"}

async def main():
    asyncio.create_task(dp.start_polling(bot))
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
