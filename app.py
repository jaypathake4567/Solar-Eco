from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import pickle
import pandas as pd
import numpy as np
import random
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import smtplib
from email.message import EmailMessage
import secrets
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Add a secret key for session management
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 600  # 10 minutes in seconds

# Load the trained model and feature columns
model, feature_cols = pickle.load(open("solar_model.pkl", "rb"))

# Hardcoded Twilio credentials
TWILIO_ACCOUNT_SID = "ACda22363ab0b338f46ab9be017afc6f57"
TWILIO_AUTH_TOKEN = "859a08a9aaca35c45624f2bf7d968c54"
TWILIO_PHONE_NUMBER = "+15076291316"

# Email credentials
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "vanshgujral175@gmail.com"
SENDER_PASSWORD = "xaow qamz ekyp hblu"

# Define panel brands and their characteristics
PANEL_BRANDS = {
    "Waaree": {"efficiency_boost": 0.05, "price_factor": 1.2, "power_base": 300, "lifespan": 26, "warranty": 18},
    "Tata Power": {"efficiency_boost": 0.03, "price_factor": 1.0, "power_base": 330, "lifespan": 25, "warranty": 11},
    "Luminous": {"efficiency_boost": 0.02, "price_factor": 0.85, "power_base": 350, "lifespan": 24, "warranty": 10},
    "Vikram Solar": {"efficiency_boost": 0.04, "price_factor": 1.1, "power_base": 320, "lifespan": 25, "warranty": 12},
    "Adani Solar": {"efficiency_boost": 0.03, "price_factor": 1.05, "power_base": 340, "lifespan": 25, "warranty": 15},
}

def send_email(to_email, name, panel_name, company_name):
    msg = EmailMessage()
    msg["Subject"] = "Solar Panel Booking Confirmation"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg.set_content(f"""
    Hello {name},
    Thank you for booking a {panel_name} solar panel from {company_name}.
    Your request has been received, and our team will contact you soon.
    Regards,
    SolarEco Team
    """)
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False

def send_otp_email(to_email, otp, name="User"):
    """Send OTP verification email"""
    msg = EmailMessage()
    msg["Subject"] = "SolarEco - Your Verification Code"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg.set_content(f"""
    Hello {name},
    
    Your verification code for SolarEco account registration is: {otp}
    
    This code will expire in 10 minutes.
    
    If you didn't request this code, please ignore this email.
    
    Regards,
    SolarEco Team
    """)
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        logger.info(f"OTP email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Error sending OTP email: {e}")
        return False

def make_call(to_phone, name, panel_name, company_name):
    logger.info(f"Entering make_call | To: {to_phone}")
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_PHONE_NUMBER:
        logger.error("Twilio credentials are not set")
        return None
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info(f"Twilio client initialized | SID ending: {TWILIO_ACCOUNT_SID[-4:]} | From: {TWILIO_PHONE_NUMBER}")
        
        # Validate phone number format
        if not to_phone.startswith('+') or len(to_phone) < 12:
            logger.error(f"Invalid phone format: {to_phone}. Must be E.164 (e.g., +917017336936)")
            return None
        
        message = f"Hello {name}, thank you for booking a {panel_name} solar panel from {company_name}. Our team will contact you soon."
        logger.info(f"Preparing Twilio call | To: {to_phone} | From: {TWILIO_PHONE_NUMBER} | Message: {message}")
        
        call = client.calls.create(
            twiml=f'<Response><Say>{message}</Say></Response>',
            to=to_phone,
            from_=TWILIO_PHONE_NUMBER
        )
        logger.info(f"Twilio call initiated | SID: {call.sid} | To: {to_phone} | From: {TWILIO_PHONE_NUMBER}")
        return call.sid
    except TwilioRestException as e:
        logger.error(f"Twilio API error | Code: {e.code} | Message: {e.msg}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in make_call | To: {to_phone} | Error: {str(e)}")
        return None

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/subsidy", methods=["GET", "POST"])
def subsidies():
    return render_template("subsidy.html")

