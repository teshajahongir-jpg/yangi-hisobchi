import os, asyncio, re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate
from aiohttp import web

TOKEN = "8701217643:AAGS5Sa0zybv_lASF4IcNg3_i7nQbxGMoy0"
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
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏢 Yuridik shaxs"), KeyboardButton(text="👤 Jismoniy shaxs")]
    ], resize_keyboard=True)
    await m.answer("Assalomu alaykum! Shartnoma turini tanlang:", reply_markup=kb)

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
    await m.answer("📝 Rekvizitlar jadvalini tashlang:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.rekvizitlar)

@dp.message(ContractForm.rekvizitlar)
async def process_rekvizitlar(m: Message, state: FSMContext):
    t = m.text
    
    # Ma'lumotlarni aqlli qidirish funksiyasi
    def find_data(keywords, text):
        for k in keywords:
            # Ikkita nuqta bilan yoki nuqtasiz probeldan keyingi qismni oladi
            pattern = fr"{k}[:\s]+([\w\d\s\-\/]+)"
            match = re.search(pattern, text, re.I)
            if match:
                res = match.group(1).strip().split('\n')[0]
                return res
        return "-"

    lines = t.split('\n')
    # Korxona nomi birinchi qatorda bo'ladi
    mijoz_nomi = lines[0].replace("Korxona:", "").replace("“", "").replace("”", "").replace("\"", "").strip()
    
    # Rekvizitlarni ajratib olish
    stir = find_data(["INN", "STIR", "ИНН", "Pasport", "ПАСПОРТ"], t)
    # Hisob raqam uchun barcha variantlar (X/P, H/R, Hisob)
    xr = find_data(["X/P", "H/R", "XR", "Hisob", "Ҳ/Р", "Х/Р"], t).replace(" ", "")
    mfo = find_data(["MFO", "МФО"], t).replace(" ", "")
    manzil = find_data(["Manzil", "Манзил", "Адрес"], t)
    direktor = find_data(["Direktor", "Директор", "F.I.SH", "Раҳбар"], t)

    await state.update_data(
        mijoz=mijoz_nomi,
        stir=stir,
        xr=xr,
        mfo=mfo,
        manzil=manzil,
        direktor=direktor
    )
    
    await m.answer(f"✅ Ma'lumotlar olindi:\n🏢 {mijoz_nomi}\n🔢 STIR: {stir}\n💰 H/R: {xr}\n\n7. Shartnoma raqami:")
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
    val = m.text.replace(" ", "")
    formatted = "{:,}".format(int(val)).replace(",", " ") if val.isdigit() else m.text
    await state.update_data(summa=formatted)
    await m.answer("12. Summa so'z bilan:"); await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def final_render(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text)
    data = await state.get_data()
    
    shaxs = "yu" if "Yuridik" in data['shaxs_turi'] else "jis"
    xizmat = "tezkor" if "1 oylik" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon_nomi = f"{shaxs}_{xizmat}.docx"

    try:
        if os.path.exists(shablon_nomi):
            doc = DocxTemplate(shablon_nomi)
            doc.render(data)
            out = "Amaan mijozlar bilan shartnoma.docx"
            doc.save(out)
            await m.answer_document(FSInputFile(out), caption="✅ Tayyor!")
            os.remove(out)
        else:
            await m.answer(f"❌ {shablon_nomi} topilmadi.")
    except Exception as e:
        await m.answer(f"⚠️ Word shablonda xato: {str(e)}")
    
    await state.clear()

async def handle(r): return web.Response(text="Bot Live")
async def main():
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start(); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
