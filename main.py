import os
import pytz
import gspread
from google.oauth2.service_account import Credentials
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# 🚨 ASOSIY SOZLAMALAR
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738
GOOGLE_JADVAL_ID = "1tCGJQuk9MJ-DZ5JuKMPlxoPPTNdvsVktgU_hYS3A90" 

# 📍 ISHXONA LOKATSIYASI (Buxoro)
ISHXONA_LAT = 39.745430  
ISHXONA_LON = 64.439307  
RUXSAT_MASOFA = 100  

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

UZ_TZ = pytz.timezone('Asia/Tashkent')

# Ma'lumotlar bazasi (Xodimlarni ID raqami bo'yicha saqlaydi)
# Aslida buni faylda yoki database'da saqlash kerak, vaqtincha xotirada turadi.
xodimlar_bazasi = {} 
ishchilar_baza = {}

class Registration(StatesGroup):
    ism_kutish = State()

# KECHIKISH VAQTINI GOOGLE JADVALGA QO'SHISH FUNKSIYASI
def jadvalga_kechikish_yoz(xodim_ismi, kechikkan_minut):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_JADVAL_ID).sheet1
        
        # Xodimni jadvaldagi haqiqiy ismi bo'yicha qidiramiz
        cell = sheet.find(xodim_ismi)
        if cell:
            row = cell.row
            qoshiladigan_soat = kechikkan_minut // 60
            qoshiladigan_minut = kechikkan_minut % 60
            
            if qoshiladigan_minut > 0:
                joriy_minut = int(sheet.cell(row, 2).value or 0)
                sheet.update_cell(row, 2, joriy_minut + qoshiladigan_minut)
                
            if qoshiladigan_soat > 0:
                joriy_soat = int(sheet.cell(row, 3).value or 0)
                sheet.update_cell(row, 3, joriy_soat + qoshiladigan_soat)
            return True
        return False
    except Exception as e:
        print(f"Jadval xatosi: {e}")
        return False

def masofani_hisobla(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    return c * 6371 * 1000  

def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash (Lokatsiya bilan)", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash (Lokatsiya bilan)", request_location=True)],
        [KeyboardButton(text="📊 Mening bugungi hisobotim")]
    ], resize_keyboard=True)

def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash (Lokatsiya bilan)", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash (Lokatsiya bilan)", request_location=True)],
        [KeyboardButton(text="📊 Mening bugungi hisobotim")],
        [KeyboardButton(text="👑 Barcha xodimlar hisoboti")]
    ], resize_keyboard=True)

@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    
    if user_id == ADMIN_ID:
        xodimlar_bazasi[user_id] = {"ism": "Jahongir (Admin)", "status": "approved"}
        await m.answer("👑 Xush kelibsiz, Jahongir aka!", reply_markup=admin_klaviatura())
        return

    # Xodim ro'yxatdan o'tganmi tekshirish
    if user_id in xodimlar_bazasi:
        status = xodimlar_bazasi[user_id].get("status")
        ism = xodimlar_bazasi[user_id].get("ism")
        if status == "approved":
            await m.answer(f"Salom, {ism}! Ish tizimi faol.", reply_markup=xodim_klaviatura())
        elif status == "pending":
            await m.answer("⏳ Ro'yxatdan o'tishingiz admin tomonidan ko'rib chiqilmoqda...")
    else:
        await m.answer("📌 Tizimdan foydalanish uchun ro'yxatdan o'tishingiz kerak.\n\n"
                       "Iltimos, **Google jadvaldagi ismingizni** aynan o'zini yozib yuboring:\n"
                       "(Masalan: Sevinch, Charos, Ozodbek...)")
        await state.set_state(Registration.ism_kutish)

@dp.message(Registration.ism_kutish)
async def process_name(m: Message, state: FSMContext):
    xodim_ismi = m.text.strip()
    user_id = m.from_user.id
    username = f"@{m.from_user.username}" if m.from_user.username else "yo'q"
    
    # Vaqtincha kutish rejimiga o'tkazish
    xodimlar_bazasi[user_id] = {"ism": xodim_ismi, "status": "pending"}
    await state.clear()
    
    await m.answer("✅ Rahmat. So'rovingiz adminga yuborildi. Tasdiqlanishini kuting.")
    
    # Adminga tugma yuborish
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ruxsat berish", callback_data=f"app_{user_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rej_{user_id}")
        ]
    ])
    await bot.send_message(
        ADMIN_ID, 
        f"🔔 **Yangi xodim ro'yxatdan o'tmoqchi!**\n\n"
        f"👤 Telegram ismi: {m.from_user.full_name}\n"
        f"🔗 Username: {username}\n"
        f"📝 Jadvaldagi ismi: **{xodim_ismi}**\n\n"
        f"Ushbu xodimga botdan foydalanishga ruxsat berasizmi?",
        reply_markup=kb
    )

