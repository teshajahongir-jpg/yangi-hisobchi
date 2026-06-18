import logging
import sqlite3
import os
from datetime import datetime, date, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from namoz_data import bugungi_namoz_vaqtlari

# ─── SOZLAMALAR ───────────────────────────────────────────────
BOT_TOKEN = "8680299057:AAGNxlp-pZAsRD2iCDgtcRjydvT7REOvJvw"
ADMIN_ID = 8252424738

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "xarajat.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ConversationHandler holatlari
KIRIM_MIQDOR, KIRIM_TAVSIF = range(2)
CHIQIM_MIQDOR, CHIQIM_KATEGORIYA, CHIQIM_TAVSIF = range(2, 5)
LIMIT_KIRITISH = 5
BYUDJET_KIRITISH = 6
QARZ_ISM, QARZ_MIQDOR, QARZ_TUR, QARZ_ESLATMA, QARZ_IZOH = range(10, 15)

KATEGORIYALAR = [
    "🍔 Oziq-ovqat", "🚌 Transport", "🏠 Uy-joy", "👕 Kiyim",
    "💊 Sog'liq", "📚 Ta'lim", "🎉 Dam olish", "📦 Boshqa"
]

MOTIVATSION_XABARLAR = [
    "☀️ Assalomu alaykum! Bugun ham samarali kun bo'lsin!",
    "🌟 Yangi kun — yangi imkoniyat! Maqsadlaringizga qadam tashlang!",
    "💪 Bugun kechagidan yaxshiroq bo'lish uchun imkoniyatingiz bor!",
    "🤲 Alloh barchangizga barakali kun bersin!",
    "✨ Bugun kichik qadamlar katta natijalarga olib boradi!",
    "🌱 Har bir yaxshi ish bilan kun boshlansin!",
    "💡 Bugun bitta yangi narsa o'rganing — bu sizni oldinga olib boradi!",
]


# ─── DATABASE ─────────────────────────────────────────────────
def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db_connect()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            ism TEXT,
            username TEXT,
            royxatdan_otgan TEXT,
            kunlik_limit REAL DEFAULT 0,
            oylik_byudjet REAL DEFAULT 0,
            eslatmalar INTEGER DEFAULT 1
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tur TEXT,
            miqdor REAL,
            kategoriya TEXT,
            tavsif TEXT,
            sana TEXT,
            vaqt TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS limit_ogohlantirish (
            user_id INTEGER,
            sana TEXT,
            yuborilgan INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, sana)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS qarzlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            ism TEXT,
            miqdor REAL,
            tur TEXT,
            sana TEXT,
            qaytarish_sanasi TEXT,
            izoh TEXT,
            qaytarildi INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def royxatdan_otkazish(user_id, ism, username):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (user_id, ism, username, royxatdan_otgan) VALUES (?,?,?,?)",
            (user_id, ism or "", username or "", str(date.today()))
        )
        conn.commit()
    conn.close()


def barcha_userlar():
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT user_id, ism, username, kunlik_limit, eslatmalar FROM users")
    rows = c.fetchall()
    conn.close()
    return rows


def qosh_tranzaksiya(user_id, tur, miqdor, kategoriya, tavsif):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO transactions (user_id, tur, miqdor, kategoriya, tavsif, sana, vaqt) VALUES (?,?,?,?,?,?,?)",
        (user_id, tur, miqdor, kategoriya, tavsif, str(date.today()), datetime.now().strftime("%H:%M"))
    )
    conn.commit()
    conn.close()


def oxirgi_yozuvni_ochirish(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT id, tur, miqdor, tavsif FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    if row:
        c.execute("DELETE FROM transactions WHERE id=?", (row[0],))
        conn.commit()
    conn.close()
    return row


def bugungi_hisobot_db(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT tur, miqdor, kategoriya, tavsif, vaqt FROM transactions WHERE user_id=? AND sana=? ORDER BY id",
        (user_id, str(date.today()))
    )
    rows = c.fetchall()
    conn.close()
    return rows


def bugungi_chiqim_jami(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(SUM(miqdor),0) FROM transactions WHERE user_id=? AND sana=? AND tur='chiqim'",
        (user_id, str(date.today()))
    )
    jami = c.fetchone()[0]
    conn.close()
    return jami


def oylik_hisobot_db(user_id):
    conn = db_connect()
    c = conn.cursor()
    oy = datetime.now().strftime("%Y-%m")
    c.execute(
        "SELECT tur, SUM(miqdor) FROM transactions WHERE user_id=? AND sana LIKE ? GROUP BY tur",
        (user_id, f"{oy}%")
    )
    rows = c.fetchall()
    conn.close()
    return rows


def davr_hisobot_db(user_id, boshlanish):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT tur, miqdor, kategoriya, tavsif, sana, vaqt FROM transactions "
        "WHERE user_id=? AND sana>=? ORDER BY sana, id",
        (user_id, str(boshlanish))
    )
    rows = c.fetchall()
    conn.close()
    return rows


def kategoriya_hisobot_db(user_id):
    conn = db_connect()
    c = conn.cursor()
    oy = datetime.now().strftime("%Y-%m")
    c.execute(
        "SELECT kategoriya, SUM(miqdor) FROM transactions "
        "WHERE user_id=? AND tur='chiqim' AND sana LIKE ? GROUP BY kategoriya ORDER BY SUM(miqdor) DESC",
        (user_id, f"{oy}%")
    )
    rows = c.fetchall()
    conn.close()
    return rows


