import os
import sqlite3
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

# ===================== SOZLAMALAR =====================
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738

ISHXONA_LAT = 39.745430
ISHXONA_LON = 64.439307
MAKS_MASOFA = 150       # metr

ISH_BOSHLANISH = 9      # soat
ISH_TUGASH = 18         # soat

# Xodimlar: oylik, 1 minut kechikish narxi, 1 kun kelmagan narxi
XODIMLAR = {
    "Sevinch":      {"oylik": 4000000, "minut_narxi": 14743.59, "kun_narxi": 153846.15},
    "Charos":       {"oylik": 6000000, "minut_narxi": 3846.15,  "kun_narxi": 230769.23},
    "Ozodbek":      {"oylik": 6000000, "minut_narxi": 49038.46, "kun_narxi": 230769.23},
    "Xudoyorxon":   {"oylik": 5200000, "minut_narxi": 75000.0,  "kun_narxi": 200000.0},
    "Ruxshona":     {"oylik": 5200000, "minut_narxi": 3333.33,  "kun_narxi": 200000.0},
    "Ferangiz":     {"oylik": 3000000, "minut_narxi": 1923.08,  "kun_narxi": 115384.62},
    "Jahongir":     {"oylik": 1200000, "minut_narxi": 769.23,   "kun_narxi": 46153.85},
    "Muqaddas opa": {"oylik": 2200000, "minut_narxi": 1410.26,  "kun_narxi": 84615.38},
    "Avazbek":      {"oylik": 2000000, "minut_narxi": 801.28,   "kun_narxi": 76923.08},
}
# ======================================================

