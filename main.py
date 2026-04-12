import os
import asyncio
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

TOKEN = "8701217643:AAHnHsVJHykwIpezdLgnzHgmC-HTgntTQbM"

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
    data = await state.get_data()
    if "Yuridik" in data['shaxs_turi']:
        await message.answer("🏢 Korxona rekvizitlarini blok ko'rinishida tashlang (Nomi, INN, MFO, Direktor...):", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("👤 Mijozning ism-familiyasini kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def p_mijoz_block(m: Message, state: FSMContext):
    data = await state.get_data()
    text = m.text
    
    if "Yuridik" in data['shaxs_turi']:
        # Blokdan ma'lumotlarni ajratib olish (Regex)
        inn = re.search(r"(?:INN|STIR):\s*(\d+)", text, re.I)
        xr = re.search(r"(?:H/R|XR):\s*(\d+)", text, re.I)
        mfo = re.search(r"MFO:\s*(\d+)", text, re.I)
        dir_name = re.search(r"Direktor:\s*([^\n]+)", text, re.I)
        manzil = re.search(r"Manzil:\s*([^\n]+)", text, re.I)
        nomi = re.search(r"(?:Korxona|Nomi):\s*([^\n]+)", text, re.I) or re.search(r"“([^”]+)”", text)

        await state.update_data(
            mijoz=nomi.group(1).strip() if nomi else text.split('\n')[0],
            stir=inn.group(1) if inn else "-",
            xr=xr.group(1) if xr else "-",
            mfo=mfo.group(1) if mfo else "-",
            direktor=dir_name.group(1).strip() if dir_name else "-",
            manzil=manzil.group(1).strip() if manzil else "-"
        )
        await m.answer("✅ Rekvizitlar qabul qilindi. Endi tovar belgisi nomini kiriting:")
        await state.set_state(ContractForm.tovar_nomi)
    else:
        await state.update_data(mijoz=text)
        await m.answer("📍 Yashash manzilingizni kiriting:")
        await state.set_state(ContractForm.manzil)

# Qolgan savollar (Brend, Raqam, Sana, Summa...)
@dp.message(ContractForm.tovar_nomi)
async def p_tovar(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text); await m.answer("1. Shartnoma raqami:"); await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.manzil)
async def p_manzil_jis(m: Message, state: FSMContext):
    await state.update_data(manzil=m.text); await m.answer("Pasport seriya va raqami:"); await state.set_state(ContractForm.stir)

@dp.message(ContractForm.raqam)
async def p1(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text); await m.answer("2. Sana:"); await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p2(m: Message, state: FSMContext):
    await state.update_data(sana=m.text); await m.answer("Summa (faqat raqamda):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p9(m: Message, state: FSMContext):
    await state.update_data(summa=m.text); await m.answer("Summa (so'z bilan):"); await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def p10(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text); await m.answer("Tovar sinfi:"); await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def final(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text)
    data = await state.get_data()
    pref = "yu" if "Yuridik" in data['shaxs_turi'] else "jis"
    suf = "tezkor" if "1 oylik" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon = f"{pref}_{suf}.docx"
    try:
        doc = DocxTemplate(shablon); doc.render(data)
        path = f"S_{data['raqam'].replace('/', '_')}.docx"
        doc.save(path); await m.answer_document(FSInputFile(path), caption="✅ Tayyor!"); os.remove(path)
    except: await m.answer(f"❌ Fayl xatosi: {shablon} topilmadi.")
    await state.clear()

async def handle(r): return web.Response(text="Live")
async def main():
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start(); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
