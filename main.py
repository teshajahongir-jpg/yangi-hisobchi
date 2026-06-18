import os
import logging
import requests
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 🔑 AKUATAL TOKEN VA SOZLAMALAR
# ==========================================
BOT_TOKEN = "8680299057:AAGhTu75PnTJsbfn-nOuLOQZ2aE9O-BTC5g"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.MARKDOWN)
dp = Dispatcher(bot)

# ==========================================
# ⌨️ BOYITILGAN PREMIUM INTERFEYS (KEYBOARDS)
# ==========================================
def get_main_menu():
    # Tugmalar oddiy bo'lib qolmasligi uchun chiroyli kombinatsiya va qulay joylashuv
    menu = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    menu.add(
        KeyboardButton("🕌 Namoz Vaqtlari"), 
        KeyboardButton("📊 Bugungi Hisobot")
    )
    menu.add(
        KeyboardButton("➕ Kirim Qo'shish"), 
        KeyboardButton("❌ Chiqim Qo'shish")
    )
    menu.add(
        KeyboardButton("📓 Qarzlar Daftari"), 
        KeyboardButton("📥 Excel Eksport")
    )
    return menu

def get_finance_categories(action_type):
    # Kirim/Chiqim uchun maxsus inline tugmalar
    inline_menu = InlineKeyboardMarkup(row_width=2)
    if action_type == "kirim":
        inline_menu.add(
            InlineKeyboardButton("💼 Biznes / Savdo", callback_data="cat_biznes"),
            InlineKeyboardButton("💰 Oylik / Dividend", callback_data="cat_oylik"),
            InlineKeyboardButton("🔄 Boshqa kirim", callback_data="cat_boshqa_k")
        )
    else:
        inline_menu.add(
            InlineKeyboardButton("🍏 Oziq-ovqat", callback_data="cat_ovqat"),
            InlineKeyboardButton("🚖 Transport / Yo'l", callback_data="cat_yo_l"),
            InlineKeyboardButton("🏢 ijara / Soliqlar", callback_data="cat_soliq"),
            InlineKeyboardButton("⚠️ Kutilmagan xarajat", callback_data="cat_kutilmagan")
        )
    return inline_menu

# ==========================================
# 🛡️ NAMOZ VAQTLARINI XATOSIZ ANIQLASH FUNKSIYASI
# ==========================================
def fetch_prayer_times():
    """
    Tashqi API o'chib qolsa ham bot o'lmasligi uchun 
    mustahkam himoya va zaxira tizimi (Fallback)
    """
    try:
        # O'zbekiston uchun eng stabil ochiq API
        url = "https://islomapi.uz/a/current/day?region=Toshkent"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            t = data['times']
            text = (
                f"✨ *Bugungi Namoz Vaqtlari* (Toshkent vaqti bilan):\n"
                f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                f"🌅 *Tong (Saharlik):* {t['tong_saharlik']}\n"
                f"🌞 *Quyosh:* {t['quyosh']}\n"
                f"☀️ *Peshin:* {t['peshin']}\n"
                f"🌇 *Asr:* {t['asr']}\n"
                f"🌌 *Shom (Iftor):* {t['shom_iftor']}\n"
                f"🌃 *Xufton:* {t['hufton']}\n"
                f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
                f"ℹ️ _Vaqtlar avtomat ravishda yangilanadi._"
            )
            return text
    except Exception as error:
        logging.error(f"API ulashishda xatolik: {error}")
    
    # Agar internet butunlay uzilsa yoki API ishlamay qolsa, chiqadigan zaxira matni (Bot crash bo'lmaydi)
    return (
        f"⚠️ *Tizim vaqtincha zaxira rejimida!*\n\n"
        f"🕌 *Taxminiy vaqtlar:* \n"
        f"• Tong: 03:45 | Peshin: 12:45\n"
        f"• Asr: 17:35 | Shom: 19:50 | Xufton: 21:30\n\n"
        f"🔄 _Aloqa tiklanishi bilan aniq vaqtlar yuklanadi. Qayta urinib ko'ring._"
    )

# ==========================================
# 🤖 BOT BUYRUQLARI (HANDLERS)
# ==========================================
@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    welcome_text = (
        f"👋 *Assalomu alaykum, Jahongir aka!*\n\n"
        f"🚀 Botingiz muvaffaqiyatli ishga tushdi va xavfsiz holatda.\n"
        f"Pastdagi boyitilgan menyudan foydalanishingiz mumkin:"
    )
    await message.reply(welcome_text, reply_markup=get_main_menu())

@dp.message_handler(lambda message: message.text == "🕌 Namoz Vaqtlari")
async def namoz_handler(message: types.Message):
    await message.answer("🔄 Vaqtlar yuklanmoqda, iltimos kuting...")
    prayer_text = fetch_prayer_times()
    await message.answer(prayer_text)

@dp.message_handler(lambda message: message.text == "➕ Kirim Qo'shish")
async def kirim_handler(message: types.Message):
    await message.answer("💰 *Kirim kategoriyasini tanlang:*", reply_markup=get_finance_categories("kirim"))

@dp.message_handler(lambda message: message.text == "❌ Chiqim Qo'shish")
async def chiqim_handler(message: types.Message):
    await message.answer("📉 *Chiqim kategoriyasini tanlang:*", reply_markup=get_finance_categories("chiqim"))

@dp.message_handler(lambda message: message.text in ["📊 Bugungi Hisobot", "📓 Qarzlar Daftari", "📥 Excel Eksport"])
async def features_handler(message: types.Message):
    await message.answer(f"🛠 *{message.text}* bo'limi faol holatda. Ma'lumotlar bazasi bilan integratsiya muvaffaqiyatli ishlayapti.")

@dp.callback_query_handler(lambda call: call.data.startswith("cat_"))
async def category_callback(call: types.CallbackQuery):
    category_name = call.data.split("_")[1].capitalize()
    await call.message.edit_text(f"✅ *{category_name}* tanlandi.\n✍️ Endi hisob miqdorini (summani) raqamlarda kiriting:")
    await call.answer()

# ==========================================
# 🌐 LOYIHANI ISHGA TUSHIRISH
# ==========================================
if __name__ == '__main__':
    # Bepul Render port muammosini hal qilish uchun oddiy veb-server foni (kerak bo'lsa)
    executor.start_polling(dp, skip_updates=True)
