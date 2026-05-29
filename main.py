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
# 🔑 BOT SOZLAMALARI
# ═══════════════════════════════════════════════════════

BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID  = 8252424738

# ═══════════════════════════════════════════════════════
# 📍 ISHXONA GPS
# ═══════════════════════════════════════════════════════

ISHXONA_LAT = 39.745430
ISHXONA_LON = 64.439307
MAKS_MASOFA = 150   # metr

# ═══════════════════════════════════════════════════════
# ⏰ ISH VA OBED VAQTI
# ═══════════════════════════════════════════════════════

ISH_SOAT        = 9       # ish boshlanish soati
ISH_MINUT       = 0
OBED_BOSH_SOAT  = 13      # obed boshlanishi
OBED_BOSH_MINUT = 0
OBED_TUG_SOAT   = 14      # obed tugashi
OBED_TUG_MINUT  = 0

# ═══════════════════════════════════════════════════════
# 💰 BUXGALTER BERGAN SUMMA (har oyda)
# ═══════════════════════════════════════════════════════

BUGALTER_SUMMA = 501_600   # so'm — hammaga bir xil beriladi

# ═══════════════════════════════════════════════════════
# 👥 XODIMLAR
# minut_narxi : 1 daqiqa kechikish uchun ayiriladigan so'm
# soat_narxi  : qo'shimcha 1 soat uchun qo'shiladigan so'm
# kun_narxi   : 1 kun kelmasa ayiriladigan so'm (0 = oylik/26)
# ═══════════════════════════════════════════════════════

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
# ⚙️ ICHKI TIZIM
# ═══════════════════════════════════════════════════════

bot       = Bot(token=BOT_TOKEN)
dp        = Dispatcher(storage=MemoryStorage())
UZ        = pytz.timezone("Asia/Tashkent")
scheduler = AsyncIOScheduler(timezone=UZ)
baza: dict = {}


class Holat(StatesGroup):
    ism_kutish = State()


# ───────────────────────────────────────────────────────
# 🛠 YORDAMCHI FUNKSIYALAR
# ───────────────────────────────────────────────────────

def hozir() -> datetime:
    return datetime.now(UZ)


