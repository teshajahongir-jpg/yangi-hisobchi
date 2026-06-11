# -*- coding: utf-8 -*-
"""
Xodimlar keldi-ketdi nazorati boti — to'liq versiya
Xodim:  Ishni boshlash/yakunlash (lokatsiya bilan), Obed, Qo'shimcha ish, o'z hisoboti
Admin:  jonli panel (kim ishda/obedda/ketgan/kelmagan), xodimlar boshqaruvi,
        kunlik/oylik hisobot, Excel eksport (buxgalteriya), hisobni nollash, sozlamalar
Kutubxonalar: pip install aiogram apscheduler openpyxl aiohttp pytz
"""

import os
import sqlite3
import asyncio
from math import radians, cos, sin, asin, sqrt
from datetime import datetime, timedelta
import pytz
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
# 💡 DIQQAT: Admin_ID faqat shaxsiy akkaunt ID raqami bo'lishi kerak!
ADMIN_ID = 8252424738  

ISH_KUNLARI = 26            # oyda nechta ish kuni
DAM_KUNLARI = [6]           # 6 = yakshanba
TZ = pytz.timezone("Asia/Tashkent")
DB = "davomat.db"

STANDART_SOZLAMALAR = {
    "ish_boshlanish": "09:00",
    "ish_tugash": "18:00",
    "obed_limit": "60",       # daqiqa
    "radius": "150",          # metr
    "lat": "39.745430",
    "lon": "64.439307",
}
# ====================================================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
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
            obed_chiqdi TEXT,
            obed_min INTEGER DEFAULT 0,
            qoshimcha_min INTEGER DEFAULT 0,
            kechikish_min INTEGER DEFAULT 0,
            jarima INTEGER DEFAULT 0,
            daromad INTEGER DEFAULT 0,
            holat TEXT DEFAULT 'ishda',
            tolangan INTEGER DEFAULT 0,
            UNIQUE(sana, telegram_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS sozlamalar (
            kalit TEXT PRIMARY KEY, qiymat TEXT
        )""")
        for k, v in STANDART_SOZLAMALAR.items():
            c.execute(
                "INSERT OR IGNORE INTO sozlamalar (kalit, qiymat) VALUES (?,?)", (k, v)
            )

init_db()

def sozlama(kalit: str) -> str:
    with db() as c:
        return c.execute(
            "SELECT qiymat FROM sozlamalar WHERE kalit=?", (kalit,)
        ).fetchone()["qiymat"]


def sozlama_yoz(kalit: str, qiymat: str):
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO sozlamalar (kalit, qiymat) VALUES (?,?)",
            (kalit, str(qiymat)),
        )


def now():
    return datetime.now(TZ)


def bugun():
    return now().strftime("%Y-%m-%d")


def get_xodim(tg_id: int):
    with db() as c:
        return c.execute(
            "SELECT * FROM xodimlar WHERE telegram_id=?", (tg_id,)
        ).fetchone()


def bugungi_yozuv(tg_id: int):
    with db() as c:
        return c.execute(
            "SELECT * FROM davomat WHERE sana=? AND telegram_id=?", (bugun(), tg_id)
        ).fetchone()


# ==================== HISOB-KITOB ====================
def ish_minutlari() -> int:
    b = datetime.strptime(sozlama("ish_boshlanish"), "%H:%M")
    t = datetime.strptime(sozlama("ish_tugash"), "%H:%M")
    return (t - b).seconds // 60


def kun_narxi(oylik: int) -> float:
    return oylik / ISH_KUNLARI


def minut_narxi(oylik: int) -> float:
    return kun_narxi(oylik) / ish_minutlari()


def masofa_m(lat1, lon1) -> float:
    lat2, lon2 = float(sozlama("lat")), float(sozlama("lon"))
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def som(x) -> str:
    return f"{int(round(x)):,}".replace(",", " ") + " so'm"


def vaqt_soz(minutlar: int) -> str:
    minutlar = max(0, int(minutlar))
    s, d = divmod(minutlar, 60)
    if s and d:
        return f"{s} soat {d} daqiqa"
    if s:
        return f"{s} soat"
    return f"{d} daqiqa"


def dt(sana: str, vaqt: str) -> datetime:
    return datetime.strptime(f"{sana} {vaqt}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def kun_hisobla(yozuv) -> dict:
    xodim = get_xodim(yozuv["telegram_id"])
    oylik = xodim["oylik"]
    keldi = dt(yozuv["sana"], yozuv["keldi"])
    ketdi = dt(yozuv["sana"], yozuv["ketdi"])

    jami_min = int((ketdi - keldi).total_seconds() // 60)
    sof_min = max(0, jami_min - yozuv["obed_min"])

    obed_limit = int(sozlama("obed_limit"))
    obed_oshdi = max(0, yozuv["obed_min"] - obed_limit)

    jarima = int(round(
        (yozuv["kechikish_min"] + obed_oshdi) * minut_narxi(oylik)
    ))
    bonus = int(round(yozuv["qoshimcha_min"] * minut_narxi(oylik)))
    daromad = max(0, int(round(kun_narxi(oylik))) - jarima + bonus)
    return {
        "sof_min": sof_min, "obed_oshdi": obed_oshdi,
        "jarima": jarima, "bonus": bonus, "daromad": daromad,
    }


# ==================== KLAVIATURALAR ====================
xodim_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🟢 Ishni boshlash")],
    [KeyboardButton(text="🥪 Obedga chiqish"), KeyboardButton(text="🔙 Obeddan qaytish")],
    [KeyboardButton(text="⏰ Qo'shimcha ishlash")],
    [KeyboardButton(text="🔴 Ishni yakunlash")],
    [KeyboardButton(text="📊 Mening hisobotim")],
], resize_keyboard=True)

admin_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Bugun"), KeyboardButton(text="📅 Hisobot")],
    [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="➕ Xodim qo'shish")],
    [KeyboardButton(text="📥 Excel (Buxgalteriya)"), KeyboardButton(text="💰 Hisobni nollash")],
    [KeyboardButton(text="⚙️ Sozlamalar")],
], resize_keyboard=True)

lokatsiya_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📍 Lokatsiyani yuborish", request_location=True)],
    [KeyboardButton(text="◀️ Orqaga")],
], resize_keyboard=True)


class Holat(StatesGroup):
    lokatsiya = State()        
    yangi_id = State()
    yangi_ism = State()
    yangi_oylik = State()
    oylik_tahrir = State()     
    soz_qiymat = State()       
    soz_lokatsiya = State()


# ==================== XODIM: START ====================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id == ADMIN_ID:
        return await message.answer("👨‍💼 <b>Admin panel</b>", reply_markup=admin_kb)
    if get_xodim(message.from_user.id):
        return await message.answer(
            "Assalomu alaykum! Tugmalardan foydalaning 👇", reply_markup=xodim_kb
        )
    await message.answer(
        "Siz hali ro'yxatda yo'qsiz.\n"
        f"Sizning ID raqamingiz: <code>{message.from_user.id}</code>\n"
        "Shu raqamni rahbaringizga bering."
    )


# ==================== XODIM: ISH BOSHLASH / YAKUNLASH ====================
@dp.message(F.text.in_({"🟢 Ishni boshlash", "🔴 Ishni yakunlash"}))
async def ish_amal(message: Message, state: FSMContext):
    if not get_xodim(message.from_user.id):
        return await message.answer("Avval ro'yxatdan o'ting: /start")
    amal = "boshlash" if "boshlash" in message.text else "yakunlash"
    y = bugungi_yozuv(message.from_user.id)
    if amal == "boshlash" and y:
        return await message.answer("Bugun ish allaqachon boshlangan.")
    if amal == "yakunlash":
        if not y or not y["keldi"]:
            return await message.answer("Avval ishni boshlang.")
        if y["ketdi"]:
            return await message.answer("Bugun ish allaqachon yakunlangan.")
        if y["holat"] == "obedda":
            return await message.answer("Avval 🔙 Obeddan qaytish tugmasini bosing.")
    await state.set_state(Holat.lokatsiya)
    await state.update_data(amal=amal)
    await message.answer(
        "Ishxonada ekaningizni tasdiqlang — lokatsiya yuboring:",
        reply_markup=lokatsiya_kb,
    )


@dp.message(Holat.lokatsiya, F.text == "◀️ Orqaga")
async def lok_bekor(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=xodim_kb)


@dp.message(Holat.lokatsiya, F.location)
async def lok_qabul(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    xodim = get_xodim(message.from_user.id)
    m = masofa_m(message.location.latitude, message.location.longitude)
    radius = int(sozlama("radius"))
    if m > radius:
        return await message.answer(
            f"❌ Siz ishxonadan <b>{int(m)} m</b> uzoqdasiz "
            f"(ruxsat: {radius} m).", reply_markup=xodim_kb,
        )

    vaqt = now()
    if data["amal"] == "boshlash":
        bosh = dt(bugun(), sozlama("ish_boshlanish"))
        kech = max(0, int((vaqt - bosh).total_seconds() // 60))
        with db() as c:
            c.execute(
                "INSERT INTO davomat (sana, telegram_id, keldi, kechikish_min, holat) "
                "VALUES (?,?,?,?, 'ishda')",
                (bugun(), message.from_user.id, vaqt.strftime("%H:%M"), kech),
            )
        if kech:
            jarima = int(round(kech * minut_narxi(xodim["oylik"])))
            await message.answer(
                f"✅ Ish boshlandi. Vaqt: {vaqt.strftime('%H:%M')}\n"
                f"⚠️ Kechikish: <b>{vaqt_soz(kech)}</b> | Jarima: <b>{som(jarima)}</b>",
                reply_markup=xodim_kb,
            )
            await bot.send_message(
                ADMIN_ID,
                f"⏰ <b>{xodim['ism']}</b> {vaqt_soz(kech)} kechikdi "
                f"({vaqt.strftime('%H:%M')}). Jarima: {som(jarima)}",
            )
        else:
            await message.answer(
                f"✅ Ish boshlandi. Vaqt: {vaqt.strftime('%H:%M')}\nYaxshi ish kuni tilaymiz!",
                reply_markup=xodim_kb,
            )
    else:  
        y = bugungi_yozuv(message.from_user.id)
        with db() as c:
            c.execute(
                "UPDATE davomat SET ketdi=?, holat='ketdi' WHERE id=?",
                (vaqt.strftime("%H:%M"), y["id"]),
            )
            y = c.execute("SELECT * FROM davomat WHERE id=?", (y["id"],)).fetchone()
            h = kun_hisobla(y)
            c.execute(
                "UPDATE davomat SET jarima=?, daromad=? WHERE id=?",
                (h["jarima"], h["daromad"], y["id"]),
            )
        matn = (
            f"🔴 Ish yakunlandi. Vaqt: {vaqt.strftime('%H:%M')}\n"
            f"Sof ish vaqti: <b>{vaqt_soz(h['sof_min'])}</b>\n"
        )
        if y["obed_min"]:
            matn += f"Obed: {vaqt_soz(y['obed_min'])}"
            if h["obed_oshdi"]:
                matn += f" (limitdan {h['obed_oshdi']} daq oshdi)"
            matn += "\n"
        if y["qoshimcha_min"]:
            matn += f"Qo'shimcha ish: {vaqt_soz(y['qoshimcha_min'])} (+{som(h['bonus'])})\n"
        if h["jarima"]:
            matn += f"Jarima: {som(h['jarima'])}\n"
        matn += f"Bugungi daromad: <b>{som(h['daromad'])}</b>"
        await message.answer(matn, reply_markup=xodim_kb)


@dp.message(Holat.lokatsiya)
async def lok_notogri(message: Message):
    await message.answer("Iltimos, 📍 tugma orqali lokatsiya yuboring.")


# ==================== XODIM: OBED ====================
@dp.message(F.text == "🥪 Obedga chiqish")
async def obed_chiqish(message: Message):
    y = bugungi_yozuv(message.from_user.id)
    if not y or y["ketdi"]:
        return await message.answer("Hozir ish vaqtida emassiz.")
    if y["holat"] == "obedda":
        return await message.answer("Siz allaqachon obeddasiz.")
    if y["obed_min"] > 0:
        return await message.answer("Bugun obedga chiqib bo'lgansiz.")
    with db() as c:
        c.execute(
            "UPDATE davomat SET obed_chiqdi=?, holat='obedda' WHERE id=?",
            (now().strftime("%H:%M"), y["id"]),
        )
    await message.answer(
        f"🥪 Yoqimli ishtaha! Obed limiti: {sozlama('obed_limit')} daqiqa."
    )


@dp.message(F.text == "🔙 Obeddan qaytish")
async def obed_qaytish(message: Message):
    y = bugungi_yozuv(message.from_user.id)
    if not y or y["holat"] != "obedda":
        return await message.answer("Siz obedga chiqmagansiz.")
    chiqdi = dt(bugun(), y["obed_chiqdi"])
    obed_min = max(1, int((now() - chiqdi).total_seconds() // 60))
    with db() as c:
        c.execute(
            "UPDATE davomat SET obed_min=?, holat='ishda' WHERE id=?",
            (obed_min, y["id"]),
        )
    limit = int(sozlama("obed_limit"))
    matn = f"🔙 Qaytdingiz. Obed: <b>{vaqt_soz(obed_min)}</b>"
    if obed_min > limit:
        matn += f"\n⚠️ Limitdan {obed_min - limit} daqiqa oshdi — jarima yoziladi."
    await message.answer(matn)


# ==================== XODIM: QO'SHIMCHA ISH ====================
@dp.message(F.text == "⏰ Qo'shimcha ishlash")
async def qoshimcha(message: Message):
    y = bugungi_yozuv(message.from_user.id)
    if not y or not y["ketdi"]:
        return await message.answer(
            "Qo'shimcha ish — asosiy ish yakunlangandan keyin boshlanadi.\n"
            "Avval 🔴 Ishni yakunlash tugmasini bosing, keyin qo'shimcha ishni boshlang."
        )
    with db() as c:
        boshlandi = dt(bugun(), y["ketdi"]) + timedelta(minutes=y["qoshimcha_min"])
        qo_min = max(0, int((now() - boshlandi).total_seconds() // 60))
        if qo_min == 0:
            return await message.answer(
                "⏰ Qo'shimcha ish boshlandi. Tugatganingizda shu tugmani yana bosing."
            )
        jami = y["qoshimcha_min"] + qo_min
        c.execute("UPDATE davomat SET qoshimcha_min=? WHERE id=?", (jami, y["id"]))
        y2 = c.execute("SELECT * FROM davomat WHERE id=?", (y["id"],)).fetchone()
        h = kun_hisobla(y2)
        c.execute(
            "UPDATE davomat SET jarima=?, daromad=? WHERE id=?",
            (h["jarima"], h["daromad"], y["id"]),
        )
    await message.answer(
        f"⏰ Qo'shimcha ish: <b>{vaqt_soz(jami)}</b> | Bonus: <b>{som(h['bonus'])}</b>\n"
        f"Bugungi daromad: <b>{som(h['daromad'])}</b>"
    )


# ==================== XODIM: O'Z HISOBOTI ====================
@dp.message(F.text == "📊 Mening hisobotim")
async def mening(message: Message):
    xodim = get_xodim(message.from_user.id)
    if not xodim:
        return await message.answer("Avval ro'yxatdan o'ting: /start")
    with db() as c:
        rows = c.execute(
            "SELECT * FROM davomat WHERE telegram_id=? AND tolangan=0",
            (message.from_user.id,),
        ).fetchall()
    kelgan = sum(1 for r in rows if r["holat"] != "kelmadi")
    kelmagan = sum(1 for r in rows if r["holat"] == "kelmadi")
    kechikish = sum(r["kechikish_min"] for r in rows)
    qoshimcha_m = sum(r["qoshimcha_min"] for r in rows)
    jarima = sum(r["jarima"] for r in rows)
    balans = sum(r["daromad"] for r in rows)
    await message.answer(
        f"📊 <b>{xodim['ism']}</b> — joriy hisob:\n\n"
        f"Kelgan kunlar: {kelgan}\n"
        f"Kelmagan kunlar: {kelmagan}\n"
        f"Jami kechikish: {vaqt_soz(kechikish)}\n"
        f"Qo'shimcha ish: {vaqt_soz(qoshimcha_m)}\n"
        f"Jami jarima: {som(jarima)}\n"
        f"💰 To'lanadigan balans: <b>{som(balans)}</b>"
    )


# ==================== ADMIN: BUGUN (JONLI PANEL) ====================
def faqat_admin(message: Message) -> bool:
    return message.from_user.id == ADMIN_ID


@dp.message(F.text == "📊 Bugun", faqat_admin)
async def admin_bugun(message: Message):
    with db() as c:
        xodimlar = c.execute("SELECT * FROM xodimlar ORDER BY ism").fetchall()
        rows = {
            r["telegram_id"]: r
            for r in c.execute("SELECT * FROM davomat WHERE sana=?", (bugun(),)).fetchall()
        }
    if not xodimlar:
        return await message.answer("Xodimlar ro'yxati bo'sh.")
    ishda, obedda, ketgan, kelmagan = [], [], [], []
    for x in xodimlar:
        r = rows.get(x["telegram_id"])
        if not r:
            kelmagan.append(x["ism"])
        elif r["holat"] == "kelmadi":
            kelmagan.append(f"{x['ism']} (jarima yozilgan)")
        elif r["holat"] == "obedda":
            obedda.append(f"{x['ism']} — {r['obed_chiqdi']} dan beri")
        elif r["holat"] == "ketdi":
            h = kun_hisobla(r)
            ketgan.append(
                f"{x['ism']} — {r['keldi']}–{r['ketdi']}, sof {vaqt_soz(h['sof_min'])}"
            )
        else:
            s = f"{x['ism']} — {r['keldi']} da keldi"
            if r["kechikish_min"]:
                s += f" (⚠️ {vaqt_soz(r['kechikish_min'])} kechikdi)"
            ishda.append(s)
    matn = [f"📊 <b>Bugun — {now().strftime('%d.%m.%Y, %H:%M')}</b>\n"]
    matn.append(f"🟢 Ishda ({len(ishda)}):")
    matn += [f"  • {s}" for s in ishda] or ["  —"]
    matn.append(f"\n🥪 Obedda ({len(obedda)}):")
    matn += [f"  • {s}" for s in obedda] or ["  —"]
    matn.append(f"\n🔴 Ishni tugatgan ({len(ketgan)}):")
    matn += [f"  • {s}" for s in ketgan] or ["  —"]
    matn.append(f"\n❌ Kelmagan ({len(kelmagan)}):")
    matn += [f"  • {s}" for s in kelmagan] or ["  —"]
    await message.answer("\n".join(matn))


# ==================== ADMIN: HISOBOT ====================
@dp.message(F.text == "📅 Hisobot", faqat_admin)
async def admin_hisobot_menyu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Bugun", callback_data="his:kun"),
        InlineKeyboardButton(text="Shu oy", callback_data="his:oy"),
        InlineKeyboardButton(text="To'lanmagan balans", callback_data="his:balans"),
    ]])
    await message.answer("Qaysi hisobot kerak?", reply_markup=kb)


@dp.callback_query(F.data.startswith("his:"))
async def admin_hisobot(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Ruxsat yo'q", show_alert=True)
    tur = call.data.split(":")[1]
    with db() as c:
        xodimlar = c.execute("SELECT * FROM xodimlar ORDER BY ism").fetchall()
        if tur == "kun":
            rows = c.execute("SELECT * FROM davomat WHERE sana=?", (bugun(),)).fetchall()
            sarlavha = f"📅 Bugungi hisobot ({now().strftime('%d.%m.%Y')})"
        elif tur == "oy":
            rows = c.execute(
                "SELECT * FROM davomat WHERE sana LIKE ?", (now().strftime("%Y-%m") + "%",)
            ).fetchall()
            sarlavha = f"📅 {now().strftime('%m.%Y')} oyi hisoboti"
        else:
            rows = c.execute("SELECT * FROM davomat WHERE tolangan=0").fetchall()
            sarlavha = "💰 To'lanmagan balanslar"
    matn = [f"<b>{sarlavha}</b>\n"]
    jami_balans = 0
    for x in xodimlar:
        xr = [r for r in rows if r["telegram_id"] == x["telegram_id"]]
        if not xr:
            continue
        kelgan = sum(1 for r in xr if r["holat"] != "kelmadi")
        kelmagan = sum(1 for r in xr if r["holat"] == "kelmadi")
        kechikish = sum(r["kechikish_min"] for r in xr)
        jarima = sum(r["jarima"] for r in xr)
        balans = sum(r["daromad"] for r in xr)
        jami_balans += balans
        matn.append(
            f"👤 <b>{x['ism']}</b>\n"
            f"  Kelgan: {kelgan} | Kelmagan: {kelmagan} | "
            f"Kechikish: {vaqt_soz(kechikish)}\n"
            f"  Jarima: {som(jarima)} | Hisoblangan: <b>{som(balans)}</b>\n"
        )
    matn.append(f"\n<b>Jami: {som(jami_balans)}</b>")
    await call.message.edit_text("\n".join(matn))


# ==================== ADMIN: EXCEL ====================
@dp.message(F.text == "📥 Excel (Buxgalteriya)", faqat_admin)
async def admin_excel(message: Message):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    oy = now().strftime("%Y-%m")
    with db() as c:
        xodimlar = c.execute("SELECT * FROM xodimlar ORDER BY ism").fetchall()
        rows = c.execute(
            "SELECT * FROM davomat WHERE sana LIKE ?", (oy + "%",)
        ).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Oylik hisobot"
    sarlavha = ["Xodim", "Kelgan kun", "Kelmagan kun", "Kechikish (daq)",
                "Qo'shimcha (daq)", "Jarima (so'm)", "Hisoblangan (so'm)",
                "To'lanmagan balans (so'm)"]
    ws.append(sarlavha)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for x in xodimlar:
        xr = [r for r in rows if r["telegram_id"] == x["telegram_id"]]
        balans = sum(
            r["daromad"] for r in xr if not r["tolangan"]
        )
        ws.append([
            x["ism"],
            sum(1 for r in xr if r["holat"] != "kelmadi"),
            sum(1 for r in xr if r["holat"] == "kelmadi"),
            sum(r["kechikish_min"] for r in xr),
            sum(r["qoshimcha_min"] for r in xr),
            sum(r["jarima"] for r in xr),
            sum(r["daromad"] for r in xr),
            balans,
        ])
    for col in "ABCDEFGH":
        ws.column_dimensions[col].width = 20

    fayl = f"hisobot_{oy}.xlsx"
    wb.save(fayl)
    await message.answer_document(
        FSInputFile(fayl), caption=f"📥 {now().strftime('%m.%Y')} oyi hisoboti"
    )
    os.remove(fayl)


# ==================== ADMIN: NOLLASH ====================
@dp.message(F.text == "💰 Hisobni nollash", faqat_admin)
async def nollash_sorov(message: Message):
    with db() as c:
        jami = c.execute(
            "SELECT COALESCE(SUM(daromad),0) j FROM davomat WHERE tolangan=0"
        ).fetchone()["j"]
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Ha, to'landi", callback_data="nol:ha"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="nol:yoq"),
    ]])
    await message.answer(
        f"Jami to'lanmagan balans: <b>{som(jami)}</b>\n\n"
        "Hammasi to'lab berildimi? Tasdiqlasangiz, barcha xodimlar balansi "
        "0 ga tushadi (tarix o'chmaydi, «to'langan» deb belgilanadi).",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("nol:"))
async def nollash(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Ruxsat yo'q", show_alert=True)
    if call.data == "nol:yoq":
        return await call.message.edit_text("Bekor qilindi.")
    with db() as c:
        c.execute("UPDATE davomat SET tolangan=1 WHERE tolangan=0")
    await call.message.edit_text(
        "✅ Barcha xodimlarning hisob-kitoblari 0 ga tushirildi."
    )


# ==================== ADMIN: XODIMLAR ====================
@dp.message(F.text == "👥 Xodimlar", faqat_admin)
async def admin_xodimlar(message: Message):
    with db() as c:
        rows = c.execute("SELECT * FROM xodimlar ORDER BY ism").fetchall()
    if not rows:
        return await message.answer("Ro'yxat bo'sh. ➕ Xodim qo'shish tugmasini bosing.")
    for r in rows:
        with db() as c:
            balans = c.execute(
                "SELECT COALESCE(SUM(daromad),0) j FROM davomat "
                "WHERE telegram_id=? AND tolangan=0", (r["telegram_id"],)
            ).fetchone()["j"]
