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
    stir = State()  # STIR orqali hamma ma'lumotni olamiz
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
    await message.answer("🏢 Korxona STIR (INN) raqamini kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.stir)

@dp.message(ContractForm.stir)
async def fetch_org_data(message: Message, state: FSMContext):
    stir = message.text
    if not stir.isdigit() or len(stir) != 9:
        await message.answer("❌ STIR 9 ta raqamdan iborat bo'lishi kerak. Qayta kiriting:")
        return

    await message.answer("🔍 Ma'lumotlar qidirilmoqda...")
    
    # Bu yerda STIR orqali ma'lumot oluvchi API (masalan, Didox yoki soliq) bo'lishi kerak
    # Hozircha namunaviy (avtomatik) to'ldirishni simulyatsiya qilamiz
    try:
        async with aiohttp.ClientSession() as session:
            # Namuna uchun ochiq API yoki sizning ichki bazangiz
            url = f"https://api.didox.uz/v1/dictionary/participant/{stir}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    org_data = await resp.json()
                    # Bazadan olingan ma'lumotlarni saqlaymiz
                    await state.update_data(
                        mijoz=org_data.get('name', 'Noma'lum korxona'),
                        manzil=org_data.get('address', 'Noma'lum manzil'),
                        xr=org_data.get('account', '-'),
                        mfo=org_data.get('mfo', '-'),
                        direktor=org_data.get('director', '-'),
                        stir=stir
                    )
                    await message.answer(f"✅ Topildi: {org_data.get('name')}\nEndi shartnoma raqamini kiriting:")
                    await state.set_state(ContractForm.raqam)
                else:
                    # Agar API ishlamasa, qo'lda kiritishga o'tkazsak bo'ladi yoki xato beramiz
                    await message.answer("❌ Ma'lumot topilmadi. Iltimos, shartnoma raqamini kiriting (qolganini qo'lda to'ldirasiz):")
                    await state.update_data(stir=stir, mijoz="Noma'lum", manzil="-", xr="-", mfo="-", direktor="-")
                    await state.set_state(ContractForm.raqam)
    except:
        await message.answer("⚠️ Tizimda uzilish. Shartnoma raqamini kiriting:")
        await state.update_data(stir=stir, mijoz="Noma'lum", manzil="-", xr="-", mfo="-", direktor="-")
        await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p_raqam(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text)
    await m.answer("📅 Sana (masalan, 12.04.2026):")
    await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p_sana(m: Message, state: FSMContext):
    await state.update_data(sana=m.text)
    await m.answer("🏷 Tovar belgisi (Brend) nomi:")
    await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p_brend(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text)
    await m.answer("🔢 Tovar sinfi (masalan, 25, 35):")
    await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p_sinf(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text)
    await m.answer("💰 Shartnoma summasi (raqamda):")
    await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p_summa(m: Message, state: FSMContext):
    await state.update_data(summa=m.text)
    await m.answer("✍️ Summani so'z bilan kiriting:")
    await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def final_step(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text)
    data = await state.get_data()
    
    await m.answer("⏳ Shartnoma shakllantirilmoqda...")
    
    # Shablonni tanlash (Yuridik shaxs uchun)
    suf = "tezkor" if "1 oylik" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon_nomi = f"yu_{suf}.docx"

    try:
        doc = DocxTemplate(shablon_nomi)
        doc.render(data)
        path = f"Shartnoma_{data['raqam']}.docx"
        doc.save(path)
        await m.answer_document(FSInputFile(path), caption="✅ Shartnoma tayyor!")
        os.remove(path)
    except Exception as e:
        await m.answer(f"❌ Xato yuz berdi: {str(e)}")
    
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
