import asyncio, logging, os, hashlib
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# --- CONFIGURATION (Ganti sesuai data kakak) ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")
PAYMENT_BOT = "WarungLENDIR_Robot"

# Target Milestone
TARGET_KLIK = 100
TARGET_SALES = 3

logging.basicConfig(level=logging.INFO)

m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
reff_col = db["referrals"]
pm_users_col = db["pm_users"]
hashes_col = db["processed_hashes"]
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

# --- 1. HANDLER START (DETEKSI KLIK REFERRAL) ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, msg):
    u_id = msg.from_user.id
    args = msg.text.split()
    
    if len(args) > 1 and "invite_" in args[1]:
        inviter_id = int(args[1].replace("invite_", ""))
        # Cek apakah user ini benar-benar baru di sistem kita
        is_new = await pm_users_col.find_one({"user_id": u_id}) is None
        
        if is_new and inviter_id != u_id:
            # +1 Klik Poin di Database
            res = await reff_col.find_one_and_update(
                {"user_id": inviter_id},
                {"$inc": {"click_points": 1}},
                upsert=True, return_document=True
            )
            # Simpan data pengundang di profil user baru
            await pm_users_col.update_one(
                {"user_id": u_id},
                {"$set": {"invited_by": inviter_id}},
                upsert=True
            )
            # Notifikasi Milestone 100 Klik
            if res.get("click_points") == TARGET_KLIK:
                try: await user.send_message(inviter_id, "🔥 **MISI VIRAL SELESAI!**\n100 Orang telah klik linkmu. Kamu dapat **DISKON 50%**. Hubungi admin!")
                except: pass

    # Registrasi User
    await pm_users_col.update_one({"user_id": u_id}, {"$set": {"last_active": datetime.now()}}, upsert=True)
    await msg.reply("<b>Selamat Datang di Syndicate Asahan!</b>\nKirim bukti TF untuk join VIP, atau ketik <code>.reff</code> untuk ambil link referralmu.")

# --- 2. HANDLER ASISTEN (USER SESSION) ---
@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def assistant_handler(client, msg):
    u_id = msg.from_user.id
    text = (msg.text or "").lower().strip()

    # A. TAMPILKAN PANEL REFERRAL
    if text in [".reff", ".referral", "/reff", "/referral"]:
        bot_me = await bot.get_me()
        link = f"https://t.me/{bot_me.username}?start=invite_{u_id}"
        data = await reff_col.find_one({"user_id": u_id})
        k = data.get("click_points", 0) if data else 0
        s = data.get("success_sales", 0) if data else 0
        
        panel_text = (
            f"👑 **PANEL AFFILIATE SYNDICATE**\n\n"
            f"Bagikan link ini ke teman/grup:\n<code>{link}</code>\n\n"
            f"📊 **PROGRES HADIAH:**\n"
            f"• Misi Viral: **{k}/{TARGET_KLIK}** Klik (Diskon 50%)\n"
            f"• Misi Sales: **{s}/{TARGET_SALES}** Beli (VIP Gratis)\n\n"
            f"⚠️ *Poin sales hanya masuk jika temanmu membeli lewat Asisten ini.*"
        )
        await msg.reply(panel_text, parse_mode=ParseMode.HTML)
        return

    # B. LOGIKA FOTO & ANTI-SPAM BUKTI TF
    if msg.photo:
        f_hash = await get_photo_hash(client, msg)
        if await hashes_col.find_one({"hash": f_hash}):
            return await msg.reply("⚠️ Bukti transfer ini sudah diproses. Mohon jangan spam!")
        
        await hashes_col.insert_one({"hash": f_hash, "user_id": u_id, "date": datetime.now()})
        # Tandai sedang menunggu bayar (untuk sistem antrean)
        await pm_users_col.update_one(
            {"user_id": u_id}, 
            {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, 
            upsert=True
        )
        await msg.forward(PAYMENT_BOT)
        await msg.reply("🛡️ **Sedang diverifikasi...** Mohon tunggu sebentar.")
        return

# --- 3. HANDLER PAYMENT BOT (POIN SALES HANYA LEWAT USERBOT) ---
@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_handler(client, msg):
    text_bot = (msg.text or "").lower()
    
    # Ambil pembeli yang paling baru mengirim bukti ke USERBOT
    buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
    if not buyer: return
    
    target_id = buyer["user_id"]
    u_obj = await client.get_users(target_id)

    # Jika Terdeteksi Link Join (Sukses)
    if "t.me/+" in text_bot or "t.me/joinchat" in text_bot:
        # 1. Kirim & Pin Link ke Pembeli
        sent_msg = await msg.copy(target_id)
        await sent_msg.pin(both_sides=True)
        
        thanks_raw = await get_config("thanks_text", "Terima kasih {mention} sudah join Syndicate!")
        await client.send_message(target_id, format_html(thanks_raw, u_obj))
        
        # 2. Matikan Status Waiting
        await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

        # 3. LOGIKA SALES POINT (HANYA UNTUK USER YANG ADA DI DB USERBOT)
        if "invited_by" in buyer:
            inviter_id = buyer["invited_by"]
            # +1 Poin Sales Sukses
            res_sales = await reff_col.find_one_and_update(
                {"user_id": inviter_id},
                {"$inc": {"success_sales": 1}},
                upsert=True, return_document=True
            )
            
            s_count = res_sales.get("success_sales", 0)
            if s_count >= TARGET_SALES:
                # Milestone 3 Penjualan Tercapai
                await user.send_message(inviter_id, "🎊 **CONGRATS! 3 SALES BERHASIL!**\nKamu berhak dapat **1 Channel VIP Gratis**. Silakan pilih daftar channelnya di admin!")
                await reff_col.update_one({"user_id": inviter_id}, {"$set": {"success_sales": 0}}) # Reset Cycle
            else:
                await user.send_message(inviter_id, f"💰 **Sales Sukses!**\nTeman yang kamu ajak baru saja join VIP.\nProgres: **{s_count}/{TARGET_SALES}**")

# --- MAIN ---
async def main():
    await user.start()
    await bot.start()
    print("🚀 ASISTEN AFFILIATE SYNDICATE ONLINE!")
    await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
