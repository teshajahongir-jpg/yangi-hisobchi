import os
import math
import logging
import asyncio
from datetime import datetime, time
import sqlite3
import pandas as pd

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from fastapi import FastAPI
import uvicorn

# =============================================
# 1. SOZLAMALAR — bu yerlarni o'zgartiring!
# =============================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "TOKEN_NI_BU_YERGA_YOZING")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))  # O'z Telegram ID-ingizni yozing

OFFICE_LAT = 39.7747
OFFICE_LON = 64.4286
ALLOWED_RADIUS_METERS = 100.0

WORK_START_TIME = time(9, 0)
OBED_LIMIT_MINUTES = 60

logging.basicConfig(level=logging.INFO)
DB_FILE = "attendance_system.db"

# =============================================
# 2. MA'LUMOTLAR BAZASI
# =============================================
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
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# =============================================
# 3. BOT
# =============================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class EmployeeForm(StatesGroup):
    tg_id = State()
    full_name = State()
    salary = State()

def get_admin_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 Xodimlar Ro'yxati"), KeyboardButton(text="➕ Xodim Qo'shish")],
        [KeyboardButton(text="📊 Excel Hisobot Yuklash"), KeyboardButton(text="⚙ Dam olish kunlari")]
    ], resize_keyboard=True)

def get_employee_keyboard(status):
    if status == 'inactive':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🟢 Ishni boshlash", request_location=True)]
        ], resize_keyboard=True)
    elif status == 'working':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🍽 Obedga chiqish")],
            [KeyboardButton(text="⏰ Qo'shimcha ishlash")],
            [KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
        ], resize_keyboard=True)
    elif status == 'lunch':
        return ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📴 Obeddan qaytish", request_location=True)]
        ], resize_keyboard=True)
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔄 Yangilash")]], resize_keyboard=True)

