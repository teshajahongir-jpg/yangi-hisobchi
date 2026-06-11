# -*- coding: utf-8 -*-
"""
TimePay uslubidagi xodimlar keldi-ketdi nazorati boti
Xodim:  lokatsiya bilan Keldim / Ketdim, o'z hisobotini ko'rish
Admin:  bugungi jonli panel, xodim qo'shish/o'chirish, oylik hisob-kitob
Jarima: kechikkan har daqiqa va kelmagan har kun uchun avtomatik
Kutubxonalar: pip install aiogram apscheduler
"""

import os
import sqlite3
import asyncio
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==================== SOZLAMALAR ====================
BOT_TOKEN = os.getenv("8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk")   # tokenni env'da saqlang!
ADMIN_ID = int(os.getenv("-1003995667403", "8252424738"))

ISHXONA_LAT = 39.745430
ISHXONA_LON = 64.439307
MAKS_MASOFA = 150          # metr

ISH_BOSHLANISH = "09:00"   # ish boshlanish vaqti
ISH_TUGASH = "18:00"       # ish tugash vaqti
ISH_KUNLARI = 26           # oyda nechta ish kuni (oylik shu songa bo'linadi)
DAM_KUNLARI = [6]          # 6 = yakshanba (0 = dushanba)
TZ = ZoneInfo("Asia/Tashkent")
DB = "davomat.db"
# ====================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TZ)


# ==================== BAZA ====================
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS xodimlar (
            telegram_id INTEGER PRIMARY KEY,
            ism TEXT NOT NULL,
            oylik INTEGER NOT NULL,
            qoshilgan TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS davomat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sana TEXT NOT NULL,
            telegram_id INTEGER NOT NULL,
            keldi TEXT,
            ketdi TEXT,
            kechikish_min INTEGER DEFAULT 0,
            jarima INTEGER DEFAULT 0,
            holat TEXT DEFAULT 'keldi',
            UNIQUE(sana, telegram_id)
        )""")


def now():
    return datetime.now(TZ)


def bugun():
    return now().strftime("%Y-%m-%d")


def get_xodim(tg_id: int):
    with db() as c:
        return c.execute(
            "SELECT * FROM xodimlar WHERE telegram_id=?", (tg_id,)
        ).fetchone()


def kun_narxi(oylik: int) -> float:
    return oylik / ISH_KUNLARI


def minut_narxi(oylik: int) -> float:
    bosh = datetime.strptime(ISH_BOSHLANISH, "%H:%M")
    tug = datetime.strptime(ISH_TUGASH, "%H:%M")
    ish_minut = (tug - bosh).seconds // 60
    return kun_narxi(oylik) / ish_minut


def masofa_m(lat1, lon1, lat2, lon2) -> float:
    """Haversine — ikki nuqta orasidagi masofa (metr)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def som(x) -> str:
    return f"{int(round(x)):,}".replace(",", " ") + " so'm"


# ==================== KLAVIATURALAR ====================
xodim_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="✅ Keldim"), KeyboardButton(text="🏁 Ketdim")],
    [KeyboardButton(text="📊 Mening hisobotim")],
], resize_keyboard=True)

admin_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Bugun"), KeyboardButton(text="📅 Oylik hisobot")],
    [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="➕ Xodim qo'shish")],
], resize_keyboard=True)

lokatsiya_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
    [KeyboardButton(text="◀️ Orqaga")],
], resize_keyboard=True)


class Holat(StatesGroup):
    lokatsiya_kutish = State()   # data: amal = keldi/ketdi
    yangi_id = State()
    yangi_ism = State()
    yangi_oylik = State()


# ==================== START ====================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id == ADMIN_ID:
        return await message.answer("Admin panel:", reply_markup=admin_kb)
    if get_xodim(message.from_user.id):
        return await message.answer(
            "Assalomu alaykum! Kelganingizda ✅ Keldim, ketayotganda 🏁 Ketdim tugmasini bosing.",
            reply_markup=xodim_kb,
        )
    await message.answer(
        "Siz hali ro'yxatda yo'qsiz.\n"
        f"Sizning ID raqamingiz: <code>{message.from_user.id}</code>\n"
        "Shu raqamni rahbaringizga bering — u sizni qo'shadi.",
        parse_mode="HTML",
    )


