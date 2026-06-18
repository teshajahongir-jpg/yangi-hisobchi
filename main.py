import logging
import sqlite3
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests

# --- SOZLAMALAR ---
BOT_TOKEN = "8680299057:AAFgeWD5wewc4dZXCx9BSrb_LvY67fq0id8"  # @BotFather dan oling
ADMIN_ID = 8252424738  # Sizning ID raqamingiz
PHOTO_URL = "https://t.me/AgACAgIAAxkBAAEq2vlqM5l_Q5AU-nUqltwmM0zeQQbhsAACzBxG44wmUkK2OF-jPZzmAEAAwIAA3gAAzwE" # SHU YERGA O'Z RASMINGIZ URL MANZILINI QO'YING

CITY_ID = "4563"  # Aladhan API Buxoro ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    # Foydalanuvchilarni saqlash jadvali
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    # Xarajatlar jadvali
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tur TEXT,
            miqdor REAL,
            tavsif TEXT,
            sana TEXT,
            vaqt TEXT
        )
    """)
    conn.commit()
    conn.close()

def qosh_user(user_id):
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def barcha_userlarni_ol():
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def qosh_tranzaksiya(user_id, tur, miqdor, tavsif):
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO transactions (user_id, tur, miqdor, tavsif, sana, vaqt) VALUES (?,?,?,?,?,?)",
        (user_id, tur, miqdor, tavsif, str(date.today()), datetime.now().strftime("%H:%M"))
    )
    conn.commit()
    conn.close()

def bugungi_hisobot(user_id):
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    bugun = str(date.today())
    c.execute("SELECT tur, miqdor, tavsif, vaqt FROM transactions WHERE user_id=? AND sana=? ORDER BY id", (user_id, bugun))
    rows = c.fetchall()
    conn.close()
    return rows

def oylik_hisobot(user_id):
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    oy = datetime.now().strftime("%Y-%m")
    c.execute("SELECT tur, SUM(miqdor) FROM transactions WHERE user_id=? AND sana LIKE ? GROUP BY tur", (user_id, f"{oy}%"))
    rows = c.fetchall()
    conn.close()
    return rows

# --- NAMOZ VAQTLARI ---
def namoz_vaqtlarini_ol():
    try:
        bugun = datetime.now()
        url = f"https://api.aladhan.com/v1/timings/{bugun.day}-{bugun.month}-{bugun.year}"
        params = {
            "latitude": 39.7747,
            "longitude": 64.4286,
            "method": 4  # Umm Al-Qura
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        timings = data["data"]["timings"]
        return {
            "Bomdod": timings["Fajr"],
            "Peshin": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Shom": timings["Maghrib"],
            "Xufton": timings["Isha"]
        }
    except Exception as e:
        logger.error(f"Namoz vaqtlari xatosi: {e}")
        return None

# --- BOTGA ESLATMALAR REJALASHTIRISH ---
async def barchaga_yubor(application, text):
    users = barcha_userlarni_ol()
    for user_id in users:
        try:
            await application.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except Exception:
            pass # Bloklagan userlarga bormaydi

async def namoz_oldidan_eslatma(application, namoz_nomi):
    await barchaga_yubor(application, f"🕌 *{namoz_nomi}* namoziga 15 daqiqa qoldi. Tahoratingizni yangilab oling!")

async def namoz_keyin_sorov(application, namoz_nomi):
    await barchaga_yubor(application, f"✨ *{namoz_nomi}* namozini o'qib oldingizmi? Alloh qabul qilsin!")

def rejalashtirish(scheduler, application):
    # Namoz vaqtlarini har kuni tungi 3:00 da yangilab rejalashtirish
    scheduler.add_job(
        namoz_rejalashtir, "cron", hour=3, minute=0,
        args=[scheduler, application], id="namoz_yangi"
    )

def namoz_rejalashtir(scheduler, application):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar:
        return

    namozlar = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]

    for namoz in namozlar:
        if namoz not in vaqtlar:
            continue
        vaqt_str = vaqtlar[namoz]
        soat, daqiqa = map(int, vaqt_str.split(":"))

        # 1. Namozdan 15 daqiqa oldin ogohlantirish
        oldin_daq = daqiqa - 15
        oldin_soat = soat
        if oldin_daq < 0:
            oldin_daq += 60
            oldin_soat -= 1

        try:
            scheduler.remove_job(f"namoz_oldin_{namoz}")
        except: pass

        scheduler.add_job(
            namoz_oldidan_eslatma, "cron",
            hour=oldin_soat, minute=oldin_daq,
            args=[application, namoz], id=f"namoz_oldin_{namoz}"
        )

        # 2. Namoz kirgandan 20 daqiqa keyin "o'qib oldingizmi?" deb so'rash
        keyin_daq = daqiqa + 20
        keyin_soat = soat
        if keyin_daq >= 60:
            keyin_daq -= 60
            keyin_soat += 1
            if keyin_soat >= 24:
                keyin_soat -= 24

        try:
            scheduler.remove_job(f"namoz_keyin_{namoz}")
        except: pass

        scheduler.add_job(
            namoz_keyin_sorov, "cron",
            hour=keyin_soat, minute=keyin_daq,
            args=[application, namoz], id=f"namoz_keyin_{namoz}"
        )

# --- MENYU TUGMALARI ---
def asosiy_menyu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Bugungi hisobot"), KeyboardButton("📅 Oylik hisobot")],
        [KeyboardButton("🕌 Namoz vaqtlari"), KeyboardButton("🎯 Kunlik limit qo'shish")],
        [KeyboardButton("ℹ️ Yordam (Qo'llanma)")]
    ], resize_keyboard=True)

# --- KOMANDALAR VA TUGMALAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    qosh_user(user_id) # Bazaga saqlaymiz (hamma foydalanuvchilar eslatma olishi uchun)
    
    matn = (
        "Jahongir akadan foydalisi!\n\n"
        "Assalomu alaykum. Botga xush kelibsiz! \n"
        "Men orqali daromad va xarajatlaringizni kuzatishingiz, hamda "
        "namoz vaqtlari va foydali odatlarni nazorat qilishingiz mumkin."
    )
    
    # Rasmli start xabari
    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=matn, reply_markup=asosiy_menyu())
    except Exception as e:
        # Agar rasm ssilkasi ishlamasa, oddiy matn yuboradi
        await update.message.reply_text(matn, reply_markup=asosiy_menyu())

# MATNLI TUGMALARNI USHLAB OLISH
async def tugmalar_boshqaruvi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "📊 Bugungi hisobot":
        await bugun_hisobot(update, context)
    elif text == "📅 Oylik hisobot":
        await oy_hisobot(update, context)
    elif text == "🕌 Namoz vaqtlari":
        await namoz_vaqtlari(update, context)
    elif text == "🎯 Kunlik limit qo'shish":
        await kunlik_limit(update, context)
    elif text == "ℹ️ Yordam (Qo'llanma)":
        await yordam(update, context)

# XARAJAT/DAROMAD KOMANDALARI
async def kirim_qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        miqdor = float(context.args[0])
        tavsif = " ".join(context.args[1:]) or "Kirim"
        qosh_tranzaksiya(update.effective_user.id, "kirim", miqdor, tavsif)
        await update.message.reply_text(f"✅ Kirim qo'shildi: *{miqdor:,.0f} so'm* — {tavsif}", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("❗ To'g'ri yozing: `/kirim 50000 maosh`", parse_mode="Markdown")

async def chiqim_qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        miqdor = float(context.args[0])
        tavsif = " ".join(context.args[1:]) or "Chiqim"
        qosh_tranzaksiya(update.effective_user.id, "chiqim", miqdor, tavsif)
        await update.message.reply_text(f"❌ Chiqim qo'shildi: *{miqdor:,.0f} so'm* — {tavsif}", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("❗ To'g'ri yozing: `/chiqim 15000 tushlik`", parse_mode="Markdown")

async def bugun_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = bugungi_hisobot(update.effective_user.id)
    if not rows:
        await update.message.reply_text("📭 Bugun hech narsa kiritilmagan.")
        return

    kirim = sum(r[1] for r in rows if r[0] == "kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
    qoldiq = kirim - chiqim

    matn = f"📊 *Bugun — {date.today().strftime('%d.%m.%Y')}*\n─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n❌ Chiqim: *{chiqim:,.0f} so'm*\n─────────────────\n💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
    await update.message.reply_text(matn, parse_mode="Markdown")

async def oy_hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = oylik_hisobot(update.effective_user.id)
    if not rows:
        await update.message.reply_text("📭 Bu oy hech narsa kiritilmagan.")
        return

    kirim = next((r[1] for r in rows if r[0] == "kirim"), 0)
    chiqim = next((r[1] for r in rows if r[0] == "chiqim"), 0)
    qoldiq = kirim - chiqim
    oy_nomi = datetime.now().strftime("%B %Y")

    matn = f"📅 *{oy_nomi} oylik hisobot*\n─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n❌ Chiqim: *{chiqim:,.0f} so'm*\n─────────────────\n💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
    await update.message.reply_text(matn, parse_mode="Markdown")

async def namoz_vaqtlari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar:
        await update.message.reply_text("❗ Namoz vaqtlarini olishda xatolik yuz berdi.")
        return

    matn = f"🕌 *Buxoro namoz vaqtlari — {date.today().strftime('%d.%m.%Y')}*\n\n"
    emoji = {"Bomdod": "🌙", "Peshin": "☀️", "Asr": "🌤", "Shom": "🌇", "Xufton": "🌃"}
    for nom, vaqt in vaqtlar.items():
        matn += f"{emoji.get(nom, '•')} *{nom}:* {vaqt}\n"
    await update.message.reply_text(matn, parse_mode="Markdown")

async def kunlik_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = (
        "🎯 *Kunlik limit va odatlar*\n\n"
        "Tez orada bu yerda o'z kunlik maqsadlaringizni (masalan: kuniga 10 bet kitob o'qish, "
        "sport bilan shug'ullanish) qo'shish va belgilash imkoniyati ishga tushadi!"
    )
    await update.message.reply_text(matn, parse_mode="Markdown")

async def yordam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = (
        "📋 *Barcha komandalar va yordam:*\n\n"
        "Siz menyudagi tugmalar orqali asosiy amallarni bajarishingiz mumkin.\n\n"
        "Kirim/Chiqimni yozish uchun komandalardan foydalaning:\n"
        "➕ `/kirim 50000 maosh`\n"
        "➖ `/chiqim 15000 tushlik`\n\n"
        "⏰ *Namoz eslatmalari avtomatik ishlaydi:*\n"
        "• Har namozdan 15 daqiqa oldin ogohlantirish keladi.\n"
        "• Namoz vaqti kirgandan 20 daqiqa o'tib, 'o'qib oldingizmi?' deb so'raladi."
    )
    await update.message.reply_text(matn, parse_mode="Markdown")

# ADMIN UCHUN BARCHAGA XABAR YUBORISH KOMANDASI
async def sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    xabar = " ".join(context.args)
    if not xabar:
        await update.message.reply_text("Xabar matnini kiriting: `/sendall Assalomu alaykum!`")
        return
    await barchaga_yubor(context.application, f"🗣 *Admindan xabar:*\n\n{xabar}")
    await update.message.reply_text("✅ Xabar barchaga yuborildi.")

# --- ASOSIY ---
def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # Komandalar
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("kirim", kirim_qosh))
    application.add_handler(CommandHandler("chiqim", chiqim_qosh))
    application.add_handler(CommandHandler("sendall", sendall))
    
    # Tugmalar uchun handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tugmalar_boshqaruvi))

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    rejalashtirish(scheduler, application)

    # Bugungi namoz vaqtlarini darhol rejalashtirish
    namoz_rejalashtir(scheduler, application)
    scheduler.start()

    logger.info("Bot ishga tushdi!")
    application.run_polling()

if __name__ == "__main__":
    main()
