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

# 🚨 ASOSIY TIZIM SOZLAMALARI
BOT_TOKEN = "8701217643:AAF4ft6b-OJZHe7_N1-RkIS7qKXbimi39mk"
ADMIN_ID = 8252424738

# 📍 LOKATSIYA VA MASOFA
ISHXONA_LAT = 39.745430   
ISHXONA_LON = 64.439307   
MAKS_MASOFA = 150         

# 💰 STAVKALAR BAZASI (Oylikdan ayirish mantiqi uchun)
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

# 🗄 SQLITE MA'LUMOTLAR BAZASINI SOZLACH
def init_db():
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    # Xodimlar holati jadvali
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
            obed_minutlari INTEGER DEFAULT 0
        )
    """)
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

# Baza bilan xavfsiz ishlash funksiyalari
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

# ⏰ HAR KUNI SOAT 20:00 DA ISHGA KELMAGANLARNI TEKSHIRISH (8 SOAT AYIRISH MALIKASI)
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
                cursor.execute("UPDATE xodimlar SET kelmagan_kunlar = ? WHERE tg_id = ?", (yangi_kelmagan, row['tg_id']))
                try:
                    await bot.send_message(row['tg_id'], "⚠️ **Ogohlantirish!** Bugun ishga kelganingiz qayd etilmadi. Oyligingizdan 1 kunlik (8 soat) ish haqi chegirildi.")
                except: pass
    
    cursor.execute("UPDATE xodimlar SET bugun_keldi = 0, came = 0, obedda = 0, overtime_active = 0")
    conn.commit()
    conn.close()
    await bot.send_message(ADMIN_ID, "📢 Kun yakunlandi. Kelmagan xodimlardan 8 soatlik jarima hisoblandi va dashboard yangilandi.")

async def kunlik_eslatma():
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id FROM xodimlar")
    ids = cursor.fetchall()
    conn.close()
    for row in ids:
        if row[0] != ADMIN_ID:
            try:
                await bot.send_message(row[0], "⏰ **Ish vaqti tugadi!**\n\nIltimos, qaytishda tugmalarni bosing.", reply_markup=xodim_klaviatura())
            except: pass

def xodim_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🟢 Ishni boshlash", request_location=True)],
        [KeyboardButton(text="🥪 Obedga chiqish"), KeyboardButton(text="🔙 Obeddan qaytish")],
        [KeyboardButton(text="⏰ Qo'shimcha ishlash", request_location=True)],
        [KeyboardButton(text="🔴 Ishni yakunlash", request_location=True)]
    ], resize_keyboard=True)

def admin_klaviatura():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Xodimlar hisoboti (Buxgalteriya)")],
        [KeyboardButton(text="💰 Buxgalter hamma summani tashlab berdi")]
    ], resize_keyboard=True)

@dp.message(F.text == "/start")
async def cmd_start(m: Message, state: FSMContext):
    user_id = m.from_user.id
    await state.clear()
    
    if user_id == ADMIN_ID:
        await m.answer("👑 Xush kelibsiz Jahongir aka! Web Boshqaruv paneli ishga tushdi.", reply_markup=admin_klaviatura())
        return

    xodim = get_xodim(user_id)
    if xodim:
        await m.answer(f"✨ Xush kelibsiz, {xodim['ism']}!\nTugmalardan foydalanib vaqtingizni qayd eting:", reply_markup=xodim_klaviatura())
    else:
        await m.answer("📌 Botdan foydalanish uchun ro'yxatdagi ismingizni kiriting (Masalan: Sevinch, Charos):")
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
        await m.answer(f"❌ Ism topilmadi!\nTo'g'ri kiriting:\n`{ismlar_listi}`")
        return
        
    await state.clear()
    
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO xodimlar (tg_id, ism, jami_minut, jami_soat, kelmagan_kunlar, obed_minutlari)
        VALUES (?, ?, 0, 0, 0, 0)
    """, (user_id, topilgan_ism))
    conn.commit()
    conn.close()
    
    await m.answer(f"✅ Rahmat, {topilgan_ism}! Tizimga ulandingiz.", reply_markup=xodim_klaviatura())
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi xodim qo'shildi:** {topilgan_ism}")

@dp.message(F.text == "🥪 Obedga chiqish")
async def obed_boshlash(m: Message):
    xodim = get_xodim(m.from_user.id)
    if not xodim or not xodim['came']: return
    
    update_xodim(m.from_user.id, obedda=1, obed_start=datetime.now(UZ_TZ).isoformat())
    await m.answer("🥪 Obed vaqtingiz boshlandi. Yoqimli ishtaha!")

