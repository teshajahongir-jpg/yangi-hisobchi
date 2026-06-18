import logging
import sqlite3
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests

# --- SOZLAMALAR ---
BOT_TOKEN = "8680299057:AAFgeWD5wewc4dZXCx9BSrb_LvY67fq0id8"  # @BotFather dan oling
ADMIN_ID = 8252424738  # Sizning ID raqamingiz
PHOTO_URL = "AgACAgIAAxkBAAEq2vlqM5l_Q5AU-nUqltwmM0zeQQbhsAACzBxG44wmUkK2OF-jPZzmAEAAwIAA3gAAzwE" # Siz tanlagan eng sifatli rasm kodi

# ConversationHandler uchun holatlar
MIQDOR, TAVSIF = range(2)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("xarajat.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
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
        params = {"latitude": 39.7747, "longitude": 64.4286, "method": 4}
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

# --- AVTOMATIK ESLATMALAR ---
async def barchaga_yubor(application, text, reply_markup=None):
    users = barcha_userlarni_ol()
    for user_id in users:
        try:
            await application.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception:
            pass

async def namoz_oldidan_eslatma(application, namoz_nomi):
    await barchaga_yubor(application, f" 🕌 *{namoz_nomi}* namoziga 15 daqiqa qoldi. Tahoratingizni yangilab oling!")

async def namoz_keyin_sorov(application, namoz_nomi):
    # Surovnoma tugmasi (Inline)
    keyboard = [[InlineKeyboardButton("✅ Ha, o'qidim", callback_data="namoz_ha")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await barchaga_yubor(application, f"✨ *{namoz_nomi}* vaqti kirdi. Namozlarni o'qib oldingizmi?", reply_markup=reply_markup)

def rejalashtirish(scheduler, application):
    scheduler.add_job(namoz_rejalashtir, "cron", hour=3, minute=0, args=[scheduler, application], id="namoz_yangi")

def namoz_rejalashtir(scheduler, application):
    vaqtlar = namoz_vaqtlarini_ol()
    if not vaqtlar: return

    namozlar = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]
    for namoz in namozlar:
        if namoz not in vaqtlar: continue
        vaqt_str = vaqtlar[namoz]
        soat, daqiqa = map(int, vaqt_str.split(":"))

        # 15 daqiqa oldin eslatish
        oldin_daq = daqiqa - 15
        oldin_soat = soat
        if oldin_daq < 0:
            oldin_daq += 60
            oldin_soat -= 1

        try: scheduler.remove_job(f"namoz_oldin_{namoz}")
        except: pass
        scheduler.add_job(namoz_oldidan_eslatma, "cron", hour=oldin_soat, minute=oldin_daq, args=[application, namoz], id=f"namoz_oldin_{namoz}")

        # Namoz kirgandan 1 minut keyin so'rovnoma yuborish
        keyin_daq = daqiqa + 1
        keyin_soat = soat
        if keyin_daq >= 60:
            keyin_daq -= 60
            keyin_soat += 1

        try: scheduler.remove_job(f"namoz_keyin_{namoz}")
        except: pass
        scheduler.add_job(namoz_keyin_sorov, "cron", hour=keyin_soat, minute=keyin_daq, args=[application, namoz], id=f"namoz_keyin_{namoz}")

# --- MENYU TUGMALARI ---
def asosiy_menyu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Kirim qo'shish"), KeyboardButton("❌ Chiqim qo'shish")],
        [KeyboardButton("📊 Bugungi hisobot"), KeyboardButton("📅 Oylik hisobot")],
        [KeyboardButton("🕌 Namoz vaqtlari"), KeyboardButton("🎯 Kunlik limit qo'shish")],
        [KeyboardButton("ℹ️ Yordam (Qo'llanma)")]
    ], resize_keyboard=True)

# --- PANEL VA INTERFEYS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    qosh_user(user_id)
    matn = "Jahongir akadan foydalisi!\n\nAssalomu alaykum. Botga xush kelibsiz!"
    try:
        await update.message.reply_photo(photo=PHOTO_URL, caption=matn, reply_markup=asosiy_menyu())
    except Exception:
        await update.message.reply_text(matn, reply_markup=asosiy_menyu())

# --- INTERFAOL KORXONA (CONVERSATION HANDLER) ---
async def kirim_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tur'] = 'kirim'
    await update.message.reply_text("💰 **Kirim miqdorini kiriting (faqat raqamda):**\nMasalan: `50000`", parse_mode="Markdown")
    return MIQDOR

async def chiqim_boshlash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['tur'] = 'chiqim'
    await update.message.reply_text("💸 **Chiqim miqdorini kiriting (faqat raqamda):**\nMasalan: `15000`", parse_mode="Markdown")
    return MIQDOR

async def miqdor_qabul_qilish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        miqdor = float(update.message.text.replace(" ", ""))
        context.user_data['miqdor'] = miqdor
        await update.message.reply_text("📝 **Tavsif yoki sababini kiriting:**\nMasalan: `Oylik maosh` yoki `Tushlik uchun`", parse_mode="Markdown")
        return TAVSIF
    except ValueError:
        await update.message.reply_text("❗ Iltimos, faqat raqam kiriting. Qaytadan urinib ko'ring:")
        return MIQDOR

