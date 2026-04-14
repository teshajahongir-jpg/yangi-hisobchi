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
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏢 Yuridik shaxs"), KeyboardButton(text="👤 Jismoniy shaxs")]
    ], resize_keyboard=True)
    await m.answer("Salom! Shartnoma turini tanlang:", reply_markup=kb)

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
    
    # Ma'lumotlarni topish uchun kuchaytirilgan qidiruv tizimi
    def extract(patterns, text):
        for p in patterns:
            match = re.search(p, text, re.I | re.M)
            if match:
                return match.group(1).strip()
        return "-"

    # INN/STIR uchun qidiruv (oxiridagi X harfini ham hisobga oladi)
    stir = extract([r"(?:INN|STIR|ИНН|Pasport|JSHSHIR)[:\s]+([\w\d\s]+)"], text)
    # Hisob raqami (X/P yoki X/R yoki Hisob)
    xr = extract([r"(?:H/R|XR|Х/Р|X/P|Hisob|X/P)[:\s]+([\d\s]{15,30})"], text)
    # MFO
    mfo = extract([r"(?:MFO|МФО)[:\s]+([\d\s]{5,7})"], text)
    # Direktor
    direktor = extract([r"(?:Direktor|Директор|F\.I\.SH)[:\s]+([^\n]+)"], text)
    # Manzil
    manzil = extract([r"(?:Manzil|Манзил)[:\s]+([^\n]+)"], text)
    # Korxona nomi (Birinchi qator yoki "Korxona" so'zi bilan)
    mijoz = text.split('\n')[0].replace("Korxona:", "").replace("“", "").replace("”", "").strip()

    await state.update_data(
        mijoz=mijoz,
        stir=re.sub(r"[^\w\d]", "", stir), # Faqat harf va raqamlarni qoldiradi
        xr=re.sub(r"\s+", "", xr),
        mfo=re.sub(r"\s+", "", mfo),
        direktor=direktor,
        manzil=manzil
    )
    
    await m.answer("✅ Rekvizitlar tahlil qilindi.\n\nEndi: **Shartnoma raqamini** yuboring:")
    await state.set_state(ContractForm.raqam)

# --- QOLGAN BOSQIChLAR ---
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
    await state.update_data(sinf=m.text); await m.answer("11. Summa (faqat raqam):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p_summa(m: Message, state: FSMContext):
    val = m.text.replace(" ", "")
    try:
        formatted = "{:,}".format(int(val)).replace(",", " ")
        await state.update_data(summa=formatted)
    except:
        await state.update_data(summa=m.text)
    await m.answer("12. Summa so'z bilan:"); await state.set_state(ContractForm.summa_soz)

@dp.message(ContractForm.summa_soz)
async def final_render(m: Message, state: FSMContext):
    await state.update_data(summa_soz=m.text)
    data = await state.get_data()
    pref = "yu" if "Yuridik" in data['shaxs_turi'] else "jis"
    suf = "tezkor" if "tezkor" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon = f"{pref}_{suf}.docx"
    try:
        doc = DocxTemplate(shablon); doc.render(data)
        file_name = f"Amaan mijozlar bilan shartnoma №{data['raqam']}.docx"
        doc.save(file_name)
        await m.answer_document(FSInputFile(file_name), caption="✅ Shartnoma tayyor!")
        os.remove(file_name)
    except Exception as e:
        await m.answer("❌ Xato: Shablon fayli topilmadi!")
    await state.clear()

async def handle(r): return web.Response(text="Bot Live")
async def main():
    app = web.Application(); app.router.add_get("/", handle)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start(); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
