import os
import time
import requests
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
DOWNLOAD_FOLDER = "polito_videos"
VIDEO_LOAD_WAIT_TIME = 15  # Generous wait time for the player to appear

def sanitize_filename(name):
    """Cleans up the text to make it a valid filename."""
    clean = re.sub(r'[^\w\s-]', '', name).strip()
    return clean

def download_file(url, filename, cookies):
    local_filename = os.path.join(DOWNLOAD_FOLDER, f"{filename}.mp4")
    
    if os.path.exists(local_filename):
        print(f"   [!] File already exists: {local_filename}")
        return

    print(f"   [...] Downloading to {local_filename}...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        with requests.get(url, stream=True, cookies=cookies, headers=headers) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("   [V] Download complete!")
    except Exception as e:
        print(f"   [X] Download failed: {e}")

def main():
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)

    print("Launching Chrome...")
    driver = webdriver.Chrome()
    driver.maximize_window()
    
    # 1. Open the portal
    driver.get("https://didattica.polito.it/")

    # 2. Manual Login Wait
    print("------------------------------------------------")
    print("PLEASE LOG IN MANUALLY IN THE BROWSER WINDOW.")
    print("Navigate to the specific course page so the blue links are visible.")
    print("------------------------------------------------")
    input("Press ENTER here once the page is fully loaded and ready...")

    # 3. Collect Unique IDs first (This prevents StaleElementReferenceException)
    print("Scanning for videos...")
    sidebar_selector = "a.link_vc_date"
    
    video_data = []
    
    try:
        # We grab the 'data-bbb-id' and the text for every link found
        elements = driver.find_elements(By.CSS_SELECTOR, sidebar_selector)
        for el in elements:
            try:
                # [cite_start]Based on your source code: [cite: 159, 160]
                bbb_id = el.get_attribute("data-bbb-id")
                text_content = el.text
                if bbb_id and text_content.strip():
                    video_data.append((bbb_id, text_content))
            except:
                continue
                
        print(f"Found {len(video_data)} videos to process.")
        
    except Exception as e:
        print(f"Error finding links: {e}")
        driver.quit()
        return

    # Capture cookies
    session_cookies = {cookie['name']: cookie['value'] for cookie in driver.get_cookies()}

    # 4. Iterate using the IDs
    for i, (bbb_id, raw_text) in enumerate(video_data):
        print(f"Processing ({i+1}/{len(video_data)}): {raw_text}")
        
        try:
            # --- ROBUST FIND: Find the specific element by its ID right now ---
            # This ensures the element is fresh and not 'stale'
            xpath_selector = f"//a[@data-bbb-id='{bbb_id}']"
            link_element = driver.find_element(By.XPATH, xpath_selector)
            
            # Scroll to center to avoid header overlap
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_element)
            time.sleep(1)
            
            # Force Click
            driver.execute_script("arguments[0].click();", link_element)
            
            # Wait for the <video> tag
            try:
                # Wait for any video tag to appear with a longer timeout
                video_element = WebDriverWait(driver, VIDEO_LOAD_WAIT_TIME).until(
                    EC.presence_of_element_located((By.TAG_NAME, "video"))
                )
                
                # Wait for the video source to be populated
                wait_time = 0
                video_url = None
                while wait_time < 10:
                    video_url = video_element.get_attribute("src")
                    if video_url and video_url.strip():
                        break
                    time.sleep(1)
                    wait_time += 1
                    # Re-find the video element in case it changed
                    try:
                        video_element = driver.find_element(By.TAG_NAME, "video")
                    except Exception:
                        pass
                
                if not video_url:
                    # Try to find source tags inside video
                    sources = video_element.find_elements(By.TAG_NAME, "source")
                    for source in sources:
                        src = source.get_attribute("src")
                        if src:
                            video_url = src
                            break
                
                if video_url and (video_url.strip()):
                    clean_name = sanitize_filename(raw_text)
                    download_file(video_url, clean_name, session_cookies)
                else:
                    print(f"   [X] Video URL not found. Found: {video_url}")

            except Exception as e:
                print(f"   [X] Timed out waiting for video player: {e}")
                # Try to go back to the main page to recover
                try:
                    driver.back()
                    time.sleep(2)
                except Exception:
                    pass

        except Exception as e:
            print(f"   [X] Error interacting with link: {e}")

    print("All done!")
    driver.quit()

if __name__ == "__main__":
    main()