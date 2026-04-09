import asyncio
import os
import re
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# --- KONFIGURATSIYA ---
TOKEN = "8701217643:AAFEHQZR6PLOiODYDD4uxMG7TkRQdoecq-c"
USER_ID = 8252424738
DATA_FILE = "finance_data.json"

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- XOTIRA FUNKSIYALARI ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"kirim": [], "chiqim": [], "total_kirim": 0, "total_chiqim": 0}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# Bot yoqilganda ma'lumotlarni yuklaymiz
user_finance = load_data()

# --- TUGMALAR ---
kb = [
    [KeyboardButton(text="💰 Kirim"), KeyboardButton(text="💸 Chiqim")],
    [KeyboardButton(text="📊 Bugungi balans"), KeyboardButton(text="🧹 Tozalash")]
]
main_menu = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def extract_amount(text):
    numbers = re.findall(r'\d+', text.replace(" ", "").replace(",", ""))
    return int(numbers[0]) if numbers else 0

async def handle(request):
    return web.Response(text="Bot temir xotira rejimida ishlayapti!")

async def send_daily_report():
    global user_finance
    qoldiq = user_finance["total_kirim"] - user_finance["total_chiqim"]
    if user_finance["total_kirim"] > 0 or user_finance["total_chiqim"] > 0:
        report = f"🌙 **KUNLIK HISOBOT**\n\n➕ Kirim: {user_finance['total_kirim']:,}\n➖ Chiqim: {user_finance['total_chiqim']:,}\n💳 Qoldiq: {qoldiq:,}\n"
        await bot.send_message(chat_id=USER_ID, text=report, parse_mode="Markdown")
        # Yangi kunga tozalash
        user_finance = {"kirim": [], "chiqim": [], "total_kirim": 0, "total_chiqim": 0}
        save_data(user_finance)

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    if message.from_user.id == USER_ID:
        await message.answer("Xush kelibsiz! Endi ma'lumotlaringiz xavfsiz saqlanadi.", reply_markup=main_menu)

@dp.message(F.text == "📊 Bugungi balans")
async def show_balance(message: Message):
    if message.from_user.id == USER_ID:
        qoldiq = user_finance["total_kirim"] - user_finance["total_chiqim"]
        await message.answer(f"📈 **Balans:**\n\nKirim: {user_finance['total_kirim']:,}\nChiqim: {user_finance['total_chiqim']:,}\n💰 **Qoldiq: {qoldiq:,} so'm**", parse_mode="Markdown")

@dp.message(F.text == "🧹 Tozalash")
async def clear_data(message: Message):
    if message.from_user.id == USER_ID:
        global user_finance
        user_finance = {"kirim": [], "chiqim": [], "total_kirim": 0, "total_chiqim": 0}
        save_data(user_finance)
        await message.answer("Barcha ma'lumotlar o'chirildi! 🧹")

@dp.message()
async def process_finance(message: Message):
    if message.from_user.id == USER_ID:
        msg_text = message.text
        amount = extract_amount(msg_text)
        now = datetime.now().strftime("%H:%M")
        
        if amount == 0:
            await message.answer("Raqam kiritilmadi!")
            return

        if "kirim" in msg_text.lower():
            user_finance["total_kirim"] += amount
            user_finance["kirim"].append(f"✅ [{now}] {msg_text}")
        else:
            user_finance["total_chiqim"] += amount
            user_finance["chiqim"].append(f"❌ [{now}] {msg_text}")
        
        save_data(user_finance) # Har bir xabardan keyin faylga yozamiz
        await message.answer(f"Saqlandi: {amount:,} so'm")

async def main():
    scheduler.add_job(send_daily_report, 'cron', hour=23, minute=55)
    scheduler.start()
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 10000))); await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