def get_employee(tg_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status, daily_rate, minute_rate, full_name FROM employees WHERE tg_id = ?", (tg_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# =============================================
# 4. HANDLERLAR
# =============================================

# --- /start ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Xush kelibsiz, Admin!", reply_markup=get_admin_keyboard())
        return

    emp = get_employee(message.from_user.id)
    if not emp:
        await message.answer("❌ Siz tizimga xodim sifatida kiritilmagansiz.")
        return
    await message.answer(f"Salom, {emp[3]}!", reply_markup=get_employee_keyboard(emp[0]))

# --- Xodimlar ro'yxati ---
@dp.message(F.text == "👥 Xodimlar Ro'yxati", F.from_user.id == ADMIN_ID)
async def list_employees(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id, full_name, monthly_salary, status FROM employees")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("Hech qanday xodim yo'q.")
        return

    text = "👥 *Xodimlar ro'yxati:*\n\n"
    for r in rows:
        emoji = "🟢" if r[3] == 'working' else "🔴"
        text += f"{emoji} {r[1]} | ID: `{r[0]}` | Maosh: {r[2]:,.0f} so'm\n"
    await message.answer(text, parse_mode="Markdown")

# --- Xodim qo'shish ---
@dp.message(F.text == "➕ Xodim Qo'shish", F.from_user.id == ADMIN_ID)
async def add_emp(message: types.Message, state: FSMContext):
    await message.answer("Xodim Telegram ID raqamini kiriting:")
    await state.set_state(EmployeeForm.tg_id)

@dp.message(EmployeeForm.tg_id)
async def add_emp_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting!")
        return
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
    try:
        salary = float(message.text)
    except ValueError:
        await message.answer("❌ Faqat raqam kiriting!")
        return

    data = await state.get_data()
    daily_rate = salary / 26
    minute_rate = daily_rate / 540

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO employees (tg_id, full_name, monthly_salary, daily_rate, minute_rate, status) VALUES (?, ?, ?, ?, ?, 'inactive')",
        (data['tg_id'], data['full_name'], salary, daily_rate, minute_rate)
    )
    conn.commit()
    conn.close()

    await message.answer(f"✅ {data['full_name']} tizimga qo'shildi!", reply_markup=get_admin_keyboard())
    await state.clear()

# --- Dam olish kunlari ---
@dp.message(F.text == "⚙ Dam olish kunlari", F.from_user.id == ADMIN_ID)
async def off_days_menu(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT day_name, is_off FROM off_days")
    rows = cursor.fetchall()
    conn.close()

    text = "📅 *Dam olish kunlari:*\n\n"
    for day, is_off in rows:
        mark = "✅ Dam olish" if is_off else "💼 Ish kuni"
        text += f"{day}: {mark}\n"

    # Inline tugmalar
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for day, is_off in rows:
        label = f"{'✅' if is_off else '💼'} {day}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"toggle_day:{day}")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=markup)

@dp.callback_query(F.data.startswith("toggle_day:"))
async def toggle_day(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    day = callback.data.split(":")[1]
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_off FROM off_days WHERE day_name = ?", (day,))
    current = cursor.fetchone()[0]
    new_val = 0 if current else 1
    cursor.execute("UPDATE off_days SET is_off = ? WHERE day_name = ?", (new_val, day))
    conn.commit()
    conn.close()
    await callback.answer(f"{day} {'dam olish kuni' if new_val else 'ish kuni'} qilindi.")
    await off_days_menu(callback.message)

# --- Excel hisobot ---
@dp.message(F.text == "📊 Excel Hisobot Yuklash", F.from_user.id == ADMIN_ID)
async def export_excel(message: types.Message):
    conn = sqlite3.connect(DB_FILE)
    df_daily = pd.read_sql_query("""
        SELECT e.full_name, a.date, a.arrival_time, a.departure_time,
               a.late_minutes, a.lunch_over_minutes, a.earned_today, a.status
        FROM attendance a
        JOIN employees e ON a.tg_id = e.tg_id
    """, conn)
    df_monthly = pd.read_sql_query("""
        SELECT e.full_name, SUM(a.late_minutes) as Kechikish_min,
               SUM(a.earned_today) as Jami_Maosh
        FROM attendance a
        JOIN employees e ON a.tg_id = e.tg_id
        GROUP BY a.tg_id
    """, conn)
    conn.close()

    file_path = "Attendance_Report.xlsx"
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df_daily.to_excel(writer, sheet_name='Kunlik', index=False)
        df_monthly.to_excel(writer, sheet_name='Oylik', index=False)

    await message.answer_document(types.FSInputFile(file_path), caption="📊 Hisobot tayyor!")
    os.remove(file_path)

# --- LOKATSIYA HANDLERLARI ---

# Ishni boshlash (inactive → working)
@dp.message(F.location, F.from_user.id != ADMIN_ID)
async def process_location(message: types.Message):
    dist = calculate_distance(
        message.location.latitude, message.location.longitude,
        OFFICE_LAT, OFFICE_LON
    )
    if dist > ALLOWED_RADIUS_METERS:
        await message.answer(f"❌ Ofis hududida emassiz!\nMasofa: {dist:.0f} m (ruxsat: {ALLOWED_RADIUS_METERS:.0f} m)")
        return

    emp = get_employee(message.from_user.id)
    if not emp:
        await message.answer("❌ Siz tizimda yo'qsiz.")
        return

    status, daily_rate, minute_rate, full_name = emp
    now_str = datetime.now().strftime("%H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # --- Ishni boshlash ---
    if status == 'inactive':
        now_time = datetime.now().time()
        late_minutes = 0
        if now_time > WORK_START_TIME:
            d1 = datetime.strptime(now_str, '%H:%M:%S')
            d2 = datetime.strptime("09:00:00", '%H:%M:%S')
            late_minutes = int((d1 - d2).total_seconds() / 60)

        earned = max(0, daily_rate - (late_minutes * minute_rate))

        cursor.execute(
            "INSERT INTO attendance (tg_id, date, arrival_time, late_minutes, earned_today, status) VALUES (?, ?, ?, ?, ?, 'working')",
            (message.from_user.id, today_str, now_str, late_minutes, earned)
        )
        cursor.execute("UPDATE employees SET status = 'working' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()

        late_text = f"⚠️ Kechikish: {late_minutes} min." if late_minutes > 0 else "✅ O'z vaqtida keldingiz!"
        await message.answer(f"🟢 Ish boshlandi!\nVaqt: {now_str}\n{late_text}", reply_markup=get_employee_keyboard('working'))
        await bot.send_message(ADMIN_ID, f"🟢 {full_name} ishga keldi. Kechikish: {late_minutes} min.")

    # --- Obeddan qaytish ---
    elif status == 'lunch':
        cursor.execute("SELECT lunch_start FROM attendance WHERE tg_id = ? AND date = ?", (message.from_user.id, today_str))
        row = cursor.fetchone()
        lunch_over = 0
        if row and row[0]:
            ls = datetime.strptime(row[0], '%H:%M:%S')
            le = datetime.strptime(now_str, '%H:%M:%S')
            diff = int((le - ls).total_seconds() / 60)
            if diff > OBED_LIMIT_MINUTES:
                lunch_over = diff - OBED_LIMIT_MINUTES

        cursor.execute(
            "UPDATE attendance SET lunch_end = ?, lunch_over_minutes = ?, status = 'working' WHERE tg_id = ? AND date = ?",
            (now_str, lunch_over, message.from_user.id, today_str)
        )
        cursor.execute("UPDATE employees SET status = 'working' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()

        over_text = f"⚠️ Obed oshib ketdi: {lunch_over} min!" if lunch_over > 0 else "✅ Obed vaqtida!"
        await message.answer(f"✅ Obeddan qaytdingiz!\nVaqt: {now_str}\n{over_text}", reply_markup=get_employee_keyboard('working'))

    # --- Ishni yakunlash ---
    elif status == 'working':
        cursor.execute(
            "UPDATE attendance SET departure_time = ?, status = 'completed' WHERE tg_id = ? AND date = ?",
            (now_str, message.from_user.id, today_str)
        )
        cursor.execute("UPDATE employees SET status = 'inactive' WHERE tg_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()

        await message.answer(f"🔴 Ish kuni yakunlandi!\nVaqt: {now_str}", reply_markup=get_employee_keyboard('inactive'))
        await bot.send_message(ADMIN_ID, f"🔴 {full_name} ishni yakunladi. Vaqt: {now_str}")

    else:
        conn.close()

# --- Obedga chiqish ---
@dp.message(F.text == "🍽 Obedga chiqish")
async def lunch_start(message: types.Message):
    emp = get_employee(message.from_user.id)
    if not emp or emp[0] != 'working':
        await message.answer("❌ Siz hozir ish rejimida emassiz.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%H:%M:%S")
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("UPDATE attendance SET lunch_start = ? WHERE tg_id = ? AND date = ?", (now_str, message.from_user.id, today_str))
    cursor.execute("UPDATE employees SET status = 'lunch' WHERE tg_id = ?", (message.from_user.id,))
    conn.commit()
    conn.close()
    await message.answer(f"🍽 Obed boshlandi! Vaqt: {now_str}\n⏱ {OBED_LIMIT_MINUTES} minutdan oshirmang.", reply_markup=get_employee_keyboard('lunch'))

# --- Qo'shimcha ishlash ---
@dp.message(F.text == "⏰ Qo'shimcha ishlash")
async def overtime_click(message: types.Message):
    emp = get_employee(message.from_user.id)
    if not emp:
        return
    await message.answer("🚀 Qo'shimcha ish vaqti yoqildi! Tizim davom ettiradi.")
    await bot.send_message(ADMIN_ID, f"⏰ {emp[3]} qo'shimcha ish rejimini faollashtirdi.")

# =============================================
# 5. FASTAPI + ISHGA TUSHIRISH
# =============================================
app = FastAPI()

@app.get("/")
def home():
    return {"status": "running", "bot": "Attendance Bot"}

async def run_bot():
    await dp.start_polling(bot)

async def run_web():
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    await asyncio.gather(
        run_bot(),
        run_web()
    )

if __name__ == "__main__":
    asyncio.run(main())
