import os
import pytz
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup

# 🚨 ASOSIY SOZLAMALAR
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738

# 📍 ISHXONA ANIQLANGAN LOKATSIYASI
ISHXONA_LAT = 39.745430  
ISHXONA_LON = 64.439307  
RUXSAT_MASOFA = 100  # Ishxonadan necha metrgacha uzoqlikda bosishga ruxsat (metrda)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

UZ_TZ = pytz.timezone('Asia/Tashkent')
ishchilar_baza = {}

# Masofani hisoblash funksiyasi (Xodim haqikatda ishxonadami?)
def masofani_hisobla(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    r = 6371  # Yer radiusi (km)
    return c * r * 1000  # Metrga o'tkazish

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
async def cmd_start(m: Message):
    user_id = m.from_user.id
    matn = (
        f"Salom, {m.from_user.full_name}!\n"
        "Ish vaqtini nazorat qilish tizimiga xush kelibsiz.\n\n"
        "⚠️ DIQQAT: Bot faqat ishxona hududida turganingizda ishlaydi. "
        "Tugmani bosganda lokatsiya yuborishga ruxsat bering."
    )
    if user_id == ADMIN_ID:
        await m.answer(matn + "\n\n👑 Siz: **Nazoratchi (Admin)**", reply_markup=admin_klaviatura())
    else:
        await m.answer(matn, reply_markup=xodim_klaviatura())

# LOKATSIYA KELGANDA ISHNI BOSHLASH YOKI YAKUNLASH
@dp.message(F.location)
async def handle_location(m: Message):
    user_id = m.from_user.id
    xodim_lat = m.location.latitude
    xodim_lon = m.location.longitude
    hozir = datetime.now(UZ_TZ)
    
    # Masofani tekshirish
    masofa = masofani_hisobla(ISHXONA_LAT, ISHXONA_LON, xodim_lat, xodim_lon)
    
    if masofa > RUXSAT_MASOFA:
        await m.answer(
            f"❌ Xatolik! Siz ishxonada emassiz!\n"
            f"Ishxonagacha masofa: {int(masofa)} metr.\n"
            f"Iltimos, ishxonaga kelib qayta urunib ko'ring."
        )
        return

    # Foydalanuvchi ma'lumotlarini bazaga kiritish
    if user_id not in ishchilar_baza:
        ishchilar_baza[user_id] = {
            'ism': m.from_user.full_name,
            'username': f"@{m.from_user.username}" if m.from_user.username else "Yo'q"
        }

    # Ishchi hozir keldimi yoki ketmoqchimi - aniqlash (bazadagi 'start' holatiga qarab)
    if 'start' not in ishchilar_baza[user_id] or 'end' in ishchilar_baza[user_id]:
        # ISHNI BOSHLASH
        ishchilar_baza[user_id]['start'] = hozir
        if 'end' in ishchilar_baza[user_id]:
            del ishchilar_baza[user_id]['end']
        await m.answer(f"🟢 Ish joyidasiz. Kelgan vaqtingiz yozib olindi: **{hozir.strftime('%H:%M:%S')}**\nIshga omad!")
    else:
        # ISHNI YAKUNLASH
        start_vaqt = ishchilar_baza[user_id]['start']
        yakun_vaqt = hozir
        ishchilar_baza[user_id]['end'] = yakun_vaqt
        
        farq = yakun_vaqt - start_vaqt
        jami_sekund = farq.total_seconds()
        
        obed_ayrildi = False
        if start_vaqt.hour < 13 and yakun_vaqt.hour >= 14:
            jami_sekund -= 3600  # 1 soat obedni ayirish
            obed_ayrildi = True

        soat = int(jami_sekund // 3600)
        minut = int((jami_sekund % 3600) // 60)
        ishchilar_baza[user_id]['sof_soat'] = f"{soat} soat, {minut} minut"
        
        matn = (
            f"🏁 Ish yakunlandi!\n\n"
            f"📅 Kelgan vaqt: {start_vaqt.strftime('%H:%M:%S')}\n"
            f"📅 Ketgan vaqt: {yakun_vaqt.strftime('%H:%M:%S')}\n"
        )
        if obed_ayrildi:
            matn += "🥪 Obed vaqti (1 soat) avtomatik ayirildi.\n"
        matn += f"⏱ **Sof ish vaqtingiz:** {soat} soat, {minut} minut."
        await m.answer(matn)

@dp.message(F.text == "📊 Mening bugungi hisobotim")
async def xodim_report(m: Message):
    user_id = m.from_user.id
    if user_id not in ishchilar_baza or 'start' not in ishchilar_baza[user_id]:
        await m.answer("📊 Siz bugun hali ish boshlamadingiz.")
        return
        
    data = ishchilar_baza[user_id]
    matn = f"📝 Sizning bugungi hisobotingiz:\n\n🟢 Kelgan vaqt: {data['start'].strftime('%H:%M:%S')}\n"
    if 'end' in data:
        matn += f"🔴 Ketgan vaqt: {data['end'].strftime('%H:%M:%S')}\n"
        matn += f"⏱ Sof ish vaqti: {data.get('sof_soat', '-')}"
    else:
        matn += "⏳ Ishingiz hali davom etmoqda..."
    await m.answer(matn)

@dp.message(F.text == "👑 Barcha xodimlar hisoboti")
async def admin_report(m: Message):
    if m.from_user.id != ADMIN_ID:
        await m.answer("⚠️ Bu tugma faqat nazoratchi uchun!")
        return
        
    if not ishchilar_baza:
        await m.answer("📊 Bugun hali hech qaysi xodim ish boshlamadi.")
        return
        
    hisobot = "📋 **Bugungi umumiy ishchilar nazorati:**\n\n"
    for uid, data in ishchilar_baza.items():
        hisobot += f"👤 **Xodim:** {data['ism']} ({data['username']})\n"
        
        if 'start' in data:
            hisobot += f" ├ 🟢 Keldi: {data['start'].strftime('%H:%M:%S')}\n"
        else:
            hisobot += f" ├ 🟢 Keldi: -\n"
            
        if 'end' in data:
            hisobot += f" ├ 🔴 Ketdi: {data['end'].strftime('%H:%M:%S')}\n"
            hisobot += f" └ ⏱ Sof ish vaqti: {data['sof_soat']}\n"
        else:
            hisobot += f" └ ⏳ Hozirda ishda davom etmoqda...\n"
        hisobot += "───────────────────\n"
    await m.answer(hisobot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
