import asyncio, logging, os, urllib.parse
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- KONFIGURASI ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
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

async def get_config(key, default_text):
    res = await config_col.find_one({"key": key})
    return res["val"] if res else default_text

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
    
    welcome_text = await get_config("welcome_msg", "<b>SYNDICATE VIP ACCESS ✅</b>\nKlik tombol di bawah.")
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 LANJUT KE @WarungLENDIR_Robot", url=f"https://t.me/{PAYMENT_BOT}?start=start")],
        [InlineKeyboardButton("👩‍💻 CHAT ASISTEN (@belaa)", url=f"https://t.me/{ADMIN_USER}?text=Halo%20kak%20saya%20di%20undang%20teman")]
    ])
    await msg.reply(welcome_text, reply_markup=btn)

# --- 2. USERBOT HANDLER (@belaa) ---

# PERINTAH ADMIN (CEK REFF, HELP, SETTINGS)
@user.on_message(filters.me & filters.command(["help", "setharga", "setthanks", "setwelcome", "cekreff"], prefixes="."))
async def admin_tools(client, msg):
    cmd = msg.command[0]
    if cmd == "help":
        await msg.edit("👑 **ADMIN HELP**\n`.reff`, `.cekreff`, `.setharga`, `.setthanks`, `.setwelcome`")
    elif cmd in ["setharga", "setthanks", "setwelcome"]:
        if len(msg.command) < 2: return
        key_map = {"setharga": "price_list", "setthanks": "thanks_msg", "setwelcome": "welcome_msg"}
        await config_col.update_one({"key": key_map[cmd]}, {"$set": {"val": msg.text.split(None, 1)[1]}}, upsert=True)
        await msg.edit("✅ Update Berhasil!")
    elif cmd == "cekreff":
        target = msg.reply_to_message.from_user.id if msg.reply_to_message else (int(msg.command[1]) if len(msg.command) > 1 else None)
        data = await reff_col.find_one({"user_id": target})
        await msg.edit(f"📊 Klik: {data.get('click_points', 0)} | Sales: {data.get('success_sales', 0)}" if data else "❌ No Data")

# MAIN HANDLER (AUTO-REPLY & FORWARD)
@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def userbot_main_handler(client, msg):
    u_id = msg.from_user.id
    text = (msg.text or "").lower().strip()

    # 1. FITUR LAMA: Jika teks mengandung format order, teruskan ke Bot Payment (JANGAN DI-STOP)
    if any(keyword in text for keyword in ["nama paket:", "metode pembayaran:", "super indo", "premium"]):
        await msg.forward(PAYMENT_BOT)
        return # Selesai, jangan kirim daftar harga lagi

    # 2. FITUR LAMA: .reff member
    if text == ".reff":
        bot_info = await bot.get_me()
        await msg.reply(f"👑 Link: <code>https://t.me/{bot_info.username}?start=invite_{u_id}</code>")
        return

    # 3. AUTO-REPLY HARGA (Hanya jika bertanya harga)
    if any(k in text for k in ["harga", "price", "daftar", "join vip"]):
        harga = await get_config("price_list", "Daftar harga belum diatur.")
        await msg.reply(harga)
        return

    # 4. FORWARD FOTO TF
    if msg.photo:
        await pm_users_col.update_one({"user_id": u_id}, {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, upsert=True)
        await msg.forward(PAYMENT_BOT)
        await msg.reply("🛡️ **Bukti terkirim!** Sedang dicek.")

# --- 3. MONITORING SALES ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_monitor(client, msg):
    text_bot = (msg.text or "").lower()
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if buyer and ("t.me/+" in text_bot or "berhasil" in text_bot):
        thanks = await get_config("thanks_msg", "Berhasil!")
        await user.send_message(buyer["user_id"], thanks)
        await msg.copy(buyer["user_id"])
        await pm_users_col.update_one({"user_id": buyer["user_id"]}, {"$set": {"waiting_payment": False}})
        if "invited_by" in buyer:
            await reff_col.update_one({"user_id": buyer["invited_by"]}, {"$inc": {"success_sales": 1}}, upsert=True)

async def main():
    await user.start(); await bot.start()
    print("🚀 FIXED SYSTEM ONLINE!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
