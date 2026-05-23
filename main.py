import os
import pytz
import gspread
import asyncio
import base64
from math import radians, cos, sin, asin, sqrt
from google.oauth2.service_account import Credentials
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

# 🚨 ASOSIY SOZLAMALAR
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738
GOOGLE_JADVAL_ID = "1tCGJQuk9MJ-DZ5JuKMPlxoPPTNdvsVktgU_hYS3A90" 

# 📍 ISHXONA KOORDINATALARI
ISHXONA_LAT = 39.745430   
ISHXONA_LON = 64.439307   
MAKS_MASOFA = 150         

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
UZ_TZ = pytz.timezone('Asia/Tashkent')

ishchilar_baza = {} 

class BotStates(StatesGroup):
    ism_kutish = State()

def masofani_hisobla(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371000 
    return c * r

def get_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_JADVAL_ID).sheet1

def _jadvaldan_ism_izla(user_id):
    try:
        sheet = get_google_sheet()
        id_ustuni = sheet.col_values(4)
        for index, tg_id in enumerate(id_ustuni):
            if str(tg_id).strip() == str(user_id):
                return sheet.cell(index + 1, 1).value
        return None
    except Exception as e:
        print(f"Jadval xatosi: {e}")
        return None

def _sing_jadvalga_yoz(xodim_ismi, ustun, qiymat, user_id=None):
    try:
        sheet = get_google_sheet()
        ismlar_ustuni = sheet.col_values(1)
        row = None
        for index, name in enumerate(ismlar_ustuni):
            if name and str(name).strip().lower() == str(xodim_ismi).strip().lower():
                row = index + 1
                break
        if row:
            sheet.update_cell(row, ustun, qiymat)
            if user_id:
                sheet.update_cell(row, 4, str(user_id))
            return True
        return False
    except Exception as e:
        print(f"Jadvalga yozish xatosi: {e}")
        return False

async def jadvaldan_ism_ol(user_id):
    if user_id == ADMIN_ID:
        return "Jahongir (Admin)"
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _jadvaldan_ism_izla, user_id)

async def jadvalga_yoz(xodim_ismi, ustun, qiymat, user_id=None):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sing_jadvalga_yoz, xodim_ismi, ustun, qiymat, user_id)

def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
    ], resize_keyboard=True)

def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
    ], resize_keyboard=True)

# 🔍 JADVALNI TEKSHIRISH BUYRUG'I (FAQAT ADMIN UCHUN)
@dp.message(F.text == "/test_sheet")
async def test_sheet_connection(m: Message):
    if m.from_user.id != ADMIN_ID: 
        return
    try:
        sheet = get_google_sheet()
        ismlar = sheet.col_values(1)
        await m.answer(f"✅ Google Sheets ulanishi muvaffaqiyatli!\n\nJadvaldagi birinchi 5 ta ism:\n{', '.join(ismlar[:5])}")
    except Exception as e:
        await m.answer(f"❌ Jadvalni o'qishda xatolik!\n\nSiz bergan xato xabari: {e}")

# 🛑 /start BUYRUG'I
@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    await state.clear()
    
    if user_id == ADMIN_ID:
        await m.answer("👑 Xush kelibsiz Jahongir aka! Tizim boshqaruvga tayyor.", reply_markup=admin_klaviatura())
        return

    xodim_ismi = await jadvaldan_ism_ol(user_id)
    if xodim_ismi:
        await m.answer(f"Xush kelibsiz, {xodim_ismi}! Keldi-ketdini qayd etish uchun pastdagi maxsus tugmalardan foydalaning:", reply_markup=xodim_klaviatura())
    else:
        await m.answer("📌 Tizimdan foydalanish uchun Google jadvaldagi (Excel) to'liq ismingizni qanday bo'lsa shunday yozib yuboring:")
        await state.set_state(BotStates.ism_kutish)

# 👤 ISMNI QABUL QILISH
@dp.message(BotStates.ism_kutish)
async def process_name(m: Message, state: FSMContext):
    xodim_ismi = m.text.strip()
    user_id = m.from_user.id
    
    if xodim_ismi.startswith("/"):
        await m.answer("📌 Iltimos, buyruq yubormang. Ismingizni kiriting:")
        return
        
    await state.clear()
    await m.answer("✅ Ro'yxatdan o'tish so'rovi adminga yuborildi. Tasdiqlashlarini kuting.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_{user_id}_{base64.b64encode(xodim_ismi.encode()).decode()}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{user_id}")
    ]])
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi xodim ro'yxatdan o'tmoqchi:**\n👤 Ismi: {xodim_ismi}\n🆔 Telegram ID: {user_id}", reply_markup=kb)

