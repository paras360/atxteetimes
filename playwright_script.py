import asyncio
import json
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

async def book_tee_time(date, time_of_day, user_data):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Set headless to True
        page = await browser.new_page()
        
        try:
            # Navigate to the booking search page and wait for it to load
            await page.goto('https://web2.myvscloud.com/wbwsc/txaustinwt.wsc/search.html?display=detail&module=GR')
            await page.wait_for_load_state('networkidle')

            # Extra wait for any JavaScript to execute
            await asyncio.sleep(5)

            # Ensure that all necessary elements are visible using JavaScript
            await page.evaluate('document.querySelector("#secondarycode").style.display = "block"')
            await page.evaluate('document.querySelector("#numberofplayers").style.display = "block"')
            await page.evaluate('document.querySelector("#numberofholes").style.display = "block"')
            await page.evaluate('document.querySelector("#begindate").style.display = "block"')
            await page.evaluate('document.querySelector("#begintime").style.display = "block"')

            # Wait for the course selector to be visible
            await page.wait_for_selector('#secondarycode', state='visible', timeout=30000)
            await page.select_option('#secondarycode', '4')

            # Wait for and select the number of players
            await page.wait_for_selector('#numberofplayers', state='visible', timeout=30000)
            await page.select_option('#numberofplayers', '4')

            # Wait for and select the number of holes
            await page.wait_for_selector('#numberofholes', state='visible', timeout=30000)
            await page.select_option('#numberofholes', '18')

            # Wait for and fill in the date
            await page.wait_for_selector('#begindate', state='visible', timeout=30000)
            await page.fill('#begindate', date)

            # Wait for and fill in the begin time
            await page.wait_for_selector('#begintime', state='visible', timeout=30000)
            await page.fill('#begintime', time_of_day)

            # Wait for and click the search button
            await page.wait_for_selector('button:has-text("Search")', state='visible', timeout=30000)
            await page.click('button:has-text("Search")')

            # Wait for the booking results to load
            await page.wait_for_selector('.group__inner', timeout=30000)
            
            # Select the first available tee time
            first_available_button = await page.query_selector('.cart-button')
            if (first_available_button):
                await first_available_button.click()
                await page.wait_for_selector('form')

                # Fill in guest information
                await page.fill('#processingprompts_dailyfirstname', user_data['first_name'])
                await page.fill('#processingprompts_dailylastname', user_data['last_name'])
                await page.fill('#processingprompts_dailyphone', user_data['phone'])
                await page.fill('#processingprompts_dailyemail', user_data['email'])

                # Click the continue button to complete the booking
                await page.click('button:has-text("Continue")')

                # Take a screenshot for confirmation
                screenshot_path = f'screenshot_{date.replace("/", "-")}_{time_of_day.replace(":", "")}.png'
                await page.screenshot(path=screenshot_path)

                return screenshot_path
            else:
                print("No available tee times found.")

        except PlaywrightTimeoutError as e:
            print(f"Timeout Error: {e}")
        finally:
            await browser.close()

    return None

def get_optimal_time(day_of_week):
    if day_of_week in [5, 6]:  # Saturday or Sunday
        return '7:00 am'  # Morning tee time
    else:
        return '7:00 am'  # Default time for other days

async def main(selected_date, user_data):
    day_of_week = datetime.strptime(selected_date, '%m/%d/%Y').weekday()
    time_of_day = get_optimal_time(day_of_week)
    
    # Determine when to run the scraper based on booking rules
    if day_of_week in [5, 6]:  # Saturday or Sunday
        # Scraper should run on Tuesday at 9:00 am
        target_time = datetime.strptime(selected_date, '%m/%d/%Y') - timedelta(days=(day_of_week - 1))
        target_time = target_time.replace(hour=9, minute=0)
    else:
        # Scraper should run 7 days before at 7:00 am
        target_time = datetime.strptime(selected_date, '%m/%d/%Y') - timedelta(days=7)
        target_time = target_time.replace(hour=7, minute=0)

    now = datetime.now()
    delay = (target_time - now).total_seconds()
    
    if delay > 0:
        await asyncio.sleep(delay)
    
    screenshot_path = await book_tee_time(selected_date, time_of_day, user_data)
    return screenshot_path

def load_configs():
    try:
        with open('configs.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"bookings": []}

def save_configs(configs):
    with open('configs.json', 'w') as f:
        json.dump(configs, f)

if __name__ == "__main__":
    user_data = {
        "first_name": input("Enter your first name: "),
        "last_name": input("Enter your last name: "),
        "phone": input("Enter your phone: "),
        "email": input("Enter your email: "),
    }
    selected_date = input("Enter the date in mm/dd/yyyy format: ")
    asyncio.run(main(selected_date, user_data))