import streamlit as st
import pandas as pd
import asyncio
from datetime import datetime
from playwright_script import main as automate_booking, load_configs, save_configs
import subprocess

# Ensure that Playwright browsers are installed
def install_playwright_browsers():
    subprocess.run(["playwright", "install"], check=True)

install_playwright_browsers()

# Title of the Streamlit app
st.title('ATX Tee Time Booking System')

# Description
st.write('This application automatically books tee times based on rules defined for specific days of the week.')

# User input fields
first_name = st.text_input("First Name", "")
last_name = st.text_input("Last Name", "")
phone = st.text_input("Phone Number", "")
email = st.text_input("Email", "")

# Booking date input
selected_date = st.date_input("Select a date for booking", datetime.now())

# Load and display future bookings
configs = load_configs()

# Function to display future bookings
def display_bookings():
    if 'bookings' in configs and len(configs['bookings']) > 0:
        st.write("Future Bookings:")
        df = pd.DataFrame(configs['bookings'])
        st.dataframe(df)
    else:
        st.write("No future bookings found.")

# Display current and future bookings
st.subheader('Current and Future Bookings')
display_bookings()

# Command to run the booking automation
if st.button('Run Booking Automation'):
    st.write('Starting the booking process...')

    user_data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
        "email": email,
    }

    screenshots = asyncio.run(automate_booking(selected_date.strftime('%m/%d/%Y'), user_data))

    # Save the booking configuration
    if 'bookings' not in configs:
        configs['bookings'] = []
    configs['bookings'].append({
        "date": selected_date.strftime('%Y-%m-%d'),
        "time": "1:00 PM" if selected_date.weekday() not in [5, 6] else "7:00 AM",
        "status": "Booked"
    })
    save_configs(configs)

    st.write('Booking process completed!')

    # Check if screenshot path is not None before displaying
    if screenshots:
        st.image(screenshots, caption=screenshots)
    else:
        st.write("No screenshot available")

    # Refresh the view to display the latest bookings
    st.experimental_rerun()