@dp.message(F.text == "🔙 Obeddan qaytish")
async def obed_tugatish(m: Message):
    xodim = get_xodim(m.from_user.id)
    if not xodim or not xodim['obedda']: return
    
    hozir = datetime.now(UZ_TZ)
    obed_start = datetime.fromisoformat(xodim['obed_start'])
    obed_minut = max(1, int((hozir - obed_start).total_seconds() // 60))
    
    yangi_obed = xodim['obed_minutlari'] + obed_minut
    update_xodim(m.from_user.id, obedda=0, obed_minutlari=yangi_obed)
    await m.answer(f"🔙 Obeddan qaytdingiz. Obed davomiyligi: {obed_minut} minut.")

@dp.message(F.location)
async def handle_location(m: Message):
    user_id = m.from_user.id
    xodim = get_xodim(user_id)
    if not xodim: return
    
    masofa = masofani_hisobla(m.location.latitude, m.location.longitude, ISHXONA_LAT, ISHXONA_LON)
    if masofa > MAKS_MASOFA:
        await m.answer(f"❌ Ishxonada emassiz! Masofa: {int(masofa)} m.")
        return

    hozir = datetime.now(UZ_TZ)

    # Qo'shimcha ishlash
    if m.reply_markup and any(b.text == "⏰ Qo'shimcha ishlash" for row in m.reply_markup.keyboard for b in row if hasattr(b, 'text')):
        if not xodim['came']: return
        update_xodim(user_id, overtime_active=1, overtime_start=hozir.isoformat())
        await m.answer(f"⏰ Qo'shimcha ishlash vaqti boshlandi: {hozir.strftime('%H:%M')}")
        return

    # Ishni boshlash
    if not xodim['came']:
        kechikish = 0
        if hozir.hour > 9 or (hozir.hour == 9 and hozir.minute > 0):
            kechikish = (hozir.hour - 9) * 60 + hozir.minute
            
        yangi_minut = xodim['jami_minut'] + kechikish
        update_xodim(user_id, came=1, bugun_keldi=1, start_time=hozir.isoformat(), jami_minut=yangi_minut)
        
        msg = f"✅ Ish boshlandi. Vaqt: {hozir.strftime('%H:%M')}"
        if kechikish > 0: msg += f"\n⚠️ Siz bugun {kechikish} minut kechikdingiz."
        await m.answer(msg)
    
    # Ishni yakunlash
    else:
        start_vaqt = datetime.fromisoformat(xodim['start_time'])
        overtime_minut = 0
        
        if xodim['overtime_active'] and xodim['overtime_start']:
            o_start = datetime.fromisoformat(xodim['overtime_start'])
            overtime_minut = int((hozir - o_start).total_seconds() // 60)
            
        farq_soniya = (hozir - start_vaqt).total_seconds() - (xodim['obed_minutlari'] * 60)
        ishlangan_soat = max(1, int(farq_soniya // 3600))
        
        yangi_minut = max(0, xodim['jami_minut'] - overtime_minut)
        yangi_soat = xodim['jami_soat'] + ishlangan_soat
        
        update_xodim(user_id, came=0, overtime_active=0, jami_minut=yangi_minut, jami_soat=yangi_soat, obed_minutlari=0)
        await m.answer(f"🔴 Ish yakunlandi. Bugun sof {ishlangan_soat} soat ishladingiz.")

@dp.message(F.text == "📊 Xodimlar Hisoboti (Buxgalteriya)" or F.text == "📊 Xodimlar hisoboti (Buxgalteriya)")
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
        
    matn = "📊 **BUXGALTERIYA HISOBOTI**\n\n"
    for r in rows:
        ism = r['ism']
        if ism not in XODIMLAR_BAZASI: continue
        st = XODIMLAR_BAZASI[ism]
        vaz = r['jami_minut'] * st['minut_narxi']
        k_narx = st['kun_narxi'] if st['kun_narxi'] > 0 else (st['oylik'] / 26)
        kel_jar = r['kelmagan_kunlar'] * k_narx
        yakuniy = st['oylik'] - vaz - kel_jar + (r['jami_soat'] * st['soat_narxi'])
        
        matn += f"👤 **{ism}**:\n⏱ Kechikish: {r['jami_minut']} m | ❌ Kelmagan: {r['kelmagan_kunlar']} kun\n💰 **Qo'lga tegadigani:** {max(0, yakuniy):,.2f} so'm\n"
    await m.answer(matn)

@dp.message(F.text == "💰 Buxgalter hamma summani tashlab berdi")
async def clear_balances(m: Message):
    if m.from_user.id != ADMIN_ID: return
    conn = sqlite3.connect("davomat.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE xodimlar SET jami_minut=0, jami_soat=0, kelmagan_kunlar=0, came=0, obedda=0")
    conn.commit()
    conn.close()
    await m.answer("✅ Barcha xodimlarning oylik hisob-kitoblari 0 ga tushirildi.")

# 🖥 DYNAMIC HTML WEB-DASHBOARD (image_b683a2.png DIZAYNI ASOSIDA)
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
        st = XODIMLAR_BAZASI.get(ism, {"oylik": 0, "minut_narxi": 0, "soat_narxi": 0})
        vazvirat = r['jami_minut'] * st['minut_narxi']
        k_narx = st.get('kun_narxi', 0) if st.get('kun_narxi', 0) > 0 else (st['oylik'] / 26)
        kel_jar = r['kelmagan_kunlar'] * k_narx
        yakuniy = st['oylik'] - vazvirat - kel_jar + (r['jami_soat'] * st['soat_narxi'])
        
        status_badge = '<span style="background:#e8f5e9;color:#2e7d32;padding:4px 8px;border-radius:6px;font-size:12px;">Ishda</span>' if r['came'] else '<span style="background:#ffebee;color:#c62828;padding:4px 8px;border-radius:6px;font-size:12px;">Ketgan/Kelmagan</span>'
        
        table_rows += f"""
        <tr style="border-bottom: 1px solid #f0f0f0;">
            <td style="padding: 15px; font-weight: 600; color: #333;">{ism}</td>
            <td style="padding: 15px;">{status_badge}</td>
            <td style="padding: 15px; color: #c62828; font-weight: 600;">{r['jami_minut']} min</td>
            <td style="padding: 15px; color: #2e7d32; font-weight: 600;">{r['jami_soat']} soat</td>
            <td style="padding: 15px; color: #e65100;">{r['kelmagan_kunlar']} kun</td>
            <td style="padding: 15px; font-weight: bold; color: #ff9800;">{st['oylik']:,.0f} UZS</td>
            <td style="padding: 15px; font-weight: bold; color: #1e88e5;">{max(0, yakuniy):,.0f} UZS</td>
        </tr>
        """
        
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>SHERIN - Davomat Boshqaruv Paneli</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
            body {{ background: #f8f9fa; padding: 30px; }}
            .header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom: 30px; }}
            .title {{ font-size: 24px; font-weight: 700; color: #222; }}
            .stats-container {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
            .card {{ background: white; padding: 25px; border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.02); display: flex; justify-content: space-between; align-items: center; border: 1px solid #f0f0f0; }}
            .card-title {{ font-size: 14px; color: #666; font-weight: 600; text-transform: uppercase; }}
            .card-value {{ font-size: 28px; font-weight: 700; color: #222; margin-top: 5px; }}
            .card-icon {{ width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 20px; }}
            .table-container {{ background: white; border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.02); padding: 20px; border: 1px solid #f0f0f0; }}
            .table-title {{ font-size: 18px; font-weight: 700; margin-bottom: 20px; color: #333; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th {{ padding: 15px; color: #666; font-weight: 600; font-size: 13px; text-transform: uppercase; border-bottom: 2px solid #f0f0f0; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">📋 Boshqaruv paneli <span style="font-size:14px; color:#888; font-weight:normal;">/ Sherin Tizimi</span></div>
            <div style="background:white; padding:10px 20px; border-radius:10px; font-weight:600; border:1px solid #e0e0e0;"><i class="fa-regular fa-calendar-days"></i> Cani: {datetime.now(UZ_TZ).strftime('%d.%m.2026')}</div>
        </div>
        
        <div class="stats-container">
            <div class="card">
                <div><div class="card-title">Barchasi</div><div class="card-value">{barchasi}</div></div>
                <div class="card-icon" style="background:#e8f5e9; color:#2e7d32;"><i class="fa-solid fa-users"></i></div>
            </div>
            <div class="card">
                <div><div class="card-title">Ishda</div><div class="card-value">{ishda}</div></div>
                <div class="card-icon" style="background:#e0f2f1; color:#004d40;"><i class="fa-solid fa-user-check"></i></div>
            </div>
            <div class="card">
                <div><div class="card-title">Kechikkanlar</div><div class="card-value">{kechikkanlar}</div></div>
                <div class="card-icon" style="background:#fff3e0; color:#e65100;"><i class="fa-solid fa-user-clock"></i></div>
            </div>
            <div class="card">
                <div><div class="card-title">Ishda emas</div><div class="card-value">{ishda_emas}</div></div>
                <div class="card-icon" style="background:#ffebee; color:#c62828;"><i class="fa-solid fa-user-slash"></i></div>
            </div>
        </div>

        <div class="table-container">
            <div class="table-title">Davomat va Buxgalteriya oylik balansi</div>
            <table>
                <thead>
                    <tr>
                        <th>Xodim</th>
                        <th>Holati</th>
                        <th>Jami Kechikish</th>
                        <th>Qo'shimcha Soat</th>
                        <th>Kelmagan Kunlari</th>
                        <th>Asosiy Oylik</th>
                        <th>Qo'lga Tegadigan Summa</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
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
    import asyncio
    asyncio.run(main())
