import os
import sqlite3
import pytz
import asyncio
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
 
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738
 
ISHXONA_LAT = 39.745430
ISHXONA_LON = 64.439307
MAKS_MASOFA = 150
 
XODIMLAR_BAZASI = {
    "Sevinch":      {"oylik": 4000000, "minut_narxi": 14743.59, "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Charos":       {"oylik": 6000000, "minut_narxi": 3846.15,  "soat_narxi": 201923.08, "kun_narxi": 0.0},
    "Ozodbek":      {"oylik": 6000000, "minut_narxi": 49038.46, "soat_narxi": 28846.15,  "kun_narxi": 0.0},
    "Xudoyorxon":   {"oylik": 5200000, "minut_narxi": 75000.0,  "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Ruxshona":     {"oylik": 5200000, "minut_narxi": 3333.33,  "soat_narxi": 50000.0,   "kun_narxi": 200000.0},
    "Ferangiz":     {"oylik": 3000000, "minut_narxi": 1923.08,  "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Jahongir":     {"oylik": 1200000, "minut_narxi": 0.0,      "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Muqaddas opa": {"oylik": 2200000, "minut_narxi": 0.0,      "soat_narxi": 0.0,       "kun_narxi": 0.0},
    "Avazbek":      {"oylik": 2000000, "minut_narxi": 801.28,   "soat_narxi": 0.0,       "kun_narxi": 0.0}
}
 
# ✅ TUZATISH: Har bir xodim uchun keyingi lokatsiya maqsadini saqlaymiz
# "boshlash", "yakunlash", "overtime" - qaysi tugma bosilganini eslab qolamiz
lokatsiya_holati: dict[int, str] = {}
 
def init_db():
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS xodimlar (
            tg_id INTEGER PRIMARY KEY,
            ism TEXT,
            came INTEGER DEFAULT 0,
            obedda INTEGER DEFAULT 0,
            bugun_keldi INTEGER DEFAULT 0,
            overtime_active INTEGER DEFAULT 0,
            start_time TEXT,
            obed_start TEXT,
            overtime_start TEXT,
            jami_minut INTEGER DEFAULT 0,
            jami_soat INTEGER DEFAULT 0,
            kelmagan_kunlar INTEGER DEFAULT 0,
            obed_minutlari INTEGER DEFAULT 0,
            bugungi_tarix TEXT DEFAULT 'Hali ma''lumot yo''q'
        )
    """)
    try:
        cursor.execute("ALTER TABLE xodimlar ADD COLUMN bugungi_tarix TEXT DEFAULT 'Hali ma''lumot yo''q'")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()
 
init_db()
 
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
UZ_TZ = pytz.timezone('Asia/Tashkent')
scheduler = AsyncIOScheduler(timezone=UZ_TZ)
 
class BotStates(StatesGroup):
    ism_kutish = State()
 
def masofani_hisobla(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371000
 
def get_xodim(tg_id):
    conn = sqlite3.connect("davomat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM xodimlar WHERE tg_id = ?", (tg_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
 
def update_xodim(tg_id, **kwargs):
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    set_query = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [tg_id]
    cursor.execute(f"UPDATE xodimlar SET {set_query} WHERE tg_id = ?", values)
    conn.commit()
    conn.close()
 
def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash", request_location=True)],
        [KeyboardButton(text="🥪 Obedga chiqish"), KeyboardButton(text="🔙 Obeddan qaytish")],
        [KeyboardButton(text="⏰ Qo'shimcha ishlash boshlash")],
        [KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)],
        [KeyboardButton(text="📊 Mening shaxsiy hisobotim 💰")]
    ], resize_keyboard=True)
 
def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Hamma xodimlar hisoboti (Buxgalteriya)")],
        [KeyboardButton(text="💰 Buxgalter hamma summani tashlab berdi")]
    ], resize_keyboard=True)
 
async def kunlik_tekshiruv():
    conn = sqlite3.connect("davomat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM xodimlar")
    rows = cursor.fetchall()
    for row in rows:
        if row['tg_id'] != ADMIN_ID:
            if not row['bugun_keldi']:
                yangi_kelmagan = row['kelmagan_kunlar'] + 1
                cursor.execute("""
                    UPDATE xodimlar
                    SET kelmagan_kunlar = ?, bugungi_tarix = '❌ Bugun ishga kelmadi (Jarima 8 soat)'
                    WHERE tg_id = ?
                """, (yangi_kelmagan, row['tg_id']))
                try:
                    await bot.send_message(row['tg_id'], "⚠️ Kunlik hisobot: Bugun ishga kelganingiz qayd etilmadi. Oyligingizdan 1 kunlik ish haqi chegirildi.")
                except:
                    pass
    cursor.execute("UPDATE xodimlar SET came = 0, obedda = 0, overtime_active = 0, bugun_keldi = 0")
    conn.commit()
    conn.close()
 
async def kunlik_eslatma():
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id FROM xodimlar")
    ids = cursor.fetchall()
    conn.close()
    for row in ids:
        if row[0] != ADMIN_ID:
            try:
                await bot.send_message(row[0], "⏰ Ish vaqti tugadi! Ishni yakunlash tugmasini bosing.", reply_markup=xodim_klaviatura())
            except:
                pass
 
@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    await state.clear()
    if user_id == ADMIN_ID:
        await m.answer("👑 Xush kelibsiz! Boshqaruv paneli.", reply_markup=admin_klaviatura())
        return
    xodim = get_xodim(user_id)
    if xodim:
        await m.answer(f"✨ Xush kelibsiz, {xodim['ism']}!", reply_markup=xodim_klaviatura())
    else:
        await m.answer("📌 Ro'yxatdagi ismingizni kiriting (Masalan: Sevinch, Charos):")
        await state.set_state(BotStates.ism_kutish)
 
@dp.message(BotStates.ism_kutish)
async def process_name(m: Message, state: FSMContext):
    xodim_ismi = m.text.strip()
    user_id = m.from_user.id
    if xodim_ismi.startswith("/"): return
    topilgan_ism = None
    for k in XODIMLAR_BAZASI.keys():
        if k.lower() == xodim_ismi.lower():
            topilgan_ism = k
            break
    if not topilgan_ism:
        ismlar_listi = ", ".join(XODIMLAR_BAZASI.keys())
        await m.answer(f"❌ Ism topilmadi! Quyidagilardan birini kiriting:\n{ismlar_listi}")
        return
    await state.clear()
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO xodimlar (tg_id, ism, jami_minut, jami_soat, kelmagan_kunlar, obed_minutlari, bugungi_tarix)
        VALUES (?, ?, 0, 0, 0, 0, 'Hali ma''lumot yo''q')
    """, (user_id, topilgan_ism))
    conn.commit()
    conn.close()
    await m.answer(f"✅ Rahmat, {topilgan_ism}! Tizimga ulandingiz.", reply_markup=xodim_klaviatura())
 
@dp.message(F.text == "📊 Mening shaxsiy hisobotim 💰")
async def shaxsiy_hisobot(m: Message):
    xodim = get_xodim(m.from_user.id)
    if not xodim:
        await m.answer("Siz ro'yxatdan o'tmagansiz.")
        return
    ism = xodim['ism']
    st = XODIMLAR_BAZASI[ism]
    vaz = xodim['jami_minut'] * st['minut_narxi']
    k_narx = st['kun_narxi'] if st['kun_narxi'] > 0 else (st['oylik'] / 26)
    kel_jar = xodim['kelmagan_kunlar'] * k_narx
    yakuniy = st['oylik'] - vaz - kel_jar + (xodim['jami_soat'] * st['soat_narxi'])
    hisobot = (
        f"👤 Xodim: {ism}\n"
        f"💰 Asosiy oylik: {st['oylik']:,.0f} so'm\n"
        f"───────────────────\n"
        f"⏱ Jami kechikish: {xodim['jami_minut']} minut\n"
        f"⏰ Qo'shimcha soat: {xodim['jami_soat']} soat\n"
        f"❌ Kelmagan kunlar: {xodim['kelmagan_kunlar']} kun\n"
        f"───────────────────\n"
        f"📅 Bugungi holat:\n{xodim['bugungi_tarix']}\n"
        f"───────────────────\n"
        f"💵 Toza oylik (Qo'lga): {max(0, yakuniy):,.0f} so'm"
    )
    await m.answer(hisobot)
 
@dp.message(F.text == "🥪 Obedga chiqish")
async def obed_boshlash(m: Message):
    xodim = get_xodim(m.from_user.id)
    if not xodim or not xodim['came']:
        await m.answer("❌ Avval ishni boshlang.")
        return
    if xodim['obedda']:
        await m.answer("❌ Siz allaqachon obeddasiz.")
        return
    hozir = datetime.now(UZ_TZ)
    tarix = xodim['bugungi_tarix'] + f"\n🥪 Obedga chiqdi: {hozir.strftime('%H:%M')}"
    update_xodim(m.from_user.id, obedda=1, obed_start=hozir.isoformat(), bugungi_tarix=tarix)
    await m.answer("🥪 Obed vaqtingiz boshlandi. Yoqimli ishtaha!")
 
@dp.message(F.text == "🔙 Obeddan qaytish")
async def obed_tugatish(m: Message):
    xodim = get_xodim(m.from_user.id)
    if not xodim or not xodim['obedda']:
        await m.answer("❌ Siz obedda emassiz.")
        return
    hozir = datetime.now(UZ_TZ)
    obed_start = datetime.fromisoformat(xodim['obed_start'])
    obed_minut = max(1, int((hozir - obed_start).total_seconds() // 60))
    yangi_obed = xodim['obed_minutlari'] + obed_minut
    tarix = xodim['bugungi_tarix'] + f"\n🔙 Obeddan qaytdi: {hozir.strftime('%H:%M')} ({obed_minut} min)"
    update_xodim(m.from_user.id, obedda=0, obed_minutlari=yangi_obed, bugungi_tarix=tarix)
    await m.answer(f"🔙 Obeddan qaytdingiz. Davomiyligi: {obed_minut} minut.")
 
# ✅ TUZATISH: Overtime tugmasi endi lokatsiyasiz, faqat tasdiqlash so'raydi
@dp.message(F.text == "⏰ Qo'shimcha ishlash boshlash")
async def overtime_boshlash(m: Message):
    xodim = get_xodim(m.from_user.id)
    if not xodim or not xodim['came']:
        await m.answer("❌ Avval ishni boshlang.")
        return
    if xodim['overtime_active']:
        await m.answer("❌ Qo'shimcha ishlash allaqachon faol.")
        return
    hozir = datetime.now(UZ_TZ)
    tarix = xodim['bugungi_tarix'] + f"\n⏰ Overtime boshladi: {hozir.strftime('%H:%M')}"
    update_xodim(m.from_user.id, overtime_active=1, overtime_start=hozir.isoformat(), bugungi_tarix=tarix)
    await m.answer(f"⏰ Qo'shimcha ishlash boshlandi: {hozir.strftime('%H:%M')}")
 
# ✅ TUZATISH: Lokatsiya handler faqat 2 holat: boshlash yoki yakunlash
# Qaysi tugma bosilganini "request_location" orqali bilamiz: 
# "🟢 Ishni boshlash" => came=0 bo'lsa boshlash
# "🔴 Ishni yakunlash" => came=1 bo'lsa yakunlash
@dp.message(F.location)
async def handle_location(m: Message):
    user_id = m.from_user.id
    xodim = get_xodim(user_id)
    if not xodim:
        await m.answer("Siz ro'yxatdan o'tmagansiz. /start bosing.")
        return
 
    masofa = masofani_hisobla(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    if masofa > MAKS_MASOFA:
        await m.answer(f"❌ Ishxonada emassiz! Masofa: {int(masofa)} m. (Ruxsat: {MAKS_MASOFA} m)")
        return
 
    hozir = datetime.now(UZ_TZ)
 
    # Agar xodim hali kelmagan bo'lsa => ISHNI BOSHLASH
    if not xodim['came']:
        kechikish = 0
        if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
            kechikish = (hozir.hour - 9) * 60 + hozir.minute
 
        yangi_minut = xodim['jami_minut'] + kechikish
        tarix = f"🟢 Ishga keldi: {hozir.strftime('%H:%M')}"
        if kechikish > 0:
            tarix += f" (Kechikish: {kechikish} min)"
 
        update_xodim(user_id, came=1, bugun_keldi=1, start_time=hozir.isoformat(),
                     jami_minut=yangi_minut, bugungi_tarix=tarix)
 
        msg = f"✅ Ish boshlandi: {hozir.strftime('%H:%M')}"
        if kechikish > 0:
            msg += f"\n⚠️ Kechikish: {kechikish} minut"
        await m.answer(msg, reply_markup=xodim_klaviatura())
 
    # Agar xodim kelgan bo'lsa => ISHNI YAKUNLASH
    else:
        start_vaqt = datetime.fromisoformat(xodim['start_time'])
        overtime_minut = 0
 
        if xodim['overtime_active'] and xodim['overtime_start']:
            o_start = datetime.fromisoformat(xodim['overtime_start'])
            overtime_minut = int((hozir - o_start).total_seconds() // 60)
 
        farq_soniya = (hozir - start_vaqt).total_seconds() - (xodim['obed_minutlari'] * 60)
        ishlangan_soat = max(1, int(farq_soniya // 3600))
 
        # Overtime soatlarni qo'shamiz, kechikishdan ayirmaymiz (overtime alohida hisob)
        yangi_soat = xodim['jami_soat'] + (overtime_minut // 60)
 
        tarix = xodim['bugungi_tarix'] + f"\n🔴 Yakunladi: {hozir.strftime('%H:%M')} ({ishlangan_soat} soat)"
 
        update_xodim(user_id, came=0, overtime_active=0, jami_soat=yangi_soat,
                     obed_minutlari=0, bugungi_tarix=tarix)
 
        msg = f"🔴 Ish yakunlandi: {hozir.strftime('%H:%M')}\n✅ Bugun {ishlangan_soat} soat ishladingiz."
        if overtime_minut > 0:
            msg += f"\n⏰ Qo'shimcha: {overtime_minut} minut ({overtime_minut // 60} soat {overtime_minut % 60} min)"
        await m.answer(msg, reply_markup=xodim_klaviatura())
 
@dp.message(F.text == "📊 Hamma xodimlar hisoboti (Buxgalteriya)")
async def text_report(m: Message):
    if m.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect("davomat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM xodimlar")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        await m.answer("Baza bo'sh.")
        return
    matn = "📊 UMUMIY BUXGALTERIYA HISOBOTI\n\n"
    for r in rows:
        ism = r['ism']
        if ism not in XODIMLAR_BAZASI: continue
        st = XODIMLAR_BAZASI[ism]
        vaz = r['jami_minut'] * st['minut_narxi']
        k_narx = st['kun_narxi'] if st['kun_narxi'] > 0 else (st['oylik'] / 26)
        kel_jar = r['kelmagan_kunlar'] * k_narx
        yakuniy = st['oylik'] - vaz - kel_jar + (r['jami_soat'] * st['soat_narxi'])
        matn += (f"👤 {ism}:\n"
                 f"⏱ Kechikish: {r['jami_minut']} min | ❌ Kelmagan: {r['kelmagan_kunlar']} kun\n"
                 f"💰 Oylik (Qo'lga): {max(0, yakuniy):,.0f} so'm\n\n")
    await m.answer(matn)
 
@dp.message(F.text == "💰 Buxgalter hamma summani tashlab berdi")
async def clear_balances(m: Message):
    if m.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE xodimlar SET jami_minut=0, jami_soat=0, kelmagan_kunlar=0, came=0, obedda=0, bugungi_tarix='Hali ma''lumot yo''q'")
    conn.commit()
    conn.close()
    await m.answer("✅ Barcha xodimlarning hisob-kitoblari yangilandi.")
 
async def handle_dashboard(request):
    conn = sqlite3.connect("davomat.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM xodimlar")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
 
    barchasi = len(rows)
    ishda = sum(1 for r in rows if r['came'] == 1)
    ishda_emas = sum(1 for r in rows if r['bugun_keldi'] == 0)
    kechikkanlar = sum(1 for r in rows if r['jami_minut'] > 0 and r['bugun_keldi'] == 1)
 
    table_rows = ""
    for r in rows:
        ism = r['ism']
        st = XODIMLAR_BAZASI.get(ism, {"oylik": 0, "minut_narxi": 0, "soat_narxi": 0, "kun_narxi": 0})
        vazvirat = r['jami_minut'] * st['minut_narxi']
        k_narx = st.get('kun_narxi', 0) if st.get('kun_narxi', 0) > 0 else (st['oylik'] / 26)
        kel_jar = r['kelmagan_kunlar'] * k_narx
        yakuniy = st['oylik'] - vazvirat - kel_jar + (r['jami_soat'] * st['soat_narxi'])
        status_badge = '<span style="background:#e8f5e9;color:#2e7d32;padding:6px 12px;border-radius:20px;font-size:12px;font-weight:600;">Ishda</span>' if r['came'] else '<span style="background:#ffebee;color:#c62828;padding:6px 12px;border-radius:20px;font-size:12px;font-weight:600;">Ishda emas</span>'
        tarix_html = r['bugungi_tarix'].replace('\n', '<br>')
        table_rows += f"""
        <tr style="border-bottom: 1px solid #f1f3f9;">
            <td style="padding:16px 20px;font-weight:600;color:#2c3e50;">{ism}</td>
            <td style="padding:16px 20px;">{status_badge}</td>
            <td style="padding:16px 20px;font-size:13px;color:#555;line-height:1.4;">{tarix_html}</td>
            <td style="padding:16px 20px;color:#e74c3c;font-weight:600;">{r['jami_minut']} min</td>
            <td style="padding:16px 20px;color:#2ecc71;font-weight:600;">{r['jami_soat']} soat</td>
            <td style="padding:16px 20px;color:#e67e22;font-weight:600;">{r['kelmagan_kunlar']} kun</td>
            <td style="padding:16px 20px;font-weight:700;color:#2c3e50;font-size:15px;">{max(0, yakuniy):,.0f} UZS</td>
        </tr>"""
 
    html_content = f"""<!DOCTYPE html>
    <html lang="uz"><head><meta charset="UTF-8">
    <title>TIMEPAY - Boshqaruv paneli</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}}
        body{{background:#f4f6f9;padding:30px;color:#333;}}
        .header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:35px;}}
        .title{{font-size:26px;font-weight:700;color:#2c3e50;}}
        .stats-container{{display:grid;grid-template-columns:repeat(4,1fr);gap:22px;margin-bottom:35px;}}
        .card{{background:white;padding:25px;border-radius:16px;box-shadow:0 4px 12px rgba(0,0,0,0.03);display:flex;justify-content:space-between;align-items:center;border:1px solid #eef2f5;}}
        .card-title{{font-size:13px;color:#8a99a8;font-weight:600;text-transform:uppercase;}}
        .card-value{{font-size:32px;font-weight:700;color:#2c3e50;margin-top:6px;}}
        .card-icon{{width:52px;height:52px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;}}
        .table-container{{background:white;border-radius:18px;box-shadow:0 4px 12px rgba(0,0,0,0.03);padding:25px;border:1px solid #eef2f5;}}
        .table-title{{font-size:19px;font-weight:700;margin-bottom:22px;color:#2c3e50;}}
        table{{width:100%;border-collapse:collapse;text-align:left;}}
        th{{padding:16px 20px;color:#8a99a8;font-weight:600;font-size:12px;text-transform:uppercase;border-bottom:2px solid #eef2f5;}}
        tr:hover{{background-color:#f8fafc;}}
    </style></head><body>
    <div class="header">
        <div class="title">Boshqaruv paneli <span style="font-size:15px;color:#95a5a6;font-weight:normal;margin-left:10px;">/ Sherin Bakery</span></div>
        <div style="background:white;padding:12px 24px;border-radius:12px;font-weight:600;color:#2c3e50;border:1px solid #eef2f5;">
            <i class="fa-regular fa-calendar-days" style="margin-right:8px;color:#3498db;"></i>
            {datetime.now(UZ_TZ).strftime('%d.%m.%Y %H:%M')}
        </div>
    </div>
    <div class="stats-container">
        <div class="card"><div><div class="card-title">Barchasi</div><div class="card-value">{barchasi}</div></div><div class="card-icon" style="background:#e8f5e9;color:#2e7d32;"><i class="fa-solid fa-users"></i></div></div>
        <div class="card"><div><div class="card-title">Ishda</div><div class="card-value">{ishda}</div></div><div class="card-icon" style="background:#e0f2f1;color:#004d40;"><i class="fa-solid fa-briefcase"></i></div></div>
        <div class="card"><div><div class="card-title">Kech</div><div class="card-value">{kechikkanlar}</div></div><div class="card-icon" style="background:#fff3e0;color:#e65100;"><i class="fa-solid fa-user-clock"></i></div></div>
        <div class="card"><div><div class="card-title">Ishda emas</div><div class="card-value">{ishda_emas}</div></div><div class="card-icon" style="background:#ffebee;color:#c62828;"><i class="fa-solid fa-user-slash"></i></div></div>
    </div>
    <div class="table-container">
        <div class="table-title">Bugungi Jonli Davomat Jadvali</div>
        <table><thead><tr>
            <th>Xodim</th><th>Holati</th><th>Xronologiya</th>
            <th>Kechikish</th><th>Qo'shimcha</th><th>Kelmagan</th><th>Oylik</th>
        </tr></thead><tbody>{table_rows}</tbody></table>
    </div>
    </body></html>"""
    return web.Response(text=html_content, content_type='text/html')
 
async def main():
    scheduler.add_job(kunlik_eslatma, 'cron', hour=17, minute=0)
    scheduler.add_job(kunlik_tekshiruv, 'cron', hour=20, minute=0)
    scheduler.start()
 
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling(bot))
 
    app = web.Application()
    app.router.add_get('/', handle_dashboard)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await asyncio.Event().wait()
 
if __name__ == "__main__":
    asyncio.run(main())
