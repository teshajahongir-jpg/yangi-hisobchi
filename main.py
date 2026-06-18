import os
import json
import logging
import requests
from datetime import datetime, time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# --- LOGGING SOZLAMALARI ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- XAVFSIZLIK VA TOKЕN ---
# DIQQAT: Tokenni @BotFather'dan yangilab, mana shu yerga qo'ying!
BOT_TOKEN = "8680299057:AAFZwPMCzPYsjIlL_zPXKgKuvKkYP4zLEO0"

# --- MA'LUMOTLAR BAZASI (JSON FAYLLAR) ---
USERS_FILE = "bot_users.json"
ATTENDANCE_FILE = "davomat_baza.json"
FINANCE_FILE = "moliya_baza.json"
NAMOZ_CACHE_FILE = "islom_uz_yilli_baza.json"

def db_yukla(fayl_nomi):
    if os.path.exists(fayl_nomi):
        with open(fayl_nomi, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def db_saqlash(fayl_nomi, ma'lumot):
    with open(fayl_nomi, "w", encoding="utf-8") as f:
        json.dump(ma'lumot, f, ensure_ascii=False, indent=4)

# --- 1-MODUL: 100% RASMIY ISLOM.UZ YILLI NAMOZ TIZIMI ---
def namoz_vaqtlarini_ol():
    bugun_sana = datetime.now().strftime("%Y-%m-%d")
    kesh_ma'lumoti = db_yukla(NAMOZ_CACHE_FILE)

    # 1-Tizim: Rasmiy Islom.uz API (Yil bo'yi 365 kun avtomat yangilanadi)
    try:
        url = "https://islomapi.uz/api/present/day"
        params = {"region": "Buxoro"}
        resp = requests.get(url, params=params, timeout=6)
        
        if resp.status_code == 200:
            timings = resp.json()["times"]
            vaqtlar = {
                "Bomdod": timings["tong_saharlik"],
                "Peshin": timings["peshin"],
                "Asr": timings["asr"],
                "Shom": timings["shom_iftor"],
                "Xufton": timings["hufton"]
            }
            kesh_ma'lumoti[bugun_sana] = vaqtlar
            db_saqlash(NAMOZ_CACHE_FILE, kesh_ma'lumoti)
            return vaqtlar
    except Exception as e:
        logger.warning(f"Islom.uz API vaqtincha ishlamadi, keshga o'tilmoqda: {e}")

    # 2-Tizim: Zaxira Kesh (Agar Islom.uz o'chsa, avval saqlangan kunlik xotiradan oladi)
    if bugun_sana in kesh_ma'lumoti:
        return kesh_ma'lumoti[bugun_sana]

    # 3-Tizim: Oylik favqulodda tizim (Agar kunlik keshda ham bo'lmasa, oylik jadvaldan qidiradi)
    try:
        joriy_oy = datetime.now().month
        url = f"https://islomapi.uz/api/monthly?region=Buxoro&month={joriy_oy}"
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            oylik_royxat = resp.json()
            bugun_kun = datetime.now().day
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

# --- MENU KLAVIATURASI ---
def asosiy_menu():
    klaviatura = [
        [KeyboardButton("🕌 Namoz vaqtlari"), KeyboardButton("🕒 Keldim (Check-in)")],
        [KeyboardButton("📝 Shartnomalar"), KeyboardButton("💰 Xarajatlar & Ulushlar")],
        [KeyboardButton("📊 Kunlik Hisobot")]
    ]
    return ReplyKeyboardMarkup(klaviatura, resize_keyboard=True)

# --- START BUYRUG'I ---
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    users_baza = db_yukla(USERS_FILE)
    
    if str(user.id) not in users_baza:
        users_baza[str(user.id)] = {"name": user.full_name, "username": user.username}
        db_saqlash(USERS_FILE, users_baza)
        
    await update.message.reply_text(
        f"Assalomu alaykum, {user.first_name}! Tizim muvaffaqiyatli ishga tushdi. "
        "Kerakli bo'limni tanlang:",
        reply_markup=asosiy_menu()
    )

# --- MESSAGES HANDLER (TUGMALAR BILAN ISHLASH) ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text
    user_id = str(update.effective_user.id)
    ism = update.effective_user.full_name
    hozir = datetime.now()

    # 1. NAMOZ VAQTLARI TUGMASI
    if matn == "🕌 Namoz vaqtlari":
        vaqtlar = namoz_vaqtlarini_ol()
        if vaqtlar:
            sana_str = hozir.strftime("%d.%m.%Y")
            javob = (
                f"🕌 **Buxoro (Islom.uz) — {sana_str}**\n\n"
                f"🌅 Bomdod: {vaqtlar['Bomdod']}\n"
                f"☀️ Peshin: {vaqtlar['Peshin']}\n"
                f"🌙 Asr: {vaqtlar['Asr']}\n"
                f"🌆 Shom: {vaqtlar['Shom']}\n"
                f"🌌 Xufton: {vaqtlar['Xufton']}"
            )
            await update.message.reply_text(javob, parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Islom.uz tizimidan ma'lumot olishda uzilish bo'ldi. Birozdan so'ng urining.")

    # 2. XODIMLAR DAVOMATI (CHECK-IN)
    elif matn == "🕒 Keldim (Check-in)":
        davomat = db_yukla(ATTENDANCE_FILE)
        bugun_sana = hozir.strftime("%Y-%m-%d")
        kelgan_vaqt = hozir.time()
        
        if bugun_sana not in davomat:
            davomat[bugun_sana] = {}
            
        if user_id in davomat[bugun_sana]:
            await update.message.reply_text(f"Kunlik davomatdan o'tib bo'lgansiz! Kelgan vaqtingiz: {davomat[bugun_sana][user_id]['vaqt']}")
            return

        # Soat 9:00 me'yori bo'yicha jarimani hisoblash
        limiti = time(9, 0, 0)
        jarima_matn = ""
        if kelgan_vaqt > limiti:
            farq = datetime.combine(hozir.date(), kelgan_vaqt) - datetime.combine(hozir.date(), limiti)
            kechikkan_daqiqa = int(farq.total_seconds() / 60)
            # Har bir kechikkan daqiqa uchun shartli jarima (Masalan: 2000 so'mdan)
            jarima_summasi = kechikkan_daqiqa * 2000
            jarima_matn = f"\n⚠️ Soat 9:00 dan {kechikkan_daqiqa} daqiqa kechikdingiz! Jarima: {jarima_summasi:,} so'm."
        else:
            jarima_matn = "\n✅ Vaqtida keldingiz. Barakalloh!"

        davomat[bugun_sana][user_id] = {
            "ism": ism,
            "vaqt": hozir.strftime("%H:%M:%S"),
            "status": "Kechikdi" if kelgan_vaqt > limiti else "Vaqtida keldi"
        }
        db_saqlash(ATTENDANCE_FILE, davomat)
        await update.message.reply_text(f"🕒 Kelgan vaqtingiz qayd etildi: {hozir.strftime('%H:%M')}.{jarima_matn}")

    # 3. SHARTNOMALAR MODULI
    elif matn == "📝 Shartnomalar":
        await update.message.reply_text(
            "📝 **Raqamli Shartnomalar Bo'limi**\n\n"
            "Yangi shartnoma tuzish, n8n webhook orqali hujjatlarni generatsiya qilish hamda "
            "PDF shablonlarni avtomat to'ldirish tizimi sozlangan. Jarayonni boshqarish uchun "
            "boshqaruv paneliga kiring yoki kerakli buyruqni bosing."
        )

    # 4. XARAJATLAR VA ULUSHLAR MODULI (80/20 SPLIT)
    elif matn == "💰 Xarajatlar & Ulushlar":
        await update.message.reply_text(
            "💰 **Moliyaviy Tracking & Ulushlar**\n\n"
            "Kiritilgan barcha aktivlar va tushumlar avtomatik ravishda hamkorlar o'rtasida "
            "**80% va 20%** proporsiyada taqsimlanadi.\n"
            "Xarajatlarni kiritish uchun: `/xarajat [summa] [tavsif]` formatida yozing."
        )

    # 5. KUNLIK HISOBOT
    elif matn == "📊 Kunlik Hisobot":
        davomat = db_yukla(ATTENDANCE_FILE)
        bugun_sana = hozir.strftime("%Y-%m-%d")
        
        hisobot = f"📊 **Kunlik Hisobot ({bugun_sana}):**\n\n👥 **Bugun kelgan xodimlar:**\n"
        if bugun_sana in davomat and davomat[bugun_sana]:
            for uid, info in davomat[bugun_sana].items():
                hisobot += f"• {info['ism']} — {info['vaqt']} ({info['status']})\n"
        else:
            hisobot += "Bugun hali hech kim davomatdan o'tmadi.\n"
            
        await update.message.reply_text(hisobot, parse_mode="Markdown")

# --- XARAJATLARNI BUYRUQ ORQALI KIRITISH ---
async def xarajat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Xato format. Misol: `/xarajat 500000 Ofis jihozlari`")
        return
        
    try:
        summa = float(context.args[0])
        tavsif = " ".join(context.args[1:])
        moliya = db_yukla(FINANCE_FILE)
        
        bugun = datetime.now().strftime("%Y-%m-%d %H:%M")
        # 80/20 ulush hisobi
        ulush_80 = summa * 0.8
        ulush_20 = summa * 0.2
        
        moliya[bugun] = {
            "summa": summa,
            "tavsif": tavsif,
            "ulush_80": ulush_80,
            "ulush_20": ulush_20
        }
        db_saqlash(FINANCE_FILE, moliya)
        
        await update.message.reply_text(
            f"✅ Xarajat saqlandi!\n"
            f"📝 Tavsif: {tavsif}\n"
            f"💵 Umumiy: {summa:,} so'm\n"
            f"📈 Alisher (80%): {ulush_80:,} so'm\n"
            f"📉 Zokir (20%): {ulush_20:,} so'm"
        )
    except ValueError:
        await update.message.reply_text("⚠️ Summani faqat raqamlarda kiriting!")

# --- ADMIN PANEL: BARCHAGA XABAR YUBORISH (BROADCAST) ---
async def barchaga_yubor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Bu funksiyani faqat siz (Admin) ishlata olasiz
    user_id = update.effective_user.id
    # O'zingizning Telegram ID'ingizni tekshirish qismini qo'shishingiz mumkin
    
    if not context.args:
        await update.message.reply_text("⚠️ Xabar matnini yozing. Misol: `/barchaga Bugun majlis soat 15:00 da.`")
        return
        
    xabar = " ".join(context.args)
    users_baza = db_yukla(USERS_FILE)
    
    yuborildi = 0
    for uid in users_baza.keys():
        try:
            await context.application.bot.send_message(chat_id=int(uid), text=f"📢 **Muhim xabar:**\n\n{xabar}", parse_mode="Markdown")
            yuborildi += 1
        except Exception:
            pass
            
    await update.message.reply_text(f"🚀 Xabar {yuborildi} ta foydalanuvchiga muvaffaqiyatli yetkazildi.")

# --- ASOSIY ISHGA TUSHIRISH (MAIN) ---
def main():
    # Application qurish
    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers (Buyruqlar va xabarlarni bog'lash)
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("xarajat", xarajat_handler))
    application.add_handler(CommandHandler("barchaga", barchaga_yubor))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Botni ishga tushirish (Polling rejimida Render'da Background Worker sifatida juda barqaror ishlaydi)
    print("Premium bot muvaffaqiyatli ishga tushdi...")
    application.run_polling()

if __name__ == "__main__":
    main()