# ADMIN TASDIQLASHI
@dp.callback_query(F.data.startswith("app_"))
async def approve_user(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    if uid in xodimlar_bazasi:
        xodimlar_bazasi[uid]["status"] = "approved"
        ism = xodimlar_bazasi[uid]["ism"]
        await call.answer("Xodim tasdiqlandi!")
        await call.message.edit_text(f"✅ **{ism}** ismli xodim muvaffaqiyatli tasdiqlandi!")
        await bot.send_message(uid, "🎉 Admin sizga ruxsat berdi! Botdan foydalanishingiz mumkin.\n/start tugmasini bosing.", reply_markup=xodim_klaviatura())

@dp.callback_query(F.data.startswith("rej_"))
async def reject_user(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    if uid in xodimlar_bazasi:
        del xodimlar_bazasi[uid]
        await call.answer("Rad etildi!")
        await call.message.edit_text("❌ Ro'yxatdan o'tish so'rovi rad etildi.")
        await bot.send_message(uid, "❌ Afsuski, admin sizning so'rovingizni rad etdi.")

@dp.message(F.location)
async def handle_location(m: Message):
    user_id = m.from_user.id
    
    # Ro'yxatdan o'tmagan bo'lsa tekshirish
    if user_id not in xodimlar_bazasi or xodimlar_bazasi[user_id].get("status") != "approved":
        await m.answer("⚠️ Botdan foydalanish uchun avval ro'yxatdan o'ting! /start bosing.")
        return

    xodim_lat = m.location.latitude
    xodim_lon = m.location.longitude
    hozir = datetime.now(UZ_TZ)
    
    masofa = masofani_hisobla(ISHXONA_LAT, ISHXONA_LON, xodim_lat, xodim_lon)
    if masofa > RUXSAT_MASOFA:
        await m.answer(f"❌ Xatolik! Siz ishxonada emassiz!\nMasofa: {int(masofa)} metr.")
        return

    xodim_haqiqiy_ismi = xodimlar_bazasi[user_id]["ism"] # Telegram ismiga qaramaydi, ro'yxatdan o'tgan ismini oladi

    if user_id not in ishchilar_baza:
        ishchilar_baza[user_id] = {}

    # 🟢 ISHNI BOSHLASH
    if 'start' not in ishchilar_baza[user_id] or 'end' in ishchilar_baza[user_id]:
        ishchilar_baza[user_id]['start'] = hozir
        if 'end' in ishchilar_baza[user_id]:
            del ishchilar_baza[user_id]['end']
            
        matn = f"🟢 Kelgan vaqtingiz yozib olindi: **{hozir.strftime('%H:%M:%S')}**\n"
        
        if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
            kechikkan_minut = (hozir.hour - 9) * 60 + hozir.minute
            muvaffaqiyatli = jadvalga_kechikish_yoz(xodim_haqiqiy_ismi, kechikkan_minut)
            
            soat_qismi = kechikkan_minut // 60
            minut_qismi = kechikkan_minut % 60
            
            if muvaffaqiyatli:
                matn += f"⚠️ Siz bugun ishga **{soat_qismi} soat, {minut_qismi} minut** kechikdingiz. Ma'lumot jadvalga qo'shildi!"
            else:
                matn += f"⚠️ Siz bugun ishga kechikdingiz, lekin **'{xodim_haqiqiy_ismi}'** ismi jadvaldan topilmadi!"
        else:
            matn += "✅ Vaqtida keldingiz, barakalla!"
            
        await m.answer(matn)
        
    # 🔴 ISHNI YAKUNLASH
    else:
        start_vaqt = ishchilar_baza[user_id]['start']
        yakun_vaqt = hozir
        ishchilar_baza[user_id]['end'] = yakun_vaqt
        
        farq = yakun_vaqt - start_vaqt
        jami_sekund = farq.total_seconds()
        
        if start_vaqt.hour < 13 and yakun_vaqt.hour >= 14:
            jami_sekund -= 3600  
            
        soat = int(jami_sekund // 3600)
        minut = int((jami_sekund % 3600) // 60)
        await m.answer(f"🏁 Ish yakunlandi!\n📅 Bugungi sof ish vaqtingiz: **{soat} soat, {minut} minut**.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
