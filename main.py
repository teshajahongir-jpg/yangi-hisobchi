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

BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738
GOOGLE_JADVAL_ID = "1tCGJQuk9MJ-DZ5JuKMPlxoPPTNdvsVktgU_hYS3A90" 

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
    return c * 6371000

def get_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_JADVAL_ID).sheet1

def _jadvaldan_xodimni_top(user_id):
    try:
        sheet = get_google_sheet()
        id_ustuni = sheet.col_values(13) # M ustuni (13-ustun)
        for index, tg_id in enumerate(id_ustuni):
            if str(tg_id).strip() == str(user_id):
                qator_raqami = index + 1
                ism = sheet.cell(qator_raqami, 1).value
                return {"ism": ism, "qator": qator_raqami}
        return None
    except Exception as e:
        print(f"Xatolik: {e}")
        return None

def _jadvalga_id_boglash(xodim_ismi, user_id):
    try:
        sheet = get_google_sheet()
        ismlar_ustuni = sheet.col_values(1)
        for index, name in enumerate(ismlar_ustuni):
            if name and str(name).strip().lower() == str(xodim_ismi).strip().lower():
                sheet.update_cell(index + 1, 13, str(user_id)) # M ustuniga yozadi
                return True
        return False
    except Exception as e:
        print(f"Xatolik: {e}")
        return False

def _jadvalga_raqam_qush(qator, ustun, qushiladigan_qiymat):
    try:
        sheet = get_google_sheet()
        joriy_qiymat = sheet.cell(qator, ustun).value
        try:
            eski_son = int(float(str(joriy_qiymat).replace(',', '.'))) if joriy_qiymat else 0
        except:
            eski_son = 0
        yangi_son = eski_son + int(qushiladigan_qiymat)
        sheet.update_cell(qator, ustun, yangi_son)
        return True
    except Exception as e:
        print(f"Xatolik: {e}")
        return False

def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
    ], resize_keyboard=True)

def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Jadvalni tekshirish")]
    ], resize_keyboard=True)

@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    await state.clear()
    
    if user_id == ADMIN_ID:
        await m.answer("👑 Xush kelibsiz Jahongir aka! Tizim yangi jadval formatiga moslashtirildi.", reply_markup=admin_klaviatura())
        return

    loop = asyncio.get_event_loop()
    xodim = await loop.run_in_executor(None, _jadvaldan_xodimni_top, user_id)
    
    if xodim and xodim["ism"]:
        await m.answer(f"✨ Xush kelibsiz, {xodim['ism']}!\nLokatsiya orqali keldi-ketdini qayd qilishingiz mumkin:", reply_markup=xodim_klaviatura())
    else:
        await m.answer("📌 Tizimdan foydalanish uchun Google jadvaldagi to'liq ismingizni qanday bo'lsa shunday yozib yuboring (Masalan: Sevinch, Charos, Muqaddas opa):")
        await state.set_state(BotStates.ism_kutish)

@dp.message(BotStates.ism_kutish)
async def process_name(m: Message, state: FSMContext):
    xodim_ismi = m.text.strip()
    user_id = m.from_user.id
    
    if xodim_ismi.startswith("/"):
        await m.answer("📌 Iltimos, ismingizni to'g'ri kiriting:")
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
    
    loop = asyncio.get_event_loop()
    muvaffaqiyat = await loop.run_in_executor(None, _jadvalga_id_boglash, xodim_ismi, uid)
    
    if muvaffaqiyat:
        await call.message.edit_text(f"✅ {xodim_ismi} muvaffaqiyatli tasdiqlandi!")
        await bot.send_message(uid, "🎉 Admin sizni tasdiqladi! Endi /start buyrug'ini bosing.", reply_markup=xodim_klaviatura())
    else:
        await call.message.edit_text(f"❌ Xatolik: Jadvaldan '{xodim_ismi}' ismi topilmadi! Ism 1-ustunda ekanligini tekshiring.")

@dp.callback_query(F.data.startswith("rej_"))
async def reject_user(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    await call.message.edit_text("❌ Rad etildi.")
    await bot.send_message(uid, "❌ So'rovingiz rad etildi.")

@dp.message(F.location)
async def handle_location(m: Message):
    user_id = m.from_user.id
    
    if user_id == ADMIN_ID:
        await m.answer("👑 Jahongir aka, siz adminsiz. Keldi-ketdi faqat xodimlar uchun.")
        return

    loop = asyncio.get_event_loop()
    xodim = await loop.run_in_executor(None, _jadvaldan_xodimni_top, user_id)
    
    if not xodim or not xodim["ism"]:
        await m.answer("📌 Iltimos, oldin /start bosing va ro'yxatdan o'ting.")
        return
        
    xodim_ismi = xodim["ism"]
    qator = xodim["qator"]
    
    masofa = masofani_hisobla(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    
    if masofa > MAKS_MASOFA:
        await m.answer(f"❌ **Tizim rad etdi!**\nSiz ishxonada emassiz. Masofa: {int(masofa)} metr.")
        return

    hozir = datetime.now(UZ_TZ)
    if user_id not in ishchilar_baza:
        ishchilar_baza[user_id] = {}

    if not ishchilar_baza[user_id].get('came', False):
        ishchilar_baza[user_id]['start'] = hozir
        ishchilar_baza[user_id]['came'] = True
        
        matn = f"🟢 **{xodim_ismi}** ishni boshladi.\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}\n"
        # 9:00 dan kechiksa B (2) ustuniga minutni qo'shadi
        if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
            kechikkan = (hozir.hour - 9) * 60 + hozir.minute
            await loop.run_in_executor(None, _jadvalga_raqam_qush, qator, 2, kechikkan)
            matn += f"⚠️ {kechikkan} minut kechikdi (Jadvalga qo'shildi)."
        else:
            matn += "✅ Vaqtida keldi."
                
        await bot.send_message(ADMIN_ID, f"🔔 **Keldi hisoboti:**\n{matn}")
        await m.answer(f"✅ Ish boshlangan vaqtingiz qayd etildi: {hozir.strftime('%H:%M')}")
    else:
        start_vaqt = ishch
