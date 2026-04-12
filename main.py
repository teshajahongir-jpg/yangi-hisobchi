import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

TOKEN = "8701217643:AAFrMUwSBEZCV3kybsEWYzHGjFczJ9fBXcs"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ContractForm(StatesGroup):
    xizmat_turi = State()
    mijoz = State()
    manzil = State()
    stir = State()
    xr = State()
    mfo = State()
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
        [KeyboardButton(text="⚡️ 1 oylik tezkor"), KeyboardButton(text="📅 7 oylik")],
        [KeyboardButton(text="🔍 Expert tekshiruv")]
    ], resize_keyboard=True)
    await message.answer("Xizmat turini tanlang:", reply_markup=kb)

@dp.message(F.text.in_(["⚡️ 1 oylik tezkor", "📅 7 oylik", "🔍 Expert tekshiruv"]))
async def select_xizmat(message: Message, state: FSMContext):
    await state.update_data(xizmat_turi=message.text)
    await message.answer("📝 Korxona (Mijoz) nomi:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def p_mijoz(m: Message, state: FSMContext):
    await state.update_data(mijoz=m.text); await m.answer("📍 Manzili:"); await state.set_state(ContractForm.manzil)

@dp.message(ContractForm.manzil)
async def p_manzil(m: Message, state: FSMContext):
    await state.update_data(manzil=m.text); await m.answer("🔢 STIR (INN):"); await state.set_state(ContractForm.stir)

@dp.message(ContractForm.stir)
async def p_stir(m: Message, state: FSMContext):
    await state.update_data(stir=m.text); await m.answer("💳 Hisob raqami (X/R):"); await state.set_state(ContractForm.xr)

@dp.message(ContractForm.xr)
async def p_xr(m: Message, state: FSMContext):
    await state.update_data(xr=m.text); await m.answer("🏦 MFO:"); await state.set_state(ContractForm.mfo)

@dp.message(ContractForm.mfo)
async def p_mfo(m: Message, state: FSMContext):
    await state.update_data(mfo=m.text); await m.answer("👤 Direktor ismi:"); await state.set_state(ContractForm.direktor)

@dp.message(ContractForm.direktor)
async def p_direktor(m: Message, state: FSMContext):
    await state.update_data(direktor=m.text); await m.answer("🔢 Shartnoma raqami:"); await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p_raqam(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text); await m.answer("📅 Sana:"); await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p_sana(m: Message, state: FSMContext):
    await state.update_data(sana=m.text); await m.answer("🏷 Brend nomi:"); await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p_brend(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text); await m.answer("🔢 Tovar sinfi:"); await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p_sinf(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text); await m.answer("💰 Summa (raqamda):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p_summa(m: Message, state: FSMContext):
    await state.update_data(summa=m.text); await m.answer("✍️ Summa (so'z bilan):"); await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def final_step(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text)
    data = await state.get_data()
    await m.answer("⏳ Shartnoma tayyorlanmoqda...")
    
    suf = "tezkor" if "1 oylik" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon_nomi = f"yu_{suf}.docx"

    try:
        doc = DocxTemplate(shablon_nomi)
        doc.render(data)
        path = f"S_{data['raqam'].replace('/', '_')}.docx"
        doc.save(path)
        await m.answer_document(FSInputFile(path), caption="✅ Tayyor!")
        os.remove(path)
    except:
        await m.answer(f"❌ Xato: {shablon_nomi} topilmadi.")
    await state.clear()

async def handle(request): return web.Response(text="Bot Live")
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