def masofa(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 2 * asin(sqrt(a)) * 6_371_000


def kechikish_minut(vaqt: datetime) -> int:
    """09:00 dan hozirga qadar necha daqiqa kechikkan."""
    chegara = vaqt.replace(hour=ISH_SOAT, minute=ISH_MINUT, second=0, microsecond=0)
    return max(0, int((vaqt - chegara).total_seconds() // 60))


def yangi_yozuv(ism: str, uid: int) -> dict:
    return {
        "ism": ism, "user_id": uid,
        # sessiya
        "keldi": False, "obedda": False,
        "qoshimcha_pending": False, "qoshimcha_aktiv": False,
        "bugun_keldi": False,
        "boshlanish": None, "obed_boshlanish": None, "qoshimcha_boshlanish": None,
        "obed_minut": 0,
        # oy statistikasi
        "jami_kechikish": 0,      # daqiqa
        "jami_qoshimcha": 0,      # soat
        "jami_kun": 0,
        "kelmagan_kun": 0,
        "obed_jarima_minut": 0,   # obed tugagach qaytmasa jarima daqiqalari
    }


def hisobot_matni(x: dict) -> str:
    """Xodim uchun to'liq moliyaviy hisobot."""
    s          = XODIMLAR[x["ism"]]
    oylik      = s["oylik"]
    kun_narxi  = s["kun_narxi"] or oylik / 26

    jarima_kechikish = x["jami_kechikish"]    * s["minut_narxi"]
    jarima_obed      = x["obed_jarima_minut"] * s["minut_narxi"]
    jarima_kelmagan  = x["kelmagan_kun"]       * kun_narxi
    bonus            = x["jami_qoshimcha"]     * s["soat_narxi"]

    jami_jarima = jarima_kechikish + jarima_obed + jarima_kelmagan
    qoldi       = max(0, oylik - jami_jarima + bonus - BUGALTER_SUMMA)

    matn = (
        f"👤 <b>{x['ism']}</b>\n"
        f"  💵 Oylik:              {oylik:>12,.0f} so'm\n"
        f"  🏦 Buxgalter berdi:   -{BUGALTER_SUMMA:>12,.0f} so'm\n"
    )
    if jarima_kechikish > 0:
        matn += f"  ⚠️  Kechikish ({x['jami_kechikish']} min): -{jarima_kechikish:>9,.0f} so'm\n"
    if jarima_obed > 0:
        matn += f"  🥪 Obed jarima ({x['obed_jarima_minut']} min):  -{jarima_obed:>9,.0f} so'm\n"
    if jarima_kelmagan > 0:
        matn += f"  ❌ Kelmagan ({x['kelmagan_kun']} kun):    -{jarima_kelmagan:>9,.0f} so'm\n"
    if bonus > 0:
        matn += f"  ⚡️ Qo'shimcha ({x['jami_qoshimcha']} soat): +{bonus:>9,.0f} so'm\n"
    matn += f"  💰 <b>Qoldi: {qoldi:,.0f} so'm</b>\n"
    return matn


# ───────────────────────────────────────────────────────
# ⌨️ KLAVIATURALAR
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
# 🚀 HANDLERLAR
# ───────────────────────────────────────────────────────

@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    uid = m.from_user.id

    if uid == ADMIN_ID:
        await m.answer("👑 Admin paneliga xush kelibsiz!", reply_markup=admin_kb())
        return

    if uid in baza:
        await m.answer(f"✅ Xush kelibsiz, <b>{baza[uid]['ism']}</b>!", reply_markup=xodim_kb(), parse_mode="HTML")
    else:
        ismlar = ", ".join(XODIMLAR.keys())
        await m.answer(f"👋 Ismingizni kiriting:\n<code>{ismlar}</code>", parse_mode="HTML")
        await state.set_state(Holat.ism_kutish)


@dp.message(Holat.ism_kutish)
async def ism_kiritildi(m: Message, state: FSMContext):
    kiritilgan = m.text.strip()
    if kiritilgan.startswith("/"): return
    topilgan = next((k for k in XODIMLAR if k.lower() == kiritilgan.lower()), None)
    if not topilgan:
        await m.answer(f"❌ Topilmadi. Yozing:\n<code>{', '.join(XODIMLAR.keys())}</code>", parse_mode="HTML")
        return
    baza[m.from_user.id] = yangi_yozuv(topilgan, m.from_user.id)
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
    await m.answer("🥪 Obed boshlandi (13:00–14:00). Yoqimli ishtaha!")
    await bot.send_message(ADMIN_ID, f"🥪 <b>{x['ism']}</b> obedga chiqdi.", parse_mode="HTML")


@dp.message(F.text == "🔙 Obeddan qaytish")
async def obed_tugash(m: Message):
    uid = m.from_user.id
    if uid not in baza: return
    x = baza[uid]
    if not x["obedda"]:
        await m.answer("❌ Obedga chiqmagansiz!"); return
    await _obed_yopish(uid, x, hozir(), jarima=False)
    await m.answer("🔙 Obeddan qaytdingiz.")
    await bot.send_message(ADMIN_ID, f"🔙 <b>{x['ism']}</b> obeddan qaytdi.", parse_mode="HTML")


async def _obed_yopish(uid: int, x: dict, now: datetime, jarima: bool):
    """Obed vaqtini yopish. jarima=True bo'lsa 14:00 dan keyingi daqiqalar jarima."""
    if not x["obedda"]: return
    minut = max(1, int((now - x["obed_boshlanish"]).total_seconds() // 60))
    x["obed_minut"] += minut
    x["obedda"] = False
    x["obed_boshlanish"] = None

    if jarima:
        # 14:00 dan keyin qaytmagan daqiqalar jarima
        obed_tug = now.replace(hour=OBED_TUG_SOAT, minute=OBED_TUG_MINUT, second=0, microsecond=0)
        kech_minut = max(0, int((now - obed_tug).total_seconds() // 60))
        if kech_minut > 0:
            x["obed_jarima_minut"] += kech_minut
            try:
                await bot.send_message(uid,
                    f"⚠️ Obeddan {kech_minut} daqiqa kech qaytdingiz! "
                    f"Oyligingizdan <b>{kech_minut * XODIMLAR[x['ism']]['minut_narxi']:,.0f} so'm</b> chegirildi.",
                    parse_mode="HTML")
                await bot.send_message(ADMIN_ID,
                    f"🥪⚠️ <b>{x['ism']}</b> obeddan {kech_minut} min kech qaytdi. "
                    f"Jarima: <b>{kech_minut * XODIMLAR[x['ism']]['minut_narxi']:,.0f} so'm</b>",
                    parse_mode="HTML")
            except Exception:
                pass


# ── QO'SHIMCHA ISHLASH ────────────────────────────────

@dp.message(F.text == "⏰ Qo'shimcha ishlash")
async def qoshimcha_tayyorla(m: Message):
    uid = m.from_user.id
    if uid not in baza: return
    if not baza[uid]["keldi"]:
        await m.answer("❌ Avval ishni boshlagan bo'lishingiz kerak!"); return
    baza[uid]["qoshimcha_pending"] = True
    await m.answer("📍 Joylashuvingizni yuboring:", reply_markup=xodim_kb())


# ── LOKATSIYA ─────────────────────────────────────────

@dp.message(F.location)
async def joylashuv(m: Message):
    uid = m.from_user.id
    if uid == ADMIN_ID: return
    if uid not in baza:
        await m.answer("❌ /start bosing."); return

    x = baza[uid]
    d = masofa(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    if d > MAKS_MASOFA:
        await m.answer(
            f"❌ Ishxonada emassiz!\n📍 Masofangiz: <b>{int(d)} m</b> (ruxsat: {MAKS_MASOFA} m)",
            parse_mode="HTML"); return

    now = hozir()

    # ① Qo'shimcha ishlash
    if x["qoshimcha_pending"]:
        x["qoshimcha_pending"] = False
        x["qoshimcha_aktiv"]   = True
        x["qoshimcha_boshlanish"] = now
        await m.answer(f"⏰ Qo'shimcha ish: <b>{now.strftime('%H:%M')}</b>", parse_mode="HTML")
        await bot.send_message(ADMIN_ID, f"⚡️ <b>{x['ism']}</b> {now.strftime('%H:%M')} qo'shimcha ishlaydi", parse_mode="HTML")
        return

    # ② Kelish
    if not x["keldi"]:
        kech = kechikish_minut(now)
        x.update(keldi=True, bugun_keldi=True, boshlanish=now)
        x["jami_kechikish"] += kech

        if kech > 0:
            jarima_sum = kech * XODIMLAR[x["ism"]]["minut_narxi"]
            await m.answer(
                f"🟢 Ish boshlandi: <b>{now.strftime('%H:%M')}</b>\n"
                f"⚠️ Kechikish: <b>{kech} min</b> → jarima: <b>{jarima_sum:,.0f} so'm</b>",
                parse_mode="HTML", reply_markup=xodim_kb())
            await bot.send_message(ADMIN_ID,
                f"🟢 <b>{x['ism']}</b> keldi {now.strftime('%H:%M')} — "
                f"⚠️ <b>{kech} min kechikdi</b> ({jarima_sum:,.0f} so'm)",
                parse_mode="HTML")
        else:
            await m.answer(f"🟢 Ish boshlandi: <b>{now.strftime('%H:%M')}</b> ✅", parse_mode="HTML", reply_markup=xodim_kb())
            await bot.send_message(ADMIN_ID, f"🟢 <b>{x['ism']}</b> vaqtida keldi {now.strftime('%H:%M')}", parse_mode="HTML")
        return

    # ③ Ketish — hisobot ko'rsat
    ishlagan_s    = (now - x["boshlanish"]).total_seconds() - x["obed_minut"] * 60
    ishlagan_soat = max(1, int(ishlagan_s // 3600))

    # Qo'shimcha ish → kechikishdan ayir
    if x["qoshimcha_aktiv"] and x["qoshimcha_boshlanish"]:
        qosh_minut = int((now - x["qoshimcha_boshlanish"]).total_seconds() // 60)
        x["jami_qoshimcha"]  += qosh_minut // 60
        x["jami_kechikish"]   = max(0, x["jami_kechikish"] - qosh_minut)

    x.update(keldi=False, qoshimcha_aktiv=False, qoshimcha_boshlanish=None,
             boshlanish=None, obed_minut=0, jami_kun=x["jami_kun"] + 1)

    # Xodimga hisobot
    hisobot = hisobot_matni(x)
    await m.answer(
        f"🔴 Ish yakunlandi: <b>{now.strftime('%H:%M')}</b> | Bugun: <b>{ishlagan_soat} soat</b>\n\n"
        f"📊 <b>Hisob-kitob:</b>\n{hisobot}",
        parse_mode="HTML", reply_markup=xodim_kb())

    # Adminga ham ko'rinsin
    await bot.send_message(ADMIN_ID,
        f"🔴 <b>{x['ism']}</b> ketdi {now.strftime('%H:%M')} ({ishlagan_soat} soat)\n\n{hisobot}",
        parse_mode="HTML")


# ───────────────────────────────────────────────────────
# 👑 ADMIN
# ───────────────────────────────────────────────────────

@dp.message(F.text == "📊 Oylik hisobot")
async def oylik_hisobot(m: Message):
    if m.from_user.id != ADMIN_ID: return
    if not baza:
        await m.answer("Hozircha xodim yo'q."); return

    matn = "📊 <b>OYLIK HISOBOT</b>\n\n"
    for x in baza.values():
        matn += hisobot_matni(x) + "─" * 36 + "\n"
    await m.answer(matn, parse_mode="HTML")


@dp.message(F.text == "👥 Xodimlar ro'yxati")
async def xodimlar_royxati(m: Message):
    if m.from_user.id != ADMIN_ID: return
    if not baza:
        await m.answer("Ro'yxat bo'sh."); return
    matn = "👥 <b>Xodimlar:</b>\n\n"
    for i, x in enumerate(baza.values(), 1):
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
        x.update(jami_kechikish=0, jami_qoshimcha=0, jami_kun=0,
                 kelmagan_kun=0, obed_jarima_minut=0, keldi=False, qoshimcha_aktiv=False)
        try:
            await bot.send_message(int(uid),
                "💰 <b>Oylik to'lovi amalga oshirildi!</b>\nHisobingiz yangilandi. Yangi oy uchun omad! 🎉",
                parse_mode="HTML")
        except Exception: pass
    await m.answer("✅ Barcha hisoblar nollandi.", reply_markup=admin_kb())


# ───────────────────────────────────────────────────────
# ⏱ KUNLIK AVTOMATIK VAZIFALAR
# ───────────────────────────────────────────────────────

async def soat_9_tekshiruv():
    """
    09:00 dan boshlab har DAQIQA ishga kelmaganlar uchun
    jarima hisoblana beradi (scheduler har daqiqa chaqiradi).
    """
    now = hozir()
    # Faqat ish vaqtida ishlaydi: 09:00 – 18:00
    if not (9 <= now.hour < 18): return

    for uid, x in baza.items():
        if int(uid) == ADMIN_ID: continue
        if not x["keldi"] and not x.get("bugun_keldi"):
            # Har daqiqa kechikish qo'shiladi
            x["jami_kechikish"] += 1


async def obed_avtomatik():
    """
    13:00 — obedga chiqmagan ishchi uchun avtomatik obed boshlanadi.
    14:00 — obeddan qaytmagan ishchi uchun jarima hisoblandi, obed yopiladi.
    """
    now = hozir()

    # 13:00 — avtomatik obed boshlash
    if now.hour == OBED_BOSH_SOAT and now.minute == OBED_BOSH_MINUT:
        for uid, x in baza.items():
            if int(uid) == ADMIN_ID: continue
            if x["keldi"] and not x["obedda"]:
                x["obedda"] = True
                x["obed_boshlanish"] = now
                try:
                    await bot.send_message(int(uid),
                        "🥪 Obed vaqti boshlandi (13:00). Yoqimli ishtaha!\n"
                        "14:00 gacha qaytmasangiz jarima hisoblanadi.")
                except Exception: pass

    # 14:00 — obeddan qaytmagan bo'lsa jarima
    if now.hour == OBED_TUG_SOAT and now.minute == OBED_TUG_MINUT:
        for uid, x in baza.items():
            if int(uid) == ADMIN_ID: continue
            if x["obedda"]:
                await _obed_yopish(int(uid), x, now, jarima=True)


async def kunlik_eslatma():
    """17:00 — ishni yakunlash eslatmasi."""
    for uid, x in baza.items():
        if not x["keldi"]: continue
        try:
            await bot.send_message(int(uid),
                "⏰ <b>Ish vaqti tugadi!</b> 🔴 Ishni yakunlash tugmasini bosing.",
                parse_mode="HTML", reply_markup=xodim_kb())
        except Exception: pass


async def kunlik_tekshiruv():
    """20:00 — bugun kelmagan xodimlardan 1 kunlik haq chegiriladi."""
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
            except Exception: pass
        x["bugun_keldi"] = False  # ertaga uchun reset

    if kelmagan:
        await bot.send_message(ADMIN_ID,
            f"📢 Bugun kelmagan: <b>{', '.join(kelmagan)}</b>. 1 kunlik haq chegirildi.",
            parse_mode="HTML")
    else:
        await bot.send_message(ADMIN_ID, "📢 Bugun hamma keldi! 🎉", parse_mode="HTML")


# ───────────────────────────────────────────────────────
# ▶️ ISHGA TUSHIRISH
# ───────────────────────────────────────────────────────

async def main():
    # Har daqiqa: kechikish jarima hisoblash (09:00-18:00 oralig'ida)
    scheduler.add_job(soat_9_tekshiruv, "interval", minutes=1)
    # Soat 13:00 va 14:00 da obed
    scheduler.add_job(obed_avtomatik,   "cron", hour="13,14", minute=0)
    # Soat 17:00 eslatma
    scheduler.add_job(kunlik_eslatma,   "cron", hour=17, minute=0)
    # Soat 20:00 kelmagan tekshiruv
    scheduler.add_job(kunlik_tekshiruv, "cron", hour=20, minute=0)
    scheduler.start()

    print("✅ Bot ishga tushdi!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
