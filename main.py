import logging
import sqlite3
import os
from datetime import datetime, date, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

# --- SOZLAMALAR ---
BOT_TOKEN = "8680299057:AAEBw-pAsK_it0cvsY8RUGbtcNVX_UmsPyQ"  # @BotFather dan oling
ADMIN_ID = 8252424738  # Sizning Telegram ID (admin huquqi shu ID ga beriladi)

# Buxoro koordinatalari (namoz vaqtlari uchun)
LATITUDE = 39.7747
LONGITUDE = 64.4286

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "xarajat.db")
START_IMAGE_PATH = os.path.join(BASE_DIR, "start_rasm.jpg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ConversationHandler holatlari
KIRIM_MIQDOR, KIRIM_TAVSIF = range(2)
CHIQIM_MIQDOR, CHIQIM_KATEGORIYA, CHIQIM_TAVSIF = range(2, 5)
LIMIT_KIRITISH = 5

# Standart kategoriyalar
KATEGORIYALAR = ["🍔 Oziq-ovqat", "🚌 Transport", "🏠 Uy-joy", "👕 Kiyim",
                  "💊 Sog'liq", "📚 Ta'lim", "🎉 Dam olish", "📦 Boshqa"]


# ============================================================
#                        DATABASE
# ============================================================
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
            ro_yxatdan_otgan TEXT,
            kunlik_limit REAL DEFAULT 0,
            eslatmalar_yoqilgan INTEGER DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tur TEXT,            -- 'kirim' yoki 'chiqim'
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

    conn.commit()
    conn.close()


def royxatdan_otkazish(user_id, ism, username):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (user_id, ism, username, ro_yxatdan_otgan) VALUES (?,?,?,?)",
            (user_id, ism, username, str(date.today()))
        )
        conn.commit()
    conn.close()


def barcha_userlar():
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT user_id, ism, username, kunlik_limit, eslatmalar_yoqilgan FROM users ORDER BY user_id")
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
    yangi_id = c.lastrowid
    conn.close()
    return yangi_id


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


