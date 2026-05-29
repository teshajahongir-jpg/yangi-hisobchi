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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
 
# ═══════════════════════════════════════════════════════
# 🔑 BOT SOZLAMALARI  (faqat shu yerda o'zgartiring)
# ═══════════════════════════════════════════════════════
 
BOT_TOKEN  = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID   = 8252424738
 
# ═══════════════════════════════════════════════════════
# 📍 ISHXONA GPS KOORDINATASI
# ═══════════════════════════════════════════════════════
 
ISHXONA_LAT  = 39.745430
ISHXONA_LON  = 64.439307
MAKS_MASOFA  = 150          # metr
 
# ═══════════════════════════════════════════════════════
# ⏰ ISH VAQTI
# ═══════════════════════════════════════════════════════
 
ISH_BOSHLANISH_SOAT  = 9
ISH_BOSHLANISH_MINUT = 0
 
# ═══════════════════════════════════════════════════════
# 👥 XODIMLAR — oylik va jarima stavkalari
# ═══════════════════════════════════════════════════════
# minut_narxi : 1 daqiqa kechikish uchun ayiriladigan so'm
# soat_narxi  : 1 qo'shimcha soat uchun qo'shiladigan so'm
# kun_narxi   : 1 kun kelmasa ayiriladigan so'm (0 = oylik/26)
 
XODIMLAR = {
    "Sevinch":      {"oylik": 4_000_000, "minut_narxi": 14_743.59, "soat_narxi":       0, "kun_narxi":       0},
    "Charos":       {"oylik": 6_000_000, "minut_narxi":  3_846.15, "soat_narxi": 201_923, "kun_narxi":       0},
    "Ozodbek":      {"oylik": 6_000_000, "minut_narxi": 49_038.46, "soat_narxi":  28_846, "kun_narxi":       0},
    "Xudoyorxon":   {"oylik": 5_200_000, "minut_narxi": 75_000.00, "soat_narxi":       0, "kun_narxi":       0},
    "Ruxshona":     {"oylik": 5_200_000, "minut_narxi":  3_333.33, "soat_narxi":  50_000, "kun_narxi": 200_000},
    "Ferangiz":     {"oylik": 3_000_000, "minut_narxi":  1_923.08, "soat_narxi":       0, "kun_narxi":       0},
    "Jahongir":     {"oylik": 1_200_000, "minut_narxi":       0.0, "soat_narxi":       0, "kun_narxi":       0},
    "Muqaddas opa": {"oylik": 2_200_000, "minut_narxi":       0.0, "soat_narxi":       0, "kun_narxi":       0},
    "Avazbek":      {"oylik": 2_000_000, "minut_narxi":    801.28, "soat_narxi":       0, "kun_narxi":       0},
}
 
# ═══════════════════════════════════════════════════════
# ⚙️  ICHKI TIZIM  (o'zgartirmang)
# ═══════════════════════════════════════════════════════
 
bot       = Bot(token=BOT_TOKEN)
dp        = Dispatcher(storage=MemoryStorage())
UZ        = pytz.timezone("Asia/Tashkent")
scheduler = AsyncIOScheduler(timezone=UZ)
 
# RAM da saqlanadigan xodimlar holati
# { user_id: { ... } }
baza: dict = {}
 
 
class Holat(StatesGroup):
    ism_kutish = State()
 
 
# ───────────────────────────────────────────────────────
# 🛠  YORDAMCHI FUNKSIYALAR
# ───────────────────────────────────────────────────────
 
def hozir() -> datetime:
    return datetime.now(UZ)
 
 