@app.route("/send-otp", methods=["POST"])
def send_otp():
    """API endpoint to send OTP for registration"""
    try:
        data = request.json
        email = data.get("email")
        first_name = data.get("firstName", "User")
        
        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400
            
        # Generate a 6-digit OTP
        otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        # Store OTP in session with 10-minute expiry
        session[f"otp_{email}"] = otp
        logger.info(f"OTP generated for {email}: {otp}")
        
        # Send OTP via email
        if send_otp_email(email, otp, first_name):
            return jsonify({
                "success": True, 
                "message": "Verification code sent to your email"
            })
        else:
            return jsonify({
                "success": False, 
                "message": "Failed to send verification code. Please try again."
            }), 500
            
    except Exception as e:
        logger.error(f"Error sending OTP: {str(e)}")
        return jsonify({
            "success": False, 
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    """API endpoint to verify OTP"""
    try:
        data = request.json
        email = data.get("email")
        entered_otp = data.get("otp")
        
        if not email or not entered_otp:
            logger.warning("Missing email or OTP in verification request")
            return jsonify({
                "success": False, 
                "message": "Email and OTP are required"
            }), 400
            
        # Get stored OTP from session
        stored_otp = session.get(f"otp_{email}")
        logger.info(f"Verifying OTP for {email}. Entered: {entered_otp}, Stored: {stored_otp}")
        
        if not stored_otp:
            logger.warning(f"No OTP found in session for {email}")
            return jsonify({
                "success": False, 
                "message": "OTP expired or not found. Please request a new code."
            }), 400
            
        # Verify OTP
        if entered_otp == stored_otp:
            # Clear OTP from session after successful verification
            session.pop(f"otp_{email}", None)
            logger.info(f"OTP verified successfully for {email}")
            
            # Set a flag in session indicating this email is verified
            session[f"verified_{email}"] = True
            
            return jsonify({
                "success": True, 
                "message": "OTP verified successfully"
            })
        else:
            logger.warning(f"Invalid OTP entered for {email}")
            return jsonify({
                "success": False, 
                "message": "Invalid verification code. Please try again."
            }), 400
            
    except Exception as e:
        logger.error(f"Error verifying OTP: {str(e)}")
        return jsonify({
            "success": False, 
            "message": f"An error occurred: {str(e)}"
        }), 500

@app.route("/create-user", methods=["POST"])
def create_user():
    """API endpoint to handle Firebase user creation result"""
    try:
        data = request.json
        email = data.get("email")
        success = data.get("success")
        error = data.get("error")
        
        if success:
            logger.info(f"Firebase user created successfully for {email}")
            return jsonify({
                "success": True,
                "message": "User account created successfully"
            })
        else:
            logger.error(f"Firebase error for {email}: {error}")
            return jsonify({
                "success": False,
                "message": f"Firebase error: {error}"
            })
    except Exception as e:
        logger.error(f"Error in create-user endpoint: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        }), 500

@app.route("/recommendation", methods=["GET", "POST"])
def recommendation():
    if request.method == "POST":
        try:
            budget = int(request.form["budget"])
            climate = request.form["climate"]
            
            # Validate budget
            if budget < 10000:
                return render_template("index.html", error="Budget must be at least ₹10,000")
                
            # Map climate to panel characteristics
            climate_characteristics = {
                "Tropical": {"temp_range": (28, 38), "humidity_range": (60, 90), "best_for": "Hot"},
                "Dry": {"temp_range": (30, 45), "humidity_range": (20, 50), "best_for": "Hot"},
                "Temperate": {"temp_range": (18, 28), "humidity_range": (40, 70), "best_for": "Moderate"}
            }
            
            climate_data = climate_characteristics[climate]
            
            # Create panel configurations for each brand
            all_panels = []
            
            for brand, specs in PANEL_BRANDS.items():
                # Base panel configuration
                temp_base = np.random.randint(*climate_data["temp_range"])
                humidity_base = np.random.randint(*climate_data["humidity_range"])
                
                # Create panel data
                panel_data = {
                    "Brand": brand,
                    "Temperature (°C)": temp_base,
                    "Humidity (%)": humidity_base,
                    "Dust_Level": np.random.choice(["Low", "Medium", "High"], p=[0.4, 0.4, 0.2]),
                    "Days_Since_Cleaning": np.random.randint(1, 31),
                    "Panel_Age (years)": 0,  # New panels
                    "Type": "Polycrystalline",
                    "Best_Climate": climate_data["best_for"],
                    "Lifespan": specs["lifespan"],
                    "Warranty": specs["warranty"],
                }
                
                all_panels.append(panel_data)
            
            # Convert to DataFrame
            df = pd.DataFrame(all_panels)
            
            # Calculate pricing based on brand specifications and budget
            total_price_factor = sum(specs["price_factor"] for specs in PANEL_BRANDS.values())
            budget_per_unit = budget / total_price_factor
            
            for i, row in df.iterrows():
                brand = row["Brand"]
                price_factor = PANEL_BRANDS[brand]["price_factor"]
                df.at[i, "Price"] = int(budget_per_unit * price_factor)
                
                # Vary power based on brand and add some randomness
                power_base = PANEL_BRANDS[brand]["power_base"]
                df.at[i, "Power"] = power_base + np.random.randint(-30, 30)
            
            # Prepare data for model prediction
            df_pred = df.copy()
            # Create copy of required columns for prediction
            df_input = df_pred[["Temperature (°C)", "Humidity (%)", "Dust_Level", 
                               "Days_Since_Cleaning", "Panel_Age (years)"]].copy()
            
            # Create dummy variables for categorical features
            df_input = pd.get_dummies(df_input)
            
            # Add missing columns if any
            for col in feature_cols:
                if col not in df_input.columns:
                    df_input[col] = 0
            
            # Make sure we only use the columns the model was trained on
            for col in df_input.columns:
                if col not in feature_cols:
                    df_input.drop(col, axis=1, inplace=True)
            
            # Ensure all feature columns are present
            for col in feature_cols:
                if col not in df_input.columns:
                    df_input[col] = 0
            
            # Reorder columns to match feature_cols order
            df_input = df_input[feature_cols]
            
            # Add the interaction term if your model uses it
            if "Temp_Humidity" in feature_cols:
                df_input["Temp_Humidity"] = df_pred["Temperature (°C)"] * df_pred["Humidity (%)"] / 100
            
            # Predict efficiency
            predictions = model.predict(df_input)
            df["Base_Efficiency"] = predictions
            
            # Apply brand-specific efficiency boost
            for i, row in df.iterrows():
                brand = row["Brand"]
                boost = PANEL_BRANDS[brand]["efficiency_boost"]
                df.at[i, "Efficiency"] = round(row["Base_Efficiency"] + boost * 100, 1)  # Convert to percentage
            
            # Select top 3 panels based on a combination of efficiency and price value
            df["Value_Score"] = df["Efficiency"] / (df["Price"] / 10000)  # Higher efficiency per 10k rupees is better
            top3 = df.sort_values("Value_Score", ascending=False).head(3)
            
            # Format result for display
            result = []
            for i, row in top3.iterrows():
                result.append({
                    "brand": row["Brand"],
                    "type": row["Type"],
                    "price": int(row["Price"]),
                    "efficiency": row["Efficiency"],
                    "power": f"{int(row['Power'])}W",
                    "lifespan": f"{int(row['Lifespan'])} years",
                    "warranty": f"{int(row['Warranty'])} years",
                    "climate": row["Best_Climate"]
                })
            
            return render_template("recommendation.html", result=result)
            
        except Exception as e:
            logger.error(f"Error in recommendation: {str(e)}")
            return render_template("recommendation.html", error=f"Error: {str(e)}")
    
    return render_template("recommendation.html")

@app.route("/efficiency", methods=["GET", "POST"])
def efficiency():
    if request.method == "POST":
        try:
            dust = request.form["dust"]
            age = int(request.form["age"])
            cleaned = int(request.form["cleaned"])
            temp = int(request.form["temp"])
            humid = int(request.form["humid"])
            
            # Prepare the input data for prediction
            data = {
                "Temperature (°C)": temp,
                "Humidity (%)": humid,
                "Dust_Level": dust,
                "Days_Since_Cleaning": cleaned,
                "Panel_Age (years)": age,
            }
            
            df = pd.DataFrame([data])
            df_input = pd.get_dummies(df)
            
            # Add missing columns if any
            for col in feature_cols:
                if col not in df_input.columns:
                    df_input[col] = 0
            
            # Only use the columns the model was trained on
            df_input = df_input[feature_cols]
            
            # Add interaction term if model uses it
            if "Temp_Humidity" in feature_cols:
                df_input["Temp_Humidity"] = df["Temperature (°C)"] * df["Humidity (%)"] / 100
            
            prediction = model.predict(df_input)[0]
            return render_template("efficiency.html", prediction=round(prediction, 2))
            
        except Exception as e:
            logger.error(f"Error in efficiency calculation: {str(e)}")
            return render_template("efficiency.html", error=f"Error: {str(e)}")
    
    return render_template("efficiency.html")

@app.route("/book", methods=["POST"])
def book():
    logger.info("Received POST request to /book")
    try:
        data = request.get_json()
        if not data:
            logger.warning("No JSON data received")
            return {"error": "No data provided"}, 400
        
        name = data.get("name")
        phone = data.get("phone")
        email = data.get("email")
        panel_name = data.get("panelName")
        company_name = data.get("brandName")

        logger.info(f"Booking data: {data}")
        if not all([name, phone, email, panel_name, company_name]):
            logger.warning("Validation failed: Missing fields")
            return {"error": "All fields are required"}, 400

        # Save booking to file
        booking_data = f"Name: {name}, Phone: {phone}, Email: {email}, Panel: {panel_name}, Company: {company_name}\n"
        try:
            with open("booking.txt", "a") as f:
                f.write(booking_data)
            logger.info(f"Booking saved: {booking_data.strip()}")
        except Exception as e:
            logger.error(f"Failed to save booking: {e}")

        # Send email
        try:
            send_email(email, name, panel_name, company_name)
        except Exception as e:
            logger.error(f"Email failed: {e}")

        # Trigger Twilio call
        call_sid = make_call(phone, name, panel_name, company_name)
        call_status = "success" if call_sid else "failed"
        logger.info(f"Call attempt completed | Status: {call_status} | SID: {call_sid if call_sid else 'None'}")

        response = {
            "message": "Booking processed",
            "booking_saved": "success",
            "call_status": call_status
        }
        logger.info(f"Response: {response}")
        return response, 200

    except Exception as e:
        logger.error(f"Error in /book: {str(e)}")
        return {"error": f"Internal server error: {str(e)}"}, 500

# Route for logout functionality
@app.route("/logout")
def logout():
    # Client-side Firebase logout is handled in JavaScript
    # This route is just to redirect to the home page
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)
