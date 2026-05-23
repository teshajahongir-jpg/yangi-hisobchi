import os
import pytz
import gspread
import asyncio
import json
import base64
from google.oauth2.service_account import Credentials
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, WebAppInfo, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# 🚨 ASOSIY SOZLAMALAR
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738
GOOGLE_JADVAL_ID = "1tCGJQuk9MJ-DZ5JuKMPlxoPPTNdvsVktgU_hYS3A90" 
WEBAPP_URL = "https://mening-hisobchi-botim.onrender.com" # Render saytingiz manzili

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
UZ_TZ = pytz.timezone('Asia/Tashkent')

xodimlar_bazasi = {} 
ishchilar_baza = {} # {user_id: {"start": datetime, "end": datetime, "came": True}}

class BotStates(StatesGroup):
    ism_kutish = State()
    admin_notif_kutish = State()

# GOOGLE JADVAL BILAN ISHLASH
def _sing_jadvalga_yoz(xodim_ismi, ustun, qiymat):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_JADVAL_ID).sheet1
        
        ismlar_ustuni = sheet.col_values(1)
        row = None
        for index, name in enumerate(ismlar_ustuni):
            if name.strip().lower() == xodim_ismi.strip().lower():
                row = index + 1
                break
        if row:
            sheet.update_cell(row, ustun, qiymat)
            return True
        return False
    except Exception as e:
        print(f"Jadval xatosi: {e}")
        return False

async def jadvalga_yoz(xodim_ismi, ustun, qiymat):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sing_jadvalga_yoz, xodim_ismi, ustun, qiymat)

# WEB-APP TUGMALARI (KOMPYUTER VA TELEFON UCHUN ASOSIY MENYU)
def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash (Kamera)", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?mode=start"))],
        [KeyboardButton(text="🔴 Ishni yakunlash (Kamera)", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?mode=end"))],
        [KeyboardButton(text="📊 Mening hisobotim")]
    ], resize_keyboard=True)

def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash (Kamera)", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?mode=start"))],
        [KeyboardButton(text="🔴 Ishni yakunlash (Kamera)", web_app=WebAppInfo(url=f"{WEBAPP_URL}/?mode=end"))],
        [KeyboardButton(text="📢 Xodimlarga xabar yuborish")],
        [KeyboardButton(text="👑 Xodimlar ro'yxati")]
    ], resize_keyboard=True)

@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    await state.clear()
    if user_id == ADMIN_ID:
        xodimlar_bazasi[user_id] = {"ism": "Jahongir (Admin)", "status": "approved", "tg_name": m.from_user.full_name}
        await m.answer("👑 Xush kelibsiz Jahongir aka! Kamera va Nazorat tizimi faol.", reply_markup=admin_klaviatura())
        return
    if user_id in xodimlar_bazasi:
        if xodimlar_bazasi[user_id].get("status") == "approved":
            await m.answer("Ish tizimi faol. Kamera orqali tasdiqlang.", reply_markup=xodim_klaviatura())
    else:
        await m.answer("📌 Tizimga qo'shilish uchun Google jadvaldagi ismingizni yuboring:")
        await state.set_state(BotStates.ism_kutish)

@dp.message(BotStates.ism_kutish)
async def process_name(m: Message, state: FSMContext):
    xodim_ismi = m.text.strip()
    user_id = m.from_user.id
    xodimlar_bazasi[user_id] = {"ism": xodim_ismi, "status": "pending", "tg_name": m.from_user.full_name}
    await state.clear()
    await m.answer("✅ So'rovingiz adminga yuborildi.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_{user_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{user_id}")
    ]])
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi xodim:** {xodim_ismi}\nTasdiqlaysizmi?", reply_markup=kb)

