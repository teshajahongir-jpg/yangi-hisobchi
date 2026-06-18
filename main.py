import logging
import sqlite3
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, date
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests

# --- SOZLAMALAR ---
BOT_TOKEN = "8680299057:AAFZwPMCzPYsjIlL_zPXKgKuvKkYP4zLEO0"
ADMIN_ID = 8252424738
PHOTO_URL = "https://images.unsplash.com/photo-1542831371-29b0f74f9713?q=80&w=640&auto=format&fit=crop"

MIQDOR, TAVSIF = range(2)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- RENDER UCHUN LIVE SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is active and synced with Islom.uz!")
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

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

# --- NAMOZ VAQTLARI (100% ISLOM.UZ YILLI AVTOMAT TIZIM) ---
def namoz_vaqtlarini_ol():
    import json
    import os
    
    bugun_sana = datetime.now().strftime("%Y-%m-%d")
    kesh_fayli = "islom_uz_yilli_baza.json"

    # 1-TIZIM: Rasmiy Islom.uz API (Yil bo'yi 365 kun avtomat ishlaydi)
    try:
        url = "https://islomapi.uz/api/present/day"
        params = {"region": "Buxoro"}
        resp = requests.get(url, params=params, timeout=7)
        
        if resp.status_code == 200:
            timings = resp.json()["times"]
            vaqtlar = {
                "Bomdod": timings["tong_saharlik"],
                "Peshin": timings["peshin"],
                "Asr": timings["asr"],
                "Shom": timings["shom_iftor"],
                "Xufton": timings["hufton"]
            }
            
            # Kelajakda API o'chib qolgan vaziyatlar uchun bazani yangilab qo'yamiz
            kesh_ma'lumoti = {}
            if os.path.exists(kesh_fayli):
                with open(kesh_fayli, "r", encoding="utf-8") as f:
                    try: kesh_ma'lumoti = json.load(f)
                    except: pass
            
            kesh_ma'lumoti[bugun_sana] = vaqtlar
            with open(kesh_fayli, "w", encoding="utf-8") as f:
                json.dump(kesh_ma'lumoti, f, ensure_ascii=False, indent=4)
                
            return vaqtlar
    except Exception as e:
        logger.warning(f"Islom.uz API vaqtincha ishlamadi, zaxira bazadan olinmoqda: {e}")

    # 2-TIZIM: ZAXIRA (Agar Islom.uz o'chib qolsa, o'zining yilli kesh bazasidan oladi)
    if os.path.exists(kesh_fayli):
        with open(kesh_fayli, "r", encoding="utf-8") as f:
            try:
                kesh_ma'lumoti = json.load(f)
                if bugun_sana in kesh_ma'lumoti:
                    return kesh_ma'lumoti[bugun_sana]
            except:
                pass

    # 3-TIZIM: FAVQULODDA HOLAT (Agar keshda ham bo'lmasa, Islom.uz oylik jadvalidan to'g'ridan-to'g'ri tortadi)
    try:
        joriy_oy = datetime.now().month
        url = f"https://islomapi.uz/api/monthly?region=Buxoro&month={joriy_oy}"
        resp = requests.get(url, timeout=7)
        if resp.status_code == 200:
            oylik_royxat = resp.json()
            bugun_kun = datetime.now().day
            # Bugungi kunga mos keladigan qatorni topamiz
            for kunlik in oylik_royxat:
                if kunlik.get("date") and int(kunlik["date"].split(".")[0]) == bugun_kun:
                    t = kunlik["times"]
                    return {
                        "Bomdod": t["tong_saharlik"],
                        "Peshin": t["peshin"],
                        "Asr": t["asr"],
                        "Shom": t["shom_iftor"],
                        "Xufton": t["hufton"]
                    }
    except Exception as e:
        logger.error(f"Hech qaysi namoz tizimi ishlamadi: {e}")
        
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
    await barchaga_yubor(application, f"🕌 *{namoz_nomi}* namoziga 15 daqiqa qoldi. Tahoratingizni yangilab oling!")

async def namoz_keyin_sorov(application, namoz_nomi):
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

        # 15 daqiqa oldin eslatma
        oldin_daq = daqiqa - 15
        oldin_soat = soat
        if oldin_daq < 0:
            oldin_daq += 60
            oldin_soat -= 1

        try: scheduler.remove_job(f"namoz_oldin_{namoz}")
        except: pass
        scheduler.add_job(namoz_oldidan_eslatma, "cron", hour=oldin_soat, minute=oldin_daq, args=[application, namoz], id=f"namoz_oldin_{namoz}")

        # 1 daqiqa keyin so'rovnoma
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

# --- CONVERSATION HANDLER ---
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

async def namoz_tugma_bosildi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "namoz_ha":
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
        
    elif text == "🕌 Namoz vaqtlari":
        vaqtlar = namoz_vaqtlarini_ol()
        if not vaqtlar:
            await update.message.reply_text("❗ Islom.uz tizimidan ma'lumot olishda xato yuz berdi. Birozdan so'ng urining.")
            return
        matn = f"🕌 *Buxoro (Islom.uz) — {date.today().strftime('%d.%m.%Y')}*\n\n"
        emoji = {"Bomdod": "🌙", "Peshin": "☀️", "Asr": "🌤", "Shom": "🌇", "Xufton": "🌃"}
        for nom, vaqt in vaqtlar.items():
            matn += f"{emoji.get(nom, '•')} *{nom}:* {vaqt}\n"
        await update.message.reply_text(matn, parse_mode="Markdown")
        
    elif text == "🎯 Kunlik limit qo'shish":
        await update.message.reply_text("🎯 *Kunlik limit va odatlar*\n\nTez orada bu funksiya to'liq ishga tushadi!", parse_mode="Markdown")
    elif text == "ℹ️ Yordam (Qo'llanma)":
        await update.message.reply_text("💡 **Yordam:**\n\nKirim va chiqimlarni kiritish uchun yuqoridagi mos tugmalarni bosing.")

# --- MAIN ---
def main():
    init_db()

    # Render uchun fon serveri
    threading.Thread(target=run_health_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

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
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(namoz_tugma_bosildi))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, boshqa_tugmalar))

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    rejalashtirish(scheduler, application)
    namoz_rejalashtir(scheduler, application)
    scheduler.start()

    logger.info("Bot Islom.uz bazasiga muvaffaqiyatli ulandi!")
    application.run_polling()

if __name__ == "__main__":
    main()
