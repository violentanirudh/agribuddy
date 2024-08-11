from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai
from config import Config
import requests
import typing_extensions as typing

app = Flask(__name__)
app.secret_key = 'agribuddy' 
app.config.from_object(Config)

genai.configure(api_key=Config.API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# VERIFICATION

def verify_login():
    if 'user_id' not in session:
        return redirect(url_for('signin'))
    return True

# SCHEMA

class LoanOffer(typing.TypedDict):
    bank_name: str
    type: str
    interest_rate: str  # This is a string as per the JSON provided
    eligibility: str
    features: str

class Blog(typing.TypedDict):
    heading: str
    link: str  # This is a string as per the JSON provided

# MAIN

@app.route('/')
def index():
    verification = verify_login()
    if verification is not True:
        return verification

    # Retrieve chat data from the database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    user_email = session.get('user_email')
    cursor.execute('SELECT email, user_query, gemini_response FROM chats WHERE email = ?', (user_email,))
    
    chats = cursor.fetchall()
    conn.close()

    return render_template('index.html', title="Agribuddy", chats=chats, page='chat')


@app.route('/crop')
def crop():
    verification = verify_login()
    if verification is not True:
        return verification

    return render_template('crop-management.html', title="Agribuddy", page='crop')

@app.route('/bank-and-loans')
def bank_and_loans():
    verification = verify_login()
    if verification is not True:
        return verification

    return render_template('bank-and-loans.html', title="Agribuddy", page='schemes')

@app.route('/weather')
def weather():
    verification = verify_login()
    if verification is not True:
        return verification

    return render_template('weather.html', title="Weather", page='weather')

@app.route('/expert')
def expert():
    verification = verify_login()
    if verification is not True:
        return verification

    return render_template('expert.html', title="Expert Blogs", page='expert')

@app.route('/api/expert-blogs')
def api_expert_blogs():
    model = genai.GenerativeModel('gemini-1.5-flash', generation_config={
        "response_mime_type": "application/json",
        "response_schema": list[Blog]
    })

    response = model.generate_content(
        'Some internet articles on farming to improve harvest: {'
        '"heafing": "How to grow rice?", '
        '"link": "https://something.com/blog"}'
        'Generate 10'
    )

    try:
        blogs = response.text  # Assuming the response is JSON formatted
        return jsonify(blogs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/weather-data')
def api_weather_data():
    user_ip = ''
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        user_ip = request.environ['REMOTE_ADDR']
    else:
        user_ip = request.environ['HTTP_X_FORWARDED_FOR']

    user_ip = '152.58.60.209'

    api_key = '4000d0879091471eb13164311240908'
    try:
        location_request = requests.get(f'https://ipinfo.io/{user_ip}/json')
        location_request = location_request.json()
        weather_url = f'https://api.weatherapi.com/v1/current.json?key={api_key}&q={location_request["loc"]}&aqi=no'
    except Exception as e:
        return jsonify({'error': f"API Error {e}"})
    
    try:
        # Fetch weather data
        response = requests.get(weather_url)
        weather_data = response.json()
        
        if response.status_code == 200 and 'error' not in weather_data:
            location = weather_data['location']
            current = weather_data['current']
            
            prompt = (
                f"Current weather in {location['name']}, {location['region']}, {location['country']}:\n\n"
                f"- Temperature: {current['temp_c']}°C ({current['temp_f']}°F)\n"
                f"- Condition: {current['condition']['text']}\n"
                f"- Wind Speed: {current['wind_kph']} kph ({current['wind_mph']} mph)\n"
                f"- Pressure: {current['pressure_mb']} mb ({current['pressure_in']} in)\n"
                f"- Precipitation: {current['precip_mm']} mm ({current['precip_in']} in)\n"
                f"- Humidity: {current['humidity']}%\n"
                f"- Cloud Cover: {current['cloud']}%\n\n"
                f"Based on this data, recommend the best crops for this region and any other advice to enhance agricultural productivity. In 1000 words."
            )
            
            try:
                # Call the model's content generation method
                response = model.generate_content(prompt)
                response_text = response.text
                
                return jsonify({
                    'weather': weather_data,
                    'report': response_text
                })
            except Exception as e:
                return jsonify({'error': f"Response Error"})
        
        else:
            return jsonify({'error': "Unable to fetch weather data"})
    
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        # Insert into SQLite database
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)", (username, email, hashed_password))
        conn.commit()
        conn.close()

        flash('Account Created!', 'success')

        return redirect(url_for('signin'))

    return render_template('signup.html', title="Sign Up")

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Validate credentials
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        print(user)
        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['user_email'] = user[2]
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials', 'error')

    return render_template('signin.html', title="Sign In")

@app.route('/generate-response', methods=['POST'])
def generate_response():
    data = request.json
    prompt = data.get('prompt', '')
    user_email = session.get('user_email')

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    response = model.generate_content(f"PROMPT : {prompt} in 200 words. If prompt isn't related to agriculture then return 'Please specify your query in detail! I'm happy to chat about farming, crops, or anything related to the field.'")
    response_text = response.text

    # Store the chat data in the database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO chats (email, user_query, gemini_response)
        VALUES (?, ?, ?)
    ''', (user_email, prompt, response_text))
    conn.commit()
    conn.close()

    return jsonify({"response": response_text})

@app.route('/generate-crop-care', methods=['POST'])
def generate_crop_care():
    data = request.get_json()
    crop_name = data.get('crop_name')
    
    response = model.generate_content(f"PROMPT : Generate a care instructions for {crop_name} (crop) production also specify timing in months or days about proper growth in 800 words, use lists. If crop isn't valid return a polite text just to ensure that user enters a valid crop name.")
    response_text = response.text
    
    return jsonify({"response": response_text})

@app.route('/bank-loans', methods=['GET'])
def get_bank_loans():
    model = genai.GenerativeModel('gemini-1.5-flash', generation_config={"response_mime_type": "application/json", "response_schema": list[LoanOffer]})

    response = model.generate_content(
        "Generate a list of loan offers/schemes by the Indian Government for farmers. Return JSON format like this: {"
        '"bank_name": "HDFC Bank", '
        '"type": "Kisan Gold Card", '
        '"interest_rate": 8.0, '
        '"eligibility": "Farmers with a Kisan Credit Card", '
        '"features": "Instant loan approval, easy documentation."}'
        'Generate 10'
    )

    loans = response.text
    return jsonify({"loans": loans})

# Route to view and update account settings
@app.route('/account', methods=['GET', 'POST'])
def account():
    verification = verify_login()
    if verification is not True:
        return verification

    user_id = session.get('user_id')

    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm-password']

        if password != confirm_password or len(password) <= 6:
            flash('Invalid Password.', 'error')
            return redirect(url_for('account'))

        # Hash the new password
        hashed_password = generate_password_hash(password)

        # Update user details in the database
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET password = ? 
            WHERE id = ?
        """, (hashed_password, user_id))
        conn.commit()
        conn.close()

        flash('Account Updated!', 'success')
        return redirect(url_for('account'))

    # Fetch current user data
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, email FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    return render_template('account.html', title="Account Settings", user=user, page='account')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('signin'))

if __name__ == "__main__":
    app.run()