@dp.callback_query(F.data.startswith("app_"))
async def approve_user(call: CallbackQuery):
    parts = call.data.split("_")
    uid, xodim_ismi = int(parts[1]), base64.b64decode(parts[2].encode()).decode()
    
    muvaffaqiyat = await jadvalga_yoz(xodim_ismi, 4, str(uid))
    
    if muvaffaqiyat:
        await call.message.edit_text(f"✅ {xodim_ismi} muvaffaqiyatli tasdiqlandi!")
        await bot.send_message(uid, "🎉 Admin sizni tasdiqladi! Endi /start bosing va tizimdan foydalaning.", reply_markup=xodim_klaviatura())
    else:
        await call.message.edit_text(f"❌ Xatolik: Google jadvaldan '{xodim_ismi}' degan ism topilmadi! Oldin ismni jadvalga qo'shing.")

@dp.callback_query(F.data.startswith("rej_"))
async def reject_user(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    await call.message.edit_text("❌ Rad etildi.")
    await bot.send_message(uid, "❌ So'rovingiz rad etildi.")

# 📍 LOKATSIYA KELGANDA TEKSHIRUV
@dp.message(F.location)
async def handle_location(m: Message):
    user_id = m.from_user.id
    xodim_ismi = await jadvaldan_ism_ol(user_id)
    
    if not xodim_ismi:
        await m.answer("📌 Iltimos, oldin /start bosing va ismingizni kiriting.")
        return
        
    masofa = masofani_hisobla(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    
    if user_id != ADMIN_ID and masofa > MAKS_MASOFA:
        await m.answer(f"❌ **Tizim rad etdi!**\nSiz ishxonada emassiz. Masofa: {int(masofa)} metr.")
        return

    hozir = datetime.now(UZ_TZ)
    if user_id not in ishchilar_baza:
        ishchilar_baza[user_id] = {}

    if not ishchilar_baza[user_id].get('came', False):
        ishchilar_baza[user_id]['start'] = hozir
        ishchilar_baza[user_id]['came'] = True
        
        matn = f"🟢 **{xodim_ismi}** ishni boshladi.\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}\n"
        if user_id != ADMIN_ID:
            if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
                kechikkan = (hozir.hour - 9) * 60 + hozir.minute
                await jadvalga_yoz(xodim_ismi, 2, f"+{kechikkan} min")
                matn += f"⚠️ {kechikkan} minut kechikdi."
            else:
                await jadvalga_yoz(xodim_ismi, 2, "Vaqtida")
                matn += "✅ Vaqtida keldi."
                
        await bot.send_message(ADMIN_ID, f"🔔 **Keldi hisoboti:**\n{matn}")
        await m.answer(f"✅ Ish boshlangan vaqtingiz qayd etildi: {hozir.strftime('%H:%M')}")
    else:
        start_vaqt = ishchilar_baza[user_id].get('start', hozir)
        ishchilar_baza[user_id]['came'] = False
        
        farq = (hozir - start_vaqt).total_seconds()
        if start_vaqt.hour < 13 and hozir.hour >= 14:
            farq -= 3600
        soat, minut = int(farq // 3600), int((farq % 3600) // 60)
        
        if user_id != ADMIN_ID:
            await jadvalga_yoz(xodim_ismi, 3, f"{soat} soat {minut} m")
            
        await bot.send_message(ADMIN_ID, f"🔔 **Ketdi hisoboti:**\n👤 {xodim_ismi}\n📅 Ish vaqti: {soat} soat {minut} min")
        await m.answer(f"🔴 Ish yakunlangan vaqtingiz qayd etildi: {hozir.strftime('%H:%M')}\nCharchamang!")

# ⚠️ ORTIQCHA MATNLARNI INKOR QILISH
@dp.message(F.text)
async def ignore_other_texts(m: Message):
    user_id = m.from_user.id
    if user_id == ADMIN_ID:
        await m.answer("👑 Jahongir aka, keldi-ketdi tugmalaridan foydalanishingiz mumkin yoki jadvalni tekshirish uchun /test_sheet deb yozing.")
    else:
        await m.answer("ℹ️ Iltimos, botga matnli xabar yubormang. Faqat pastdagi yashil yoki qizil tugmalarni bosib, lokatsiya yuboring.")

async def handle_ping(request):
    return web.Response(text="Bot is running", status=200)

async def main():
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling(bot))

    app = web.Application()
    app.router.add_get('/', handle_ping)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
