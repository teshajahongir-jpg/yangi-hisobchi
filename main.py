import os
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

TOKEN = "8701217643:AAEF3xSLSF10AYYwMH13p8QP612_cbvwoHs"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ContractForm(StatesGroup):
    xizmat_turi = State()
    stir = State()
    tovar_nomi = State()
    raqam = State()
    sana = State()
    sinf = State()
    summa = State()
    summa_soz = State()

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1 oylik tezkor")],
        [KeyboardButton(text="📅 7 oylik")],
        [KeyboardButton(text="🔍 Expert tekshiruv")]
    ], resize_keyboard=True)
    await message.answer("Xizmat turini tanlang:", reply_markup=kb)

@dp.message(F.text.contains("oylik") | F.text.contains("Expert"))
async def select_xizmat(message: Message, state: FSMContext):
    await state.update_data(xizmat_turi=message.text)
    await message.answer("🏢 Korxona STIR (INN) raqamini kiriting (9 ta raqam):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.stir)

@dp.message(ContractForm.stir)
async def fetch_org_data(message: Message, state: FSMContext):
    stir = message.text.strip()
    if not stir.isdigit() or len(stir) != 9:
        await message.answer("❌ Xato! STIR 9 ta raqam bo'lishi kerak. Qayta kiriting:")
        return

    await message.answer("🔍 Rekvizitlar qidirilmoqda...")
    
    # Baza topilmasa xato bermasligi uchun default ma'lumotlar
    await state.update_data(stir=stir, mijoz="Noma'lum", manzil="-", xr="-", mfo="-", direktor="-")

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.didox.uz/v1/dictionary/participant/{stir}"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    await state.update_data(
                        mijoz=res.get('name', "Noma'lum"),
                        manzil=res.get('address', "-"),
                        xr=res.get('account', "-"),
                        mfo=res.get('mfo', "-"),
                        direktor=res.get('director', "-")
                    )
                    await message.answer(f"✅ Ma'lumotlar topildi: {res.get('name')}")
                else:
                    await message.answer("⚠️ Didox-dan ma'lumot olinmadi, lekin davom etamiz.")
    except:
        await message.answer("⚠️ Qidiruvda uzilish, keyingi bosqichga o'tamiz.")

    await message.answer("1. Shartnoma raqamini kiriting:")
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p_raqam(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text)
    await m.answer("2. Sana (masalan, 12.04.2026):")
    await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p_sana(m: Message, state: FSMContext):
    await state.update_data(sana=m.text)
    await m.answer("3. Tovar belgisi (Brend) nomi:")
    await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p_brend(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text)
    await m.answer("4. Tovar sinfi (masalan, 25):")
    await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p_sinf(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text)
    await m.answer("5. Shartnoma summasi (faqat raqam):")
    await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p_summa(m: Message, state: FSMContext):
    await state.update_data(summa=m.text)
    await m.answer("6. Summani so'z bilan kiriting:")
    await state.set_state(ContractForm.summa_soz)

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
        path = f"Shartnoma_{data['raqam'].replace('/', '_')}.docx"
        doc.save(path)
        await m.answer_document(FSInputFile(path), caption="✅ Marhamat, shartnoma tayyor!")
        os.remove(path)
    except:
        await m.answer(f"❌ Xato: {shablon_nomi} topilmadi.")
    await state.clear()

async def handle(request): return web.Response(text="Bot is running")
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