def bugungi_hisobot(user_id):
    conn = db_connect()
    c = conn.cursor()
    bugun = str(date.today())
    c.execute(
        "SELECT tur, miqdor, kategoriya, tavsif, vaqt FROM transactions WHERE user_id=? AND sana=? ORDER BY id",
        (user_id, bugun)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def bugungi_chiqim_jami(user_id):
    conn = db_connect()
    c = conn.cursor()
    bugun = str(date.today())
    c.execute(
        "SELECT COALESCE(SUM(miqdor),0) FROM transactions WHERE user_id=? AND sana=? AND tur='chiqim'",
        (user_id, bugun)
    )
    jami = c.fetchone()[0]
    conn.close()
    return jami


def davr_hisobot(user_id, boshlanish_sana):
    """boshlanish_sana dan bugungacha bo'lgan barcha tranzaksiyalar"""
    conn = db_connect()
    c = conn.cursor()
    c.execute(
        "SELECT tur, miqdor, kategoriya, tavsif, sana, vaqt FROM transactions "
        "WHERE user_id=? AND sana>=? ORDER BY sana, id",
        (user_id, str(boshlanish_sana))
    )
    rows = c.fetchall()
    conn.close()
    return rows


def oylik_hisobot(user_id):
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


def kategoriya_boyicha_chiqim(user_id, oy=None):
    conn = db_connect()
    c = conn.cursor()
    if oy is None:
        oy = datetime.now().strftime("%Y-%m")
    c.execute(
        "SELECT kategoriya, SUM(miqdor) FROM transactions "
        "WHERE user_id=? AND tur='chiqim' AND sana LIKE ? GROUP BY kategoriya ORDER BY SUM(miqdor) DESC",
        (user_id, f"{oy}%")
    )
    rows = c.fetchall()
    conn.close()
    return rows


def limit_oynat(user_id, limit_qiymati):
    conn = db_connect()
    c = conn.cursor()
    c.execute("UPDATE users SET kunlik_limit=? WHERE user_id=?", (limit_qiymati, user_id))
    conn.commit()
    conn.close()


def limit_olish(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT kunlik_limit FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0


def eslatma_holati_almashtirish(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT eslatmalar_yoqilgan FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    yangi_holat = 0 if (row and row[0] == 1) else 1
    c.execute("UPDATE users SET eslatmalar_yoqilgan=? WHERE user_id=?", (yangi_holat, user_id))
    conn.commit()
    conn.close()
    return yangi_holat


def eslatma_holati(user_id):
    conn = db_connect()
    c = conn.cursor()
    c.execute("SELECT eslatmalar_yoqilgan FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 1


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


def admin_umumiy_statistika():
    conn = db_connect()
    c = conn.cursor()
    bugun = str(date.today())
    oy = datetime.now().strftime("%Y-%m")

    c.execute("SELECT COUNT(*) FROM users")
    jami_userlar = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT user_id) FROM transactions WHERE sana=?", (bugun,))
    bugun_faol = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(miqdor),0) FROM transactions WHERE tur='kirim' AND sana LIKE ?", (f"{oy}%",))
    oylik_kirim = c.fetchone()[0]

    c.execute("SELECT COALESCE(SUM(miqdor),0) FROM transactions WHERE tur='chiqim' AND sana LIKE ?", (f"{oy}%",))
    oylik_chiqim = c.fetchone()[0]

    conn.close()
    return {
        "jami_userlar": jami_userlar,
        "bugun_faol": bugun_faol,
        "oylik_kirim": oylik_kirim,
        "oylik_chiqim": oylik_chiqim
    }


# ============================================================
#                    NAMOZ VAQTLARI (Aladhan API)
# ============================================================
def namoz_vaqtlarini_ol():
    try:
        bugun = datetime.now()
        url = f"https://api.aladhan.com/v1/timings/{bugun.day}-{bugun.month}-{bugun.year}"
        params = {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "method": 2  # Umm Al-Qura metodi
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        timings = data["data"]["timings"]
        return {
            "Bomdod": timings["Fajr"],
            "Quyosh": timings["Sunrise"],
            "Peshin": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Shom": timings["Maghrib"],
            "Xufton": timings["Isha"]
        }
    except Exception as e:
        logger.error(f"Namoz vaqtlari xatosi: {e}")
        return None


def vaqt_qoshish(soat, daqiqa, qoshiladigan_daqiqa):
    """soat:daqiqa ga necha daqiqa qo'shish/ayirish (manfiy bo'lishi mumkin), 24-soatlik formatda qaytaradi"""
    umumiy = soat * 60 + daqiqa + qoshiladigan_daqiqa
    umumiy %= 24 * 60
    return umumiy // 60, umumiy % 60


# ============================================================
#                  ESLATMALARNI YUBORISH FUNKSIYALARI
# ============================================================
async def barcha_faol_userlarga_yubor(application, matn, reply_markup=None, parse_mode="Markdown"):
    for user_id, ism, username, limit_q, eslatma_yoqilgan in barcha_userlar():
        if eslatma_yoqilgan != 1:
            continue
        try:
            await application.bot.send_message(
                chat_id=user_id, text=matn, parse_mode=parse_mode, reply_markup=reply_markup
            )
        except Exception as e:
            logger.warning(f"{user_id} ga xabar yuborib bo'lmadi: {e}")


async def namoz_eslatma(application, namoz_nomi):
    await barcha_faol_userlarga_yubor(
        application,
        f"🕌 *{namoz_nomi}* namoziga 15 daqiqa qoldi!"
    )


async def namoz_oqildimi_sorov(application, namoz_nomi):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Ha, o'qidim", callback_data=f"namoz_ha_{namoz_nomi}"),
            InlineKeyboardButton("❌ Yo'q", callback_data=f"namoz_yoq_{namoz_nomi}")
        ]
    ])
    for user_id, ism, username, limit_q, eslatma_yoqilgan in barcha_userlar():
        if eslatma_yoqilgan != 1:
            continue
        try:
            await application.bot.send_message(
                chat_id=user_id,
                text=f"🕌 *{namoz_nomi}* namozini o'qib bo'ldingizmi?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"{user_id} ga so'rov yuborib bo'lmadi: {e}")


async def uyqu_eslatma(application):
    await barcha_faol_userlarga_yubor(
        application,
        "😴 Uxlash vaqti keldi! Yaxshi tun, ertaga yangi kun.",
        parse_mode=None
    )


async def uyg_onish_eslatma(application):
    await barcha_faol_userlarga_yubor(
        application,
        "☀️ Bomdod vaqti yaqinlashdi! Uyg'oning!",
        parse_mode=None
    )


def hisobot_matni_tuz(sarlavha, rows):
    if not rows:
        return f"{sarlavha}\n\n📭 Hech qanday kirim/chiqim kiritilmadi."

    kirim = sum(r[1] for r in rows if r[0] == "kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
    qoldiq = kirim - chiqim

    matn = f"{sarlavha}\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
    return matn


async def tungi_hisobot(application):
    for user_id, ism, username, limit_q, eslatma_yoqilgan in barcha_userlar():
        rows = bugungi_hisobot(user_id)
        if not rows:
            continue

        kirim = sum(r[1] for r in rows if r[0] == "kirim")
        chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
        qoldiq = kirim - chiqim

        matn = "📊 *Kunlik hisobot* (00:00)\n"
        matn += "─────────────────\n"
        matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
        matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
        matn += "─────────────────\n"
        matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n\n"

        chiqimlar = [(r[3], r[1], r[4]) for r in rows if r[0] == "chiqim"]
        if chiqimlar:
            matn += "📝 *Chiqimlar:*\n"
            for tavsif, miqdor, vaqt in chiqimlar:
                matn += f"  {vaqt} — {tavsif}: {miqdor:,.0f} so'm\n"

        try:
            await application.bot.send_message(chat_id=user_id, text=matn, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"{user_id} ga kunlik hisobot yuborilmadi: {e}")


# ============================================================
#                      REJALASHTIRISH (Scheduler)
# ============================================================
def rejalashtirish(scheduler, application):
    scheduler.add_job(
        uyqu_eslatma, "cron", hour=22, minute=30,
        args=[application], id="uyqu", replace_existing=True
    )

    scheduler.add_job(
        tungi_hisobot, "cron", hour=0, minute=0,
        args=[application], id="hisobot", replace_existing=True
    )

    scheduler.add_job(
        namoz_rejalashtir, "cron", hour=3, minute=0,
        args=[scheduler, application], id="namoz_yangi", replace_existing=True
    )


def namoz_rejalashtir(scheduler, application):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar:
        logger.error("Namoz vaqtlarini olib bo'lmadi, rejalashtirish o'tkazib yuborildi.")
        return

    namozlar = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]

    for namoz in namozlar:
        if namoz not in vaqtlar:
            continue
        vaqt_str = vaqtlar[namoz]
        soat, daqiqa = map(int, vaqt_str.split(":"))

        # --- 15 daqiqa OLDIN eslatma ---
        oldin_soat, oldin_daqiqa = vaqt_qoshish(soat, daqiqa, -15)
        job_id = f"namoz_oldin_{namoz}"
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        scheduler.add_job(
            namoz_eslatma, "cron",
            hour=oldin_soat, minute=oldin_daqiqa,
            args=[application, namoz],
            id=job_id, replace_existing=True
        )

        # --- 20 daqiqa KEYIN "o'qidingizmi?" so'rovi ---
        keyin_soat, keyin_daqiqa = vaqt_qoshish(soat, daqiqa, 20)
        job_id2 = f"namoz_keyin_{namoz}"
        try:
            scheduler.remove_job(job_id2)
        except Exception:
            pass
        scheduler.add_job(
            namoz_oqildimi_sorov, "cron",
            hour=keyin_soat, minute=keyin_daqiqa,
            args=[application, namoz],
            id=job_id2, replace_existing=True
        )

        # Bomdod uchun alohida uyg'otish eslatmasi (15 daqiqa oldin)
        if namoz == "Bomdod":
            try:
                scheduler.remove_job("uyg_onish")
            except Exception:
                pass
            scheduler.add_job(
                uyg_onish_eslatma, "cron",
                hour=oldin_soat, minute=oldin_daqiqa,
                args=[application],
                id="uyg_onish", replace_existing=True
            )

    logger.info(f"Namoz vaqtlari rejalashtirildi: {vaqtlar}")


# ============================================================
#                       TUGMALI MENYU
# ============================================================
def asosiy_menyu(user_id=None):
    tugmalar = [
        ["➕ Kirim qo'shish", "➖ Chiqim qo'shish"],
        ["📊 Bugungi hisobot", "📅 Oylik hisobot"],
        ["🗓 Haftalik hisobot", "📂 Kategoriya bo'yicha"],
        ["🕌 Namoz vaqtlari", "💸 Kunlik limit"],
        ["📥 Excel hisobot", "🗑 Oxirgi yozuvni o'chirish"],
        ["🔔 Eslatmalar", "❓ Yordam"],
    ]
    if user_id == ADMIN_ID:
        tugmalar.append(["👑 Admin panel"])
    return ReplyKeyboardMarkup(tugmalar, resize_keyboard=True)


def bekor_qilish_menyu():
    return ReplyKeyboardMarkup([["🚫 Bekor qilish"]], resize_keyboard=True)


def kategoriya_menyu():
    qatorlar = [KATEGORIYALAR[i:i + 2] for i in range(0, len(KATEGORIYALAR), 2)]
    qatorlar.append(["🚫 Bekor qilish"])
    return ReplyKeyboardMarkup(qatorlar, resize_keyboard=True)


# ============================================================
#                          /start
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    royxatdan_otkazish(chat_id, user.first_name or "", user.username or "")

    matn = (
        "👋 *Xush kelibsiz!*\n\n"
        "✨ _Jahongir akadan foydalisi_ ✨\n\n"
        f"Sizning ID: `{chat_id}`\n\n"
        "📌 Quyidagi tugmalardan foydalanib, kirim-chiqimlaringizni boshqaring, "
        "namoz vaqtlari va eslatmalarni kuzatib boring.\n\n"
        "❓ Yordam tugmasini bosib, barcha imkoniyatlar bilan tanishing."
    )

    if os.path.exists(START_IMAGE_PATH):
        try:
            with open(START_IMAGE_PATH, "rb") as rasm:
                await update.message.reply_photo(
                    photo=rasm, caption=matn, parse_mode="Markdown",
                    reply_markup=asosiy_menyu(chat_id)
                )
            return
        except Exception as e:
            logger.warning(f"Rasm yuborishda xato: {e}")

    await update.message.reply_text(matn, parse_mode="Markdown", reply_markup=asosiy_menyu(chat_id))


# ============================================================
#                  KIRIM QO'SHISH (Conversation)
# ============================================================
async def kirim_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ Kirim miqdorini kiriting (faqat son, masalan: 500000):",
        reply_markup=bekor_qilish_menyu()
    )
    return KIRIM_MIQDOR


