import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

BOT_TOKEN = '8367296175:AAFpHB3MhCw4hS9NYNAD4VaU0ghENQ7DQuQ'
ATTEMPS = 3
DELAY = 15
