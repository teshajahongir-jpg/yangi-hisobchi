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
WEBAPP_URL = "https://mening-hisobchi-botim.onrender.com"

# 🌐 ISHXONA STATIK IP MANZILI
ISHXONA_IP = "84.54.71.205" 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
UZ_TZ = pytz.timezone('Asia/Tashkent')

# Vaqtinchalik operativ xotira
ishchilar_baza = {} 

class BotStates(StatesGroup):
    ism_kutish = State()

# GOOGLE JADVAL BILAN BOG'LANISH
def get_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_JADVAL_ID).sheet1

def _jadvaldan_ism_izla(user_id):
    try:
        sheet = get_google_sheet()
        id_ustuni = sheet.col_values(4) # 4-ustun: Telegram ID
        for index, tg_id in enumerate(id_ustuni):
            if str(tg_id).strip() == str(user_id):
                return sheet.cell(index + 1, 1).value # 1-ustun: Ism
        return None
    except Exception as e:
        print(f"Jadvaldan izlashda xatolik: {e}")
        return None

def _sing_jadvalga_yoz(xodim_ismi, ustun, qiymat, user_id=None):
    try:
        sheet = get_google_sheet()
        ismlar_ustuni = sheet.col_values(1)
        row = None
        
        for index, name in enumerate(ismlar_ustuni):
            if name and name.strip().lower() == xodim_ismi.strip().lower():
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

# 🛑 /start BUYRUG'I
@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    await state.clear()
    
    # ADMIN TEKSHIRUVI
    if user_id == ADMIN_ID:
        await m.answer("👑 Xush kelibsiz Jahongir aka! Tizim mutlaqo xatosiz va tayyor holatda, IP nazorati faol.", reply_markup=admin_klaviatura())
        return

    # ODDIY FOYDALANUVCHINI TEKSHIRISH
    xodim_ismi = await jadvaldan_ism_ol(user_id)
    if xodim_ismi:
        await m.answer(f"Xush kelibsiz, {xodim_ismi}! Ish tizimi faol. Kamera orqali tasdiqlang.", reply_markup=xodim_klaviatura())
    else:
        await m.answer("📌 Tizimga qo'shilish uchun Google jadvaldagi (Excel) to'liq ismingizni qanday bo'lsa shunday yuboring:")
        await state.set_state(BotStates.ism_kutish)

# 👤 FAQAT ISMNI QABUL QILISH (STATUS ICHIDA)
@dp.message(BotStates.ism_kutish)
async def process_name(m: Message, state: FSMContext):
    xodim_ismi = m.text.strip()
    user_id = m.from_user.id
    
    # Agar adashib /start bosib yuborsa, ism deb qabul qilmaymiz
    if xodim_ismi.startswith("/"):
        await m.answer("📌 Iltimos, buyruq emas, Google jadvaldagi to'liq ismingizni yozib yuboring:")
        return
        
    await state.clear()
    await m.answer("✅ So'rovingiz adminga yuborildi. Admin tasdiqlashini kuting.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"app_{user_id}_{base64.b64encode(xodim_ismi.encode()).decode()}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{user_id}")
    ]])
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi xodim ro'yxatdan o'tmoqchi:**\n👤 Ismi: {xodim_ismi}\n🆔 Telegram ID: {user_id}\n\nTasdiqlaysizmi?", reply_markup=kb)

@dp.callback_query(F.data.startswith("app_"))
async def approve_user(call: CallbackQuery):
    data_parts = call.data.split("_")
    uid = int(data_parts[1])
    encoded_name = data_parts[2]
    xodim_ismi = base64.b64decode(encoded_name.encode()).decode()
    
    muvaffaqiyat = await jadvalga_yoz(xodim_ismi, 4, str(uid))
    
    if muvaffaqiyat:
        await call.message.edit_text(f"✅ {xodim_ismi} muvaffaqiyatli tasdiqlandi va ID jadvalga bog'landi.")
        await bot.send_message(uid, "🎉 Admin sizni tasdiqladi! Endi /start bosing va tizimdan foydalaning.", reply_markup=xodim_klaviatura())
    else:
        await call.message.edit_text(f"❌ Xatolik: Jadvaldan '{xodim_ismi}' degan ism topilmadi! Oldin ismni jadvalga kiriting, keyin xodim botdan ro'yxatdan o'tsin.")

