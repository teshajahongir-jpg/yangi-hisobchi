import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- SOZLAMALAR ---
BOT_TOKEN = "8680299057:AAFZwPMCzPYsjIlL_zPXKgKuvKkYP4zLEO0"
ADMIN_ID = 8252424738  # O'zingizning Telegram ID-ingizni yozing
# Rasm URL-i yoki Telegram yuklangan rasmning file_id si
START_PHOTO = "https://images.unsplash.com/photo-1542838132-92c53300491e" 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- MA'LUMOTLAR BAZASI (SQLite) ---
def init_db():
    conn = sqlite3.connect("namoz_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            daily_limit INTEGER DEFAULT 5
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER,
            date TEXT,
            bomdod INTEGER DEFAULT 0,
            peshin INTEGER DEFAULT 0,
            asr INTEGER DEFAULT 0,
            shom INTEGER DEFAULT 0,
            xufton INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- KLAVIATURALAR ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🕌 Namozlarni belgilash")
    builder.button(text="📊 Hisobot olish")
    builder.button(text="⚙️ Kunlik limit")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

def prayers_inline(user_id):
    date_str = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("namoz_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT bomdod, peshin, asr, shom, xufton FROM stats WHERE user_id=? AND date=?", (user_id, date_str))
    row = cursor.fetchone()
    conn.close()

    if not row:
        row = (0, 0, 0, 0, 0)

    builder = InlineKeyboardBuilder()
    prayers = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]
    for i, prayer in enumerate(prayers):
        status = "✅" if row[i] == 1 else "❌"
        builder.button(text=f"{prayer} {status}", callback_data=f"toggle_{prayer.lower()}")
    
    builder.adjust(2, 3)
    return builder.as_markup()

# --- FSM (Holatlar) ---
class Form(StatesGroup):
    set_limit = State()

# --- BOT FUNKSIYALARI ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Foydalanuvchi"
    
    # Foydalanuvchini bazaga qo'shish
    conn = sqlite3.connect("namoz_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

    # Rasm va matn bilan start berish
    await message.answer_photo(
        photo=START_PHOTO,
        caption="<b>Jahongir akadan foydalisi</b>\n\nBotga xush kelibsiz! Quyidagi tugmalardan foydalaning:",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

@dp.message(F.text == "🕌 Namozlarni belgilash")
async def show_prayers(message: types.Message):
    await message.answer("Bugungi namozlaringizni belgilang:", reply_markup=prayers_inline(message.from_user.id))

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_prayer(callback: types.CallbackQuery):
    prayer = callback.data.split("_")[1]
    user_id = callback.from_user.id
    date_str = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("namoz_bot.db")
    cursor = conn.cursor()
    
    # Bugungi kun uchun qator bormligini tekshirish
    cursor.execute("INSERT OR IGNORE INTO stats (user_id, date) VALUES (?, ?)", (user_id, date_str))
    
    # Joriy holatni o'zgartirish (0 edi -> 1 bo'ladi, 1 edi -> 0)
    cursor.execute(f"UPDATE stats SET {prayer} = NOT {prayer} WHERE user_id=? AND date=?", (user_id, date_str))
    conn.commit()
    conn.close()

    await callback.message.edit_reply_markup(reply_markup=prayers_inline(user_id))
    await callback.answer("Holat yangilandi!")

@dp.message(F.text == "📊 Hisobot olish")
async def get_report(message: types.Message):
    user_id = message.from_user.id
    date_str = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("namoz_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT bomdod, peshin, asr, shom, xufton FROM stats WHERE user_id=? AND date=?", (user_id, date_str))
    row = cursor.fetchone()
    cursor.execute("SELECT daily_limit FROM users WHERE user_id=?", (user_id,))
    limit_row = cursor.fetchone()
    conn.close()

    limit = limit_row[0] if limit_row else 5
    
    if not row:
        total_read = 0
        details = "Hali birorta namoz belgilanmagan."
    else:
        total_read = sum(row)
        prayers = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]
        details = "\n".join([f"-{prayers[i]}: {'O`qildi ✅' if row[i]==1 else 'O`qilmadi ❌'}" for i in range(5)])

    report_msg = (
        f"📅 <b>Bugungi hisobotiz:</b>\n\n"
        f"{details}\n\n"
        f"🎯 Kunlik limit (maqsad): {limit} ta namoz\n"
        f"📊 O'qilgan namozlar: {total_read} ta\n"
    )
    if total_read >= limit:
        report_msg += "\n🎉 Baranalloh! Kunlik limit bajarildi!"
        
    await message.answer(report_msg, parse_mode="HTML")

@dp.message(F.text == "⚙️ Kunlik limit")
async def limit_setting(message: types.Message, state: FSMContext):
    await message.answer("Kunlik namoz o'qish limitini kiriting (Masalan: 5):")
    await state.set_state(Form.set_limit)

@dp.message(Form.set_limit)
async def process_limit(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting:")
        return

    limit = int(message.text)
    conn = sqlite3.connect("namoz_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET daily_limit = ? WHERE user_id = ?", (limit, message.from_user.id))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"✅ Kunlik limit {limit} ta namoz qilib belgilandi.", reply_markup=main_menu())

# --- AVTOMATIK ESLAТMA (Har bir namozdan keyin so'rash) ---
async def send_prayer_reminder():
    conn = sqlite3.connect("namoz_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    for user in users:
        try:
            await bot.send_message(
                chat_id=user[0], 
                text="🔔 <b>Namoz vaqti bo'ldi/o'tdi. Namozlarni o'qib oldingizmi?</b>\nBelgilash uchun 'Namozlarni belgilash' tugmasini bosing.",
                parse_mode="HTML"
            )
        except Exception:
            pass # Botni bloklagan foydalanuvchilarda xatolik bermasligi uchun

# Schedulerni sozlash (Namoz vaqtlariga qarab soatlarini o'zgartirishingiz mumkin)
# Masalan, quyida eslatma namuna sifatida har kuni soat 06:00, 13:00, 17:00, 19:30 va 21:00 da ketadi.
scheduler.add_job(send_prayer_reminder, 'cron', hour=6, minute=0)
scheduler.add_job(send_prayer_reminder, 'cron', hour=13, minute=0)
scheduler.add_job(send_prayer_reminder, 'cron', hour=17, minute=0)
scheduler.add_job(send_prayer_reminder, 'cron', hour=19, minute=30)
scheduler.add_job(send_prayer_reminder, 'cron', hour=21, minute=0)

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