def init_db():
    conn = sqlite3.connect("davomat.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS xodimlar (
            tg_id         INTEGER PRIMARY KEY,
            ism           TEXT,
            came          INTEGER DEFAULT 0,
            obedda        INTEGER DEFAULT 0,
            bugun_keldi   INTEGER DEFAULT 0,
            start_time    TEXT,
            obed_start    TEXT,
            obed_minut    INTEGER DEFAULT 0,
            kechikish_min INTEGER DEFAULT 0,
            erta_min      INTEGER DEFAULT 0,
            kelmagan_kun  INTEGER DEFAULT 0,
            xronologiya   TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()

init_db()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
UZ = pytz.timezone("Asia/Tashkent")
scheduler = AsyncIOScheduler(timezone=UZ)

class Holat(StatesGroup):
    ism_kutish = State()

# =================== DB YORDAMCHI ===================
def get_xodim(tg_id):
    conn = sqlite3.connect("davomat.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM xodimlar WHERE tg_id=?", (tg_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_xodim(tg_id, **kw):
    conn = sqlite3.connect("davomat.db")
    c = conn.cursor()
    q = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE xodimlar SET {q} WHERE tg_id=?", [*kw.values(), tg_id])
    conn.commit()
    conn.close()

# =================== KLAVIATURA ===================
def xodim_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Kelish",        request_location=True)],
        [KeyboardButton(text="🥪 Obedga chiqish"), KeyboardButton(text="🔙 Obeddan qaytish")],
        [KeyboardButton(text="🔴 Ketish",         request_location=True)],
        [KeyboardButton(text="📊 Hisobotim")],
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Barcha xodimlar")],
        [KeyboardButton(text="🗑 Oylikni nollash")],
    ], resize_keyboard=True)

# =================== MASOFA ===================
def masofa(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2-lat1, lon2-lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 2 * asin(sqrt(a)) * 6371000

# =================== HISOBOT HISOBLASH ===================
def hisobla(x):
    st = XODIMLAR[x["ism"]]
    # FIX #1: kechikish va erta ketish alohida hisoblanadi
    jarima_kechikish = x["kechikish_min"] * st["minut_narxi"]
    jarima_erta      = x["erta_min"]      * st["minut_narxi"]
    jarima_kun       = x["kelmagan_kun"]  * st["kun_narxi"]
    toza_oylik       = max(0, st["oylik"] - jarima_kechikish - jarima_erta - jarima_kun)
    return {
        "oylik":            st["oylik"],
        "jarima_kechikish": jarima_kechikish,
        "jarima_erta":      jarima_erta,
        "jarima_kun":       jarima_kun,
        "toza_oylik":       toza_oylik,
    }

# =================== AVTOMATIK VAZIFALAR ===================
async def eslatma_yubor():
    """17:45 da barcha xodimlarga eslatma"""
    conn = sqlite3.connect("davomat.db")
    c = conn.cursor()
    c.execute("SELECT tg_id, ism FROM xodimlar WHERE came=1")  # FIX #2: faqat ishda bor xodimlarga
    rows = c.fetchall()
    conn.close()
    for tg_id, ism in rows:
        if tg_id == ADMIN_ID:
            continue
        try:
            await bot.send_message(tg_id,
                f"⏰ {ism}, ish vaqti 18:00 da tugaydi!\n"
                f"Iltimos ketishdan oldin 🔴 Ketish tugmasini bosing.")
        except:
            pass

async def kechasi_tekshir():
    """20:00 da kelmagan xodimlarga jarima va kunlik holatni tozalash"""
    conn = sqlite3.connect("davomat.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM xodimlar")
    rows = c.fetchall()
    for r in rows:
        if r["tg_id"] == ADMIN_ID:
            continue
        if not r["bugun_keldi"]:
            c.execute(
                "UPDATE xodimlar SET kelmagan_kun=kelmagan_kun+1 WHERE tg_id=?",
                (r["tg_id"],)
            )
            try:
                await bot.send_message(r["tg_id"],
                    "📋 Bugun ishga kelganingiz qayd etilmadi.\n"
                    "Oyligingizdan 1 kunlik ish haqi ushlanadi.")
            except:
                pass
    # FIX #3: Kunlik holatni to'liq tozalash (obed_minut ham)
    c.execute("""
        UPDATE xodimlar SET
            came=0, obedda=0, bugun_keldi=0,
            start_time=NULL, obed_start=NULL,
            obed_minut=0, xronologiya=''
    """)
    conn.commit()
    conn.close()

# =================== /start ===================
@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    if m.from_user.id == ADMIN_ID:
        await m.answer("👑 Admin paneli", reply_markup=admin_kb())
        return
    x = get_xodim(m.from_user.id)
    if x:
        await m.answer(f"👋 Xush kelibsiz, {x['ism']}!", reply_markup=xodim_kb())
    else:
        await m.answer(
            "📌 Ismingizni kiriting:\n" + ", ".join(XODIMLAR.keys())
        )
        await state.set_state(Holat.ism_kutish)

@dp.message(Holat.ism_kutish)
async def ism_qabul(m: Message, state: FSMContext):
    kiritilgan = m.text.strip()
    topilgan = next((k for k in XODIMLAR if k.lower() == kiritilgan.lower()), None)
    if not topilgan:
        await m.answer("❌ Ism topilmadi. Qaytadan kiriting:\n" + ", ".join(XODIMLAR.keys()))
        return
    # FIX #4: INSERT OR IGNORE — mavjud xodim ustiga yozilmasin
    conn = sqlite3.connect("davomat.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO xodimlar (tg_id, ism)
        VALUES (?, ?)
    """, (m.from_user.id, topilgan))
    conn.commit()
    conn.close()
    await state.clear()
    await m.answer(f"✅ Tizimga ulandi: {topilgan}", reply_markup=xodim_kb())

# =================== LOKATSIYA (Kelish / Ketish) ===================
@dp.message(F.location)
async def lokatsiya(m: Message):
    uid = m.from_user.id
    x = get_xodim(uid)
    if not x:
        await m.answer("❌ Avval /start orqali ro'yxatdan o'ting.")
        return

    m_masofa = masofa(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    if m_masofa > MAKS_MASOFA:
        await m.answer(f"❌ Ishxonada emassiz!\nMasofa: {int(m_masofa)} m (ruxsat: {MAKS_MASOFA} m)")
        return

    hozir = datetime.now(UZ)
    vaqt_str = hozir.strftime("%H:%M")

    # -------- KELISH --------
    if not x["came"]:
        kechikish = 0
        if hozir.hour > ISH_BOSHLANISH or (hozir.hour == ISH_BOSHLANISH and hozir.minute > 0):
            kechikish = (hozir.hour - ISH_BOSHLANISH) * 60 + hozir.minute

        # FIX #5: yangi kun uchun xronologiya yangi boshlanadi
        xron = f"🟢 Keldi: {vaqt_str}"
        if kechikish > 0:
            xron += f" (kechikish: {kechikish} min)"

        update_xodim(uid,
            came=1,
            bugun_keldi=1,
            start_time=hozir.isoformat(),
            kechikish_min=x["kechikish_min"] + kechikish,
            xronologiya=xron   # yangi kun — eski xronologiya o'chiriladi
        )

        msg = f"✅ Kelish qayd etildi: {vaqt_str}"
        if kechikish > 0:
            msg += f"\n⚠️ Kechikish: {kechikish} minut — oyligingizdan ushlanadi."
        await m.answer(msg, reply_markup=xodim_kb())

    # -------- KETISH --------
    else:
        # FIX #6: obedda bo'lsa ketib bo'lmaydi
        if x["obedda"]:
            await m.answer("❌ Avval obeddan qaytishni qayd eting.")
            return

        erta_min = 0
        if hozir.hour < ISH_TUGASH:
            erta_min = (ISH_TUGASH - hozir.hour) * 60 - hozir.minute
            if erta_min < 0:
                erta_min = 0

        # Ishlangan vaqt
        start = datetime.fromisoformat(x["start_time"])
        sof_soniya = (hozir - start).total_seconds() - (x["obed_minut"] * 60)
        ishlangan = max(0, int(sof_soniya // 60))  # minut

        xron = x["xronologiya"] + f"\n🔴 Ketdi: {vaqt_str} ({ishlangan//60}s {ishlangan%60}min)"
        if erta_min > 0:
            xron += f" ⚠️ Erta: {erta_min} min jarima"

        update_xodim(uid,
            came=0,
            obedda=0,
            obed_minut=0,
            erta_min=x["erta_min"] + erta_min,
            xronologiya=xron
        )

        msg = f"🔴 Ketish qayd etildi: {vaqt_str}\n✅ Ishlangan: {ishlangan//60} soat {ishlangan%60} minut"
        if erta_min > 0:
            msg += f"\n⚠️ 18:00 dan {erta_min} minut oldin ketdingiz — jarima qo'shildi."
        await m.answer(msg, reply_markup=xodim_kb())

# =================== OBED ===================
@dp.message(F.text == "🥪 Obedga chiqish")
async def obed_boshlash(m: Message):
    x = get_xodim(m.from_user.id)
    if not x or not x["came"]:
        await m.answer("❌ Avval kelishni qayd eting.")
        return
    if x["obedda"]:
        await m.answer("❌ Allaqachon obeddasiz.")
        return
    hozir = datetime.now(UZ)
    xron = x["xronologiya"] + f"\n🥪 Obed: {hozir.strftime('%H:%M')}"
    update_xodim(m.from_user.id, obedda=1, obed_start=hozir.isoformat(), xronologiya=xron)
    await m.answer("🥪 Obed boshlandi. Yoqimli ishtaha!")

@dp.message(F.text == "🔙 Obeddan qaytish")
async def obed_tugash(m: Message):
    x = get_xodim(m.from_user.id)
    if not x or not x["obedda"]:
        await m.answer("❌ Siz obedda emassiz.")
        return
    hozir = datetime.now(UZ)
    obed_start = datetime.fromisoformat(x["obed_start"])
    minut = max(1, int((hozir - obed_start).total_seconds() // 60))
    xron = x["xronologiya"] + f"\n🔙 Qaytdi: {hozir.strftime('%H:%M')} ({minut} min)"
    update_xodim(m.from_user.id, obedda=0, obed_minut=x["obed_minut"]+minut, xronologiya=xron)
    await m.answer(f"🔙 Obeddan qaytdingiz. Davomiyligi: {minut} minut.")

# =================== HISOBOT ===================
@dp.message(F.text == "📊 Hisobotim")
async def hisobotim(m: Message):
    x = get_xodim(m.from_user.id)
    if not x:
        await m.answer("Siz ro'yxatdan o'tmagansiz.")
        return
    h = hisobla(x)
    # FIX #1: kechikish va erta ketish jarimalari alohida ko'rsatiladi
    matn = (
        f"👤 {x['ism']}\n"
        f"💰 Asosiy oylik: {h['oylik']:,.0f} so'm\n"
        f"─────────────────────\n"
        f"⏱ Kechikish: {x['kechikish_min']} min  →  -{h['jarima_kechikish']:,.0f} so'm\n"
        f"🚶 Erta ketish: {x['erta_min']} min  →  -{h['jarima_erta']:,.0f} so'm\n"
        f"❌ Kelmagan: {x['kelmagan_kun']} kun  →  -{h['jarima_kun']:,.0f} so'm\n"
        f"─────────────────────\n"
        f"💵 Qo'lga: {h['toza_oylik']:,.0f} so'm\n"
        f"─────────────────────\n"
        f"📅 Bugungi xronologiya:\n{x['xronologiya'] or 'Hali ma\\'lumot yo\\'q'}"
    )
    await m.answer(matn)

# =================== ADMIN ===================
@dp.message(F.text == "📋 Barcha xodimlar")
async def barcha_xodimlar(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("davomat.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM xodimlar")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await m.answer("Baza bo'sh.")
        return
    matn = "📋 BARCHA XODIMLAR HISOBOTI\n\n"
    for r in rows:
        if r["ism"] not in XODIMLAR:
            continue
        x = dict(r)
        h = hisobla(x)
        holat = "🟢 Ishda" if r["came"] else "⚪ Emas"
        matn += (
            f"👤 {r['ism']} — {holat}\n"
            f"⏱ Kechikish: {r['kechikish_min']} min | 🚶 Erta: {r['erta_min']} min | ❌ Kelmagan: {r['kelmagan_kun']} kun\n"
            f"💵 Qo'lga: {h['toza_oylik']:,.0f} so'm\n\n"
        )
    await m.answer(matn)

@dp.message(F.text == "🗑 Oylikni nollash")
async def nollash(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("davomat.db")
    c = conn.cursor()
    c.execute("""
        UPDATE xodimlar SET
            came=0, obedda=0, bugun_keldi=0,
            start_time=NULL, obed_start=NULL, obed_minut=0,
            kechikish_min=0, erta_min=0, kelmagan_kun=0, xronologiya=''
    """)
    conn.commit()
    conn.close()
    await m.answer("✅ Barcha xodimlarning hisob-kitoblari nolga tushirildi. Yangi oy boshlandi!")

# =================== MAIN ===================
async def main():
    scheduler.add_job(eslatma_yubor,   "cron", hour=17, minute=45)
    scheduler.add_job(kechasi_tekshir, "cron", hour=20, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
