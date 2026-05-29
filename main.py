import os
import pytz
import asyncio
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 🚨 ASOSIY TIZIM SOZLAMALARI
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738

# 📍 ISHXONA KOORDINATASI VA CHEGARA MASOFASI
ISHXONA_LAT = 39.745430   
ISHXONA_LON = 64.439307   
MAKS_MASOFA = 150         

# 💰 JADVALDAGI STAVKALAR (image_ff6d40.png bo'yicha)
XODIMLAR_BAZASI = {
    "Sevinch":      {"oylik": 4000000, "minut_narxi": 14743.59, "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Charos":       {"oylik": 6000000, "minut_narxi": 3846.15,  "soat_narxi": 201923.08, "kun_narxi": 0.0},
    "Ozodbek":      {"oylik": 6000000, "minut_narxi": 49038.46, "soat_narxi": 28846.15,  "kun_narxi": 0.0},
    "Xudoyorxon":   {"oylik": 5200000, "minut_narxi": 75000.0,  "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Ruxshona":     {"oylik": 5200000, "minut_narxi": 3333.33,  "soat_narxi": 50000.0,   "kun_narxi": 200000.0},
    "Ferangiz":     {"oylik": 3000000, "minut_narxi": 1923.08,  "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Jahongir":     {"oylik": 1200000, "minut_narxi": 0.0,      "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Muqaddas opa": {"oylik": 2200000, "minut_narxi": 0.0,      "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Avazbek":      {"oylik": 2000000, "minut_narxi": 801.28,   "soat_narxi": 0.0,       "kun_narxi": 0.0}
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
UZ_TZ = pytz.timezone('Asia/Tashkent')
scheduler = AsyncIOScheduler(timezone=UZ_TZ)

tizim_baza = {}

class BotStates(StatesGroup):
    ism_kutish = State()

def masofani_hisobla(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    return c * 6371000

async def kunlik_eslatma():
    for tg_id, info in tizim_baza.items():
        if info.get('tasdiqlangan', False) and tg_id != ADMIN_ID:
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text="⏰ **Ish vaqti tugadi!**\n\nIltimos, ishni tugatgan bo'lsangiz **🔴 Ishni yakunlash** tugmasini bosing.\nAgar qo'shimcha ishlamoqchi bo'lsangiz, **⏰ Qo'shimcha ishlash** tugmasini bosing.",
                    reply_markup=xodim_klaviatura()
                )
            except:
                pass

def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash", request_location=True)],
        [KeyboardButton(text="⏰ Qo'shimcha ishlash", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
    ], resize_keyboard=True)

def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Xodimlar hisoboti (Buxgalteriya)")],
        [KeyboardButton(text="💰 Buxgalter hamma summani tashlab berdi")]
    ], resize_keyboard=True)

@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    await state.clear()
    
    if user_id == ADMIN_ID:
        await m.answer("👑 Xush kelibsiz Jahongir aka! Tizim boshidan tozalandi va xatosiz ishga tushirildi.", reply_markup=admin_klaviatura())
        return

    if user_id in tizim_baza and tizim_baza[user_id].get('tasdiqlangan', False):
        ism = tizim_baza[user_id]['ism']
        await m.answer(f"✨ Xush kelibsiz, {ism}!\nTugmalardan foydalanib keldi-ketdini qayd eting:", reply_markup=xodim_klaviatura())
    else:
        await m.answer("📌 Botdan foydalanish uchun ro'yxatdagi ismingizni kiriting (Masalan: Sevinch, Charos):")
        await state.set_state(BotStates.ism_kutish)

@dp.message(BotStates.ism_kutish)
async def process_name(m: Message, state: FSMContext):
    xodim_ismi = m.text.strip()
    user_id = m.from_user.id
    if xodim_ismi.startswith("/"): return
    
    topilgan_ism = None
    for k in XODIMLAR_BAZASI.keys():
        if k.lower() == xodim_ismi.lower():
            topilgan_ism = k
            break
            
    if not topilgan_ism:
        ismlar_listi = ", ".join(XODIMLAR_BAZASI.keys())
        await m.answer(f"❌ Ism topilmadi!\nIsmingizni ro'yxatdagidek yozing:\n`{ismlar_listi}`")
        return
        
    await state.clear()
    
    tizim_baza[user_id] = {
        "ism": topilgan_ism,
        "tasdiqlangan": True,
        "came": False,
        "overtime_active": False,
        "start_time": None,
        "overtime_start": None,
        "jami_minut": 0,
        "jami_soat": 0,
        "jami_kun": 0
    }
    
    await m.answer(f"✅ Rahmat, {topilgan_ism}! Tizimga muvaffaqiyatli ulandingiz.", reply_markup=xodim_klaviatura())
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi xodim qo'shildi:** {topilgan_ism}")

@dp.message(F.location)
async def handle_location(m: Message):
    user_id = m.from_user.id
    if user_id == ADMIN_ID: return

    if user_id not in tizim_baza:
        await m.answer("📌 Iltimos, oldin /start buyrug'ini bosing.")
        return
        
    xodim = tizim_baza[user_id]
    xodim_ismi = xodim["ism"]
    
    masofa = masofani_hisobla(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    if masofa > MAKS_MASOFA:
        await m.answer(f"❌ **Masofa xatoligi!** Siz ishxonada emassiz. Masofa: {int(masofa)} metr.")
        return

    hozir = datetime.now(UZ_TZ)

    # 1️⃣ QO'SHIMCHA ISHLASH TUGMASI
    if m.reply_markup and any(b.text == "⏰ Qo'shimcha ishlash" for row in m.reply_markup.keyboard for b in row if hasattr(b, 'text')):
        if not xodim['came']:
            await m.answer("❌ Qo'shimcha ishlash uchun avval ishni boshlagan bo'lishingiz kerak!")
            return
        xodim['overtime_start'] = hozir
        xodim['overtime_active'] = True
        await m.answer(f"⏰ Qo'shimcha ishlash vaqti qayd etildi: {hozir.strftime('%H:%M')}\nKechikkan vaqtingiz bo'lsa, ushbu ishlagan vaqtingiz hisobiga kamayib boradi.")
        await bot.send_message(ADMIN_ID, f"⚡️ **{xodim_ismi}** soat {hozir.strftime('%H:%M')} dan qo'shimcha ishlashni boshladi.")
        return

    # 2️⃣ ISHNI BOSHLASH (KELDI)
    if not xodim['came']:
        xodim['start_time'] = hozir
        xodim['came'] = True
        matn = f"🟢 **{xodim_ismi}** ishni boshladi.\n⏰ Vaqt: {hozir.strftime('%H:%M:%S')}\n"
        
        if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
            kechikish = (hozir.hour - 9) * 60 + hozir.minute
            xodim['jami_minut'] += kechikish
            matn += f"⚠️ {kechikish} minut kechikdi."
            await m.answer(f"✅ Ish boshlandi: {hozir.strftime('%H:%M')}\n⚠️ Siz bugun {kechikish} minut kechikdingiz (Jami qoldiq: {xodim['jami_minut']} m)")
        else:
            matn += "✅ Vaqtida keldi."
            await m.answer(f"✅ Ish boshlash vaqtingiz yozildi: {hozir.strftime('%H:%M')}")
            
        await bot.send_message(ADMIN_ID, f"🔔 **Keldi hisoboti:**\n{matn}")
    
    # 3️⃣ ISHNI YAKUNLASH (KETDI)
    else:
        start_vaqt = xodim['start_time']
        xodim['came'] = False
        
        # Qo'shimcha ishlangan vaqtni hisoblash va kechikishdan chegirish
        if xodim['overtime_active'] and xodim['overtime_start']:
            overtime_farq = (hozir - xodim['overtime_start']).total_seconds()
            overtime_minut = int(overtime_farq // 60)
            
            if overtime_minut > 0:
                eski_minut = xodim['jami_minut']
                xodim['jami_minut'] -= overtime_minut
                if xodim['jami_minut'] < 0: 
                    xodim['jami_minut'] = 0
                
                await m.answer(f"🔥 Qo'shimcha {overtime_minut} minut ishladingiz! Jami kechikish vaqtingiz {eski_minut} m dan {xodim['jami_minut']} m ga kamaytirildi (ayrildi).")
            xodim['overtime_active'] = False

        farq_soniya = (hozir - start_vaqt).total_seconds()
        if start_vaqt.hour < 13 and hozir.hour >= 14:
            farq_soniya -= 3600
            
        ishlangan_soat = int(farq_soniya // 3600)
        if ishlangan_soat < 1: ishlangan_soat = 1
        
        xodim['jami_soat'] += ishlangan_soat
        xodim['jami_kun'] += 1
        
        await bot.send_message(ADMIN_ID, f"🔔 **Ketdi hisoboti:**\n👤 {xodim_ismi}\n📅 Bugun ishladi: {ishlangan_soat} soat\n⏱ Qolgan kechikish vaqti: {xodim['jami_minut']} m")
        await m.answer(f"🔴 Ish yakunlandi vaqtingiz yozildi: {hozir.strftime('%H:%M')}\nSizda saqlanib qolgan kechikish vaqti: {xodim['jami_minut']} minut.")

@dp.message(F.text == "📊 Xodimlar hisoboti (Buxgalteriya)")
async def admin_report(m: Message):
    if m.from_user.id != ADMIN_ID: return
    if not tizim_baza:
        await m.answer("📊 Hozircha xodimlar ma'lumotlar bazasi bo'sh.")
        return
        
    matn = "📊 **BUXGALTERIYA VA OYLIK HISOBOTI**\n\n"
    for uid, data in tizim_baza.items():
        ism = data['ism']
        stavka = XODIMLAR_BAZASI[ism]
        
        minut = data['jami_minut']
        soat = data['jami_soat']
        kun = data['jami_kun']
        oylik = stavka['oylik']
        
        vazvirat = minut * stavka['minut_narxi']
        qo_shimcha_soat = soat * stavka['soat_narxi']
        qo_shimcha_kun = kun * stavka['kun_narxi']
        
        bugalter_summa = oylik - vazvirat + qo_shimcha_soat + qo_shimcha_kun
        if bugalter_summa < 0: bugalter_summa = 0
        
        matn += f"👤 **Xodim:** {ism}\n"
        matn += f"⏱ Kechikkan vaqti (qoldiq): {minut} minut\n"
        matn += f"👔 Qo'shimcha soati: {soat} soat\n"
        matn += f"📉 Jarimalar (Vazvirat): {vazvirat:,.2f} so'm\n"
        matn += f"💵 Asosiy oylik: {oylik:,.2f} so'm\n"
        matn += f"💰 **Bug'alter beradigan summa:** {bugalter_summa:,.2f} so'm\n"
        matn += "--------------------------------------\n"
        
    await m.answer(matn)

@dp.message(F.text == "💰 Buxgalter hamma summani tashlab berdi")
async def clear_all_balances(m: Message):
    if m.from_user.id != ADMIN_ID: return
    if not tizim_baza:
        await m.answer("❌ Bazada xodimlar yo'q.")
        return
        
    for uid in tizim_baza.keys():
        tizim_baza[uid]['jami_minut'] = 0
        tizim_baza[uid]['jami_soat'] = 0
        tizim_baza[uid]['jami_kun'] = 0
        tizim_baza[uid]['came'] = False
        tizim_baza[uid]['overtime_active'] = False
        
        try:
            await bot.send_message(uid, "💰 **Xushxabar!**\nBuxgalteriya oylik to'lovlarini va barcha hisob-kitoblarni amalga oshirdi. Tizimdagi kechikkan minutlaringiz hamda soatlaringiz yangilandi (0 ga tushirildi). Yangi oy uchun omad!")
        except:
            pass
            
    await m.answer("✅ Muvaffaqiyatli bajarildi! Barcha xodimlarning minut/soatlari 0 ga tushirildi va ularga avtomat xushxabar ketdi.")

async def handle_ping(request):
    return web.Response(text="Bot Active", status=200)

async def main():
    scheduler.add_job(kunlik_eslatma, 'cron', hour=17, minute=0)
    scheduler.start()

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
