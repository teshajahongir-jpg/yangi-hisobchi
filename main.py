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
    await m.answer("📝 Rekvizitlar jadvalini tashlang:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ContractForm.rekvizitlar)

@dp.message(ContractForm.rekvizitlar)
async def process_rekvizitlar(m: Message, state: FSMContext):
    text = m.text
    def extract(patterns, src):
        for p in patterns:
            res = re.search(p, src, re.I)
            if res: return res.group(1).strip()
        return "-"

    await state.update_data(
        mijoz=text.split('\n')[0].replace("Korxona:", "").replace("“", "").replace("”", "").strip(),
        stir=extract([r"(?:INN|STIR|ИНН|Pasport)[:\s]+([\w\d]+)"], text),
        xr=extract([r"(?:H/R|XR|X/P|Hisob)[:\s]+([\d\s]{15,30})"], text).replace(" ", ""),
        mfo=extract([r"(?:MFO|МФО)[:\s]+([\d\s]{5,7})"], text).replace(" ", ""),
        direktor=extract([r"(?:Direktor|Директор|F\.I\.SH)[:\s]+([^\n]+)"], text),
        manzil=extract([r"(?:Manzil|Манзил)[:\s]+([^\n]+)"], text)
    )
    await m.answer("✅ 7. Shartnoma raqami:")
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def p_r(m: Message, state: FSMContext):
    await state.update_data(raqam=m.text); await m.answer("8. Sana:"); await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def p_s(m: Message, state: FSMContext):
    await state.update_data(sana=m.text); await m.answer("9. Brend nomi:"); await state.set_state(ContractForm.tovar_nomi)

@dp.message(ContractForm.tovar_nomi)
async def p_t(m: Message, state: FSMContext):
    await state.update_data(tovar_nomi=m.text); await m.answer("10. Tovar sinfi:"); await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def p_si(m: Message, state: FSMContext):
    await state.update_data(sinf=m.text); await m.answer("11. Summa (faqat raqam):"); await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def p_su(m: Message, state: FSMContext):
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
    
    # SHABLON NOMINI ANIQLASh (Kichik harflarga o'tkazish orqali xatoni kamaytirish)
    shaxs = "yu" if "Yuridik" in data['shaxs_turi'] else "jis"
    xizmat = "tezkor" if "1 oylik" in data['xizmat_turi'] else "7oy" if "7 oylik" in data['xizmat_turi'] else "expert"
    shablon_nomi = f"{shaxs}_{xizmat}.docx"

    if not os.path.exists(shablon_nomi):
        await m.answer(f"⚠️ Xato: '{shablon_nomi}' nomli fayl GitHub'da topilmadi! Iltimos, shablonlaringiz nomini tekshiring.")
        return

    try:
        doc = DocxTemplate(shablon_nomi)
        doc.render(data)
        out_path = f"Amaan_shartnoma_{data['raqam'].replace('/', '_')}.docx"
