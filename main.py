import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from docxtpl import DocxTemplate

# Loglarni sozlash
logging.basicConfig(level=logging.INFO)

# TOKKENNI SHU YERGA ANIQ QILIB YOZDIK
TOKEN = "8701217643:AAGAWkuIzgenm0bzoucyokC8C7mgqIPa7g8"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Savollar ketma-ketligi
class ContractForm(StatesGroup):
    raqam = State()
    sana = State()
    mijoz = State()
    stir = State()
    summa = State()
    sinf = State()

@dp.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await message.answer("Xush kelibsiz, Jahongir aka!\n1. Shartnoma raqamini yozing (masalan: 55/26):")
    await state.set_state(ContractForm.raqam)

@dp.message(ContractForm.raqam)
async def process_raqam(message: Message, state: FSMContext):
    await state.update_data(raqam=message.text)
    await message.answer("2. Sanani kiriting (masalan: 2026 йил 11 апрел):")
    await state.set_state(ContractForm.sana)

@dp.message(ContractForm.sana)
async def process_sana(message: Message, state: FSMContext):
    await state.update_data(sana=message.text)
    await message.answer("3. Mijoz nomi (masalan: \"WELL ROAST\" OK):")
    await state.set_state(ContractForm.mijoz)

@dp.message(ContractForm.mijoz)
async def process_mijoz(message: Message, state: FSMContext):
    await state.update_data(mijoz=message.text)
    await message.answer("4. Mijoz STIR (INN) raqami:")
    await state.set_state(ContractForm.stir)

@dp.message(ContractForm.stir)
async def process_stir(message: Message, state: FSMContext):
    await state.update_data(stir=message.text)
    await message.answer("5. Xizmat summasini kiriting (masalan: 7 272 000):")
    await state.set_state(ContractForm.summa)

@dp.message(ContractForm.summa)
async def process_summa(message: Message, state: FSMContext):
    await state.update_data(summa=message.text)
    await message.answer("6. Xizmat sinfini yozing (masalan: 35, 41):")
    await state.set_state(ContractForm.sinf)

@dp.message(ContractForm.sinf)
async def process_finish(message: Message, state: FSMContext):
    await state.update_data(sinf=message.text)
    user_data = await state.get_data()
    
    await message.answer("Fayl tayyorlanmoqda...")
    
    try:
        # Fayl nomi 'shablon.docx' bo'lishi shart
        doc = DocxTemplate("shablon.docx")
        doc.render(user_data)
        
        output_name = f"Shartnoma_{user_data['raqam'].replace('/', '_')}.docx"
        doc.save(output_name)
        
        document = FSInputFile(output_name)
        await message.answer_document(document, caption="Tayyor!")
        
        os.remove(output_name)
    except Exception as e:
        await message.answer(f"Xatolik: {e}\nEslatma: GitHub-da 'shablon.docx' borligini tekshiring.")
    
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
