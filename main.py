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
        [KeyboardButton(text="Yuridik shaxs"), KeyboardButton(text="Jismoniy shaxs")]
    ], resize_keyboard=True)
    await message.answer("Shartnoma turini tanlang:", reply_markup=kb)

@dp.message(F.text.in_(["Yuridik shaxs", "Jismoniy shaxs"]))
async def select_shaxs(message: Message, state: FSMContext):
    await state.update_data(shaxs_turi=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="1 oylik tezkor"), KeyboardButton(text="7 oylik")],
        [KeyboardButton(text="Expert tekshiruv")]
    ], resize_keyboard=True)
    await message.answer("Xizmat turini tanlang:", reply_markup=kb)
    await state.set_state(ContractForm.xizmat_turi)

@dp.message(ContractForm.xizmat_turi)
async def select_xizmat(message: Message, state: FSMContext):
    await state.update_data(xizmat_turi=message.text)
    data = await state.get_data()
    savol = "Korxona nomi:" if data['shaxs_turi'] == "Yuridik shaxs" else "Mijozning toliq ismi:"
    await message.answer(savol, reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def p1(m: Message, state: FSMContext):
    await state.update_data(mijoz=m.text)
    data = await state.get_data()
    savol = "Yuridik manzil:" if data['shaxs_turi'] == "Yuridik shaxs" else "Yashash manzili:"
    await m.answer(savol); await state.set_state(ContractForm.manzil)

@dp.message(ContractForm.manzil)
async def p2(m: Message, state: FSMContext):
    await state.update_data(manzil=m.text)
    data = await state.get_data()
    savol = "STIR (INN):" if data['shaxs_turi'] == "Yuridik shaxs" else "Pasport seriya va raqami:"
    await m.answer(savol); await state.set_state(ContractForm.stir_pasport)

@dp.message(ContractForm.stir_pasport)
async def p3(m: Message, state: FSMContext):
    await state.update_data(stir=m.text)
    data = await state.get_data()
    if data['shaxs_turi'] == "Yuridik shaxs":
        await m.answer("Hisob raqami (X/R):"); await state.set_state(ContractForm.xr_manzil)
    else:
        await m.answer("Telefon raqami:"); await state.set_state(ContractForm.xr_manzil)

@dp.message(ContractForm.xr_manzil)
async def p4(m: Message, state: FSMContext):
    await state.update_data(xr=m.text)
    data = await state.get_data()
    if data['shaxs_turi'] == "Yuridik shaxs":
        await m.answer("Bank MFOsi:"); await state.set_state(ContractForm.mfo_tel)
    else:
        await state.update_data(mfo="-", direktor="-")
        await m.answer("Shartnoma raqami:"); await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.mfo_tel)
async def p5(m: Message, state: FSMContext):
    await state.update_data(mfo=m.text)
    await m.answer("Direktor ismi:"); await state.set_state(ContractForm.direktor)

@dp.message(ContractForm.direktor)
async def p6(m: Message, state: FSMContext):
    await state.update_data(direktor=m.text)
    await m.answer("Shartnoma raqami:"); await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p7(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text); await m.answer("Sana:"); await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p8(m: Message, state: FSMContext):
    await state.update_data(sana=m.text); await m.answer("Brend nomi:"); await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p9(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text); await m.answer("Tovar sinfi:"); await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p10(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text); await m.answer("Summa (faqat raqamda):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p11(m: Message, state: FSMContext):
    await state.update_data(summa=m.text); await m.answer("Summani soz bilan yozing:"); await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def final_step(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text)
    data = await state.get_data()
    await m.answer("Tayyorlanmoqda...")
    
    prefix = "yu_" if data['shaxs_turi'] == "Yuridik shaxs" else "jis_"
    suf = "tezkor" if "tezkor" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon = f"{prefix}{suf}.docx"

    try:
        doc = DocxTemplate(shablon)
        doc.render(data)
        path = f"S_{m.from_user.id}.docx"
        doc.save(path)
        await m.answer_document(FSInputFile(path), caption="Tayyor!")
        os.remove(path)
    except:
        await m.answer(f"Xato: {shablon} topilmadi.")
    await state.clear()

async def handle(request): return web.Response(text="Live")
async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