def limit_olish(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT kunlik_limit FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


def limit_saqlash(user_id, limit):
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE users SET kunlik_limit=? WHERE user_id=?", (limit, user_id))
    conn.commit()
    conn.close()


def byudjet_olish(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT oylik_byudjet FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


def byudjet_saqlash(user_id, byudjet):
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE users SET oylik_byudjet=? WHERE user_id=?", (byudjet, user_id))
    conn.commit()
    conn.close()


def eslatma_holati(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT eslatmalar FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 1


def eslatma_almashtirish(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT eslatmalar FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    yangi = 0 if (row and row[0] == 1) else 1
    c.execute("UPDATE users SET eslatmalar=? WHERE user_id=?", (yangi, user_id))
    conn.commit()
    conn.close()
    return yangi


def limit_ogohlantirish_yuborilganmi(user_id, sana):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT yuborilgan FROM limit_ogohlantirish WHERE user_id=? AND sana=?", (user_id, str(sana)))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0] == 1)


def limit_ogohlantirish_belgilash(user_id, sana):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO limit_ogohlantirish (user_id, sana, yuborilgan) VALUES (?,?,1) "
        "ON CONFLICT(user_id, sana) DO UPDATE SET yuborilgan=1",
        (user_id, str(sana))
    )
    conn.commit()
    conn.close()


def admin_statistika():
    conn = db_connect()
    c = conn.cursor()
    bugun = str(date.today())
    oy = datetime.now().strftime("%Y-%m")
    c.execute("SELECT COUNT(*) FROM users")
    jami = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT user_id) FROM transactions WHERE sana=?", (bugun,))
    faol = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(miqdor),0) FROM transactions WHERE tur='kirim' AND sana LIKE ?", (f"{oy}%",))
    kirim = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(miqdor),0) FROM transactions WHERE tur='chiqim' AND sana LIKE ?", (f"{oy}%",))
    chiqim = c.fetchone()[0]
    conn.close()
    return jami, faol, kirim, chiqim


# ─── QARZ DB ──────────────────────────────────────────────────
def qarz_qosh_db(user_id, ism, miqdor, tur, qaytarish, izoh):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO qarzlar (user_id, ism, miqdor, tur, sana, qaytarish_sanasi, izoh, qaytarildi) VALUES (?,?,?,?,?,?,?,0)",
        (user_id, ism, miqdor, tur, str(date.today()), qaytarish, izoh)
    )
    conn.commit()
    conn.close()


