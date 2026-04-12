import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

TOKEN = "8701217643:AAHtcthzjV85AyCyS1bLd3FVIfxa7fB1WAM"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class YuridikForm(StatesGroup):
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

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏢 Yuridik shaxs shartnomasi")]], resize_keyboard=True)
    await message.answer("Xush kelibsiz! Shartnoma turini tanlang:", reply_markup=kb)

@dp.message(F.text == "🏢 Yuridik shaxs shartnomasi")
async def start_yuridik(message: Message, state: FSMContext):
    await message.answer("1. Shartnoma raqamini kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(YuridikForm.raqam)

@dp.message(YuridikForm.raqam)
async def p1(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text)
    await m.answer("2. Shartnoma sanasini kiriting (masalan: 12 aprel):")
    await state.set_state(YuridikForm.sana)

@dp.message(YuridikForm.sana)
async def p2(m: Message, state: FSMContext):
    await state.update_data(sana=m.text)
    await m.answer("3. Firma (Mijoz) nomini kiriting:")
    await state.set_state(YuridikForm.mijoz)

@dp.message(YuridikForm.mijoz)
async def p3(m: Message, state: FSMContext):
    await state.update_data(mijoz=m.text)
    await m.answer("4. Direktorning F.I.SH.ni kiriting:")
    await state.set_state(YuridikForm.direktor)

@dp.message(YuridikForm.direktor)
async def p4(m: Message, state: FSMContext):
    await state.update_data(direktor=m.text)
    await m.answer("5. Firmaning yuridik manzilini kiriting:")
    await state.set_state(YuridikForm.manzil)

@dp.message(YuridikForm.manzil)
async def p5(m: Message, state: FSMContext):
    await state.update_data(manzil=m.text)
    await m.answer("6. STIR (INN) raqamini kiriting:")
    await state.set_state(YuridikForm.stir)

@dp.message(YuridikForm.stir)
async def p6(m: Message, state: FSMContext):
    await state.update_data(stir=m.text)
    await m.answer("7. Hisob raqamini (X/R) kiriting:")
    await state.set_state(YuridikForm.xr)

@dp.message(YuridikForm.xr)
async def p7(m: Message, state: FSMContext):
    await state.update_data(xr=m.text)
    await m.answer("8. MFO kodini kiriting:")
    await state.set_state(YuridikForm.mfo)

@dp.message(YuridikForm.mfo)
async def p8(m: Message, state: FSMContext):
    await state.update_data(mfo=m.text)
    await m.answer("9. Umumiy summani raqamda kiriting (masalan: 2 300 000):")
    await state.set_state(YuridikForm.summa)

@dp.message(YuridikForm.summa)
async def p9(m: Message, state: FSMContext):
    await state.update_data(summa=m.text)
    await m.answer("10. Endi summani КИРИЛЛЧАДА (сўз bilan) yozing:")
    await state.set_state(YuridikForm.summa_soz)

@dp.message(YuridikForm.summa_soz)
async def p10(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text)
    await m.answer("11. Tovar sinflarini kiriting (masalan: 29, 30):")
    await state.set_state(YuridikForm.sinf)

@dp.message(YuridikForm.sinf)
async def p11(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text)
    data = await state.get_data()
    await m.answer("Hujjat tayyorlanmoqda, kuting...")
    
    try:
        # Fayl nomi shablon_yuridik.docx bo'lishi kerak
        doc = DocxTemplate("shablon_yuridik.docx")
        doc.render(data)
        file_name = f"Shartnoma_{data['raqam'].replace('/', '_')}.docx"
        doc.save(file_name)
        await m.answer_document(FSInputFile(file_name))
        os.remove(file_name)
    except Exception as e:
        await m.answer(f"Xato: {e}. GitHub'da shablon_yuridik.docx fayli borligini tekshiring.")
    await state.clear()

async def handle(request): return web.Response(text="Bot ishlayapti")
async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
