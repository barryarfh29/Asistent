import asyncio, logging, os, hashlib
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")
PAYMENT_BOT = "WarungLENDIR_Robot"

# Target Referral
TARGET_KLIK = 100
TARGET_SALES = 3

logging.basicConfig(level=logging.INFO)

m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
reff_col = db["referrals"]
pm_users_col = db["pm_users"]
hashes_col = db["processed_hashes"] # Untuk cek foto duplikat
config_col = db["config"]

user = Client("session_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
bot = Client("session_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- UTILS ---
async def get_config(key, default):
    res = await config_col.find_one({"key": key})
    return res["val"] if res else default

def format_html(text, user_obj):
    if not text: return ""
    name = user_obj.first_name or "Kakak"
    mention = f"<a href='tg://user?id={user_obj.id}'>{name}</a>"
    return text.replace("{mention}", mention).replace("{name}", name)

async def get_photo_hash(client, message):
    photo = await client.download_media(message, in_memory=True)
    return hashlib.md5(photo.getbuffer()).hexdigest()

# --- 1. HANDLER START & REFERRAL (BOT TOKEN) ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, msg):
    u_id = msg.from_user.id
    args = msg.text.split()
    
    if len(args) > 1 and "invite_" in args[1]:
        inviter_id = int(args[1].replace("invite_", ""))
        is_new = await pm_users_col.find_one({"user_id": u_id}) is None
        
        if is_new and inviter_id != u_id:
            # +1 Klik Poin
            res = await reff_col.find_one_and_update(
                {"user_id": inviter_id},
                {"$inc": {"click_points": 1}},
                upsert=True, return_document=True
            )
            # Simpan siapa pengundangnya untuk tracking sales nanti
            await pm_users_col.update_one(
                {"user_id": u_id},
                {"$set": {"invited_by": inviter_id}},
                upsert=True
            )
            # Notif 100 klik
            if res.get("click_points") == TARGET_KLIK:
                try: await user.send_message(inviter_id, "🔥 **TARGET 100 KLIK TERCAPAI!**\nKamu dapat DISKON 50%. Hubungi admin!")
                except: pass

    await pm_users_col.update_one({"user_id": u_id}, {"$set": {"last_active": datetime.now()}}, upsert=True)
    await msg.reply("<b>Selamat Datang di Syndicate VIP!</b>\nKirim bukti transfer untuk join, atau ketik <code>.reff</code> untuk dapat VIP Gratis.")

# --- 2. HANDLER ASISTEN (USER SESSION) ---
@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def assistant_handler(client, msg):
    u_id = msg.from_user.id
    text = (msg.text or "").lower().strip()

    # A. FITUR REFERRAL (.reff / /referral)
    if text in [".reff", ".referral", "/reff", "/referral"]:
        bot_me = await bot.get_me()
        link = f"https://t.me/{bot_me.username}?start=invite_{u_id}"
        data = await reff_col.find_one({"user_id": u_id})
        k = data.get("click_points", 0) if data else 0
        s = data.get("success_sales", 0) if data else 0
        
        await msg.reply(
            f"👑 **PANEL AFFILIATE**\n\n"
            f"Link: <code>{link}</code>\n\n"
            f"📊 **PROGRES:**\n"
            f"• Klik: **{k}/{TARGET_KLIK}** (Hadiah: Diskon 50%)\n"
            f"• Sales: **{s}/{TARGET_SALES}** (Hadiah: VIP Gratis)\n\n"
            f"<i>Sebarkan link ke grup lain untuk dapat poin!</i>"
        )
        return

    # B. FILTER ANTI-SPAM CHAT GAK PENTING
    if text in ["p", "kak", "min", "tes", "halo"] or len(text) < 2:
        return

    # C. LOGIKA FOTO & ANTI-DUPLIKAT ( ANTI-SPAM BUKTI TF )
    if msg.photo:
        f_hash = await get_photo_hash(client, msg)
        if await hashes_col.find_one({"hash": f_hash}):
            return await msg.reply("⚠️ Bukti transfer ini sudah diproses. Mohon tunggu asisten.")
        
        await hashes_col.insert_one({"hash": f_hash, "user_id": u_id, "date": datetime.now()})
        await pm_users_col.update_one(
            {"user_id": u_id}, 
            {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, 
            upsert=True
        )
        await msg.forward(PAYMENT_BOT)
        await msg.reply("🛡️ **Sedang diverifikasi...** Mohon jangan kirim bukti berulang kali.")
        return

# --- 3. HANDLER PAYMENT BOT (CEK SUKSES & SALES POINT) ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_handler(client, msg):
    text_bot = (msg.text or "").lower()
    
    # Ambil user paling baru yang kirim bukti TF
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    
    target_id = buyer["user_id"]
    u_obj = await client.get_users(target_id)

    if "t.me/+" in text_bot or "berhasil" in text_bot:
        # Kirim & Pin Link
        sent_msg = await msg.copy(target_id)
        await sent_msg.pin(both_sides=True)
        
        thanks_raw = await get_config("thanks_text", "Terima kasih {mention} sudah join!")
        await client.send_message(target_id, format_html(thanks_raw, u_obj))
        
        # Reset Status Waiting
        await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

        # CEK SALES AFFILIATE
        if "invited_by" in buyer:
            inviter = buyer["invited_by"]
            res = await reff_col.find_one_and_update(
                {"user_id": inviter}, {"$inc": {"success_sales": 1}},
                upsert=True, return_document=True
            )
            if res.get("success_sales") >= TARGET_SALES:
                await user.send_message(inviter, "🎊 **GOAL!** 3 temanmu sudah beli VIP. Pilih channel gratis kamu sekarang!")
                await reff_col.update_one({"user_id": inviter}, {"$set": {"success_sales": 0}})

# --- MAIN RUNNER ---
async def main():
    await user.start()
    await bot.start()
    print("🚀 ASISTEN SYNDICATE v2 ONLINE!")
    await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
