import os
import logging
import requests
import asyncio
import threading
from datetime import datetime, timedelta
from pymongo import MongoClient
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

@app.route('/')
def home():
    return "Telegram Bot is running successfully!"

# কনফিগারেশন
TOKEN = os.getenv("BOT_TOKEN")
FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL") 
PREMIUM_CHANNEL_ID = os.getenv("PREMIUM_CHANNEL_ID") 
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MONGO_URI = os.getenv("MONGO_URI")

SECRET_KEY = os.getenv("SECRET_KEY")
MERCHANT_ID = os.getenv("MERCHANT_ID")
API_KEY = os.getenv("API_KEY")

client = MongoClient(MONGO_URI)
db = client['telegram_premium_bot']
users_collection = db['users']

PLAN_PRICES = {
    "1d": {"days": 1, "price": 10, "name": "১ দিন"},
    "2d": {"days": 2, "price": 20, "name": "২ দিন"},
    "7d": {"days": 7, "price": 50, "name": "৭ দিন"},
    "15d": {"days": 15, "price": 90, "name": "১৫ দিন"},
    "1m": {"days": 30, "price": 150, "name": "১ মাস"},
    "2m": {"days": 60, "price": 280, "name": "২ মাস"}
}

async def check_fsub(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_name = user.first_name
    
    existing_user = users_collection.find_one({"user_id": user_id})
    if not existing_user:
        users_collection.insert_one({
            "user_id": user_id,
            "name": user_name,
            "is_premium": False,
            "expiry_date": None,
            "joined_date": datetime.utcnow()
        })
    
    is_subscribed = await check_fsub(user_id, context)
    if not is_subscribed:
        keyboard = [[InlineKeyboardButton("📢 চ্যানেলে জয়েন করুন", url=f"https://t.me/{FORCE_SUB_CHANNEL.replace('@', '')}")],
                    [InlineKeyboardButton("🔄 আবার চেক করুন", callback_data="check_sub")]]
        await update.message.reply_text(
            f"হ্যালো {user_name}! আমাদের বট ব্যবহার করতে হলে প্রথমে নিচের চ্যানেলে জয়েন করতে হবে।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    status_text = "সাধারণ মেম্বার ❌"
    if existing_user and existing_user.get("is_premium"):
        expiry = existing_user.get("expiry_date")
        if expiry and expiry > datetime.utcnow():
            status_text = f"প্রিমিয়াম মেম্বার ✅ (মেয়াদ শেষ: {expiry.strftime('%d-%m-%Y')})"
        else:
            users_collection.update_one({"user_id": user_id}, {"$set": {"is_premium": False, "expiry_date": None}})

    caption = (
        f"হ্যালো {user_name}! আমাদের প্রিমিয়াম বট সার্ভিসে স্বাগতম। 🚀\n\n"
        f"👤 **আপনার স্ট্যাটাস:** {status_text}\n\n"
        f"📜 **নোট:** ফ্রি চ্যানেলে যুক্ত থাকতে পারবেন, কিন্তু ফাইল বা ভিডিও ফরোয়ার্ড বা ডাউনলোড করতে প্রিমিয়াম মেম্বারশিপ নিতে হবে।"
    )
    
    keyboard = [
        [InlineKeyboardButton("💎 প্রিমিয়াম প্ল্যান কিনুন", callback_data="buy_plans")],
        [InlineKeyboardButton("❓ হেল্প", callback_data="help")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📢 ব্রডকাস্ট (Broadcast)", callback_data="broadcast_menu")])

    photo_url = "https://i.ibb.co/4gR9Z9y/sample.jpg"
    try:
        await update.message.reply_photo(photo=photo_url, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_sub":
        user_id = query.from_user.id
        if await check_fsub(user_id, context):
            await query.message.delete()
            await start(update, context)
        else:
            await query.answer("আপনি এখনো চ্যানেলে জয়েন করেননি!", show_alert=True)
            
    elif query.data == "buy_plans":
        plans_caption = "💳 **মেম্বারশিপ প্ল্যানসমূহ:**\nপ্রিমিয়াম ফাইল ও ভিডিও ফরোয়ার্ড আনলক করতে আপনার পছন্দের প্ল্যান সিলেক্ট করুন:"
        plans_keyboard = [
            [InlineKeyboardButton("১ দিন - ৳10", callback_data="pay_1d"), InlineKeyboardButton("২ দিন - ৳20", callback_data="pay_2d")],
            [InlineKeyboardButton("৭ দিন - ৳50", callback_data="pay_7d"), InlineKeyboardButton("১৫ দিন - ৳90", callback_data="pay_15d")],
            [InlineKeyboardButton("১ মাস - ৳150", callback_data="pay_1m"), InlineKeyboardButton("২ মাস - ৳280", callback_data="pay_2m")],
            [InlineKeyboardButton("🔙 ফিরে যান", callback_data="back_home")]
        ]
        try:
            await query.message.edit_media(media=InputMediaPhoto(media="https://i.ibb.co/4gR9Z9y/plans.jpg", caption=plans_caption, parse_mode="Markdown"), reply_markup=InlineKeyboardMarkup(plans_keyboard))
        except Exception:
            await query.edit_message_text(text=plans_caption, reply_markup=InlineKeyboardMarkup(plans_keyboard), parse_mode="Markdown")

    elif query.data.startswith("pay_"):
        plan_key = query.data.split("_")[1]
        if plan_key in PLAN_PRICES:
            plan = PLAN_PRICES[plan_key]
            user_id = query.from_user.id
            
            expiry_date = datetime.utcnow() + timedelta(days=plan['days'])
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"is_premium": True, "expiry_date": expiry_date}}
            )

            payment_url = create_gateway_payment(user_id, plan['price'], plan['name'])
            
            pay_keyboard = [
                [InlineKeyboardButton("💳 পেমেন্ট করুন", url=payment_url)],
                [InlineKeyboardButton("🔙 ফিরে যান", callback_data="buy_plans")]
            ]
            await query.message.edit_caption(
                caption=f"📦 **প্ল্যান:** {plan['name']}\n💵 **মূল্য:** ৳{plan['price']}\n\nনিচের লিংকে ক্লিক করে পেমেন্ট সম্পন্ন করুন:",
                reply_markup=InlineKeyboardMarkup(pay_keyboard)
            )

    elif query.data == "broadcast_menu":
        if query.from_user.id == ADMIN_ID:
            await query.message.reply_text("📢 ব্রডকাস্ট করতে `/broadcast [আপনার মেসেজ]` কমান্ডটি ব্যবহার করুন।")

    elif query.data == "back_home":
        await query.message.delete()
        await start(update, context)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    message_text = " ".join(context.args)
    if not message_text:
        await update.message.reply_text("দয়া করে মেসেজ লিখুন। উদাহরণ: `/broadcast আপনার নোটিশ`")
        return

    users = users_collection.find({})
    success = 0
    failed = 0

    for user in users:
        try:
            await context.bot.send_message(chat_id=user['user_id'], text=message_text)
            success += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"✅ ব্রডকাস্ট সম্পন্ন!\nসফল: {success}\nব্যর্থ: {failed}")

# প্রিমিয়াম চ্যানেল বা অন্য কোথাও থেকে আসা ফাইল কন্ট্রোল করার হ্যান্ডলার
async def handle_channel_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    
    # যদি চ্যাট প্রিমিয়াম চ্যানেল থেকে হয় বা ইউজার নরমাল চ্যাটে থাকে
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        return

    user = users_collection.find_one({"user_id": user_id})
    is_prem = False
    if user and user.get("is_premium"):
        expiry = user.get("expiry_date")
        if expiry and expiry > datetime.utcnow():
            is_prem = True

    # যদি প্রিমিয়াম না হয়, তবে ফাইল বা মিডিয়া ফরোয়ার্ড/ডাউনলোড রেস্ট্রিক্ট করবে
    if not is_prem:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ আপনার প্রিমিয়াম মেয়াদ শেষ অথবা আপনি প্রিমিয়াম মেম্বার নন! ফাইল বা ভিডিও ফরোয়ার্ড/অ্যাক্সেস করতে `/start` লিখে প্রিমিয়াম প্ল্যান কিনুন।"
            )
        except Exception:
            pass

def create_gateway_payment(user_id, amount, plan_name):
    api_endpoint = "https://api.yourpaymentgateway.com/v1/create-payment"
    payload = {
        "merchant_id": MERCHANT_ID,
        "api_key": API_KEY,
        "secret_key": SECRET_KEY,
        "amount": amount,
        "customer_id": str(user_id),
        "description": f"Premium Plan: {plan_name}"
    }
    try:
        response = requests.post(api_endpoint, json=payload, timeout=10)
        data = response.json()
        if response.status_code == 200 and "payment_url" in data:
            return data["payment_url"]
    except Exception as e:
        logging.error(f"Payment API Error: {e}")
        
    return f"https://yourpaymentgateway.com/pay?amount={amount}&user={user_id}"

def run_flask():
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

def main():
    if not TOKEN:
        print("Error: BOT_TOKEN is missing!")
        return

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # চ্যানেল বা বট চ্যাটে ফাইল/ডকুমেন্ট হ্যান্ডেল করার জন্য
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_channel_files))
    
    print("Database connected and Telegram Bot is running successfully...")
    application.run_polling()

if __name__ == '__main__':
    main()
    
