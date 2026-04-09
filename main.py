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
TOKEN = "8701217643:AAG-HKEu9vhJhYGoaZMIB5XAgF_05yMUMNs"
USER_ID = 8252424738
DATA_FILE = "finance_data.json"
DAILY_LIMIT = 200000  # Kunlik limit: 200,000 so'm

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- XOTIRA ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "total_kirim": 0, "total_chiqim": 0, 
        "weekly_kirim": 0, "weekly_chiqim": 0,
        "history": []
    }

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

user_finance = load_data()

# --- TUGMALAR ---
kb = [[KeyboardButton(text="💰 Kirim"), KeyboardButton(text="💸 Chiqim")],
      [KeyboardButton(text="📊 Bugungi balans"), KeyboardButton(text="🧹 Tozalash")]]
main_menu = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def extract_amount(text):
    numbers = re.findall(r'\d+', text.replace(" ", "").replace(",", ""))
    return int(numbers[0]) if numbers else 0

async def handle(request):
    return web.Response(text="Haftalik hisobot va Limit tizimi faol!")

# --- HISOBOTLAR ---
async def send_daily_report():
    global user_finance
    qoldiq = user_finance["total_kirim"] - user_finance["total_chiqim"]
    report = f"🌙 **KUNLIK HISOBOT**\n\n➕ Kirim: {user_finance['total_kirim']:,}\n➖ Chiqim: {user_finance['total_chiqim']:,}\n💳 Qoldiq: {qoldiq:,}"
    await bot.send_message(chat_id=USER_ID, text=report, parse_mode="Markdown")
    
    # Kunlikni nollash, lekin haftalikka qo'shish
    user_finance["total_kirim"] = 0
    user_finance["total_chiqim"] = 0
    save_data(user_finance)

async def send_weekly_report():
    global user_finance
    qoldiq = user_finance["weekly_kirim"] - user_finance["weekly_chiqim"]
    report = (f"📅 **HAFTALIK HISOBOT**\n\n"
              f"📈 Jami Kirim: {user_finance['weekly_kirim']:,} so'm\n"
              f"📉 Jami Chiqim: {user_finance['weekly_chiqim']:,} so'm\n"
              f"💰 **Haftalik Sof Foyda: {qoldiq:,} so'm**")
    await bot.send_message(chat_id=USER_ID, text=report, parse_mode="Markdown")
    
    # Haftalikni nollash
    user_finance["weekly_kirim"] = 0
    user_finance["weekly_chiqim"] = 0
    save_data(user_finance)

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    if message.from_user.id == USER_ID:
        await message.answer(f"Xush kelibsiz! Kunlik limit: {DAILY_LIMIT:,} so'm.", reply_markup=main_menu)

@dp.message(F.text == "📊 Bugungi balans")
async def show_balance(message: Message):
    if message.from_user.id == USER_ID:
        qoldiq = user_finance["total_kirim"] - user_finance["total_chiqim"]
        await message.answer(f"📈 **Bugun:**\nKirim: {user_finance['total_kirim']:,}\nChiqim: {user_finance['total_chiqim']:,}\nLimitdan qoldi: {max(0, DAILY_LIMIT - user_finance['total_chiqim']):,}\n💰 **Qoldiq: {qoldiq:,}**", parse_mode="Markdown")

@dp.message()
async def process_finance(message: Message):
    if message.from_user.id == USER_ID:
        amount = extract_amount(message.text)
        if amount == 0: return

        if "kirim" in message.text.lower():
            user_finance["total_kirim"] += amount
            user_finance["weekly_kirim"] += amount
            await message.answer(f"✅ Kirim: +{amount:,}")
        else:
            # Limit tekshiruvi
            future_chiqim = user_finance["total_chiqim"] + amount
            user_finance["total_chiqim"] += amount
            user_finance["weekly_chiqim"] += amount
            
            msg = f"❌ Chiqim: -{amount:,}"
            if future_chiqim > DAILY_LIMIT:
                msg += f"\n\n⚠️ **DIQQAT!** Kunlik limitdan ({DAILY_LIMIT:,}) o'tib ketdingiz!"
            
            await message.answer(msg, parse_mode="Markdown")
        
        save_data(user_finance)

async def main():
    scheduler.add_job(send_daily_report, 'cron', hour=23, minute=50)
    scheduler.add_job(send_weekly_report, 'cron', day_of_week='sun', hour=23, minute=55)
    scheduler.start()
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 10000))); await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