# ==================== XODIM: KELDIM / KETDIM ====================
@dp.message(F.text.in_({"✅ Keldim", "🏁 Ketdim"}))
async def keldi_ketdi(message: Message, state: FSMContext):
    if not get_xodim(message.from_user.id):
        return await message.answer("Avval ro'yxatdan o'ting: /start")
    amal = "keldi" if message.text == "✅ Keldim" else "ketdi"
    await state.set_state(Holat.lokatsiya_kutish)
    await state.update_data(amal=amal)
    await message.answer(
        "Ishxonada ekaningizni tasdiqlash uchun lokatsiyangizni yuboring:",
        reply_markup=lokatsiya_kb,
    )


@dp.message(Holat.lokatsiya_kutish, F.text == "◀️ Orqaga")
async def lok_bekor(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=xodim_kb)


@dp.message(Holat.lokatsiya_kutish, F.location)
async def lokatsiya_qabul(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    amal = data["amal"]
    xodim = get_xodim(message.from_user.id)

    m = masofa_m(
        message.location.latitude, message.location.longitude,
        ISHXONA_LAT, ISHXONA_LON,
    )
    if m > MAKS_MASOFA:
        return await message.answer(
            f"❌ Siz ishxonadan {int(m)} metr uzoqdasiz "
            f"(ruxsat etilgan: {MAKS_MASOFA} m). Ishxonaga yetib kelib bosing.",
            reply_markup=xodim_kb,
        )

    vaqt = now()
    with db() as c:
        yozuv = c.execute(
            "SELECT * FROM davomat WHERE sana=? AND telegram_id=?",
            (bugun(), message.from_user.id),
        ).fetchone()

        if amal == "keldi":
            if yozuv:
                return await message.answer(
                    "Bugun allaqachon kelganingiz belgilangan.", reply_markup=xodim_kb
                )
            bosh = vaqt.replace(
                hour=int(ISH_BOSHLANISH[:2]), minute=int(ISH_BOSHLANISH[3:]),
                second=0, microsecond=0,
            )
            kech = max(0, int((vaqt - bosh).total_seconds() // 60))
            jarima = int(round(kech * minut_narxi(xodim["oylik"])))
            c.execute(
                "INSERT INTO davomat (sana, telegram_id, keldi, kechikish_min, jarima) "
                "VALUES (?,?,?,?,?)",
                (bugun(), message.from_user.id, vaqt.strftime("%H:%M"), kech, jarima),
            )
            if kech:
                matn = (f"⏰ Keldingiz: {vaqt.strftime('%H:%M')}\n"
                        f"Kechikish: {kech} daqiqa\nJarima: {som(jarima)}")
            else:
                matn = f"✅ Xush kelibsiz! Keldingiz: {vaqt.strftime('%H:%M')}"
            await message.answer(matn, reply_markup=xodim_kb)
            if kech:
                await bot.send_message(
                    ADMIN_ID,
                    f"⏰ {xodim['ism']} {kech} daqiqa kechikdi "
                    f"({vaqt.strftime('%H:%M')}). Jarima: {som(jarima)}",
                )

        else:  # ketdi
            if not yozuv:
                return await message.answer(
                    "Avval kelganingizni belgilang.", reply_markup=xodim_kb
                )
            if yozuv["ketdi"]:
                return await message.answer(
                    "Bugun allaqachon ketganingiz belgilangan.", reply_markup=xodim_kb
                )
            c.execute(
                "UPDATE davomat SET ketdi=? WHERE id=?",
                (vaqt.strftime("%H:%M"), yozuv["id"]),
            )
            await message.answer(
                f"🏁 Yaxshi boring! Ketdingiz: {vaqt.strftime('%H:%M')}",
                reply_markup=xodim_kb,
            )


@dp.message(Holat.lokatsiya_kutish)
async def lok_notogri(message: Message):
    await message.answer("Iltimos, 📍 tugma orqali jonli lokatsiya yuboring.")


# ==================== XODIM: O'Z HISOBOTI ====================
@dp.message(F.text == "📊 Mening hisobotim")
async def mening_hisobotim(message: Message):
    xodim = get_xodim(message.from_user.id)
    if not xodim:
        return await message.answer("Avval ro'yxatdan o'ting: /start")
    oy = now().strftime("%Y-%m")
    with db() as c:
        rows = c.execute(
            "SELECT * FROM davomat WHERE telegram_id=? AND sana LIKE ?",
            (message.from_user.id, oy + "%"),
        ).fetchall()
    kelgan = sum(1 for r in rows if r["holat"] == "keldi")
    kelmagan = sum(1 for r in rows if r["holat"] == "kelmadi")
    kechikish = sum(r["kechikish_min"] for r in rows)
    jarima = sum(r["jarima"] for r in rows)
    await message.answer(
        f"📊 {now().strftime('%m.%Y')} oyi bo'yicha:\n\n"
        f"Kelgan kunlar: {kelgan}\n"
        f"Kelmagan kunlar: {kelmagan}\n"
        f"Jami kechikish: {kechikish} daqiqa\n"
        f"Jami jarima: {som(jarima)}\n"
        f"Oylik (jarimalardan keyin): {som(xodim['oylik'] - jarima)}"
    )


# ==================== ADMIN: BUGUN ====================
@dp.message(F.text == "📊 Bugun", F.from_user.id == ADMIN_ID)
async def admin_bugun(message: Message):
    with db() as c:
        xodimlar = c.execute("SELECT * FROM xodimlar").fetchall()
        rows = {
            r["telegram_id"]: r
            for r in c.execute(
                "SELECT * FROM davomat WHERE sana=?", (bugun(),)
            ).fetchall()
        }
    if not xodimlar:
        return await message.answer("Xodimlar ro'yxati bo'sh.")
    keldi, kechikdi, kelmadi = [], [], []
    for x in xodimlar:
        r = rows.get(x["telegram_id"])
        if not r or r["holat"] == "kelmadi":
            kelmadi.append(x["ism"])
        elif r["kechikish_min"] > 0:
            kechikdi.append(
                f"{x['ism']} — {r['keldi']} (+{r['kechikish_min']} daq, {som(r['jarima'])})"
            )
        else:
            keldi.append(f"{x['ism']} — {r['keldi']}")
    matn = [f"📊 Bugun ({now().strftime('%d.%m.%Y')})\n"]
    matn.append(f"✅ O'z vaqtida ({len(keldi)}):")
    matn += [f"  • {s}" for s in keldi] or ["  —"]
    matn.append(f"\n⏰ Kechikdi ({len(kechikdi)}):")
    matn += [f"  • {s}" for s in kechikdi] or ["  —"]
    matn.append(f"\n❌ Hali kelmadi ({len(kelmadi)}):")
    matn += [f"  • {s}" for s in kelmadi] or ["  —"]
    await message.answer("\n".join(matn))


# ==================== ADMIN: OYLIK HISOBOT ====================
@dp.message(F.text == "📅 Oylik hisobot", F.from_user.id == ADMIN_ID)
async def admin_oylik(message: Message):
    oy = now().strftime("%Y-%m")
    with db() as c:
        xodimlar = c.execute("SELECT * FROM xodimlar").fetchall()
        rows = c.execute(
            "SELECT * FROM davomat WHERE sana LIKE ?", (oy + "%",)
        ).fetchall()
    if not xodimlar:
        return await message.answer("Xodimlar ro'yxati bo'sh.")
    matn = [f"📅 {now().strftime('%m.%Y')} oyi hisoboti\n"]
    for x in xodimlar:
        xr = [r for r in rows if r["telegram_id"] == x["telegram_id"]]
        kelgan = sum(1 for r in xr if r["holat"] == "keldi")
        kelmagan = sum(1 for r in xr if r["holat"] == "kelmadi")
        kechikish = sum(r["kechikish_min"] for r in xr)
        jarima = sum(r["jarima"] for r in xr)
        matn.append(
            f"👤 {x['ism']}\n"
            f"  Kelgan: {kelgan} kun | Kelmagan: {kelmagan} kun\n"
            f"  Kechikish: {kechikish} daq | Jarima: {som(jarima)}\n"
            f"  Oylik: {som(x['oylik'])} → To'lanadi: {som(x['oylik'] - jarima)}\n"
        )
    await message.answer("\n".join(matn))


# ==================== ADMIN: XODIMLAR ====================
@dp.message(F.text == "👥 Xodimlar", F.from_user.id == ADMIN_ID)
async def admin_xodimlar(message: Message):
    with db() as c:
        rows = c.execute("SELECT * FROM xodimlar").fetchall()
    if not rows:
        return await message.answer("Ro'yxat bo'sh. ➕ Xodim qo'shish tugmasini bosing.")
    for r in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🗑 O'chirish", callback_data=f"del:{r['telegram_id']}"
            )
        ]])
        await message.answer(
            f"👤 {r['ism']}\nID: {r['telegram_id']}\n"
            f"Oylik: {som(r['oylik'])}\n"
            f"1 daqiqa kechikish: {som(minut_narxi(r['oylik']))} | "
            f"1 kun kelmaslik: {som(kun_narxi(r['oylik']))}",
            reply_markup=kb,
        )


