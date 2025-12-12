import os
import time
import requests
import re
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
DOWNLOAD_FOLDER = "polito_videos"
VIDEO_LOAD_WAIT_TIME = 15  # Generous wait time for the player to appear
MAX_FILE_SIZE_MB = 200  # Maximum output file size in MB
AUDIO_BITRATE = "128k"  # Good audio quality (prioritized)

def sanitize_filename(name):
    """Cleans up the text to make it a valid filename."""
    clean = re.sub(r'[^\w\s-]', '', name).strip()
    return clean

def cleanup_temp_files():
    """Remove all temporary files from interrupted downloads across all batch folders."""
    if not os.path.exists(DOWNLOAD_FOLDER):
        return
    
    temp_files_found = []
    
    # Check all subfolders for temp files
    for root, dirs, files in os.walk(DOWNLOAD_FOLDER):
        for file in files:
            if file.endswith('_temp.mp4'):
                temp_files_found.append(os.path.join(root, file))
    
    if temp_files_found:
        print(f"Found {len(temp_files_found)} interrupted download(s), cleaning up...")
        for temp_path in temp_files_found:
            try:
                os.remove(temp_path)
                print(f"   [V] Deleted: {os.path.basename(temp_path)}")
            except Exception as e:
                print(f"   [!] Could not delete {os.path.basename(temp_path)}: {e}")
    else:
        print("No interrupted downloads found.")

def get_video_duration(filename):
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return float(result.stdout.strip())
    except:
        return None

def compress_video(input_file, output_file, max_size_mb, audio_bitrate="128k"):
    """Compress video to target size, prioritizing audio quality."""
    print(f"   [...] Compressing video to max {max_size_mb}MB...")
    
    # Get video duration
    duration = get_video_duration(input_file)
    if not duration:
        print("   [!] Could not determine video duration, using conservative compression")
        video_bitrate = "500k"
    else:
        audio_bitrate_kbps = int(audio_bitrate.replace('k', ''))
        target_total_bitrate = (max_size_mb * 8192) / duration
        video_bitrate = max(100, int(target_total_bitrate - audio_bitrate_kbps - 50))
        video_bitrate = f"{video_bitrate}k"
        duration_mins = duration / 60
        print(f"   [...] Video: {duration_mins:.1f} mins, target bitrate: {video_bitrate}")
        print("   [...] Using CPU compression (240p, ultrafast)...")
    
    try:
        # Ultra-fast CPU encoding
        cmd = [
            'ffmpeg',
            '-i', input_file,
            '-vf', 'scale=-2:240',           # Scale to 240p (minimal resolution)
            '-c:v', 'libx264',
            '-b:v', video_bitrate,
            '-preset', 'ultrafast',          # Absolute fastest preset
            '-tune', 'zerolatency',          # Optimize for speed over quality
            '-crf', '28',                    # Lower quality = faster encoding
            '-threads', '0',                 # Use all CPU threads
            '-c:a', 'aac',
            '-b:a', audio_bitrate,           # Keep audio quality high
            '-movflags', '+faststart',
            '-y',
            output_file
        ]
        
        print("   [...] Encoding started (showing progress)...")
        result = subprocess.run(cmd)
        
        if result.returncode == 0:
            output_size = os.path.getsize(output_file) / (1024 * 1024)
            print(f"   [V] Compression complete! Output size: {output_size:.1f}MB")
            return True
        else:
            return False
    except FileNotFoundError:
        print("   [X] FFmpeg not found. Please install FFmpeg and add it to PATH.")
        return False
    except Exception as e:
        print(f"   [X] Compression failed: {e}")
        return False

def download_file(url, filename, cookies, should_compress=True, download_folder=None):
    # Use provided folder or default
    target_folder = download_folder if download_folder else DOWNLOAD_FOLDER
    
    # Ensure download folder exists
    os.makedirs(target_folder, exist_ok=True)
    
    local_filename = os.path.join(target_folder, f"{filename}.mp4")
    temp_filename = os.path.join(target_folder, f"{filename}_temp.mp4")
    
    # Check if the final file already exists
    if os.path.exists(local_filename):
        file_size_mb = os.path.getsize(local_filename) / (1024 * 1024)
        print(f"   [V] Already downloaded ({file_size_mb:.1f}MB) - Skipping")
        return

    print(f"   [...] Downloading to temporary file...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        # Download to temporary file first
        with requests.get(url, stream=True, cookies=cookies, headers=headers) as r:
            r.raise_for_status()
            with open(temp_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("   [V] Download complete!")
        
        # Check file size and compress if needed
        file_size_mb = os.path.getsize(temp_filename) / (1024 * 1024)
        print(f"   [...] Original file size: {file_size_mb:.1f}MB")
        
        if should_compress and file_size_mb > MAX_FILE_SIZE_MB:
            print(f"   [!] File exceeds {MAX_FILE_SIZE_MB}MB, compressing...")
            if compress_video(temp_filename, local_filename, MAX_FILE_SIZE_MB, AUDIO_BITRATE):
                # Delete temp file after successful compression
                os.remove(temp_filename)
            else:
                # If compression fails, keep the original
                print("   [!] Compression failed, keeping original file")
                os.rename(temp_filename, local_filename)
        else:
            # File is small enough or compression disabled, just rename it
            if not should_compress and file_size_mb > MAX_FILE_SIZE_MB:
                print(f"   [!] File size: {file_size_mb:.1f}MB (exceeds NotebookLM 200MB limit)")
            else:
                print("   [V] File size OK, no compression needed")
            os.rename(temp_filename, local_filename)
            
    except Exception as e:
        print(f"   [X] Download failed: {e}")
        # Clean up temp file if it exists
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except:
                pass

def main():
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
    
    # Clean up any interrupted downloads
    print("Checking for interrupted downloads...")
    cleanup_temp_files()
    print()

    # Ask for batch folder name
    print("------------------------------------------------")
    print("BATCH ORGANIZATION")
    print("Videos will be organized into a subfolder.")
    print("------------------------------------------------")
    batch_name = input("Enter a name for this batch folder (e.g., 'Lesson_Week1', 'Chapter3'): ").strip()
    
    if not batch_name:
        batch_name = f"batch_{int(time.time())}"
        print(f"No name provided, using: {batch_name}")
    
    # Create batch-specific folder
    batch_folder = os.path.join(DOWNLOAD_FOLDER, sanitize_filename(batch_name))
    os.makedirs(batch_folder, exist_ok=True)
    print(f"Videos will be saved to: {batch_folder}")
    print()

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

    # Ask about compression preference
    print("\n------------------------------------------------")
    print("VIDEO SIZE OPTIONS:")
    print("Videos larger than 200MB can be compressed (200MB is NotebookLM's max).")
    print("------------------------------------------------")
    print("Do you want to compress videos over 200MB?")
    print("  [1] Yes - Compress to 200MB (prioritizes audio quality)")
    print("  [2] No - Keep full size (may exceed NotebookLM limit)")
    print("------------------------------------------------")
    
    compress_choice = input("Enter your choice (1 or 2): ").strip()
    should_compress = compress_choice == "1"
    
    if should_compress:
        print(f"✓ Videos over 200MB will be compressed to 200MB")
    else:
        print(f"✓ Videos will be kept at full size")
    print()

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
                    download_file(video_url, clean_name, session_cookies, should_compress, batch_folder)
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

#.\.venv\Scripts\python -m main                                                       