async def kirim_miqdor_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text.strip()
    if matn == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        miqdor = float(matn.replace(" ", "").replace(",", ""))
        if miqdor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Iltimos, to'g'ri son kiriting (masalan: 500000):")
        return KIRIM_MIQDOR

    context.user_data["kirim_miqdor"] = miqdor
    await update.message.reply_text("📝 Tavsif kiriting (masalan: maosh, sovrin):")
    return KIRIM_TAVSIF


async def kirim_tavsif_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tavsif = update.message.text.strip()
    if tavsif == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)

    miqdor = context.user_data.pop("kirim_miqdor")
    user_id = update.effective_user.id
    qosh_tranzaksiya(user_id, "kirim", miqdor, None, tavsif or "Kirim")

    await update.message.reply_text(
        f"✅ Kirim qo'shildi: *{miqdor:,.0f} so'm* — {tavsif}",
        parse_mode="Markdown", reply_markup=asosiy_menyu(user_id)
    )
    return ConversationHandler.END


# ============================================================
#                 CHIQIM QO'SHISH (Conversation)
# ============================================================
async def chiqim_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➖ Chiqim miqdorini kiriting (faqat son, masalan: 25000):",
        reply_markup=bekor_qilish_menyu()
    )
    return CHIQIM_MIQDOR