@dp.callback_query(F.data.startswith("del:"))
async def xodim_ochirish(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Ruxsat yo'q", show_alert=True)
    tg_id = int(call.data.split(":")[1])
    with db() as c:
        c.execute("DELETE FROM xodimlar WHERE telegram_id=?", (tg_id,))
    await call.message.edit_text("🗑 Xodim ro'yxatdan o'chirildi.")


# ==================== ADMIN: XODIM QO'SHISH ====================
@dp.message(F.text == "➕ Xodim qo'shish", F.from_user.id == ADMIN_ID)
async def qoshish_boshla(message: Message, state: FSMContext):
    await state.set_state(Holat.yangi_id)
    await message.answer(
        "Xodimning Telegram ID raqamini yuboring.\n"
        "(Xodim botga /start bossa, bot unga ID sini ko'rsatadi.)"
    )


@dp.message(Holat.yangi_id)
async def qoshish_id(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        return await message.answer("ID faqat raqamlardan iborat bo'ladi. Qayta yuboring:")
    await state.update_data(tg_id=int(message.text.strip()))
    await state.set_state(Holat.yangi_ism)
    await message.answer("Xodimning ism-familiyasini yozing:")


@dp.message(Holat.yangi_ism)
async def qoshish_ism(message: Message, state: FSMContext):
    await state.update_data(ism=message.text.strip())
    await state.set_state(Holat.yangi_oylik)
    await message.answer("Xodimning oylik maoshini yozing (faqat raqam, masalan: 4000000):")


@dp.message(Holat.yangi_oylik)
async def qoshish_oylik(message: Message, state: FSMContext):
    raqam = message.text.strip().replace(" ", "")
    if not raqam.isdigit():
        return await message.answer("Faqat raqam yozing, masalan: 4000000")
    data = await state.get_data()
    await state.clear()
    oylik = int(raqam)
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO xodimlar (telegram_id, ism, oylik, qoshilgan) "
            "VALUES (?,?,?,?)",
            (data["tg_id"], data["ism"], oylik, bugun()),
        )
    await message.answer(
        f"✅ {data['ism']} qo'shildi.\n"
        f"Oylik: {som(oylik)}\n"
        f"1 daqiqa kechikish jarimasi: {som(minut_narxi(oylik))}\n"
        f"1 kun kelmaslik jarimasi: {som(kun_narxi(oylik))}",
        reply_markup=admin_kb,
    )
    try:
        await bot.send_message(
            data["tg_id"],
            "Siz davomat tizimiga qo'shildingiz! /start ni bosing.",
        )
    except Exception:
        pass  # xodim hali botga start bosmagan bo'lishi mumkin


# ==================== KUN YAKUNI (avtomatik) ====================
async def kun_yakuni():
    """Ish tugagach: kelmaganlarni belgilash, jarima yozish, adminga xulosa."""
    if now().weekday() in DAM_KUNLARI:
        return
    with db() as c:
        xodimlar = c.execute("SELECT * FROM xodimlar").fetchall()
        kelganlar = {
            r["telegram_id"]
            for r in c.execute(
                "SELECT telegram_id FROM davomat WHERE sana=?", (bugun(),)
            ).fetchall()
        }
        kelmaganlar = []
        for x in xodimlar:
            if x["telegram_id"] not in kelganlar:
                jarima = int(round(kun_narxi(x["oylik"])))
                c.execute(
                    "INSERT OR IGNORE INTO davomat "
                    "(sana, telegram_id, holat, jarima) VALUES (?,?,?,?)",
                    (bugun(), x["telegram_id"], "kelmadi", jarima),
                )
                kelmaganlar.append(f"{x['ism']} — jarima {som(jarima)}")
    if kelmaganlar:
        await bot.send_message(
            ADMIN_ID,
            "❌ Bugun kelmaganlar:\n" + "\n".join(f"  • {s}" for s in kelmaganlar),
        )


async def main():
    init_db()
    soat, minut = map(int, ISH_TUGASH.split(":"))
    scheduler.add_job(kun_yakuni, "cron", hour=soat, minute=minut + 30 if minut < 30 else minut)
    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
