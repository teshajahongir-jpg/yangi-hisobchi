import os, asyncio, re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

TOKEN = "8701217643:AAG0vyPcyQaCDqw8nhEcM3OrnpLgCHE3YZk"
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ContractForm(StatesGroup):
    shaxs_turi = State()
    xizmat_turi = State()
    rekvizitlar = State()
    raqam = State()
    sana = State()
    tovar_nomi = State()
    sinf = State()
    summa = State()
    summa_soz = State()

@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏢 Yuridik shaxs"), KeyboardButton(text="👤 Jismoniy shaxs")]
    ], resize_keyboard=True)
    await m.answer("Shartnoma turini tanlang:", reply_markup=kb)

@dp.message(F.text.in_(["🏢 Yuridik shaxs", "👤 Jismoniy shaxs"]))
async def select_shaxs(m: Message, state: FSMContext):
    await state.update_data(shaxs_turi=m.text)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1 oylik tezkor"), KeyboardButton(text="📅 7 oylik")],
        [KeyboardButton(text="🔍 Expert tekshiruv")]
    ], resize_keyboard=True)
    await m.answer("Xizmat turini tanlang:", reply_markup=kb)
    await state.set_state(ContractForm.xizmat_turi)

@dp.message(ContractForm.xizmat_turi)
async def ask_rekvizitlar(m: Message, state: FSMContext):
    await state.update_data(xizmat_turi=m.text)
    await m.answer("📝 Rekvizitlar jadvalini tashlang (MChJ, Manzil, INN, X/P, MFO, Direktor):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.rekvizitlar)

@dp.message(ContractForm.rekvizitlar)
async def process_rekvizitlar(m: Message, state: FSMContext):
    text = m.text
    # Ma'lumotlarni qidirish (Regex kuchaytirildi)
    inn_m = re.search(r"(?:INN|STIR|ИНН|Pasport|JSHSHIR):\s*([\d\s\w-]+)", text, re.I)
    xr_m = re.search(r"(?:H/R|XR|Х/Р|X/P|Hisob|X/P):\s*([\d\s]{20,30})", text, re.I)
    mfo_m = re.search(r"(?:MFO|МФО):\s*([\d\s]{5,7})", text, re.I)
    dir_m = re.search(r"(?:Direktor|Директор|F\.I\.SH):\s*([^\n]+)", text, re.I)
    manzil_m = re.search(r"(?:Manzil|Манзил):\s*([^\n]+)", text, re.I)
    
    # Korxona nomini birinchi qatordan tozalab olish
    mijoz_nomi = text.split('\n')[0].replace("Korxona:", "").replace("“", "").replace("”", "").replace('"', "").strip()

    await state.update_data(
        mijoz=mijoz_nomi,
        stir=re.sub(r"\s+", "", inn_m.group(1)) if inn_m else "-",
        xr=re.sub(r"\s+", "", xr_m.group(1))[:20] if xr_m else "-",
        mfo=re.sub(r"\s+", "", mfo_m.group(1)) if mfo_m else "-",
        direktor=dir_m.group(1).strip() if dir_m else "-",
        manzil=manzil_m.group(1).strip() if manzil_m else "-"
    )
    
    await m.answer("✅ Rekvizitlar olindi.\n\n7. Shartnoma raqami:")
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p_raqam(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text); await m.answer("8. Sana:"); await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p_sana(m: Message, state: FSMContext):
    await state.update_data(sana=m.text); await m.answer("9. Brend nomi:"); await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p_tovar(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text); await m.answer("10. Tovar sinfi:"); await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p_sinf(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text); await m.answer("11. Summa (faqat raqamda):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p_summa(m: Message, state: FSMContext):
    raw_val = m.text.replace(" ", "")
    try:
        # Summani orasini ochib yozish (2 000 000)
        formatted = "{:,}".format(int(raw_val)).replace(",", " ")
        await state.update_data(summa=formatted)
    except:
        await state.update_data(summa=m.text)
    await m.answer("12. Summa so'z bilan:"); await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def final_render(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text)
    data = await state.get_data()
    
    pref = "yu" if "Yuridik" in data['shaxs_turi'] else "jis"
    suf = "tezkor" if "1 oylik" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon = f"{pref}_{suf}.docx"

    try:
        doc = DocxTemplate(shablon)
        # Jismoniy shaxsda direktor bo'lmasa, uni bo'sh qoldirish yoki minus qo'yish
        if "Jismoniy" in data['shaxs_turi'] and data['direktor'] == "-":
            data['direktor'] = " " # Shartnomada ko'rinmasligi uchun
            
        doc.render(data)
        # Fayl nomi: Amaan mijozlar bilan shartnoma №...
        file_name = f"Amaan mijozlar bilan shartnoma №{data['raqam'].replace('/', '_')}.docx"
        doc.save(file_name)
        
        await m.answer_document(FSInputFile(file_name), caption="✅ Marhamat, shartnoma tayyor!")
        os.remove(file_name)
    except Exception as e:
        await m.answer(f"❌ Xato: Word shablonlari topilmadi. GitHub'ga yuklaganingizni tekshiring.")
    await state.clear()

async def handle(r): return web.Response(text="Bot Live")
async def main():
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start(); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