async def chiqim_miqdor_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text.strip()
    if matn == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        miqdor = float(matn.replace(" ", "").replace(",", ""))
        if miqdor <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Iltimos, to'g'ri son kiriting (masalan: 25000):")
        return CHIQIM_MIQDOR

    context.user_data["chiqim_miqdor"] = miqdor
    await update.message.reply_text(
        "📂 Kategoriyani tanlang:",
        reply_markup=kategoriya_menyu()
    )
    return CHIQIM_KATEGORIYA


async def chiqim_kategoriya_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text.strip()
    if matn == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    if matn not in KATEGORIYALAR:
        await update.message.reply_text("❗ Iltimos, ro'yxatdan kategoriya tanlang:", reply_markup=kategoriya_menyu())
        return CHIQIM_KATEGORIYA

    context.user_data["chiqim_kategoriya"] = matn
    await update.message.reply_text(
        "📝 Tavsif kiriting (masalan: tushlik, taksi):",
        reply_markup=bekor_qilish_menyu()
    )
    return CHIQIM_TAVSIF


async def chiqim_tavsif_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tavsif = update.message.text.strip()
    if tavsif == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)

    miqdor = context.user_data.pop("chiqim_miqdor")
    kategoriya = context.user_data.pop("chiqim_kategoriya")
    user_id = update.effective_user.id
    qosh_tranzaksiya(user_id, "chiqim", miqdor, kategoriya, tavsif or "Chiqim")

    await update.message.reply_text(
        f"❌ Chiqim qo'shildi: *{miqdor:,.0f} so'm*\n📂 {kategoriya}\n📝 {tavsif}",
        parse_mode="Markdown", reply_markup=asosiy_menyu(user_id)
    )

    # Kunlik limitni tekshirish
    limit_q = limit_olish(user_id)
    if limit_q and limit_q > 0:
        jami_chiqim = bugungi_chiqim_jami(user_id)
        if jami_chiqim >= limit_q and not limit_ogohlantirish_yuborilganmi(user_id, date.today()):
            limit_ogohlantirish_belgilash(user_id, date.today())
            await update.message.reply_text(
                f"⚠️ *Diqqat!* Bugungi xarajatingiz kunlik limitdan oshib ketdi!\n"
                f"💸 Limit: {limit_q:,.0f} so'm\n"
                f"❌ Bugungi chiqim: {jami_chiqim:,.0f} so'm",
                parse_mode="Markdown"
            )

    return ConversationHandler.END