def qarz_royxat_db(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, ism, miqdor, tur, qaytarish_sanasi, izoh FROM qarzlar "
        "WHERE user_id=? AND qaytarildi=0 ORDER BY qaytarish_sanasi",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def qarz_yop(qarz_id, user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE qarzlar SET qaytarildi=1 WHERE id=? AND user_id=?", (qarz_id, user_id))
    ta = c.rowcount
    conn.commit()
    conn.close()
    return ta > 0


def muddati_otgan_qarzlar():
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT user_id, id, ism, miqdor, tur, qaytarish_sanasi FROM qarzlar "
        "WHERE qaytarildi=0 AND qaytarish_sanasi<=?",
        (str(date.today()),)
    )
    rows = c.fetchall()
    conn.close()
    return rows


# ─── NAMOZ VAQTLARI ───────────────────────────────────────────
def namoz_vaqtlarini_ol():
    """Islom.uz dan olingan ma'lumotlardan bugungi vaqtni qaytaradi"""
    bugun = str(date.today())
    vaqtlar = bugungi_namoz_vaqtlari(bugun)
    if vaqtlar:
        return vaqtlar
    # Agar jadvalda yo'q bo'lsa Aladhan API ga murojaat
    try:
        d = datetime.now()
        url = f"https://api.aladhan.com/v1/timings/{d.day}-{d.month}-{d.year}"
        params = {"latitude": 39.7747, "longitude": 64.4286, "method": 8}
        resp = requests.get(url, params=params, timeout=10)
        t = resp.json()["data"]["timings"]
        return {
            "bomdod": t["Fajr"][:5],
            "peshin": t["Dhuhr"][:5],
            "asr": t["Asr"][:5],
            "shom": t["Maghrib"][:5],
            "xufton": t["Isha"][:5],
        }
    except Exception as e:
        logger.error(f"Namoz API xatosi: {e}")
        return None


def vaqt_qosh(soat, daqiqa, delta):
    umumiy = (soat * 60 + daqiqa + delta) % (24 * 60)
    return umumiy // 60, umumiy % 60


# ─── ESLATMALAR ───────────────────────────────────────────────
async def barcha_userlarga_yuborish(application, matn, reply_markup=None):
    for user_id, ism, username, limit_q, eslatma in barcha_userlar():
        if eslatma != 1:
            continue
        try:
            await application.bot.send_message(
                chat_id=user_id, text=matn,
                parse_mode="Markdown", reply_markup=reply_markup
            )
        except Exception as e:
            logger.warning(f"{user_id} ga yuborib bo'lmadi: {e}")


async def namoz_eslatma(application, namoz_nomi):
    await barcha_userlarga_yuborish(application, f"🕌 *{namoz_nomi}* namoziga 15 daqiqa qoldi!")


async def namoz_oqildimi_sorov(application, namoz_nomi):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Ha, o'qidim", callback_data=f"namoz_ha_{namoz_nomi}"),
        InlineKeyboardButton("❌ Yo'q", callback_data=f"namoz_yoq_{namoz_nomi}")
    ]])
    for user_id, ism, username, limit_q, eslatma in barcha_userlar():
        if eslatma != 1:
            continue
        try:
            await application.bot.send_message(
                chat_id=user_id,
                text=f"🕌 *{namoz_nomi}* namozini o'qib bo'ldingizmi?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"{user_id}: {e}")


async def uyqu_eslatma(application):
    await barcha_userlarga_yuborish(application, "😴 Uxlash vaqti keldi! Yaxshi tun 🌙")


async def uyg_onish_eslatma(application):
    await barcha_userlarga_yuborish(application, "☀️ Bomdod vaqti yaqinlashdi! Uyg'oning! 🌅")


async def motivatsion_xabar(application):
    import random
    xabar = random.choice(MOTIVATSION_XABARLAR)
    await barcha_userlarga_yuborish(application, xabar)


async def tungi_hisobot_yuborish(application):
    for user_id, ism, username, limit_q, eslatma in barcha_userlar():
        rows = bugungi_hisobot_db(user_id)
        if not rows:
            continue
        kirim = sum(r[1] for r in rows if r[0] == "kirim")
        chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
        qoldiq = kirim - chiqim
        matn = f"📊 *Kunlik hisobot — {date.today().strftime('%d.%m.%Y')}*\n"
        matn += "─────────────────\n"
        matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
        matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
        matn += "─────────────────\n"
        matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
        chiqimlar = [(r[3], r[1], r[4]) for r in rows if r[0] == "chiqim"]
        if chiqimlar:
            matn += "\n📝 *Chiqimlar:*\n"
            for tavsif, miqdor, vaqt in chiqimlar:
                matn += f"  {vaqt} — {tavsif}: {miqdor:,.0f} so'm\n"
        try:
            await application.bot.send_message(chat_id=user_id, text=matn, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"{user_id}: {e}")


async def qarz_eslatma_yuborish(application):
    qarzlar = muddati_otgan_qarzlar()
    user_map = {}
    for uid, qid, ism, miqdor, tur, sana in qarzlar:
        user_map.setdefault(uid, []).append((qid, ism, miqdor, tur, sana))
    for uid, lst in user_map.items():
        matn = "⏰ *Qarz eslatmasi!*\n\n"
        for qid, ism, miqdor, tur, sana in lst:
            if tur == "berdi":
                matn += f"📤 *{ism}* ga bergan qarzingiz:\n"
            else:
                matn += f"📥 *{ism}* dan olgan qarzingiz:\n"
            matn += f"   💰 {miqdor:,.0f} so'm | 📅 {sana}\n\n"
        try:
            await application.bot.send_message(chat_id=uid, text=matn, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"{uid}: {e}")


# ─── REJALASHTIRISH ───────────────────────────────────────────
def rejalashtirish(scheduler, application):
    scheduler.add_job(uyqu_eslatma, "cron", hour=22, minute=30, args=[application], id="uyqu", replace_existing=True)
    scheduler.add_job(tungi_hisobot_yuborish, "cron", hour=0, minute=0, args=[application], id="hisobot", replace_existing=True)
    scheduler.add_job(motivatsion_xabar, "cron", hour=7, minute=0, args=[application], id="motivatsiya", replace_existing=True)
    scheduler.add_job(qarz_eslatma_yuborish, "cron", hour=9, minute=0, args=[application], id="qarz_eslatma", replace_existing=True)
    scheduler.add_job(namoz_rejalashtir, "cron", hour=3, minute=30, args=[scheduler, application], id="namoz_yangi", replace_existing=True)


def namoz_rejalashtir(scheduler, application):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar:
        return
    namoz_emoji = {"bomdod": "🌙", "peshin": "☀️", "asr": "🌤", "shom": "🌇", "xufton": "🌃"}
    for namoz, vaqt_str in vaqtlar.items():
        if namoz == "quyosh":
            continue
        try:
            soat, daqiqa = map(int, vaqt_str.split(":"))
            # 15 daqiqa oldin eslatma
            oldin_s, oldin_d = vaqt_qosh(soat, daqiqa, -15)
            try:
                scheduler.remove_job(f"namoz_oldin_{namoz}")
            except Exception:
                pass
            scheduler.add_job(
                namoz_eslatma, "cron",
                hour=oldin_s, minute=oldin_d,
                args=[application, namoz.capitalize()],
                id=f"namoz_oldin_{namoz}", replace_existing=True
            )
            # 20 daqiqa keyin "o'qidingizmi?"
            keyin_s, keyin_d = vaqt_qosh(soat, daqiqa, 20)
            try:
                scheduler.remove_job(f"namoz_keyin_{namoz}")
            except Exception:
                pass
            scheduler.add_job(
                namoz_oqildimi_sorov, "cron",
                hour=keyin_s, minute=keyin_d,
                args=[application, namoz.capitalize()],
                id=f"namoz_keyin_{namoz}", replace_existing=True
            )
            # Bomdod uchun uyg'otish
            if namoz == "bomdod":
                try:
                    scheduler.remove_job("uyg_onish")
                except Exception:
                    pass
                scheduler.add_job(
                    uyg_onish_eslatma, "cron",
                    hour=oldin_s, minute=oldin_d,
                    args=[application],
                    id="uyg_onish", replace_existing=True
                )
        except Exception as e:
            logger.error(f"Namoz rejalashtirish xatosi {namoz}: {e}")


# ─── TUGMALAR ─────────────────────────────────────────────────
def asosiy_menyu(user_id=None):
    tugmalar = [
        ["➕ Kirim qo'shish", "➖ Chiqim qo'shish"],
        ["📊 Bugungi hisobot", "📅 Oylik hisobot"],
        ["🗓 Haftalik hisobot", "📂 Kategoriya bo'yicha"],
        ["🕌 Namoz vaqtlari", "💸 Kunlik limit"],
        ["💰 Oylik byudjet", "📒 Qarz daftari"],
        ["📥 Excel hisobot", "🗑 Oxirgi yozuvni o'chirish"],
        ["🔔 Eslatmalar", "❓ Yordam"],
    ]
    if user_id == ADMIN_ID:
        tugmalar.append(["👑 Admin panel"])
    return ReplyKeyboardMarkup(tugmalar, resize_keyboard=True)


def bekor_qilish_menyu():
    return ReplyKeyboardMarkup([["🚫 Bekor qilish"]], resize_keyboard=True)


def kategoriya_menyu():
    qatorlar = [KATEGORIYALAR[i:i+2] for i in range(0, len(KATEGORIYALAR), 2)]
    qatorlar.append(["🚫 Bekor qilish"])
    return ReplyKeyboardMarkup(qatorlar, resize_keyboard=True)


# ─── /start ───────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    royxatdan_otkazish(user.id, user.first_name, user.username)
    matn = (
        f"👋 *Assalomu alaykum, {user.first_name}!*\n\n"
        "✨ _Jahongir akadan foydalisi_ ✨\n\n"
        "Bu bot sizga quyidagilarda yordam beradi:\n"
        "• 💰 Kunlik kirim-chiqimlarni kuzatish\n"
        "• 🕌 Namoz vaqtlarini eslatish\n"
        "• 📒 Qarz daftarini yuritish\n"
        "• 📊 Hisobotlar va tahlillar\n\n"
        "Quyidagi tugmalardan foydalaning 👇"
    )
    await update.message.reply_text(matn, parse_mode="Markdown", reply_markup=asosiy_menyu(user.id))


# ─── KIRIM CONVERSATION ───────────────────────────────────────
async def kirim_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("➕ Kirim miqdorini kiriting (masalan: 500000):", reply_markup=bekor_qilish_menyu())
    return KIRIM_MIQDOR


async def kirim_miqdor_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        miqdor = float(update.message.text.replace(" ", "").replace(",", ""))
        if miqdor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ To'g'ri son kiriting:")
        return KIRIM_MIQDOR
    context.user_data["kirim_miqdor"] = miqdor
    await update.message.reply_text("📝 Tavsif kiriting (masalan: maosh):")
    return KIRIM_TAVSIF


async def kirim_tavsif_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    tavsif = update.message.text.strip()
    miqdor = context.user_data.pop("kirim_miqdor")
    user_id = update.effective_user.id
    qosh_tranzaksiya(user_id, "kirim", miqdor, None, tavsif or "Kirim")
    await update.message.reply_text(
        f"✅ Kirim qo'shildi: *{miqdor:,.0f} so'm* — {tavsif}",
        parse_mode="Markdown", reply_markup=asosiy_menyu(user_id)
    )
    return ConversationHandler.END


# ─── CHIQIM CONVERSATION ──────────────────────────────────────
async def chiqim_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("➖ Chiqim miqdorini kiriting (masalan: 25000):", reply_markup=bekor_qilish_menyu())
    return CHIQIM_MIQDOR


async def chiqim_miqdor_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        miqdor = float(update.message.text.replace(" ", "").replace(",", ""))
        if miqdor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ To'g'ri son kiriting:")
        return CHIQIM_MIQDOR
    context.user_data["chiqim_miqdor"] = miqdor
    await update.message.reply_text("📂 Kategoriyani tanlang:", reply_markup=kategoriya_menyu())
    return CHIQIM_KATEGORIYA


async def chiqim_kategoriya_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    if update.message.text not in KATEGORIYALAR:
        await update.message.reply_text("❗ Ro'yxatdan tanlang:", reply_markup=kategoriya_menyu())
        return CHIQIM_KATEGORIYA
    context.user_data["chiqim_kategoriya"] = update.message.text
    await update.message.reply_text("📝 Tavsif kiriting (masalan: tushlik):", reply_markup=bekor_qilish_menyu())
    return CHIQIM_TAVSIF


async def chiqim_tavsif_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    tavsif = update.message.text.strip()
    miqdor = context.user_data.pop("chiqim_miqdor")
    kategoriya = context.user_data.pop("chiqim_kategoriya")
    user_id = update.effective_user.id
    qosh_tranzaksiya(user_id, "chiqim", miqdor, kategoriya, tavsif or "Chiqim")
    await update.message.reply_text(
        f"❌ Chiqim qo'shildi: *{miqdor:,.0f} so'm*\n📂 {kategoriya}\n📝 {tavsif}",
        parse_mode="Markdown", reply_markup=asosiy_menyu(user_id)
    )
    limit_q = limit_olish(user_id)
    if limit_q > 0:
        jami = bugungi_chiqim_jami(user_id)
        if jami >= limit_q and not limit_ogohlantirish_yuborilganmi(user_id, date.today()):
            limit_ogohlantirish_belgilash(user_id, date.today())
            await update.message.reply_text(
                f"⚠️ *Kunlik limit oshib ketdi!*\n💸 Limit: {limit_q:,.0f} so'm\n❌ Bugungi chiqim: {jami:,.0f} so'm",
                parse_mode="Markdown"
            )
    return ConversationHandler.END


async def bekor_qilish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🚫 Bekor qilindi.", reply_markup=asosiy_menyu(update.effective_user.id))
    return ConversationHandler.END


# ─── LIMIT CONVERSATION ───────────────────────────────────────
async def limit_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    limit_q = limit_olish(update.effective_user.id)
    matn = "💸 Kunlik xarajat limitini kiriting (so'mda):\n"
    if limit_q > 0:
        matn += f"📌 Joriy limit: {limit_q:,.0f} so'm\n"
    matn += "0 kiritsangiz limit o'chiriladi."
    await update.message.reply_text(matn, reply_markup=bekor_qilish_menyu())
    return LIMIT_KIRITISH


async def limit_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        limit_q = float(update.message.text.replace(" ", "").replace(",", ""))
        if limit_q < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ To'g'ri son kiriting:")
        return LIMIT_KIRITISH
    user_id = update.effective_user.id
    limit_saqlash(user_id, limit_q)
    if limit_q == 0:
        await update.message.reply_text("✅ Kunlik limit o'chirildi.", reply_markup=asosiy_menyu(user_id))
    else:
        await update.message.reply_text(
            f"✅ Kunlik limit: *{limit_q:,.0f} so'm*",
            parse_mode="Markdown", reply_markup=asosiy_menyu(user_id)
        )
    return ConversationHandler.END


# ─── BYUDJET CONVERSATION ─────────────────────────────────────
async def byudjet_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    byudjet = byudjet_olish(update.effective_user.id)
    matn = "💰 Oylik byudjetingizni kiriting (so'mda):\n"
    if byudjet > 0:
        matn += f"📌 Joriy byudjet: {byudjet:,.0f} so'm\n"
    matn += "0 kiritsangiz byudjet o'chiriladi."
    await update.message.reply_text(matn, reply_markup=bekor_qilish_menyu())
    return BYUDJET_KIRITISH


async def byudjet_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        byudjet = float(update.message.text.replace(" ", "").replace(",", ""))
        if byudjet < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ To'g'ri son kiriting:")
        return BYUDJET_KIRITISH
    user_id = update.effective_user.id
    byudjet_saqlash(user_id, byudjet)
    if byudjet == 0:
        await update.message.reply_text("✅ Oylik byudjet o'chirildi.", reply_markup=asosiy_menyu(user_id))
    else:
        await update.message.reply_text(
            f"✅ Oylik byudjet: *{byudjet:,.0f} so'm*",
            parse_mode="Markdown", reply_markup=asosiy_menyu(user_id)
        )
    return ConversationHandler.END


# ─── QARZ CONVERSATION ────────────────────────────────────────
async def qarz_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 Men berdim", callback_data="qarz_tur_berdi"),
        InlineKeyboardButton("📥 Men oldim", callback_data="qarz_tur_oldi")
    ]])
    await update.message.reply_text("📒 *Qarz daftari*\n\nQarz turi:", parse_mode="Markdown", reply_markup=keyboard)
    return QARZ_TUR


