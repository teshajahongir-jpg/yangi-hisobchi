import logging
import sqlite3
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests

# --- SOZLAMALAR ---
BOT_TOKEN = "8701217643:AAGF39LZ8CsZd9pKmI2D0PtuWpND-1n1or0"  # @BotFather dan oling
YOUR_CHAT_ID = 8252424738  # /start bosib o'z ID ingizni oling

# Buxoro namoz vaqtlari API
CITY_ID = "4563"  # Aladhan API Buxoro ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tur TEXT,        -- 'kirim' yoki 'chiqim'
            miqdor REAL,
            tavsif TEXT,
            sana TEXT,
            vaqt TEXT
        )
    """)
    conn.commit()
    conn.close()

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
            "method": 4  # Umm Al-Qura metodi
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

# --- BOTGA ESLATMALAR REJALASHTIRISH ---
async def namoz_eslatma(application, namoz_nomi):
    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=f"🕌 *{namoz_nomi}* namoziga 15 daqiqa qoldi!",
        parse_mode="Markdown"
    )

async def uyqu_eslatma(application):
    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text="😴 Uxlash vaqti keldi! Yaxshi tun, ertaga yangi kun."
    )

async def uyg_onish_eslatma(application):
    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text="☀️ Bomdod vaqti yaqinlashdi! Uyg'oning!"
    )

async def tungi_hisobot(application):
    rows = bugungi_hisobot(YOUR_CHAT_ID)
    if not rows:
        await application.bot.send_message(
            chat_id=YOUR_CHAT_ID,
            text="📊 Bugun hech qanday kirim/chiqim kiritilmadi."
        )
        return

    kirim = sum(r[1] for r in rows if r[0] == "kirim")
    chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
    qoldiq = kirim - chiqim

    matn = "📊 *Kunlik hisobot* (00:00)\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n\n"

    # Chiqim tafsiloti
    chiqimlar = [(r[2], r[1], r[3]) for r in rows if r[0] == "chiqim"]
    if chiqimlar:
        matn += "📝 *Chiqimlar:*\n"
        for tavsif, miqdor, vaqt in chiqimlar:
            matn += f"  {vaqt} — {tavsif}: {miqdor:,.0f} so'm\n"

    await application.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=matn,
        parse_mode="Markdown"
    )

def rejalashtirish(scheduler, application):
    # Uyqu eslatmasi — 22:30
    scheduler.add_job(
        uyqu_eslatma, "cron", hour=22, minute=30,
        args=[application], id="uyqu"
    )

    # Kunlik hisobot — 00:00
    scheduler.add_job(
        tungi_hisobot, "cron", hour=0, minute=0,
        args=[application], id="hisobot"
    )

    # Namoz vaqtlarini har kuni yangilab rejalashtirish
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

        # 15 daqiqa oldin
        daqiqa -= 15
        if daqiqa < 0:
            daqiqa += 60
            soat -= 1

        job_id = f"namoz_{namoz}"
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

        scheduler.add_job(
            namoz_eslatma, "cron",
            hour=soat, minute=daqiqa,
            args=[application, namoz],
            id=job_id
        )

        # Bomdod uchun uyg'otish
        if namoz == "Bomdod":
            uyg_soat, uyg_daqiqa = soat, daqiqa
            try:
                scheduler.remove_job("uyg_onish")
            except Exception:
                pass
            scheduler.add_job(
                uyg_onish_eslatma, "cron",
                hour=uyg_soat, minute=uyg_daqiqa,
                args=[application],
                id="uyg_onish"
            )

# --- KOMANDALAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    matn = (
        f"👋 Salom! Sizning ID: `{chat_id}`\n\n"
        "📌 *Komandalar:*\n"
        "➕ `/kirim 50000 maosh` — kirim qo'shish\n"
        "➖ `/chiqim 15000 tushlik` — chiqim qo'shish\n"
        "📊 `/bugun` — bugungi hisobot\n"
        "📅 `/oy` — oylik hisobot\n"
        "🕌 `/namoz` — bugungi namoz vaqtlari\n"
        "❓ `/yordam` — barcha komandalar"
    )
    await update.message.reply_text(matn, parse_mode="Markdown")

async def kirim_qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        miqdor = float(context.args[0])
        tavsif = " ".join(context.args[1:]) or "Kirim"
        qosh_tranzaksiya(update.effective_user.id, "kirim", miqdor, tavsif)
        await update.message.reply_text(
            f"✅ Kirim qo'shildi: *{miqdor:,.0f} so'm* — {tavsif}",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text("❗ To'g'ri yozing: `/kirim 50000 maosh`", parse_mode="Markdown")

async def chiqim_qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        miqdor = float(context.args[0])
        tavsif = " ".join(context.args[1:]) or "Chiqim"
        qosh_tranzaksiya(update.effective_user.id, "chiqim", miqdor, tavsif)
        await update.message.reply_text(
            f"❌ Chiqim qo'shildi: *{miqdor:,.0f} so'm* — {tavsif}",
            parse_mode="Markdown"
        )
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

    matn = f"📊 *Bugun — {date.today().strftime('%d.%m.%Y')}*\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"

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

    matn = f"📅 *{oy_nomi} oylik hisobot*\n"
    matn += "─────────────────\n"
    matn += f"✅ Kirim:  *{kirim:,.0f} so'm*\n"
    matn += f"❌ Chiqim: *{chiqim:,.0f} so'm*\n"
    matn += "─────────────────\n"
    matn += f"💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"

    await update.message.reply_text(matn, parse_mode="Markdown")

async def namoz_vaqtlari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar:
        await update.message.reply_text("❗ Namoz vaqtlarini olishda xatolik. Internet aloqasini tekshiring.")
        return

    matn = f"🕌 *Buxoro — {date.today().strftime('%d.%m.%Y')}*\n\n"
    emoji = {"Bomdod": "🌙", "Quyosh": "🌅", "Peshin": "☀️", "Asr": "🌤", "Shom": "🌇", "Xufton": "🌃"}
    for nom, vaqt in vaqtlar.items():
        matn += f"{emoji.get(nom, '•')} *{nom}:* {vaqt}\n"

    await update.message.reply_text(matn, parse_mode="Markdown")

async def yordam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = (
        "📋 *Barcha komandalar:*\n\n"
        "➕ `/kirim [miqdor] [tavsif]` — kirim kiritish\n"
        "➖ `/chiqim [miqdor] [tavsif]` — chiqim kiritish\n"
        "📊 `/bugun` — bugungi kirim/chiqim\n"
        "📅 `/oy` — oylik jami\n"
        "🕌 `/namoz` — Buxoro namoz vaqtlari\n\n"
        "⏰ *Avtomatik eslatmalar:*\n"
        "• Har namozdan 15 daqiqa oldin\n"
        "• 22:30 — uyqu eslatmasi\n"
        "• Bomdoddan 15 daqiqa oldin — uyg'otish\n"
        "• 00:00 — kunlik hisobot\n"
    )
    await update.message.reply_text(matn, parse_mode="Markdown")

# --- ASOSIY ---
def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("kirim", kirim_qosh))
    application.add_handler(CommandHandler("chiqim", chiqim_qosh))
    application.add_handler(CommandHandler("bugun", bugun_hisobot))
    application.add_handler(CommandHandler("oy", oy_hisobot))
    application.add_handler(CommandHandler("namoz", namoz_vaqtlari))
    application.add_handler(CommandHandler("yordam", yordam))

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    rejalashtirish(scheduler, application)

    # Bugungi namoz vaqtlarini darhol rejalashtirish
    namoz_rejalashtir(scheduler, application)
    scheduler.start()

    logger.info("Bot ishga tushdi!")
    application.run_polling()

if __name__ == "__main__":
    main()