@dp.callback_query(F.data.startswith("rej_"))
async def reject_user(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    await call.message.edit_text("❌ Xodim so'rovi rad etildi.")
    await bot.send_message(uid, "❌ Afsuski, admin so'rovingizni rad etdi.")

# KELDI-KETDINI HISOB-KITOB QILISH
async def process_attendance(user_id, xodim_ismi, mode, hozir, photo_file, is_computer=False):
    if user_id not in ishchilar_baza:
        ishchilar_baza[user_id] = {}

    suffix = " (Kompyuter)" if is_computer else ""

    if mode == 'start':
        ishchilar_baza[user_id]['start'] = hozir
        ishchilar_baza[user_id]['came'] = True
        matn = f"🟢 **{xodim_ismi}** ishni boshladi!\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}\n"
        
        if user_id != ADMIN_ID:
            if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
                kechikkan_minut = (hozir.hour - 9) * 60 + hozir.minute
                await jadvalga_yoz(xodim_ismi, 2, f"+{kechikkan_minut} min")
                matn += f"⚠️ Ishga {kechikkan_minut} minut kechikdi."
            else:
                matn += "✅ Vaqtida keldi."
                await jadvalga_yoz(xodim_ismi, 2, "Vaqtida")
        else:
            matn += "👑 Admin nazorati."
            
        await bot.send_photo(ADMIN_ID, photo_file, caption=f"🟢 **Ish boshlash tasdiqlandi{suffix}**\n👤 Xodim: {xodim_ismi}\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}\n\n{matn}")

    elif mode == 'end':
        start_vaqt = ishchilar_baza.get(user_id, {}).get('start', hozir)
        ishchilar_baza[user_id]['end'] = hozir
        
        farq_sekund = (hozir - start_vaqt).total_seconds()
        if start_vaqt.hour < 13 and hozir.hour >= 14:
            farq_sekund -= 3600
            
        soat = int(farq_sekund // 3600)
        minut = int((farq_sekund % 3600) // 60)
        
        if user_id != ADMIN_ID:
            await jadvalga_yoz(xodim_ismi, 3, f"{soat} soat {minut} m")
            
        await bot.send_photo(ADMIN_ID, photo_file, caption=f"🔴 **Ish yakunlash tasdiqlandi{suffix}**\n👤 Xodim: {xodim_ismi}\n📅 Ish vaqti: {soat} soat, {minut} m\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}")

# HTML OYNANI KO'RSATISH
async def handle_html(request):
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")

# 📸 RASM QABUL QILISH VA API NAZORATI
async def handle_upload(request):
    try:
        client_ip = request.headers.get("X-Forwarded-For", request.remote).split(',')[0].strip()
        data = await request.json()
        user_id = int(data.get("user_id"))
        
        if user_id != ADMIN_ID and client_ip != ISHXONA_IP:
            await bot.send_message(user_id, f"❌ **Tizim rad etdi!**\nSiz hozir ishxonadagi Wi-Fi tarmog'iga ulanmagansiz!\nFaqat ish joyidan hisobot berishingiz mumkin.")
            return web.Response(text="IP_DENIED", status=403)

        mode = data.get("mode")
        image_base64 = data.get("image").split(",")[1]
        image_bytes = base64.b64decode(image_base64)
        hozir = datetime.now(UZ_TZ)
        
        if user_id == ADMIN_ID:
            xodim_ismi = "Jahongir (Admin)"
        else:
            xodim_ismi = await jadvaldan_ism_ol(user_id)
            if not xodim_ismi:
                xodim_ismi = f"Xodim_{user_id}"
            
        photo_file = BufferedInputFile(image_bytes, filename=f"{xodim_ismi}_{mode}.jpg")
        await process_attendance(user_id, xodim_ismi, mode, hozir, photo_file, is_computer=True)
        
        if mode == 'start':
            await bot.send_message(user_id, f"✅ Ish boshlash vaqtingiz yozildi: {hozir.strftime('%H:%M')}")
        else:
            await bot.send_message(user_id, f"🔴 Ish yakunlash vaqtingiz yozildi: {hozir.strftime('%H:%M')}")

        return web.Response(text="OK", status=200)
    except Exception as e:
        print(f"API yuklash xatosi: {e}")
        return web.Response(text="Error", status=500)

async def main():
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling(bot))

    app = web.Application()
    app.router.add_get('/', handle_html)
    app.router.add_post('/upload_photo', handle_upload)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"Server {port}-portda muvaffaqiyatli yurdi!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
