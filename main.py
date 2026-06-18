import os
import asyncio
import logging
from datetime import datetime
import io

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import openpyxl
from aiohttp import web

# --- ⚙️ ASOSIY SOZLAMALAR ---
BOT_TOKEN = "8680299057:AAGhTu75PnTJsbfn-nOuLOQZ2aE9O-BTC5g"
ADMIN_ID = 8252424738  # O'zingizning Telegram ID-ingizni yozing
START_PHOTO = "https://images.unsplash.com/photo-1542838132-92c53300491e"  # Jahongir aka, o'zingizni rasmingiz URL manzilini qo'ying

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
DB_NAME = "database_v2.db"

# --- 🗄 ASINXRON MA'LUMOTLAR BAZASINI YARATISH ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                daily_limit INTEGER DEFAULT 5
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS finance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                category TEXT,
                amount REAL,
                date TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS prayer_stats (
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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                name TEXT,
                amount REAL,
                date TEXT
            )
        ''')
        await db.commit()

# --- ⌨️ TUGMALAR (REPLY & INLINE KEYBOARDS) ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Kirim qo'shish")
    builder.button(text="❌ Chiqim qo'shish")
    builder.button(text="📊 Bugungi hisobot")
    builder.button(text="📅 Oylik hisobot")
    builder.button(text="🕌 Namoz vaqtlari")
    builder.button(text="🎯 Kunlik limit qo'shish")
    builder.button(text="📓 Qarzlar daftari")
    builder.button(text="📥 Excel Eksport")
    builder.button(text="ℹ️ Yordam (Qo'llanma)")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def finance_categories(action_type: str):
    builder = InlineKeyboardBuilder()
    categories = ["Oziq-ovqat", "Transport", "Kiyim", "Biznes", "Ijara", "Boshqa"] if action_type == "chiqim" else ["Oylik", "Biznes", "Xizmat ko'rsatish", "Boshqa"]
    for cat in categories:
        builder.button(text=cat, callback_data=f"cat_{action_type}_{cat}")
    builder.adjust(2)
    return builder.as_markup()

async def prayers_inline(user_id: int, date_str: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT bomdod, peshin, asr, shom, xufton FROM prayer_stats WHERE user_id=? AND date=?", (user_id, date_str)) as cursor:
            row = await cursor.fetchone()
    if not row:
        row = (0, 0, 0, 0, 0)
    
    builder = InlineKeyboardBuilder()
    prayers = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]
    for i, prayer in enumerate(prayers):
        status = "✅" if row[i] == 1 else "❌"
        builder.button(text=f"{prayer} {status}", callback_data=f"pray_{prayer.lower()}")
    builder.adjust(2, 3)
    return builder.as_markup()

def debt_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Menga qarz berishdi", callback_data="debt_take")
    builder.button(text="💸 Men qarz berdim", callback_data="debt_give")
    builder.button(text="📜 Qarzlar ro'yxati", callback_data="debt_list")
    builder.adjust(1)
    return builder.as_markup()

# --- 🎭 FSM HOLATLARI (STATE) ---
class BotStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_limit = State()
    waiting_for_debt_name = State()
    waiting_for_debt_amount = State()

# --- 🚀 HANDLERLAR ---

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Foydalanuvchi"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        await db.commit()

    await message.answer_photo(
        photo=START_PHOTO,
        caption="<b>Jahongir akadan foydalisi</b>\n\nBotimizga xush kelibsiz! Quyidagi menyudan kerakli bo'limni tanlang:",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

# Moliya jarayoni (Kirim/Chiqim)
@dp.message(F.text.in_({"➕ Kirim qo'shish", "❌ Chiqim qo'shish"}))
async def finance_handler(message: types.Message, state: FSMContext):
    action = "kirim" if "Kirim" in message.text else "chiqim"
    await state.update_data(action_type=action)
    await message.answer(f"Kategoriyani tanlang:", reply_markup=finance_categories(action))

@dp.callback_query(F.data.startswith("cat_"))
async def category_callback(callback: types.CallbackQuery, state: FSMContext):
    _, action_type, category = callback.data.split("_")
    await state.update_data(category=category)
    await callback.message.edit_text(f"Kategoriya: <b>{category}</b>\nSumni kiriting (Faqat raqamda, masalan: 50000):", parse_mode="HTML")
    await state.set_state(BotStates.waiting_for_amount)
    await callback.answer()

@dp.message(BotStates.waiting_for_amount)
async def amount_handler(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat musbat raqam kiriting:")
        return
    
    amount = float(message.text)
    data = await state.get_data()
    date_str = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO finance (user_id, type, category, amount, date) VALUES (?, ?, ?, ?, ?)",
            (message.from_user.id, data['action_type'], data['category'], amount, date_str)
        )
        await db.commit()

    await state.clear()
    await message.answer(f"✅ Muvaffaqiyatli saqlandi!\n💰 Summa: {amount:,.0f} so'm", reply_markup=main_menu())

# Kunlik Limit
@dp.message(F.text == "🎯 Kunlik limit qo'shish")
async def set_limit_start(message: types.Message, state: FSMContext):
    await message.answer("Kunlik namoz o'qish limitini (maqsadini) raqamda kiriting (Masalan: 5):")
    await state.set_state(BotStates.waiting_for_limit)

@dp.message(BotStates.waiting_for_limit)
async def set_limit_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat raqam kiriting:")
        return
    limit = int(message.text)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET daily_limit = ? WHERE user_id = ?", (limit, message.from_user.id))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Kunlik limit {limit} ta namoz qilib belgilandi.", reply_markup=main_menu())

# Namoz bo'limi
@dp.message(F.text == "🕌 Namoz vaqtlari")
async def show_prayers_handler(message: types.Message):
    date_str = datetime.now().strftime("%Y-%m-%d")
    markup = await prayers_inline(message.from_user.id, date_str)
    await message.answer("Bugun o'qigan namozlaringizni belgilang:", reply_markup=markup)

@dp.callback_query(F.data.startswith("pray_"))
async def toggle_prayer_callback(callback: types.CallbackQuery):
    prayer = callback.data.split("_")[1]
    user_id = callback.from_user.id
    date_str = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO prayer_stats (user_id, date) VALUES (?, ?)", (user_id, date_str))
        await db.execute(f"UPDATE prayer_stats SET {prayer} = NOT {prayer} WHERE user_id=? AND date=?", (user_id, date_str))
        await db.commit()

    markup = await prayers_inline(user_id, date_str)
    await callback.message.edit_reply_markup(reply_markup=markup)
    await callback.answer("Holat yangilandi!")

# Qarzlar bo'limi
@dp.message(F.text == "📓 Qarzlar daftari")
async def debt_main(message: types.Message):
    await message.answer("Qarzlar bilan ishlash bo'limi:", reply_markup=debt_menu())

@dp.callback_query(F.data.startswith("debt_"))
async def debt_callbacks(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    if action == "list":
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT type, name, amount FROM debts WHERE user_id=?", (callback.from_user.id,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await callback.message.edit_text("Hozircha qarzlar ro'yxati bo'sh.")
            return
        msg = "📓 <b>Sizning qarzlar ro'yxatingiz:</b>\n\n"
        for r in rows:
            t = "Olinadigan (Haqdorlik) ➕" if r[0] == "give" else "Beriladigan (Qarz) ❌"
            msg += f"👤 {r[1]}: {r[2]:,.0f} so'm ({t})\n"
        await callback.message.edit_text(msg, parse_mode="HTML")
    else:
        await state.update_data(debt_type=action)
        await callback.message.edit_text("Kim bilan hisob-kitob qilyapsiz? Ismini kiriting:")
        await state.set_state(BotStates.waiting_for_debt_name)
    await callback.answer()

@dp.message(BotStates.waiting_for_debt_name)
async def debt_name_handler(message: types.Message, state: FSMContext):
    await state.update_data(debt_name=message.text)
    await message.answer("Qarz summasini kiriting:")
    await state.set_state(BotStates.waiting_for_debt_amount)

@dp.message(BotStates.waiting_for_debt_amount)
async def debt_amount_handler(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Iltimos, raqam kiriting:")
        return
    data = await state.get_data()
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO debts (user_id, type, name, amount, date) VALUES (?, ?, ?, ?, ?)",
            (message.from_user.id, data['debt_type'], data['debt_name'], float(message.text), date_str)
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Qarz muvaffaqiyatli daftarga qayd etildi!", reply_markup=main_menu())

# Hisobotlar
@dp.message(F.text == "📊 Bugungi hisobot")
async def today_report(message: types.Message):
    user_id = message.from_user.id
    date_str = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT SUM(amount) FROM finance WHERE user_id=? AND date=? AND type='kirim'", (user_id, date_str)) as c1:
            kirim = (await c1.fetchone())[0] or 0
        async with db.execute("SELECT SUM(amount) FROM finance WHERE user_id=? AND date=? AND type='chiqim'", (user_id, date_str)) as c2:
            chiqim = (await c2.fetchone())[0] or 0
        async with db.execute("SELECT bomdod, peshin, asr, shom, xufton FROM prayer_stats WHERE user_id=? AND date=?", (user_id, date_str)) as c3:
            prayers = await c3.fetchone()
        async with db.execute("SELECT daily_limit FROM users WHERE user_id=?", (user_id,)) as c4:
            limit = (await c4.fetchone())[0] or 5

    total_prayers = sum(prayers) if prayers else 0
    msg = (
        f"📊 <b>Bugungi kunlik hisobotingiz:</b>\n\n"
        f"💵 Umumiy Kirim: {kirim:,.0f} so'm\n"
        f"💸 Umumiy Chiqim: {chiqim:,.0f} so'm\n"
        f"📉 Balans: {(kirim - chiqim):,.0f} so'm\n\n"
        f"🕌 O'qilgan namozlar: {total_prayers} / {limit}\n"
    )
    if total_prayers >= limit:
        msg += "\n🎉 Barakalloh! Bugungi namoz limiti bajarildi!"
    await message.answer(msg, parse_mode="HTML")

@dp.message(F.text == "📅 Oylik hisobot")
async def monthly_report(message: types.Message):
    user_id = message.from_user.id
    month_str = datetime.now().strftime("%Y-%m") + "%"

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT SUM(amount) FROM finance WHERE user_id=? AND date LIKE ? AND type='kirim'", (user_id, month_str)) as c1:
            kirim = (await c1.fetchone())[0] or 0
        async with db.execute("SELECT SUM(amount) FROM finance WHERE user_id=? AND date LIKE ? AND type='chiqim'", (user_id, month_str)) as c2:
            chiqim = (await c2.fetchone())[0] or 0

    msg = (
        f"📅 <b>Ushbu oydagi umumiy hisobot:</b>\n\n"
        f"📈 Oylik Kirim: {kirim:,.0f} so'm\n"
        f"📉 Oylik Chiqim: {chiqim:,.0f} so'm\n"
        f"⚖️ Sof foyda: {(kirim - chiqim):,.0f} so'm\n"
    )
    await message.answer(msg, parse_mode="HTML")

# Excel eksport funksiyasi
@dp.message(F.text == "📥 Excel Eksport")
async def excel_export(message: types.Message):
    user_id = message.from_user.id
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Moliya Tahlili"
    
    ws.append(["Sana", "Turi", "Kategoriya", "Summa"])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT date, type, category, amount FROM finance WHERE user_id=?", (user_id,)) as cursor:
            async for row in cursor:
                ws.append(row)
                
    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    file_input = BufferedInputFile(excel_file.read(), filename=f"Hisobot_{user_id}.xlsx")
    await message.answer_document(document=file_input, caption="📊 Barcha moliyaviy hisobotingiz Excel formatida!")

@dp.message(F.text == "ℹ️ Yordam (Qo'llanma)")
async def help_handler(message: types.Message):
    await message.answer("ℹ️ <b>Qo'llanma:</b>\n\nUshbu bot orqali kirim va chiqimlaringizni nazorat qilishingiz, qarzlar daftari orqali hisob-kitoblarni yuritishingiz va eng asosiysi namozlaringizni o'z vaqtida qayd etib borishingiz mumkin.", parse_mode="HTML")

# --- 🔔 AVTOMATIK ESLAТMA NAVBATI (FLOOD CHEKLOVISIZ) ---
async def send_prayer_reminder():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            
    for user in users:
        try:
            await bot.send_message(
                chat_id=user[0],
                text="🔔 <b>Namoz vaqtlari o'tdi. Nomozlarni o'qib oldingizmi?</b>\nIltimos, kechiktirmasdan '🕌 Namoz vaqtlari' bo'limiga kirib belgilab qo'ying.",
                parse_mode="HTML"
            )
            await asyncio.sleep(0.05)
        except Exception:
            continue

# Eslatma vaqtlarini kunlik 5 mahal rejalashtirish
scheduler.add_job(send_prayer_reminder, 'cron', hour=6, minute=0)
scheduler.add_job(send_prayer_reminder, 'cron', hour=13, minute=15)
scheduler.add_job(send_prayer_reminder, 'cron', hour=17, minute=0)
scheduler.add_job(send_prayer_reminder, 'cron', hour=19, minute=45)
scheduler.add_job(send_prayer_reminder, 'cron', hour=21, minute=30)

# --- 🌐 RENDER UCHUN DUMMY WEB SERVER (PORT ALDASH) ---
async def handle(request):
    return web.Response(text="Bot is running perfectly!")

async def main():
    await init_db()
    scheduler.start()
    
    # Render port xatosini yo'qotish uchun veb-serverni parallel ishga tushiramiz
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    asyncio.create_task(site.start())
    
    # Botni ishga tushirish
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