async def tavsif_qabul_qilish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tavsif = update.message.text
    user_id = update.effective_user.id
    tur = context.user_data['tur']
    miqdor = context.user_data['miqdor']

    qosh_tranzaksiya(user_id, tur, miqdor, tavsif)
    
    belgi = "✅ Kirim" if tur == 'kirim' else "❌ Chiqim"
    await update.message.reply_text(
        f"{belgi} muvaffaqiyatli qo'shildi!\n💰 *Miqdor:* {miqdor:,.0f} so'm\n📝 *Tavsif:* {tavsif}",
        parse_mode="Markdown", reply_markup=asosiy_menyu()
    )
    return ConversationHandler.END

async def bekor_qilish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Jarayon bekor qilindi.", reply_markup=asosiy_menyu())
    return ConversationHandler.END

# --- SO'ROVNOMA TUGMASI JAVOBI ---
async def namoz_tugma_bosildi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "namoz_ha":
        # Eski matnni saqlab, xabarni o'zgartiramiz
        await query.edit_message_text(text=f"{query.message.text}\n\n💚 *Alloh qabul qilsin!*", parse_mode="Markdown")

# --- ODDIY MATN TUGMALARI BOSHQRUVI ---
async def boshqa_tugmalar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📊 Bugungi hisobot":
        rows = bugungi_hisobot(update.effective_user.id)
        if not rows:
            await update.message.reply_text("📭 Bugun hech narsa kiritilmagan.")
            return
        kirim = sum(r[1] for r in rows if r[0] == "kirim")
        chiqim = sum(r[1] for r in rows if r[0] == "chiqim")
        qoldiq = kirim - chiqim
        matn = f"📊 *Bugun — {date.today().strftime('%d.%m.%Y')}*\n─────────────────\n✅ Kirim:  *{kirim:,.0f} so'm*\n❌ Chiqim: *{chiqim:,.0f} so'm*\n─────────────────\n💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
        await update.message.reply_text(matn, parse_mode="Markdown")
        
    elif text == "📅 Oylik hisobot":
        rows = oylik_hisobot(update.effective_user.id)
        if not rows:
            await update.message.reply_text("📭 Bu oy hech narsa kiritilmagan.")
            return
        kirim = next((r[1] for r in rows if r[0] == "kirim"), 0)
        chiqim = next((r[1] for r in rows if r[0] == "chiqim"), 0)
        qoldiq = kirim - chiqim
        matn = f"📅 *{datetime.now().strftime('%B %Y')} oylik hisobot*\n─────────────────\n✅ Kirim:  *{kirim:,.0f} so'm*\n❌ Chiqim: *{chiqim:,.0f} so'm*\n─────────────────\n💰 Qoldiq: *{qoldiq:,.0f} so'm*\n"
        await update.message.reply_text(matn, parse_mode="Markdown")
        
    elif text == "🇺🇿 Namoz vaqtlari":
        # Yuqoridagi funksiyani chaqirish (matn mosligi uchun tekshiruv)
        pass
    elif text == "🕌 Namoz vaqtlari":
        vaqtlar = namoz_vaqtlarini_ol()
        if not vaqtlar:
            await update.message.reply_text("❗ Xatolik yuz berdi.")
            return
        matn = f"🕌 *Buxoro — {date.today().strftime('%d.%m.%Y')}*\n\n"
        emoji = {"Bomdod": "🌙", "Peshin": "☀️", "Asr": "🌤", "Shom": "🌇", "Xufton": "🌃"}
        for nom, vaqt in vaqtlar.items():
            matn += f"{emoji.get(nom, '•')} *{nom}:* {vaqt}\n"
        await update.message.reply_text(matn, parse_mode="Markdown")
        
    elif text == "🎯 Kunlik limit qo'shish":
        await update.message.reply_text("🎯 *Kunlik limit va odatlar*\n\nTez orada bu funksiya to'liq ishga tushadi!", parse_mode="Markdown")
    elif text == "ℹ️ Yordam (Qo'llanma)":
        await update.message.reply_text("💡 **Yordam:**\n\nKirim va chiqimlarni kiritish uchun yuqoridagi mos tugmalarni bosing va miqdor hamda tavsifni yozing.")

# --- MAIN ---
def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    # Kirim/Chiqim dialog boshqaruvi (Conversation)
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text("➕ Kirim qo'shish"), kirim_boshlash),
            MessageHandler(filters.Text("❌ Chiqim qo'shish"), chiqim_boshlash)
        ],
        states={
            MIQDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, miqdor_qabul_qilish)],
            TAVSIF: [MessageHandler(filters.TEXT & ~filters.COMMAND, tavsif_qabul_qilish)]
        },
        fallbacks=[CommandHandler("cancel", bekor_qilish)]
    )
    application.add_handler(conv_handler)
    
    # Boshqa handlerlar
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(namoz_tugma_bosildi))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, boshqa_tugmalar))

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    rejalashtirish(scheduler, application)
    namoz_rejalashtir(scheduler, application)
    scheduler.start()

    logger.info("Bot qayta ishga tushdi!")
    application.run_polling()

if __name__ == "__main__":
    main()
