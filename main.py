import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

TOKEN = "8701217643:AAGp4yUtbxqd2omT8SS25PcxUOuYvUNxaeI"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ContractForm(StatesGroup):
    shaxs_turi = State()
    xizmat_turi = State()
    mijoz = State()
    manzil = State()
    stir_pasport = State()
    xr_manzil = State()
    mfo_tel = State()
    direktor = State()
    raqam = State()
    sana = State()
    tovar_nomi = State()
    sinf = State()
    summa = State()
    summa_soz = State()

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏢 Yuridik shaxs"), KeyboardButton(text="👤 Jismoniy shaxs")]
    ], resize_keyboard=True)
    await message.answer("Assalomu alaykum! Kim uchun shartnoma tayyorlaymiz?", reply_markup=kb)

@dp.message(F.text.in_(["🏢 Yuridik shaxs", "👤 Jismoniy shaxs"]))
async def select_shaxs(message: Message, state: FSMContext):
    await state.update_data(shaxs_turi=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1 oylik tezkor"), KeyboardButton(text="📅 7 oylik")],
        [KeyboardButton(text="🔍 Expert tekshiruv")]
    ], resize_keyboard=True)
    await message.answer("Xizmat turini tanlang:", reply_markup=kb)
    await state.set_state(ContractForm.xizmat_turi)

@dp.message(ContractForm.xizmat_turi)
async def select_xizmat(message: Message, state: FSMContext):
    await state.update_data(xizmat_turi=message.text)
    data = await state.get_data()
    savol = "📝 Korxona (Mijoz) nomi:" if "🏢" in data['shaxs_turi'] else "👤 Mijozning F.I.Sh:"
    await message.answer(savol, reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def p1(m: Message, state: FSMContext):
    await state.update_data(mijoz=m.text)
    data = await state.get_data()
    savol = "📍 Yuridik manzil:" if "🏢" in data['shaxs_turi'] else "📍 Yashash manzili:"
    await m.answer(savol); await state.set_state(ContractForm.manzil)

@dp.message(ContractForm.manzil)
async def p2(m: Message, state: FSMContext):
    await state.update_data(manzil=m.text)
    data = await state.get_data()
    savol = "🔢 STIR (INN):" if "🏢" in data['shaxs_turi'] else "🪪 Pasport seriya va raqami:"
    await m.answer(savol); await state.set_state(ContractForm.stir_pasport)

@dp.message(ContractForm.stir_
