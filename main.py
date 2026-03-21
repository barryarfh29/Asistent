import asyncio, logging, os, urllib.parse
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- KONFIGURASI (PASTIKAN SUDAH BENAR) ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM") # Token @ReferralVVIPbot
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")

PAYMENT_BOT = "WarungLENDIR_Robot"
ADMIN_USER = "belaa"

logging.basicConfig(level=logging.INFO)
m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
reff_col = db["referrals"]
pm_users_col = db["pm_users"]
config_col = db["config"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- UTILS ---
async def get_price_list():
    res = await config_col.find_one({"key": "price_list"})
    return res["val"] if res else "<b>🔥 DAFTAR HARGA VIP:</b>\nBelum diatur. Gunakan <code>.setharga</code>"

# --- 1. BOT HANDLER (@ReferralVVIPbot) ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, msg):
    u_id = msg.from_user.id
    args = msg.text.split()
    
    if len(args) > 1 and "invite_" in args[1]:
        inviter_id = int(args[1].replace("invite_", ""))
        is_new = await pm_users_col.find_one({"user_id": u_id}) is None
        if is_new and inviter_id != u_id:
            await reff_col.update_one({"user_id": inviter_id}, {"$inc": {"click_points": 1}}, upsert=True)
            await pm_users_col.update_one({"user_id": u_id}, {"$set": {"invited_by": inviter_id}}, upsert=True)

    pesan_untuk_asisten = "Halo kak saya di undang teman untuk join vip"
    url_asisten = f"https://t.me/{ADMIN_USER}?text={urllib.parse.quote(pesan_untuk_asisten)}"
    
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 LANJUT KE @WarungLENDIR_Robot", url=f"https://t.me/{PAYMENT_BOT}?start=start")],
        [InlineKeyboardButton("👩‍💻 CHAT ASISTEN (@belaa)", url=url_asisten)]
    ])
    
    await msg.reply("<b>SYNDICATE VIP ACCESS ✅</b>\nKlik tombol di bawah untuk lanjut.", reply_markup=btn)

# --- 2. USERBOT HANDLER (@belaa) ---
@user.on_message(filters.me & filters.command("help", prefixes="."))
async def help_handler(client, msg):
    text = (
        "👑 **SYNDICATE ADMIN HELP**\n\n"
        "• `.reff` - Cek link & statistik milikmu\n"
        "• `.cekreff [ID/Reply]` - Cek poin member\n"
        "• `.setharga [Teks]` - Atur daftar harga VIP\n"
        "• `.broadcast [Teks]` - Kirim pesan ke semua member\n\n"
        "<i>Gunakan titik (.) di depan perintah.</i>"
    )
    await msg.edit(text)

@user.on_message(filters.me & filters.command("setharga", prefixes="."))
async def set_harga_handler(client, msg):
    if len(msg.command) < 2: return await msg.edit("Format: `.setharga [Isi Harga]`")
    new_price = msg.text.split(None, 1)[1]
    await config_col.update_one({"key": "price_list"}, {"$set": {"val": new_price}}, upsert=True)
    await msg.edit("✅ **Daftar harga VIP berhasil diupdate!**")

@user.on_message(filters.me & filters.command("cekreff", prefixes="."))
async def cek_reff_handler(client, msg):
    target_id = msg.reply_to_message.from_user.id if msg.reply_to_message else (int(msg.command[1]) if len(msg.command) > 1 else None)
    if not target_id: return await msg.edit("Reply chat atau gunakan ID.")
    data = await reff_col.find_one({"user_id": target_id})
    if not data: return await msg.edit("❌ Tidak ada data.")
    await msg.edit(f"📊 **USER `{target_id}`**\n• Klik: **{data.get('click_points', 0)}**\n• Sales: **{data.get('success_sales', 0)}**")

@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def auto_reply_handler(client, msg):
    text = (msg.text or "").lower()
    if "halo kak saya di undang teman untuk join vip" in text:
        harga = await get_price_list()
        await msg.reply(harga)
    elif msg.photo:
        await pm_users_col.update_one({"user_id": msg.from_user.id}, {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, upsert=True)
        await msg.forward(PAYMENT_BOT)
        await msg.reply("🛡️ **Bukti terkirim!** Sedang diverifikasi...")

# --- 3. MONITORING SALES ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_monitor(client, msg):
    text_bot = (msg.text or "").lower()
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    if "t.me/+" in text_bot or "berhasil" in text_bot:
        await msg.copy(buyer["user_id"])
        await pm_users_col.update_one({"user_id": buyer["user_id"]}, {"$set": {"waiting_payment": False}})
        if "invited_by" in buyer:
            await reff_col.update_one({"user_id": buyer["invited_by"]}, {"$inc": {"success_sales": 1}}, upsert=True)

async def main():
    await user.start(); await bot.start()
    print("🚀 SEMUA SISTEM AKTIF!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
