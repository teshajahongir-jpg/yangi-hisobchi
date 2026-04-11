import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

# TOKKEN
TOKEN = "8701217643:AAG43PL7b63u6ULkp9pcKjfblf9chCh2G78"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Render o'chib qolmasligi uchun kichik server
async def handle(request):
    return web.Response(text="Bot ishlayapti!")

# Savollar
class ContractForm(StatesGroup):
    raqam = State()
    sana = State()
    mijoz = State()
    stir = State()
    summa = State()
    sinf = State()

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📝 Yangi shartnoma")]], resize_keyboard=True)
    await message.answer("Xush kelibsiz, Jahongir aka!", reply_markup=kb)

@dp.message(F.text == "📝 Yangi shartnoma")
async def start_contract(message: Message, state: FSMContext):
    await message.answer("1. Shartnoma raqami:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p1(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text)
    await m.answer("2. Sana:")
    await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p2(m: Message, state: FSMContext):
    await state.update_data(sana=m.text)
    await m.answer("3. Mijoz nomi:")
    await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def p3(m: Message, state: FSMContext):
    await state.update_data(mijoz=m.text)
    await m.answer("4. STIR (INN):")
    await state.set_state(ContractForm.stir)

@dp.message(ContractForm.stir)
async def p4(m: Message, state: FSMContext):
    await state.update_data(stir=m.text)
    await m.answer("5. Summa:")
    await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p5(m: Message, state: FSMContext):
    await state.update_data(summa=m.text)
    await m.answer("6. Sinf:")
    await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p6(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text)
    data = await state.get_data()
    await m.answer("Hujjat tayyorlanmoqda...")
    try:
        doc = DocxTemplate("shablon.docx")
        doc.render(data)
        path = f"Shartnoma_{data['raqam'].replace('/', '_')}.docx"
        doc.save(path)
        await m.answer_document(FSInputFile(path))
        os.remove(path)
    except Exception as e:
        await m.answer(f"Xato: {e}")
    await state.clear()

async def main():
    # Serverni ishga tushirish (Render uchun)
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()
    # Botni ishga tushirish
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
