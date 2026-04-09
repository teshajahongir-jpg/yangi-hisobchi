import asyncio
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# --- MA'LUMOTLARNI TO'LDIRING ---
TOKEN = "8701217643:AAEdkKMeSXnDXAhbjRGi45fJ-lG5DsSctRE"
USER_ID = 8252424738

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
daily_expenses = []

async def handle(request):
    return web.Response(text="Bot ishlayapti!")

async def send_daily_report():
    global daily_expenses
    if daily_expenses:
        report = "\n".join(daily_expenses)
        msg = f"🌙 Kun yakunlandi! Bugungi xarajatlaringiz:\n\n{report}"
        await bot.send_message(chat_id=USER_ID, text=msg)
        daily_expenses = []

@dp.message()
async def collect_expenses(message: Message):
    if message.from_user.id == USER_ID:
        now = datetime.now().strftime("%H:%M")
        daily_expenses.append(f"[{now}] {message.text}")
        await message.answer(f"✅ Saqlandi: {message.text}")

async def main():
    scheduler.add_job(send_daily_report, 'cron', hour=23, minute=55)
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