@dp.callback_query(F.data.startswith("app_"))
async def approve_user(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    if uid in xodimlar_bazasi:
        xodimlar_bazasi[uid]["status"] = "approved"
        await call.message.edit_text(f"✅ xodim tasdiqlandi.")
        await bot.send_message(uid, "🎉 Admin sizni tasdiqladi! /start bosing.", reply_markup=xodim_klaviatura())

@dp.callback_query(F.data.startswith("rej_"))
async def reject_user(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    if uid in xodimlar_bazasi:
        del xodimlar_bazasi[uid]
        await call.message.edit_text("❌ Rad etildi.")

# TELEGRAM WEB-APP ORQALI KELADIGAN RASMLAR (ZAHIRA UCHUN)
@dp.message(F.web_app_data)
async def handle_web_app_data(m: Message):
    try:
        user_id = m.from_user.id
        xodim_ismi = xodimlar_bazasi.get(user_id, {}).get("ism", m.from_user.full_name)
        
        data = json.loads(m.web_app_data.data)
        mode = data.get("mode")
        image_base64 = data.get("image").split(",")[1]
        image_bytes = base64.b64decode(image_base64)
        
        hozir = datetime.now(UZ_TZ)
        photo_file = BufferedInputFile(image_bytes, filename=f"{xodim_ismi}_{mode}.jpg")
        
        await process_attendance(user_id, xodim_ismi, mode, hozir, photo_file)
        await m.answer(f"✅ Rasm muvaffaqiyatli qabul qilindi!")
    except Exception as e:
        print(f"WebAppData xatosi: {e}")

# KELDI-KETDINI HISOBB-KITOB QILISH FUNKSIYASI
async def process_attendance(user_id, xodim_ismi, mode, hozir, photo_file):
    if user_id not in ishchilar_baza:
        ishchilar_baza[user_id] = {}

    if mode == 'start':
        ishchilar_baza[user_id]['start'] = hozir
        ishchilar_baza[user_id]['came'] = True
        
        matn = f"🟢 **{xodim_ismi}** ishni boshladi!\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}\n"
        if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
            kechikkan_minut = (hozir.hour - 9) * 60 + hozir.minute
            await jadvalga_yoz(xodim_ismi, 2, f"+{kechikkan_minut} min")
            matn += f"⚠️ Ishga {kechikkan_minut} minut kechikdi."
        else:
            matn += "✅ Vaqtida keldi."
            
        await bot.send_photo(ADMIN_ID, photo_file, caption=f"🟢 **Ish boshlash tasdiqlandi**\n👤 Xodim: {xodim_ismi}\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}\n{matn}")

    elif mode == 'end':
        start_vaqt = ishchilar_baza.get(user_id, {}).get('start', hozir)
        ishchilar_baza[user_id]['end'] = hozir
        
        farq_sekund = (hozir - start_vaqt).total_seconds()
        if start_vaqt.hour < 13 and hozir.hour >= 14:
            farq_sekund -= 3600 # Abed avtomat ayrildi
            
        soat = int(farq_sekund // 3600)
        minut = int((farq_sekund % 3600) // 60)
        
        await jadvalga_yoz(xodim_ismi, 3, f"{soat} soat {minut} m")
        await bot.send_photo(ADMIN_ID, photo_file, caption=f"🔴 **Ish yakunlash tasdiqlandi**\n👤 Xodim: {xodim_ismi}\n📅 Ish vaqti: {soat} soat, {minut} m\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}")

# ⏰ CRON JOBS (AVTOMATIK ESLATMALAR)
async def abed_reminder():
    for uid in xodimlar_bazasi:
        if uid != ADMIN_ID:
            try: await bot.send_message(uid, "🥪 **Abedga 5 daqiqa qoldi!**\nSoat 13:00 dan 14:00 gacha abed, tizim bu vaqtni avtomatik chegirib tashlaydi.")
            except: pass

async def end_work_reminder():
    for uid in xodimlar_bazasi:
        if uid != ADMIN_ID:
            try: await bot.send_message(uid, "🔔 **Ish tugashiga 5 daqiqa qoldi!**\nIshni yakunlash (Kamera) tugmasini bosib rasmga tushish esdan chiqmasin!")
            except: pass

# 🦥 ISHGA KELMAGANLARGA AVTOMATIK JAZO (Soat 18:05 da ishlaydi)
async def check_absent_employees():
    for uid, info in xodimlar_bazasi.items():
        if uid == ADMIN_ID: continue
        if uid not in ishchilar_baza or not ishchilar_baza[uid].get('came'):
            xodim_ismi = info['ism']
            await jadvalga_yoz(xodim_ismi, 3, "KELMAGAN (8 soat)")
            try: await bot.send_message(uid, "⚠️ Siz bugun ishga kelmadingiz! Jadvalga avtomatik ravishda 'KELMAGAN' deb 8 soatlik hisob yozildi.")
            except: pass
            await bot.send_message(ADMIN_ID, f"📌 **Avto-Jazo:** {xodim_ismi} bugun ishga kelmadi. Jadvalga 8 soatlik jazo yozildi.")
    ishchilar_baza.clear()

# 🌐 WEB SERVER (AIOHTTP) HTML SAHIFANI KO'RSATISH UCHUN
async def handle_html(request):
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")

# 📸 TO'G'RIDAN-TO'G'RI RASM QABUL QILISH API (KOMPYUTERNING ALDASHINI CHETLAB O'TISH)
async def handle_upload(request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        mode = data.get("mode")
        image_base64 = data.get("image").split(",")[1]
        image_bytes = base64.b64decode(image_base64)
        
        hozir = datetime.now(UZ_TZ)
        xodim_ismi = xodimlar_bazasi.get(user_id, {}).get("ism", f"Xodim_{user_id}")
        photo_file = BufferedInputFile(image_bytes, filename=f"{xodim_ismi}_{mode}.jpg")
        
        # Hisob-kitobni ishga tushirish
        await process_attendance(user_id, xodim_ismi, mode, hozir, photo_file)
        
        # Xodimga bot orqali alohida tasdiq xabari jo'natish
        if mode == 'start':
            await bot.send_message(user_id, f"✅ Ish boshlash vaqtingiz yozildi: {hozir.strftime('%H:%M')}")
        else:
            await bot.send_message(user_id, f"🔴 Ish yakunlash vaqtingiz yozildi: {hozir.strftime('%H:%M')}")

        return web.Response(text="OK", status=200)
    except Exception as e:
        print(f"API yuklash xatosi: {e}")
        return web.Response(text="Error", status=500)

async def main():
    # Cron eslatmalarni sozlash
    scheduler.add_job(abed_reminder, 'cron', hour=12, minute=55, timezone=UZ_TZ)
    scheduler.add_job(end_work_reminder, 'cron', hour=17, minute=55, timezone=UZ_TZ)
    scheduler.add_job(check_absent_employees, 'cron', hour=18, minute=5, timezone=UZ_TZ)
    scheduler.start()

    # Botni orqa fonda yurgizish
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling(bot))

    # Aiohttp server (HTML sahifa va API yuklamalari uchun)
    app = web.Application()
    app.router.add_get('/', handle_html)
    app.router.add_post('/upload_photo', handle_upload)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"Web App Server {port}-portda muvaffaqiyatli yurdi!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