async def bekor_qilish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id
    await update.message.reply_text("🚫 Bekor qilindi.", reply_markup=asosiy_menyu(user_id))
    return ConversationHandler.END


# ============================================================
#                KUNLIK LIMIT BELGILASH (Conversation)
# ============================================================
async def limit_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    joriy_limit = limit_olish(user_id)
    matn = "💸 Kunlik xarajat limitingizni kiriting (so'mda, masalan: 100000):\n"
    if joriy_limit and joriy_limit > 0:
        matn += f"\n📌 Joriy limit: {joriy_limit:,.0f} so'm"
    matn += "\n\n0 kiritsangiz, limit o'chiriladi."
    await update.message.reply_text(matn, reply_markup=bekor_qilish_menyu())
    return LIMIT_KIRITISH


async def limit_qabul(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text.strip()
    if matn == "🚫 Bekor qilish":
        return await bekor_qilish(update, context)
    try:
        limit_q = float(matn.replace(" ", "").replace(",", ""))
        if limit_q < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❗ Iltimos, to'g'ri son kiriting:")
        return LIMIT_KIRITISH

    user_id = update.effective_user.id
    limit_oynat(user_id, limit_q)

    if limit_q == 0:
        await update.message.reply_text("✅ Kunlik limit o'chirildi.", reply_markup=asosiy_menyu(user_id))
    else:
        await update.message.reply_text(
            f"✅ Kunlik limit o'rnatildi: *{limit_q:,.0f} so'm*",
            parse_mode="Markdown", reply_markup=asosiy_menyu(user_id)
        )
    return ConversationHandler.END


# ============================================================
#                        HISOBOTLAR
# ============================================================
async def bugun_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = bugungi_hisobot(user_id)
    txn_rows = [(r[0], r[1]) for r in rows]
    sarlavha = f"📊 *Bugun — {date.today().strftime('%d.%m.%Y')}*"
    matn = hisobot_matni_tuz(sarlavha, txn_rows)
    await update.message.reply_text(matn, parse_mode="Markdown")


async def oy_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = oylik_hisobot(user_id)
    if not rows:
        await update.message.reply_text("📭 Bu oy hech narsa kiritilmagan.")
        return

    kirim = next((r[1] for r in rows if r[0] == "kirim"), 0)
    chiqim = next((r[1] for r in rows if r[0] == "chiqim"), 0)
    qoldiq = kirim - chiqim
    oy_nomi = datetime.now().strftime("%B %Y")

    matn = f"📅 *{oy_nomi} oylik hisobot*\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"

    await update.message.reply_text(matn, parse_mode="Markdown")


async def hafta_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bir_hafta_oldin = date.today() - timedelta(days=7)
    rows = davr_hisobot(user_id, bir_hafta_oldin)
    txn_rows = [(r[0], r[1]) for r in rows]
    sarlavha = f"🗓 *Oxirgi 7 kun* ({bir_hafta_oldin.strftime('%d.%m')} — {date.today().strftime('%d.%m')})"
    matn = hisobot_matni_tuz(sarlavha, txn_rows)
    await update.message.reply_text(matn, parse_mode="Markdown")


async def kategoriya_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = kategoriya_boyicha_chiqim(user_id)
    if not rows:
        await update.message.reply_text("📭 Bu oy hech qanday chiqim kiritilmagan.")
        return

    oy_nomi = datetime.now().strftime("%B %Y")
    matn = f"📂 *{oy_nomi} — kategoriya bo'yicha chiqim*\n"
    matn += "─────────────────\n"
    jami = 0
    for kategoriya, miqdor in rows:
        nomi = kategoriya or "📦 Boshqa"
        matn += f"{nomi}: *{miqdor:,.0f} so'm*\n"
        jami += miqdor
    matn += "─────────────────\n"
    matn += f"Jami: *{jami:,.0f} so'm*"

    await update.message.reply_text(matn, parse_mode="Markdown")


async def excel_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    oy = datetime.now().strftime("%Y-%m")
    boshlanish = date.today().replace(day=1)
    rows = davr_hisobot(user_id, boshlanish)

    if not rows:
        await update.message.reply_text("📭 Bu oy uchun ma'lumot topilmadi.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hisobot"

    sarlavha_uslub = Font(bold=True, color="FFFFFF")
    sarlavha_fon = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid")

    sarlavhalar = ["Sana", "Vaqt", "Turi", "Kategoriya", "Tavsif", "Miqdor (so'm)"]
    ws.append(sarlavhalar)
    for hujayra in ws[1]:
        hujayra.font = sarlavha_uslub
        hujayra.fill = sarlavha_fon
        hujayra.alignment = Alignment(horizontal="center")

    jami_kirim = 0
    jami_chiqim = 0
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

    fayl_yoli = os.path.join(BASE_DIR, f"hisobot_{user_id}_{oy}.xlsx")
    wb.save(fayl_yoli)

    with open(fayl_yoli, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=f"hisobot_{oy}.xlsx",
            caption=f"📥 *{datetime.now().strftime('%B %Y')}* oyi uchun hisobot",
            parse_mode="Markdown"
        )

    try:
        os.remove(fayl_yoli)
    except Exception:
        pass


async def oxirgi_yozuvni_ochirish_komanda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    row = oxirgi_yozuvni_ochirish(user_id)
    if not row:
        await update.message.reply_text("📭 O'chirish uchun yozuv topilmadi.")
        return

    _id, tur, miqdor, tavsif = row
    tur_matni = "Kirim" if tur == "kirim" else "Chiqim"
    await update.message.reply_text(
        f"🗑 O'chirildi: {tur_matni} — *{miqdor:,.0f} so'm* ({tavsif})",
        parse_mode="Markdown"
    )


# ============================================================
#                      NAMOZ VAQTLARI
# ============================================================
async def namoz_vaqtlari_komanda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar:
        await update.message.reply_text("❗ Namoz vaqtlarini olishda xatolik. Internet aloqasini tekshiring.")
        return

    matn = f"🕌 *Buxoro — {date.today().strftime('%d.%m.%Y')}*\n\n"
    emoji = {"Bomdod": "🌙", "Quyosh": "🌅", "Peshin": "☀️", "Asr": "🌤", "Shom": "🌇", "Xufton": "🌃"}
    for nom, vaqt in vaqtlar.items():
        matn += f"{emoji.get(nom, '•')} *{nom}:* {vaqt}\n"

    await update.message.reply_text(matn, parse_mode="Markdown")


# ============================================================
#                  ESLATMALARNI YOQISH/O'CHIRISH
# ============================================================
async def eslatmalar_komanda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    holat = eslatma_holati(user_id)
    matn = "🔔 Eslatmalar holati: " + ("✅ Yoqilgan" if holat == 1 else "🔇 O'chirilgan")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔇 O'chirish" if holat == 1 else "🔔 Yoqish",
            callback_data="eslatma_almashtirish"
        )]
    ])
    await update.message.reply_text(matn, reply_markup=keyboard)


