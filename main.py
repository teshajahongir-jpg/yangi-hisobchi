import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

# Bot tokeni
TOKEN = "8701217643:AAEF3xSLSF1OAYYwMH13p8QP612_cbvwoHs"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# FSM - Savollar ketma-ketligi
class ContractForm(StatesGroup):
    shaxs_turi = State()
    xizmat_turi = State()
    tovar_nomi = State()
    raqam = State()
    sana = State()
    mijoz = State()
    direktor = State()
    manzil = State()
    stir = State()
    xr = State()
    mfo = State()
    summa = State()
    summa_soz = State()
    sinf = State()

# 1. Start bosilganda shaxs turini tanlash
@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏢 Yuridik shaxs"), KeyboardButton(text="👤 Jismoniy shaxs")]
    ], resize_keyboard=True)
    await message.answer("Xush kelibsiz! Shartnoma uchun shaxs turini tanlang:", reply_markup=kb)

# 2. Xizmat turini tanlash (3 ta knopka)
@dp.message(F.text.in_(["🏢 Yuridik shaxs", "👤 Jismoniy shaxs"]))
async def select_shaxs(message: Message, state: FSMContext):
    await state.update_data(shaxs_turi=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1 oylik tezkor")],
        [KeyboardButton(text="📅 7 oylik")],
        [KeyboardButton(text="🔍 Expert tekshiruv")]
    ], resize_keyboard=True)
    await message.answer("Xizmat turini tanlang:", reply_markup=kb)
    await state.set_state(ContractForm.xizmat_turi)

# 3. Tovar belgisi nomini so'rash
@dp.message(ContractForm.xizmat_turi)
async def select_xizmat(message: Message, state: FSMContext):
    await state.update_data(xizmat_turi=message.text)
    await message.answer("🏷 Tovar belgisi (brend) nomini kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.tovar_nomi)

# 4. Rekvizitlarni yig'ish (Mantiqiy farqlar bilan)
@dp.message(ContractForm.tovar_nomi)
async def p_tovar(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text)
    await m.answer("1. Shartnoma raqamini kiriting:")
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p1(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text); await m.answer("2. Shartnoma sanasini kiriting:"); await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p2(m: Message, state: FSMContext):
    await state.update_data(sana=m.text)
    data = await state.get_data()
    savol = "3. Firma (Mijoz) nomini kiriting:" if "Yuridik" in data['shaxs_turi'] else "3. To'liq ism-familiyangizni kiriting:"
    await m.answer(savol); await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def p3(m: Message, state: FSMContext):
    await state.update_data(mijoz=m.text)
    data = await state.get_data()
    if "Yuridik" in data['shaxs_turi']:
        await m.answer("4. Direktor ismini kiriting:"); await state.set_state(ContractForm.direktor)
    else:
        await state.update_data(direktor="-") # Jismoniyda direktor yo'q
        await m.answer("4. Yashash manzilingizni kiriting:"); await state.set_state(ContractForm.manzil)

@dp.message(ContractForm.direktor)
async def p4(m: Message, state: FSMContext):
    if m.text != "-": await state.update_data(direktor=m.text)
    await m.answer("5. Yuridik manzilni kiriting:"); await state.set_state(ContractForm.manzil)

@dp.message(ContractForm.manzil)
async def p5(m: Message, state: FSMContext):
    await state.update_data(manzil=m.text)
    data = await state.get_data()
    savol = "6. STIR (INN) kiriting:" if "Yuridik" in data['shaxs_turi'] else "6. Pasport seriya va raqamini kiriting:"
    await m.answer(savol); await state.set_state(ContractForm.stir)

@dp.message(ContractForm.stir)
async def p6(m: Message, state: FSMContext):
    await state.update_data(stir=m.text)
    data = await state.get_data()
    if "Yuridik" in data['shaxs_turi']:
        await m.answer("7. Hisob raqami (X/R) kiriting:"); await state.set_state(ContractForm.xr)
    else:
        await state.update_data(xr="-", mfo="-")
        await m.answer("7. To'lov summasini kiriting (faqat raqamda):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.xr)
async def p7(m: Message, state: FSMContext):
    await state.update_data(xr=m.text); await m.answer("8. MFO kodini kiriting:"); await state.set_state(ContractForm.mfo)

@dp
