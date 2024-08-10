import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')
    API_KEY = os.getenv('API_KEY')
    DEBUG = os.getenv('FLASK_ENV') == 'development'
