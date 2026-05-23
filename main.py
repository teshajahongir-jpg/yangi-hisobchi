import os
import pytz
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup

# 🚨 SOZLAMALAR
BOT_TOKEN = "8701217643:AAGS5Sa0zybv_lASF4IcNg3_i7nQbxGMoy0"
ADMIN_ID = 123456789  # Bu yerga o'zingizning Telegram ID raqamingizni yozing (tirnoqsiz, faqat raqam)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# O'zbekiston vaqti
UZ_TZ = pytz.timezone('Asia/Tashkent')

# Ishchilar bazasi (Xotirada saqlash)
ishchilar_baza = {}

def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash"), KeyboardButton(text="🔴 Ishni yakunlash")],
        [KeyboardButton(text="📊 Mening bugungi hisobotim")]
    ], resize_keyboard=True)

def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash"), KeyboardButton(text="🔴 Ishni yakunlash")],
        [KeyboardButton(text="📊 Mening bugungi hisobotim")],
        [KeyboardButton(text="👑 Barcha xodimlar hisoboti")] # Faqat sizga ko'rinadi
    ], resize_keyboard=True)

@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    user_id = m.from_user.id
    matn = (
        f"Salom, {m.from_user.full_name}!\n"
        "Ish vaqtini hisoblash botiga xush kelibsiz.\n\n"
        "⏰ Ish tartibi:\n"
        "• Smena 1: 09:00 - 13:00\n"
        "• Obed (Dam olish): 13:00 - 14:00\n"
        "• Smena 2: 14:00 - 18:00"
    )
    
    if user_id == ADMIN_ID:
        await m.answer(matn + "\n\n👑 Siz tizimda **Nazoratchi (Admin)** foydalanuvchisiz.", reply_markup=admin_klaviatura())
    else:
        await m.answer(matn, reply_markup=xodim_klaviatura())

@dp.message(F.text == "🟢 Ishni boshlash")
async def start_work(m: Message):
    user_id = m.from_user.id
    hozir = datetime.now(UZ_TZ)
    
    if user_id not in ishchilar_baza:
        ishchilar_baza[user_id] = {
            'ism': m.from_user.full_name,
            'username': f"@{m.from_user.username}" if m.from_user.username else "Yo'q"
        }
        
    ishchilar_baza[user_id]['start'] = hozir
    # Agar adashib qayta bossa, eski 'end'ni o'chiradi
    if 'end' in ishchilar_baza[user_id]:
        del ishchilar_baza[user_id]['end']
        
    await m.answer(f"🟢 Ish boshlangan vaqt yozib olindi: **{hozir.strftime('%H:%M:%S')}**\nIshga omad!")

@dp.message(F.text == "🔴 Ishni yakunlash")
async def end_work(m: Message):
    user_id = m.from_user.id
    hozir = datetime.now(UZ_TZ)
    
    if user_id not in ishchilar_baza or 'start' not in ishchilar_baza[user_id]:
        await m.answer("⚠️ Siz hali ishni boshlamagansiz! Avval '🟢 Ishni boshlash' tugmasini bosing.")
        return
        
    start_vaqt = ishchilar_baza[user_id]['start']
    yakun_vaqt = hozir
    ishchilar_baza[user_id]['end'] = yakun_vaqt
    
    # Sof vaqtni hisoblash
    farq = yakun_vaqt - start_vaqt
    jami_sekund = farq.total_seconds()
    
    obed_ayrildi = False
    # Agar 13:00 dan oldin kelib, 14:00 dan keyin ketayotgan bo'lsa, 1 soat (3600 sekund) obedni ayiramiz
    if start_vaqt.hour < 13 and yakun_vaqt.hour >= 14:
        jami_sekund -= 3600
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

# 👑 FAQAT NAZORATCHI (ADMIN) UCHUN BUYRUQ
@dp.message(F.text == "👑 Barcha xodimlar hisoboti")
async def admin_report(m: Message):
    if m.from_user.id != ADMIN_ID:
        await m.answer("⚠️ Bu tugma faqat nazoratchi (admin) uchun!")
        return
        
    if not ishchilar_baza:
        await m.answer("📊 Bugun hali hech qaysi xodim tizimga kirmadi.")
        return
        
    hisobot = "📋 **Bugungi umumiy ishchilar nazorati:**\n\n"
    
    for uid, data in ishchilar_baza.items():
        hisobot += f"👤 **Xodim:** {data['ism']} ({data['username']})\n"
        hisobot += f" ├ 🟢 Keldi: {data['start'].strftime('%H:%M:%S')}\n"
        
        if 'end' in data:
            hisobot += f" ├ 🔴 Ketdi: {data['end'].strftime('%H:%M:%S')}\n"
            hisobot += f" └ ⏱ Sof ish vaqti: {data['sof_soat']}\n"
        else:
            hozir = datetime.now(UZ_TZ)
            hozirgi_farq = hozir - data['start']
            h_sekund = hozirgi_farq.total_seconds()
            if data['start'].hour < 13 and hozir.hour >= 14:
                h_sekund -= 3600
            h_soat = int(h_sekund // 3600)
            h_min = int((h_sekund % 3600) // 60)
            hisobot += f" └ ⏳ Hozirda ishda (Hozirgacha: {h_soat} soat, {h_min} minut)\n"
            
        hisobot += "───────────────────\n"
        
    await m.answer(hisobot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