async def qarz_tur_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tur = "berdi" if query.data == "qarz_tur_berdi" else "oldi"
    context.user_data["qarz_tur"] = tur
    matn = "📤 Kimga berdingiz? (Ism):" if tur == "berdi" else "📥 Kimdan oldingiz? (Ism):"
    await query.edit_message_text(matn)
    return QARZ_ISM


async def qarz_ism_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    context.user_data["qarz_ism"] = update.message.text.strip()
    await update.message.reply_text("💰 Miqdorni kiriting (so'mda):", reply_markup=bekor_qilish_menyu())
    return QARZ_MIQDOR


async def qarz_miqdor_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        miqdor = float(update.message.text.replace(" ", "").replace(",", ""))
        if miqdor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ To'g'ri son kiriting:")
        return QARZ_MIQDOR
    context.user_data["qarz_miqdor"] = miqdor
    await update.message.reply_text(
        "📅 Qaytarish sanasini kiriting (masalan: 25.07.2026):",
        reply_markup=bekor_qilish_menyu()
    )
    return QARZ_ESLATMA


async def qarz_sana_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        sana = datetime.strptime(update.message.text.strip(), "%d.%m.%Y").date()
        if sana < date.today():
            await update.message.reply_text("❗ Kelajakdagi sana kiriting:")
            return QARZ_ESLATMA
    except ValueError:
        await update.message.reply_text("❗ Format xato. Masalan: 25.07.2026")
        return QARZ_ESLATMA
    context.user_data["qarz_sana"] = str(sana)
    await update.message.reply_text("📝 Izoh kiriting (yo'q bo'lsa — tire kiriting):", reply_markup=bekor_qilish_menyu())
    return QARZ_IZOH


