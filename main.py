import os
import pytz
import asyncio
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# 🚨 ASOSIY TIZIM SOZLAMALARI
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738

# 📍 ISHXONA KOORDINATASI VA CHEGARA MASOFASI
ISHXONA_LAT = 39.745430   
ISHXONA_LON = 64.439307   
MAKS_MASOFA = 150         

# 💰 JADVALDAGI STAVKALAR (image_ff6d40.png bo'yicha)
XODIMLAR_BAZASI = {
    "Sevinch":      {"oylik": 4000000, "minut_narxi": 14743.59, "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Charos":       {"oylik": 6000000, "minut_narxi": 3846.15,  "soat_narxi": 201923.08, "kun_narxi": 0.0},
    "Ozodbek":      {"oylik": 6000000, "minut_narxi": 49038.46, "soat_narxi": 28846.15,  "kun_narxi": 0.0},
    "Xudoyorxon":   {"oylik": 5200000, "minut_narxi": 75000.0,  "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Ruxshona":     {"oylik": 5200000, "minut_narxi": 3333.33,  "soat_narxi": 50000.0,   "kun_narxi": 200000.0},
    "Ferangiz":     {"oylik": 3000000, "minut_narxi": 1923.08,  "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Jahongir":     {"oylik": 1200000, "minut_narxi": 0.0,      "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Muqaddas opa": {"oylik": 2200000, "minut_narxi": 0.0,      "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Avazbek":      {"oylik": 2000000, "minut_narxi": 801.28,   "soat_narxi": 0.0,       "kun_narxi": 0.0}
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
UZ_TZ = pytz.timezone('Asia/Tashkent')
scheduler = AsyncIOScheduler(timezone=UZ_TZ)

# Ichki ma'lumotlar bazasi
tizim_baza = {}

class BotStates(StatesGroup):
    ism_kutish = State()

def masofani_hisobla(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    return c * 6371000

# ⏰ HAR KUNI SOAT 17:00 DA AVTOMATIK SIGNAL
async def kunlik_eslatma():
    for tg_id, info in tizim_baza.items():
        if info.get('tasdiqlangan', False) and tg_id != ADMIN_ID:
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text="⏰ **Ish vaqti tugadi!**\n\nIltimos, agar ishni yakunlasangiz **🔴 Ishni yakunlash** tugmasini bosing.\nAgar qo'shimcha ishlamoqchi bo'lsangiz, **⏰ Qo'shimcha ishlash** tugmasini bosib lokatsiya yuboring.",
                    reply_markup=xodim_klaviatura()
                )
            except:
                pass
    await bot.send_message(ADMIN_ID, "📢 Xodimlarga soat 17:00