def masofa_hisobla(lat1, lon1, lat2, lon2) -> float:
    """Ikki GPS nuqta orasidagi masofani metrda qaytaradi (Haversine)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * 6_371_000
 
 
def kechikish_hisob(vaqt: datetime) -> int:
    """09:00 dan necha daqiqa kechikkanini qaytaradi."""
    chegara = vaqt.replace(
        hour=ISH_BOSHLANISH_SOAT, minute=ISH_BOSHLANISH_MINUT,
        second=0, microsecond=0
    )
    delta = (vaqt - chegara).total_seconds()
    return max(0, int(delta // 60))
 
 
def yangi_xodim_yozuvi(ism: str, user_id: int) -> dict:
    return {
        "ism": ism, "user_id": user_id,
        # joriy sessiya
        "keldi": False, "obedda": False,
        "qoshimcha_pending": False, "qoshimcha_aktiv": False,
        "bugun_keldi": False,
        "boshlanish": None, "obed_boshlanish": None, "qoshimcha_boshlanish": None,
        "obed_minut": 0,
        # oy statistikasi
        "jami_kechikish": 0,
        "jami_qoshimcha_soat": 0,
        "jami_kun": 0,
        "kelmagan_kun": 0,
    }
 
 
# ───────────────────────────────────────────────────────
# ⌨️  KLAVIATURALAR
# ───────────────────────────────────────────────────────
 
def xodim_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash",    request_location=True)],
        [KeyboardButton(text="🥪 Obedga chiqish"),
         KeyboardButton(text="🔙 Obeddan qaytish")],
        [KeyboardButton(text="⏰ Qo'shimcha ishlash", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash",   request_location=True)],
    ], resize_keyboard=True)
 
 
def admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Oylik hisobot")],
        [KeyboardButton(text="👥 Xodimlar ro'yxati")],
        [KeyboardButton(text="✅ Oylik to'landi — nollash")],
    ], resize_keyboard=True)
 
 
# ───────────────────────────────────────────────────────
# 🚀  HANDLERLAR
# ───────────────────────────────────────────────────────
 
@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    uid = m.from_user.id
 
    if uid == ADMIN_ID:
        await m.answer("👑 Admin paneliga xush kelibsiz!", reply_markup=admin_kb())
        return
 
    if uid in baza:
        ism = baza[uid]["ism"]
        await m.answer(f"✅ Xush kelibsiz, <b>{ism}</b>!", reply_markup=xodim_kb(), parse_mode="HTML")
    else:
        ismlar = ", ".join(XODIMLAR.keys())
        await m.answer(f"👋 Salom! Ismingizni kiriting:\n<code>{ismlar}</code>", parse_mode="HTML")
        await state.set_state(Holat.ism_kutish)
 
 
@dp.message(Holat.ism_kutish)
async def ism_kiritildi(m: Message, state: FSMContext):
    kiritilgan = m.text.strip()
    if kiritilgan.startswith("/"):
        return
 
    topilgan = next((k for k in XODIMLAR if k.lower() == kiritilgan.lower()), None)
    if not topilgan:
        ismlar = ", ".join(XODIMLAR.keys())
        await m.answer(f"❌ Ism topilmadi. Quyidagilardan yozing:\n<code>{ismlar}</code>", parse_mode="HTML")
        return
 
    baza[m.from_user.id] = yangi_xodim_yozuvi(topilgan, m.from_user.id)
    await state.clear()
    await m.answer(f"✅ <b>{topilgan}</b>, tizimga kirdingiz!", reply_markup=xodim_kb(), parse_mode="HTML")
    await bot.send_message(ADMIN_ID, f"🔔 Yangi xodim: <b>{topilgan}</b>", parse_mode="HTML")
 
 
# ── OBED ──────────────────────────────────────────────
 
@dp.message(F.text == "🥪 Obedga chiqish")
async def obed_boshlash(m: Message):
    uid = m.from_user.id
    if uid not in baza: return
    x = baza[uid]
 
    if not x["keldi"]:
        await m.answer("❌ Avval <b>Ishni boshlash</b> tugmasini bosing!", parse_mode="HTML"); return
    if x["obedda"]:
        await m.answer("❌ Allaqachon obeddasiz!"); return
 
    x["obedda"] = True
    x["obed_boshlanish"] = hozir()
    await m.answer("🥪 Obed boshlandi. Yoqimli ishtaha!")
    await bot.send_message(ADMIN_ID, f"🥪 <b>{x['ism']}</b> obedga chiqdi.", parse_mode="HTML")
 
 
@dp.message(F.text == "🔙 Obeddan qaytish")
async def obed_tugash(m: Message):
    uid = m.from_user.id
    if uid not in baza: return
    x = baza[uid]
 
    if not x["obedda"]:
        await m.answer("❌ Obedga chiqmagansiz!"); return
 
    minut = max(1, int((hozir() - x["obed_boshlanish"]).total_seconds() // 60))
    x["obed_minut"] += minut
    x["obedda"] = False
    x["obed_boshlanish"] = None
    await m.answer(f"🔙 Obeddan qaytdingiz. Obed vaqti: <b>{minut} minut</b>", parse_mode="HTML")
    await bot.send_message(ADMIN_ID, f"🔙 <b>{x['ism']}</b> obeddan qaytdi ({minut} min)", parse_mode="HTML")
 
 
# ── QO'SHIMCHA ISHLASH TUGMASI ────────────────────────
 
@dp.message(F.text == "⏰ Qo'shimcha ishlash")
async def qoshimcha_tayyorla(m: Message):
    uid = m.from_user.id
    if uid not in baza: return
    if not baza[uid]["keldi"]:
        await m.answer("❌ Avval ishni boshlagan bo'lishingiz kerak!"); return
    baza[uid]["qoshimcha_pending"] = True
    await m.answer("📍 Joylashuvingizni yuboring:", reply_markup=xodim_kb())
 
 
# ── LOKATSIYA HANDLER ─────────────────────────────────
 
@dp.message(F.location)
async def joylashuv(m: Message):
    uid = m.from_user.id
    if uid == ADMIN_ID: return
    if uid not in baza:
        await m.answer("❌ /start bosing."); return
 
    x = baza[uid]
 
    # GPS tekshiruv
    d = masofa_hisobla(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    if d > MAKS_MASOFA:
        await m.answer(
            f"❌ Siz ishxonada emassiz!\n📍 Masofangiz: <b>{int(d)} m</b> (ruxsat: {MAKS_MASOFA} m)",
            parse_mode="HTML"
        ); return
 
    now = hozir()
 
    # ① Qo'shimcha ishlash
    if x["qoshimcha_pending"]:
        x["qoshimcha_pending"] = False
        x["qoshimcha_aktiv"]   = True
        x["qoshimcha_boshlanish"] = now
        await m.answer(f"⏰ Qo'shimcha ish boshlandi: <b>{now.strftime('%H:%M')}</b>", parse_mode="HTML")
        await bot.send_message(ADMIN_ID, f"⚡️ <b>{x['ism']}</b> {now.strftime('%H:%M')} qo'shimcha ishlaydi", parse_mode="HTML")
        return
 
    # ② Kelish
    if not x["keldi"]:
        kechikish = kechikish_hisob(now)
        x["keldi"]         = True
        x["bugun_keldi"]   = True
        x["boshlanish"]    = now
        x["jami_kechikish"] += kechikish
 
        if kechikish > 0:
            await m.answer(f"🟢 Ish boshlandi: <b>{now.strftime('%H:%M')}</b>\n⚠️ Kechikish: <b>{kechikish} min</b>", parse_mode="HTML", reply_markup=xodim_kb())
            await bot.send_message(ADMIN_ID, f"🟢 <b>{x['ism']}</b> keldi {now.strftime('%H:%M')} — ⚠️ <b>{kechikish} min kechikdi</b>", parse_mode="HTML")
        else:
            await m.answer(f"🟢 Ish boshlandi: <b>{now.strftime('%H:%M')}</b> ✅", parse_mode="HTML", reply_markup=xodim_kb())
            await bot.send_message(ADMIN_ID, f"🟢 <b>{x['ism']}</b> vaqtida keldi {now.strftime('%H:%M')}", parse_mode="HTML")
        return
 
    # ③ Ketish
    ishlagan_s = (now - x["boshlanish"]).total_seconds() - x["obed_minut"] * 60
    ishlagan_soat = max(1, int(ishlagan_s // 3600))
 
    # Qo'shimcha ish → kechikishdan ayir
    if x["qoshimcha_aktiv"] and x["qoshimcha_boshlanish"]:
        qosh_minut = int((now - x["qoshimcha_boshlanish"]).total_seconds() // 60)
        x["jami_qoshimcha_soat"] += qosh_minut // 60
        x["jami_kechikish"]       = max(0, x["jami_kechikish"] - qosh_minut)
 
    x["keldi"]              = False
    x["qoshimcha_aktiv"]    = False
    x["qoshimcha_boshlanish"] = None
    x["boshlanish"]         = None
    x["obed_minut"]         = 0
    x["jami_kun"]          += 1
 
    await m.answer(f"🔴 Ish yakunlandi: <b>{now.strftime('%H:%M')}</b>\n🕐 Bugun: <b>{ishlagan_soat} soat</b>", parse_mode="HTML", reply_markup=xodim_kb())
    await bot.send_message(ADMIN_ID, f"🔴 <b>{x['ism']}</b> ketdi {now.strftime('%H:%M')} — {ishlagan_soat} soat", parse_mode="HTML")
 
 
# ───────────────────────────────────────────────────────
# 👑  ADMIN HANDLERLAR
# ───────────────────────────────────────────────────────
 
@dp.message(F.text == "📊 Oylik hisobot")
async def oylik_hisobot(m: Message):
    if m.from_user.id != ADMIN_ID: return
    if not baza:
        await m.answer("Hozircha xodim yo'q."); return
 
    matn = "📊 <b>OYLIK HISOBOT</b>\n\n"
    for uid, x in baza.items():
        s = XODIMLAR.get(x["ism"])
        if not s: continue
 
        oylik     = s["oylik"]
        kun_narxi = s["kun_narxi"] or oylik / 26
 
        jarima    = x["jami_kechikish"]    * s["minut_narxi"]
        kelmagan  = x["kelmagan_kun"]       * kun_narxi
        bonus     = x["jami_qoshimcha_soat"] * s["soat_narxi"]
        qolda     = max(0, oylik - jarima - kelmagan + bonus)
 
        matn += (
            f"👤 <b>{x['ism']}</b>\n"
            f"  💵 Asosiy oylik:       {oylik:>12,.0f} so'm\n"
            f"  ⚠️  Kechikish ({x['jami_kechikish']} min): -{jarima:>9,.0f} so'm\n"
        )
        if kelmagan:
            matn += f"  ❌ Kelmagan ({x['kelmagan_kun']} kun):    -{kelmagan:>9,.0f} so'm\n"
        if bonus:
            matn += f"  ⚡️ Qo'shimcha:          +{bonus:>9,.0f} so'm\n"
        matn += f"  💰 <b>Qo'lga tegadi: {qolda:,.0f} so'm</b>\n{'─'*36}\n"
 
    await m.answer(matn, parse_mode="HTML")
 
 
@dp.message(F.text == "👥 Xodimlar ro'yxati")
async def xodimlar_royxati(m: Message):
    if m.from_user.id != ADMIN_ID: return
    if not baza:
        await m.answer("Ro'yxat bo'sh."); return
 
    matn = "👥 <b>Xodimlar:</b>\n\n"
    for i, (uid, x) in enumerate(baza.items(), 1):
        holat = "🟢 Ishda" if x["keldi"] else "⚫️ Uyda"
        if x["obedda"]: holat += " 🥪"
        matn += f"{i}. <b>{x['ism']}</b> — {holat}\n"
    await m.answer(matn, parse_mode="HTML")
 
 
@dp.message(F.text == "✅ Oylik to'landi — nollash")
async def balans_nollash(m: Message):
    if m.from_user.id != ADMIN_ID: return
    if not baza:
        await m.answer("Baza bo'sh."); return
 
    for uid, x in baza.items():
        x["jami_kechikish"]      = 0
        x["jami_qoshimcha_soat"] = 0
        x["jami_kun"]            = 0
        x["kelmagan_kun"]        = 0
        x["keldi"]               = False
        x["qoshimcha_aktiv"]     = False
        try:
            await bot.send_message(int(uid),
                "💰 <b>Oylik to'lovi amalga oshirildi!</b>\nHisobingiz yangilandi. Yangi oy uchun omad! 🎉",
                parse_mode="HTML")
        except Exception:
            pass
 
    await m.answer("✅ Barcha hisoblar nollandi.", reply_markup=admin_kb())
 
 
# ───────────────────────────────────────────────────────
# ⏱  KUNLIK AVTOMATIK VAZIFALAR
# ───────────────────────────────────────────────────────
 
async def kunlik_eslatma():
    """17:00 — ishni yakunlash eslatmasi."""
    for uid, x in baza.items():
        if not x["keldi"]: continue
        try:
            await bot.send_message(int(uid),
                "⏰ <b>Ish vaqti tugadi!</b> 🔴 Ishni yakunlash tugmasini bosing.",
                parse_mode="HTML", reply_markup=xodim_kb())
        except Exception:
            pass
 
 
async def kunlik_tekshiruv():
    """20:00 — kelmagan xodimlardan 1 kunlik haq chegiriladi."""
    kelmagan = []
    for uid, x in baza.items():
        if int(uid) == ADMIN_ID: continue
        if not x.get("bugun_keldi"):
            x["kelmagan_kun"] += 1
            kelmagan.append(x["ism"])
            try:
                await bot.send_message(int(uid),
                    "⚠️ Bugun ishga kelganingiz qayd etilmadi. Oyligingizdan 1 kunlik haq chegirildi.",
                    parse_mode="HTML")
            except Exception:
                pass
        x["bugun_keldi"] = False  # ertangi kun uchun tozala
 
    if kelmagan:
        await bot.send_message(ADMIN_ID,
            f"📢 Bugun kelmagan xodimlar: <b>{', '.join(kelmagan)}</b>. Ulardan 1 kunlik haq chegirildi.",
            parse_mode="HTML")
    else:
        await bot.send_message(ADMIN_ID, "📢 Bugun hamma xodim keldi! 🎉", parse_mode="HTML")
 
 
# ───────────────────────────────────────────────────────
# ▶️  ISHGA TUSHIRISH
# ───────────────────────────────────────────────────────
 
async def main():
    scheduler.add_job(kunlik_eslatma,  "cron", hour=17, minute=0)
    scheduler.add_job(kunlik_tekshiruv,"cron", hour=20, minute=0)
    scheduler.start()
 
    print("✅ Bot ishga tushdi!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
 
 
if __name__ == "__main__":
    asyncio.run(main())
