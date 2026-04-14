import os, asyncio, re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

# TOKEN
TOKEN = "8701217643:AAG0vyPcyQaCDqw8nhEcM3OrnpLgCHE3YZk"
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ContractForm(StatesGroup):
    shaxs_turi = State()
    xizmat_turi = State()
    rekvizitlar = State()
    raqam = State()
    sana = State()
    tovar_nomi = State()
    sinf = State()
    summa = State()
    summa_soz = State()

@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏢 Yuridik shaxs"), KeyboardButton(text="👤 Jismoniy shaxs")]
    ], resize_keyboard=True)
    await m.answer("Salom! Shartnoma turini tanlang:", reply_markup=kb)

@dp.message(F.text.in_(["🏢 Yuridik shaxs", "👤 Jismoniy shaxs"]))
async def select_shaxs(m: Message, state: FSMContext):
    await state.update_data(shaxs_turi=m.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1 oylik tezkor"), KeyboardButton(text="📅 7 oylik")],
        [KeyboardButton(text="🔍 Expert tekshiruv")]
    ], resize_keyboard=True)
    await m.answer("Xizmat turini tanlang:", reply_markup=kb)
    await state.set_state(ContractForm.xizmat_turi)

@dp.message(ContractForm.xizmat_turi)
async def ask_rekvizitlar(m: Message, state: FSMContext):
    await state.update_data(xizmat_turi=m.text)
    await m.answer("📝 Rekvizitlar jadvalini tashlang:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.rekvizitlar)

@dp.message(ContractForm.rekvizitlar)
async def process_rekvizitlar(m: Message, state: FSMContext):
    t = m.text
    def get_val(keys, src):
        for k in keys:
            match = re.search(fr"{k}[:\s]+([^\n]+)", src, re.I)
            if match: return match.group(1).strip()
        return "-"

    # Rekvizitlarni jadvaldan ajratish (rasmdagi kabi)
    lines = t.split('\n')
    mijoz = lines[0].replace("Korxona:", "").replace("“", "").replace("”", "").strip()
    
    await state.update_data(
        mijoz=mijoz,
        stir=get_val(["INN", "STIR", "ИНН", "Pasport"], t),
        xr=get_val(["H/R", "XR", "X/P", "Hisob"], t).replace(" ", ""),
        mfo=get_val(["MFO", "МФО"], t).replace(" ", ""),
        direktor=get_val(["Direktor", "Директор", "F.I.SH"], t),
        manzil=get_val(["Manzil", "Манзил"], t)
    )
    await m.answer("✅ Rekvizitlar olindi. \n\n7. Shartnoma raqamini yuboring:")
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p_raqam(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text)
    await m.answer("8. Sana (masalan: 14.04.2026):")
    await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p_sana(m: Message, state: FSMContext):
    await state.update_data(sana=m.text)
    await m.answer("9. Brend nomi:")
    await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p_tovar(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text)
    await m.answer("10. Tovar sinfi:")
    await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p_sinf(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text)
    await m.answer("11. Summa