async def qarz_izoh_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    user_id = update.effective_user.id
    izoh = update.message.text.strip()
    if izoh in ["-", ".", "yo'q", "yoq"]:
        izoh = ""
    ism = context.user_data.pop("qarz_ism")
    miqdor = context.user_data.pop("qarz_miqdor")
    tur = context.user_data.pop("qarz_tur")
    sana = context.user_data.pop("qarz_sana")
    qarz_qosh_db(user_id, ism, miqdor, tur, sana, izoh)
    tur_matn = f"*{ism}* ga berdingiz" if tur == "berdi" else f"*{ism}* dan oldingiz"
    javob = f"✅ Saqlandi!\n👤 {tur_matn}\n💰 {miqdor:,.0f} so'm\n📅 Qaytarish: {sana}"
    if izoh:
        javob += f"\n📝 {izoh}"
    await update.message.reply_text(javob, parse_mode="Markdown", reply_markup=asosiy_menyu(user_id))
    return ConversationHandler.END


# ─── HISOBOTLAR ───────────────────────────────────────────────
async def bugun_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = bugungi_hisobot_db(user_id)
    if not rows:
        await update.message.reply_text("📭 Bugun hech narsa kiritilmagan.")
        return
    kirim = sum(r[1] for r in rows if r[0] == "kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
    qoldiq = kirim - chiqim
    limit_q = limit_olish(user_id)
    matn = f"📊 *Bugun — {date.today().strftime('%d.%m.%Y')}*\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
    if limit_q > 0:
        foiz = min(100, round(chiqim / limit_q * 100))
        matn += f"🎯 Limit: {foiz}% ({chiqim:,.0f}/{limit_q:,.0f})\n"
    await update.message.reply_text(matn, parse_mode="Markdown")


async def oy_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = oylik_hisobot_db(user_id)
    if not rows:
        await update.message.reply_text("📭 Bu oy hech narsa kiritilmagan.")
        return
    kirim = next((r[1] for r in rows if r[0] == "kirim"), 0)
    chiqim = next((r[1] for r in rows if r[0] == "chiqim"), 0)
    qoldiq = kirim - chiqim
    byudjet = byudjet_olish(user_id)
    matn = f"📅 *{datetime.now().strftime('%B %Y')} oylik hisobot*\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
    if byudjet > 0:
        foiz = min(100, round(chiqim / byudjet * 100))
        matn += f"💰 Byudjet: {foiz}% ({chiqim:,.0f}/{byudjet:,.0f})\n"
    await update.message.reply_text(matn, parse_mode="Markdown")


async def hafta_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bir_hafta = date.today() - timedelta(days=7)
    rows = davr_hisobot_db(user_id, bir_hafta)
    if not rows:
        await update.message.reply_text("📭 Bu hafta hech narsa kiritilmagan.")
        return
    kirim = sum(r[1] for r in rows if r[0] == "kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
    matn = f"🗓 *Oxirgi 7 kun* ({bir_hafta.strftime('%d.%m')} — {date.today().strftime('%d.%m')})\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{kirim-chiqim:,.0f} so'm*\n"
    await update.message.reply_text(matn, parse_mode="Markdown")


async def kategoriya_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = kategoriya_hisobot_db(user_id)
    if not rows:
        await update.message.reply_text("📭 Bu oy hech qanday chiqim kiritilmagan.")
        return
    matn = f"📂 *{datetime.now().strftime('%B %Y')} — kategoriya bo'yicha*\n\n"
    jami = 0
    for kategoriya, miqdor in rows:
        matn += f"{kategoriya or '📦 Boshqa'}: *{miqdor:,.0f} so'm*\n"
        jami += miqdor
    matn += f"\n─────────────────\nJami: *{jami:,.0f} so'm*"
    await update.message.reply_text(matn, parse_mode="Markdown")


async def namoz_vaqtlari_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar:
        await update.message.reply_text("❗ Namoz vaqtlarini olishda xatolik.")
        return
    emoji = {"bomdod": "🌙", "peshin": "☀️", "asr": "🌤", "shom": "🌇", "xufton": "🌃"}
    matn = f"🕌 *Buxoro — {date.today().strftime('%d.%m.%Y')}*\n\n"
    for nom, vaqt in vaqtlar.items():
        if nom == "quyosh":
            continue
        matn += f"{emoji.get(nom, '•')} *{nom.capitalize()}:* {vaqt}\n"
    await update.message.reply_text(matn, parse_mode="Markdown")


async def excel_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    boshlanish = date.today().replace(day=1)
    rows = davr_hisobot_db(user_id, boshlanish)
    if not rows:
        await update.message.reply_text("📭 Bu oy uchun ma'lumot topilmadi.")
        return
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hisobot"
    sarlavha_font = Font(bold=True, color="FFFFFF")
    sarlavha_fill = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid")
    sarlavhalar = ["Sana", "Vaqt", "Turi", "Kategoriya", "Tavsif", "Miqdor (so'm)"]
    ws.append(sarlavhalar)
    for hujayra in ws[1]:
        hujayra.font = sarlavha_font
        hujayra.fill = sarlavha_fill
        hujayra.alignment = Alignment(horizontal="center")
    jami_kirim = jami_chiqim = 0
    for tur, miqdor, kategoriya, tavsif, sana, vaqt in rows:
        ws.append([sana, vaqt, "Kirim" if tur == "kirim" else "Chiqim", kategoriya or "-", tavsif, miqdor])
        if tur == "kirim":
            jami_kirim += miqdor
        else:
            jami_chiqim += miqdor
    ws.append([])
    ws.append(["", "", "", "", "Jami kirim:", jami_kirim])
    ws.append(["", "", "", "", "Jami chiqim:", jami_chiqim])
    ws.append(["", "", "", "", "Qoldiq:", jami_kirim - jami_chiqim])
    for ustun, kenglik in zip("ABCDEF", [12, 8, 10, 16, 28, 16]):
        ws.column_dimensions[ustun].width = kenglik
    fayl = os.path.join(BASE_DIR, f"hisobot_{user_id}.xlsx")
    wb.save(fayl)
    oy = datetime.now().strftime("%B %Y")
    with open(fayl, "rb") as f:
        await update.message.reply_document(document=f, filename=f"hisobot_{oy}.xlsx",
                                             caption=f"📥 *{oy}* oyi uchun hisobot", parse_mode="Markdown")
    try:
        os.remove(fayl)
    except Exception:
        pass


async def qarz_royxat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    qarzlar = qarz_royxat_db(user_id)
    if not qarzlar:
        await update.message.reply_text("📭 Ochiq qarzlar yo'q.")
        return
    berganlar = [q for q in qarzlar if q[3] == "berdi"]
    olganlar = [q for q in qarzlar if q[3] == "oldi"]
    matn = "📒 *Qarz daftari*\n\n"
    if berganlar:
        jami = sum(q[2] for q in berganlar)
        matn += f"📤 *Men berganlarim* — {jami:,.0f} so'm\n"
        for qid, ism, miqdor, tur, sana, izoh in berganlar:
            belgi = "⚠️" if sana <= str(date.today()) else "🟢"
            matn += f"{belgi} [{qid}] {ism} — {miqdor:,.0f} so'm | {sana}\n"
        matn += "\n"
    if olganlar:
        jami = sum(q[2] for q in olganlar)
        matn += f"📥 *Men olganlarim* — {jami:,.0f} so'm\n"
        for qid, ism, miqdor, tur, sana, izoh in olganlar:
            belgi = "⚠️" if sana <= str(date.today()) else "🟢"
            matn += f"{belgi} [{qid}] {ism} — {miqdor:,.0f} so'm | {sana}\n"
    matn += "\n✅ Qaytarildi: `/qaytarildi 3`"
    await update.message.reply_text(matn, parse_mode="Markdown")


async def qarz_qaytarildi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        qarz_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❗ Yozing: `/qaytarildi 3`", parse_mode="Markdown")
        return
    if qarz_yop(qarz_id, user_id):
        await update.message.reply_text(f"✅ Qarz #{qarz_id} yopildi.")
    else:
        await update.message.reply_text("❗ Topilmadi yoki sizga tegishli emas.")


async def oxirgi_ochirish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    row = oxirgi_yozuvni_ochirish(user_id)
    if not row:
        await update.message.reply_text("📭 O'chirish uchun yozuv topilmadi.")
        return
    tur_matn = "Kirim" if row[1] == "kirim" else "Chiqim"
    await update.message.reply_text(
        f"🗑 O'chirildi: {tur_matn} — *{row[2]:,.0f} so'm* ({row[3]})",
        parse_mode="Markdown"
    )


async def eslatmalar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    holat = eslatma_holati(user_id)
    matn = "🔔 Eslatmalar: " + ("✅ Yoqilgan" if holat == 1 else "🔇 O'chirilgan")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔇 O'chirish" if holat == 1 else "🔔 Yoqish", callback_data="eslatma_toggle")
    ]])
    await update.message.reply_text(matn, reply_markup=keyboard)


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Ruxsat yo'q.")
        return
    jami, faol, kirim, chiqim = admin_statistika()
    matn = "👑 *Admin Panel*\n"
    matn += "─────────────────\n"
    matn += f"👥 Jami foydalanuvchilar: *{jami}*\n"
    matn += f"🟢 Bugun faol: *{faol}*\n"
    matn += f"✅ Oylik kirim: *{kirim:,.0f} so'm*\n"
    matn += f"❌ Oylik chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += "*Foydalanuvchilar:*\n"
    for user_id, ism, username, limit_q, eslatma in barcha_userlar():
        uname = f"@{username}" if username else "—"
        matn += f"🔹 {ism} ({uname}) — limit: {limit_q:,.0f}\n"
    if len(matn) > 4000:
        for i in range(0, len(matn), 4000):
            await update.message.reply_text(matn[i:i+4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(matn, parse_mode="Markdown")


async def yordam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = (
        "📋 *Barcha imkoniyatlar:*\n\n"
        "➕ *Kirim qo'shish* — daromad kiritish\n"
        "➖ *Chiqim qo'shish* — xarajat (kategoriya bilan)\n"
        "📊 *Bugungi hisobot* — bugungi kirim/chiqim\n"
        "📅 *Oylik hisobot* — shu oy jami\n"
        "🗓 *Haftalik hisobot* — oxirgi 7 kun\n"
        "📂 *Kategoriya bo'yicha* — chiqimlar taqsimoti\n"
        "🕌 *Namoz vaqtlari* — Buxoro (islom.uz)\n"
        "💸 *Kunlik limit* — xarajat chegarasi\n"
        "💰 *Oylik byudjet* — oylik reja\n"
        "📒 *Qarz daftari* — qarzlarni kuzatish\n"
        "📥 *Excel hisobot* — fayl yuklab olish\n"
        "🗑 *Oxirgi yozuvni o'chirish*\n"
        "🔔 *Eslatmalar* — yoqish/o'chirish\n\n"
        "⏰ *Avtomatik:*\n"
        "• 07:00 — motivatsion xabar\n"
        "• Har namozdan 15 daqiqa oldin — eslatma\n"
        "• Har namozdan 20 daqiqa keyin — tasdiq\n"
        "• 22:30 — uyqu eslatmasi\n"
        "• 00:00 — kunlik hisobot\n"
        "• 09:00 — qarz eslatmasi\n"
    )
    await update.message.reply_text(matn, parse_mode="Markdown")


# ─── CALLBACK HANDLERS ────────────────────────────────────────
async def eslatma_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    yangi = eslatma_almashtirish(user_id)
    matn = "🔔 Eslatmalar yoqildi ✅" if yangi == 1 else "🔇 Eslatmalar o'chirildi"
    await query.answer(matn)
    await query.edit_message_text(matn)


async def namoz_javob_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("namoz_ha_"):
        namoz = query.data.replace("namoz_ha_", "")
        await query.edit_message_text(f"✅ *{namoz}* namozi o'qildi. Alloh qabul qilsin! 🤲", parse_mode="Markdown")
    elif query.data.startswith("namoz_yoq_"):
        namoz = query.data.replace("namoz_yoq_", "")
        await query.edit_message_text(f"⏳ *{namoz}* namozi o'qilmadi. Imkon bo'lsa o'qing!", parse_mode="Markdown")


# ─── MATN ROUTER ──────────────────────────────────────────────
async def matn_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text.strip()
    mapping = {
        "📊 Bugungi hisobot": bugun_hisobot,
        "📅 Oylik hisobot": oy_hisobot,
        "🗓 Haftalik hisobot": hafta_hisobot,
        "📂 Kategoriya bo'yicha": kategoriya_hisobot,
        "🕌 Namoz vaqtlari": namoz_vaqtlari_cmd,
        "📥 Excel hisobot": excel_hisobot,
        "🗑 Oxirgi yozuvni o'chirish": oxirgi_ochirish,
        "🔔 Eslatmalar": eslatmalar_cmd,
        "❓ Yordam": yordam,
        "👑 Admin panel": admin_panel,
        "📒 Qarz ro'yxati": qarz_royxat_cmd,
        "➕ Yangi qarz": qarz_boshlash,
        }
    funksiya = mapping.get(matn)
    if funksiya:
        await funksiya(update, context)


# ─── MAIN ─────────────────────────────────────────────────────
def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    kirim_conv = ConversationHandler(
        entry_points=[
            CommandHandler("kirim", kirim_boshlash),
            MessageHandler(filters.Regex("^➕ Kirim qo'shish$"), kirim_boshlash)
        ],
        states={
            KIRIM_MIQDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, kirim_miqdor_qabul)],
            KIRIM_TAVSIF: [MessageHandler(filters.TEXT & ~filters.COMMAND, kirim_tavsif_qabul)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🚫 Bekor qilish$"), bekor_qilish)],
    )

    chiqim_conv = ConversationHandler(
        entry_points=[
            CommandHandler("chiqim", chiqim_boshlash),
            MessageHandler(filters.Regex("^➖ Chiqim qo'shish$"), chiqim_boshlash)
        ],
        states={
            CHIQIM_MIQDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, chiqim_miqdor_qabul)],
            CHIQIM_KATEGORIYA: [MessageHandler(filters.TEXT & ~filters.COMMAND, chiqim_kategoriya_qabul)],
            CHIQIM_TAVSIF: [MessageHandler(filters.TEXT & ~filters.COMMAND, chiqim_tavsif_qabul)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🚫 Bekor qilish$"), bekor_qilish)],
    )

    limit_conv = ConversationHandler(
        entry_points=[
            CommandHandler("limit", limit_boshlash),
            MessageHandler(filters.Regex("^💸 Kunlik limit$"), limit_boshlash)
        ],
        states={
            LIMIT_KIRITISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, limit_qabul)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🚫 Bekor qilish$"), bekor_qilish)],
    )

    byudjet_conv = ConversationHandler(
        entry_points=[
            CommandHandler("byudjet", byudjet_boshlash),
            MessageHandler(filters.Regex("^💰 Oylik byudjet$"), byudjet_boshlash)
        ],
        states={
            BYUDJET_KIRITISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, byudjet_qabul)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🚫 Bekor qilish$"), bekor_qilish)],
    )

    qarz_conv = ConversationHandler(
        entry_points=[
            CommandHandler("qarz", qarz_boshlash),
            MessageHandler(filters.Regex("^📒 Yangi qarz$"), qarz_boshlash)
        ],
        states={
            QARZ_TUR: [CallbackQueryHandler(qarz_tur_callback, pattern="^qarz_tur_")],
            QARZ_ISM: [MessageHandler(filters.TEXT & ~filters.COMMAND, qarz_ism_qabul)],
            QARZ_MIQDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, qarz_miqdor_qabul)],
            QARZ_ESLATMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, qarz_sana_qabul)],
            QARZ_IZOH: [MessageHandler(filters.TEXT & ~filters.COMMAND, qarz_izoh_qabul)],
        },
        fallbacks=[MessageHandler(filters.Regex("^🚫 Bekor qilish$"), bekor_qilish)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(kirim_conv)
    application.add_handler(chiqim_conv)
    application.add_handler(limit_conv)
    application.add_handler(byudjet_conv)
    application.add_handler(qarz_conv)
    application.add_handler(CommandHandler("bugun", bugun_hisobot))
    application.add_handler(CommandHandler("oy", oy_hisobot))
    application.add_handler(CommandHandler("hafta", hafta_hisobot))
    application.add_handler(CommandHandler("kategoriya", kategoriya_hisobot))
    application.add_handler(CommandHandler("namoz", namoz_vaqtlari_cmd))
    application.add_handler(CommandHandler("excel", excel_hisobot))
    application.add_handler(CommandHandler("qarzlar", qarz_royxat_cmd))
    application.add_handler(CommandHandler("qaytarildi", qarz_qaytarildi_cmd))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("yordam", yordam))
    application.add_handler(CallbackQueryHandler(eslatma_toggle_callback, pattern="^eslatma_toggle$"))
    application.add_handler(CallbackQueryHandler(namoz_javob_callback, pattern="^namoz_(ha|yoq)_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, matn_router))

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    rejalashtirish(scheduler, application)
    namoz_rejalashtir(scheduler, application)
    scheduler.start()

    logger.info("Bot ishga tushdi!")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
