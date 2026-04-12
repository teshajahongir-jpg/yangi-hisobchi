import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

# Yangi tokeningizni qo'ydim
TOKEN = "8701217643:AAEF3xSLSF10AYYwMH13p8QP612_cbvwoHs"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏢 Yuridik shaxs"), KeyboardButton(text="👤 Jismoniy shaxs")]
    ], resize_keyboard=True)
    await message.answer("Xush kelibsiz! Shaxs turini tanlang:", reply_markup=kb)

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

@dp.message(ContractForm.xizmat_turi)
async def select_xizmat(message: Message, state: FSMContext):
    await state.update_data(xizmat_turi=message.text)
    await message.answer("🏷 Tovar belgisi (brend) nomini kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p_tovar(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text)
    await m.answer("1. Shartnoma raqami:")
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p1(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text); await m.answer("2. Sana:"); await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p2(m: Message, state: FSMContext):
    await state.update_data(sana=m.text)
    data = await state.get_data()
    savol = "3. Firma (Mijoz) nomi:" if "Yuridik" in data['shaxs_turi'] else "3. Ism-familiyangiz:"
    await m.answer(savol); await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def p3(m: Message, state: FSMContext):
    await state.update_data(mijoz=m.text)
    data = await state.get_data()
    if "Yuridik" in data['shaxs_turi']:
        await m.answer("4. Direktor ismi:"); await state.set_state(ContractForm.direktor)
    else:
        await state.update_data(direktor="-")
        await m.answer("4. Yashash manzili:"); await state.set_state(ContractForm.manzil)

@dp.message(ContractForm.direktor)
async def p4(m: Message, state: FSMContext):
    if m.text != "-": await state.update_data(direktor=m.text)
    await m.answer("5. Manzil:"); await state.set_state(ContractForm.manzil)

@dp.message(ContractForm.manzil)
async def p5(m: Message, state: FSMContext):
    await state.update_data(manzil=m.text)
    data = await state.get_data()
    savol = "6. STIR (yoki Pasport):"
    await m.answer(savol); await state.set_state(ContractForm.stir)

@dp.message(ContractForm.stir)
async def p6(m: Message, state: FSMContext):
    await state.update_data(stir=m.text)
    data = await state.get_data()
    if "Yuridik" in data['shaxs_turi']:
        await m.answer("7. X/R:"); await state.set_state(ContractForm.xr)
    else:
        await state.update_data(xr="-", mfo="-")
        await m.answer("7. Summa (raqamda):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.xr)
async def p7(m: Message, state: FSMContext):
    await state.update_data(xr=m.text); await m.answer("8. MFO:"); await state.set_state(ContractForm.mfo)

@dp.message(ContractForm.mfo)
async def p8(m: Message, state: FSMContext):
    await state.update_data(mfo=m.text); await m.answer("9. Summa (raqamda):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p9(m: Message, state: FSMContext):
    await state.update_data(summa=m.text); await m.answer("10. Summa (so'z bilan):"); await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def p10(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text); await m.answer("11. Tovar sinfi:"); await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p11(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text)
    data = await state.get_data()
    await m.answer("⏳ Tayyorlanmoqda...")

    pref = "yu" if "Yuridik" in data['shaxs_turi'] else "jis"
    if "1 oylik" in data['xizmat_turi']: suf = "tezkor"
    elif "7 oylik" in data['xizmat_turi']: suf = "7oy"
    else: suf = "expert"
    
    shablon_nomi = f"{pref}_{suf}.docx"

    try:
        doc = DocxTemplate(shablon_nomi)
        doc.render(data)
        path = f"Shartnoma_{data['raqam'].replace('/', '_')}.docx"
        doc.save(path)
        await m.answer_document(FSInputFile(path), caption="✅ Tayyor!")
        os.remove(path)
    except Exception as e:
        await m.answer(f"❌ Xato: GitHub'da '{shablon_nomi}' topilmadi.")
    await state.clear()

async def handle(request): return web.Response(text="OK")
async def main():
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080))).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
