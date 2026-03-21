import re, asyncio, logging, os, hashlib
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InlineQueryResultCachedPhoto, InputTextMessageContent
from pyrogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "38886457"))
API_HASH = os.getenv("API_HASH", "93ae4287da188cb3ba23a620c8ca5bd4")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8655576331:AAEL8MJraLvAxcmoevPjpNeU01id-ELriKM")
SESSION_STRING = os.getenv("SESSION_STRING")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://Nadira31:Nadira31@cluster0.81zcrwl.mongodb.net/?appName=Cluster0")
PAYMENT_BOT = "WarungLENDIR_Robot"

logging.basicConfig(level=logging.INFO)

m_client = AsyncIOMotorClient(MONGO_URI)
db = m_client["userbot_db"]
notes_col = db["notes"]
pm_users_col = db["pm_users"]
config_col = db["config"]
hashes_col = db["processed_hashes"] # Untuk anti-spam foto

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
    return text.replace("{mention}", mention).replace("{name}", name).replace("{id}", str(user_obj.id))

async def get_photo_hash(client, message):
    photo = await client.download_media(message, in_memory=True)
    return hashlib.md5(photo.getbuffer()).hexdigest()

# --- HANDLER ASISTEN ---

@user.on_message(filters.private & ~filters.me & ~filters.bot)
async def assistant_handler(client, msg):
    user_id = msg.from_user.id
    text = msg.text.strip().lower() if msg.text else ""
    
    # 1. ABAIKAN CHAT TIDAK PENTING (Filter Anti-Baper)
    ignore_list = ["p", "kak", "min", "bang", "tes", "test", "halo", "oke", "makasih", "thanks"]
    if text in ignore_list or len(text) < 2:
        return

    # 2. LOGIKA FOTO (ANTI-SPAM BUKTI TF)
    if msg.photo:
        f_hash = await get_photo_hash(client, msg)
        already_processed = await hashes_col.find_one({"hash": f_hash})
        
        if already_processed:
            await msg.reply("⚠️ **Bukti transfer ini sudah pernah dikirim sebelumnya.**\nMohon tunggu asisten mengecek manual jika ada kendala.")
            return

        # Simpan hash agar tidak bisa di-spam
        await hashes_col.insert_one({"hash": f_hash, "user_id": user_id, "date": datetime.now()})
        
        # Tandai sebagai pembeli aktif di Database (Queue)
        await pm_users_col.update_one(
            {"user_id": user_id}, 
            {"$set": {"waiting_payment": True, "last_interaction": datetime.now()}}, 
            upsert=True
        )
        
        await msg.forward(PAYMENT_BOT)
        verif_raw = await get_config("verif_text", "Sabar ya {mention}, asisten sedang verifikasi pembayaranmu...")
        await msg.reply(format_html(verif_raw, msg.from_user))
        return

    # 3. LOGIKA HARGA (USER BARU vs LAMA + AUTO PIN)
    tanya_harga = ["harga", "berapa", "price", "daftar", "list", "join", "vip"]
    if any(x in text for x in tanya_harga):
        is_user_exists = await pm_users_col.find_one({"user_id": user_id})
        
        if not is_user_exists:
            # User Baru: Kirim & Pin
            note_harga = await notes_col.find_one({"key": "harga"})
            if note_harga:
                bot_me = await bot.get_me()
                inline = await user.get_inline_bot_results(bot_me.username, "harga")
                if inline.results:
                    await user.send_inline_bot_result(msg.chat.id, inline.query_id, inline.results[0].id)
                    await pm_users_col.update_one({"user_id": user_id}, {"$set": {"name": msg.from_user.first_name}}, upsert=True)
                    # Pin pesan terakhir (harga)
                    async for m in user.get_chat_history(msg.chat.id, limit=1):
                        await m.pin(both_sides=True)
                    return
        else:
            # User Lama: Ingatkan Cek Pin
            await msg.reply(format_html("Halo {mention}, harga & paket silakan cek di <b>Pesan Tersemat (Pin)</b> di atas ya! 👆", msg.from_user))
            return

# --- HANDLER DARI BOT PAYMENT ---

@user.on_message(filters.chat(PAYMENT_BOT) & ~filters.me)
async def payment_reply_handler(client, msg):
    try:
        text_bot = (msg.text or "").lower()
        
        # Cari siapa user yang paling baru kirim bukti TF (Database Queue)
        buyer = await pm_users_col.find_one({"waiting_payment": True}, sort=[("last_interaction", -1)])
        if not buyer: return
        
        target_id = buyer["user_id"]
        u_data = await client.get_users(target_id)

        # DETEKSI SUKSES (Ada link invite)
        if "t.me/+" in text_bot or "t.me/joinchat" in text_bot:
            sent_link = await msg.copy(target_id)
            await sent_link.pin(both_sides=True) # Pin link agar tidak hilang
            
            thanks_raw = await get_config("thanks_text", "none")
            warning = "\n\n⚠️ **PENTING:** Link di atas hanya bisa diklik 1x. Jangan keluar setelah masuk!"
            await client.send_message(target_id, format_html(thanks_raw, u_data) + warning)
            
            # Selesai, matikan status menunggu
            await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

        elif "gagal" in text_bot or "expired" in text_bot:
            await client.send_message(target_id, "❌ Pembayaran gagal verifikasi atau sudah expired.")
            await pm_users_col.update_one({"user_id": target_id}, {"$set": {"waiting_payment": False}})

    except Exception as e:
        logging.error(f"Error Payment Handler: {e}")

# --- START ---
async def main():
    await user.start(); await bot.start()
    print("🚀 ASISTEN ANTI-SPAM AKTIF!"); await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
