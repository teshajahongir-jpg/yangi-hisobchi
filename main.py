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
TOKEN = "8701217643:AAFsCZe9aImwXRCwXYIIt0Ghgdqew8a4-oA"
USER_ID = 8252424738
DATA_FILE = "finance_data.json"
DAILY_LIMIT = 200000  # Kunlik limit

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- XOTIRA TIZIMI (JSON) ---
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
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
kb = [
    [KeyboardButton(text="💰 Kirim"), KeyboardButton(text="💸 Chiqim")],
    [KeyboardButton(text="📊 Bugungi balans"), KeyboardButton(text="🧹 Tozalash")]
]
main_menu = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def extract_amount(text):
    numbers = re.findall(r'\d+', text.replace(" ", "").replace(",", ""))
    return int(numbers[0]) if numbers else 0

async def handle(request):
    return web.Response(text="Jahongir akaning shaxsiy hisobchisi ishlamoqda!")

# --- AVTOMATIK HISOBOTLAR ---
async def send_daily_report():
    global user_finance
    qoldiq = user_finance["total_kirim"] - user_finance["total_chiqim"]
    if user_finance["total_kirim"] > 0 or user_finance["total_chiqim"] > 0:
        report = (f"🌙 **KUNLIK HISOBOT**\n\n"
                  f"➕ Kirim: {user_finance['total_kirim']:,} so'm\n"
                  f"➖ Chiqim: {user_finance['total_chiqim']:,} so'm\n"
                  f"💳 Qoldiq: {qoldiq:,} so'm")
        await bot.send_message(chat_id=USER_ID, text=report, parse_mode="Markdown")
        
        # Kunlikni nollash
        user_finance["total_kirim"] = 0
        user_finance["total_chiqim"] = 0
        save_data(user_finance)

async def send_weekly_report():
    global user_finance
    qoldiq = user_finance["weekly_kirim"] - user_finance["weekly_chiqim"]
    report = (f"📅 **HAFTALIK YAKUN**\n\n"
              f"📈 Jami Kirim: {user_finance['weekly_kirim']:,} so'm\n"
              f"📉 Jami Chiqim: {user_finance['weekly_chiqim']:,} so'm\n"
              f"💰 **Haftalik sof foyda: {qoldiq:,} so'm**")
    await bot.send_message(chat_id=USER_ID, text=report, parse_mode="Markdown")
    
    # Haftalikni nollash
    user_finance["weekly_kirim"] = 0
    user_finance["weekly_chiqim"] = 0
    save_data(user_finance)

# --- BOT BUYRUQLARI ---
@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    if message.from_user.id == USER_ID:
        await message.answer(f"Salom, Jahongir aka! Hisob-kitobni boshlaymizmi?\nKunlik limit: {DAILY_LIMIT:,} so'm.", reply_markup=main_menu)

@dp.message(F.text == "📊 Bugungi balans")
async def show_balance(message: Message):
    if message.from_user.id == USER_ID:
        qoldiq = user_finance["total_kirim"] - user_finance["total_chiqim"]
        limit_qoldi = max(0, DAILY_LIMIT - user_finance["total_chiqim"])
        await message.answer(
            f"📈 **Bugungi hisobingiz:**\n\n"
            f"Kirim: {user_finance['total_kirim']:,} so'm\n"
            f"Chiqim: {user_finance['total_chiqim']:,} so'm\n"
            f"-------------------\n"
            f"Limitdan qoldi: {limit_qoldi:,} so'm\n"
            f"💰 **Qoldiq: {qoldiq:,} so'm**", 
            parse_mode="Markdown"
        )

@dp.message(F.text == "🧹 Tozalash")
async def clear_data(message: Message):
    if message.from_user.id == USER_ID:
        global user_finance
        user_finance = {"total_kirim": 0, "total_chiqim": 0, "weekly_kirim": 0, "weekly_chiqim": 0, "history": []}
        save_data(user_finance)
        await message.answer("Barcha ma'lumotlar tozalandi! 🧹")

@dp.message()
async def process_finance(message: Message):
    if message.from_user.id == USER_ID:
        msg_text = message.text
        amount = extract_amount(msg_text)
        
        if amount == 0:
            await message.answer("Iltimos, miqdorni raqam bilan yozing (masalan: Osh 50000)")
            return

        if "kirim" in msg_text.lower():
            user_finance["total_kirim"] += amount
            user_finance["weekly_kirim"] += amount
            await message.answer(f"✅ Baraka bersin! +{amount:,} so'm qo'shildi.")
        else:
            user_finance["total_chiqim"] += amount
            user_finance["weekly_chiqim"] += amount
            
            response = f"❌ Chiqim saqlandi: -{amount:,} so'm."
            
            # LIMIT TEKSHIRUVI VA MAXSUS XABAR
            if user_finance["total_chiqim"] > DAILY_LIMIT:
                response += (f"\n\n⚠️ **Jahongir aka, pullarni ishlatib tashayapsiz!** "
                             f"Limitdan oshdingiz-ku, jon aka, xarajatni kamaytiring! 😂")
            
            await message.answer(response, parse_mode="Markdown")
        
        save_data(user_finance)

# --- ISHGA TUSHIRISH ---
async def main():
    # Kunlik hisobot (har kuni 23:50 da)
    scheduler.add_job(send_daily_report, 'cron', hour=23, minute=50)
    # Haftalik hisobot (har yakshanba 23:55 da)
    scheduler.add_job(send_weekly_report, 'cron', day_of_week='sun', hour=23, minute=55)
    scheduler.start()
    
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