async def eslatma_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    yangi_holat = eslatma_holati_almashtirish(user_id)
    matn = "🔔 Eslatmalar yoqildi ✅" if yangi_holat == 1 else "🔇 Eslatmalar o'chirildi"
    await query.answer(matn)
    await query.edit_message_text(matn)


# ============================================================
#            "NAMOZNI O'QIDINGIZMI?" TUGMASI BOSILGANDA
# ============================================================
async def namoz_javob_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data  # namoz_ha_Bomdod yoki namoz_yoq_Bomdod

    if data.startswith("namoz_ha_"):
        namoz = data.replace("namoz_ha_", "")
        await query.answer("Alloh qabul qilsin! 🤲")
        await query.edit_message_text(f"✅ *{namoz}* namozi o'qildi. Alloh qabul qilsin! 🤲", parse_mode="Markdown")
    elif data.startswith("namoz_yoq_"):
        namoz = data.replace("namoz_yoq_", "")
        await query.answer("Unutmang, vaqtida o'qing!")
        await query.edit_message_text(
            f"⏳ *{namoz}* namozi hali o'qilmadi. Imkon qadar tezroq o'qishni unutmang!",
            parse_mode="Markdown"
        )


# ============================================================
#                        ADMIN PANEL
# ============================================================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Sizda admin huquqi yo'q.")
        return

    stat = admin_umumiy_statistika()
    matn = "👑 *Admin Panel*\n"
    matn += "─────────────────\n"
    matn += f"👥 Jami foydalanuvchilar: *{stat['jami_userlar']}*\n"
    matn += f"🟢 Bugun faol: *{stat['bugun_faol']}*\n"
    matn += f"✅ Oylik umumiy kirim: *{stat['oylik_kirim']:,.0f} so'm*\n"
    matn += f"❌ Oylik umumiy chiqim: *{stat['oylik_chiqim']:,.0f} so'm*\n"
    matn += "─────────────────\n\n"
    matn += "👥 *Foydalanuvchilar ro'yxati:*\n"

    for uid, ism, username, limit_q, eslatma_yoqilgan in barcha_userlar():
        uname = f"@{username}" if username else "—"
        limit_matn = f"{limit_q:,.0f} so'm" if limit_q else "yo'q"
        matn += f"\n🔹 `{uid}` — {ism} ({uname})\n   Limit: {limit_matn}\n"

    if len(matn) > 4000:
        for i in range(0, len(matn), 4000):
            await update.message.reply_text(matn[i:i + 4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(matn, parse_mode="Markdown")


# ============================================================
#                          /yordam
# ============================================================
async def yordam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = (
        "📋 *Barcha imkoniyatlar:*\n\n"
        "➕ *Kirim qo'shish* — daromad kiritish\n"
        "➖ *Chiqim qo'shish* — xarajat kiritish (kategoriya bilan)\n"
        "📊 *Bugungi hisobot* — bugungi kirim/chiqim\n"
        "📅 *Oylik hisobot* — shu oy jami\n"
        "🗓 *Haftalik hisobot* — oxirgi 7 kun\n"
        "📂 *Kategoriya bo'yicha* — chiqimlar taqsimoti\n"
        "🕌 *Namoz vaqtlari* — Buxoro shahri uchun\n"
        "💸 *Kunlik limit* — xarajat chegarasini belgilash\n"
        "📥 *Excel hisobot* — oylik hisobotni fayl qilib olish\n"
        "🗑 *Oxirgi yozuvni o'chirish* — xato kiritilganda\n"
        "🔔 *Eslatmalar* — yoqish/o'chirish\n\n"
        "⏰ *Avtomatik eslatmalar:*\n"
        "• Har namozdan 15 daqiqa oldin\n"
        "• Har namozdan 20 daqiqa keyin — \"o'qidingizmi?\" so'rovi\n"
        "• 22:30 — uyqu eslatmasi\n"
        "• Bomdoddan 15 daqiqa oldin — uyg'otish\n"
        "• 00:00 — kunlik hisobot\n"
        "• Kunlik limit oshganda — ogohlantirish\n"
    )
    await update.message.reply_text(matn, parse_mode="Markdown")


async def matn_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tugmalar orqali kelgan matnlarni mos funksiyalarga yo'naltirish"""
    matn = update.message.text.strip()
    mapping = {
        "📊 Bugungi hisobot": bugun_hisobot,
        "📅 Oylik hisobot": oy_hisobot,
        "🗓 Haftalik hisobot": hafta_hisobot,
        "📂 Kategoriya bo'yicha": kategoriya_hisobot,
        "🕌 Namoz vaqtlari": namoz_vaqtlari_komanda,
        "📥 Excel hisobot": excel_hisobot,
        "🗑 Oxirgi yozuvni o'chirish": oxirgi_yozuvni_ochirish_komanda,
        "🔔 Eslatmalar": eslatmalar_komanda,
        "❓ Yordam": yordam,
        "👑 Admin panel": admin_panel,
    }
    funksiya = mapping.get(matn)
    if funksiya:
        await funksiya(update, context)


# ============================================================
#                          ASOSIY
# ============================================================
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

    application.add_handler(CommandHandler("start", start))
    application.add_handler(kirim_conv)
    application.add_handler(chiqim_conv)
    application.add_handler(limit_conv)
    application.add_handler(CommandHandler("bugun", bugun_hisobot))
    application.add_handler(CommandHandler("oy", oy_hisobot))
    application.add_handler(CommandHandler("hafta", hafta_hisobot))
    application.add_handler(CommandHandler("kategoriya", kategoriya_hisobot))
    application.add_handler(CommandHandler("excel", excel_hisobot))
    application.add_handler(CommandHandler("namoz", namoz_vaqtlari_komanda))
    application.add_handler(CommandHandler("yordam", yordam))
    application.add_handler(CommandHandler("admin", admin_panel))

    application.add_handler(CallbackQueryHandler(eslatma_callback, pattern="^eslatma_almashtirish$"))
    application.add_handler(CallbackQueryHandler(namoz_javob_callback, pattern="^namoz_(ha|yoq)_"))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, matn_router))

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    rejalashtirish(scheduler, application)

    namoz_rejalashtir(scheduler, application)
    scheduler.start()

    logger.info("Bot ishga tushdi!")
    application.run_polling()


if __name__ == "__main__":
    main()
