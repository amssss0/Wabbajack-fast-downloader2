
import os
import csv
import json
import re
import requests
import cloudscraper

def get_nexusmods_download_url(url, cookie_str, game_id, logger):
    """Get direct download URL from a Nexus Mods page URL."""
    logger(f"Attempting to get download URL for: {url}")
    file_id_match = re.search(r'file_id=(\d+)', url)
    if not file_id_match:
        logger(f"Could not find file_id in URL: {url}", error=True)
        return None
    file_id = file_id_match.group(1)

    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'mobile': False
        }
    )

    cookies = {}
    if cookie_str:
        for cookie in cookie_str.split(';'):
            if cookie.strip():
                name, value = cookie.strip().split('=', 1)
                cookies[name] = value
    
    scraper.cookies.update(cookies)

    headers = {
        'origin': 'https://www.nexusmods.com',
        'referer': url,
        'x-requested-with': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    }
    scraper.headers.update(headers)

    try:
        response = scraper.post(
            'https://www.nexusmods.com/Core/Libs/Common/Managers/Downloads?GenerateDownloadUrl',
            data={'fid': file_id, 'game_id': game_id}
        )

        if response.status_code == 200:
            try:
                data = response.json()
                download_url = data.get('url')
                if download_url:
                    return download_url
                else:
                    logger(f"API returned success but no URL for {url}. Response: {data}", error=True)
                    return None
            except ValueError:
                logger(f"Failed to decode JSON for {url}. Response: {response.text}", error=True)
                return None
        else:
            logger(f"Failed to get download URL for {url}. Status: {response.status_code}, Body: {response.text}", error=True)
            return None
    except Exception as e:
        logger(f"Exception during request for {url}: {e}", error=True)
        return None

def get_filename_from_download_url(download_url, logger):
    """Get filename from Content-Disposition by making a HEAD request."""
    if not download_url:
        return None
    try:
        # We use stream=True to avoid downloading the whole file
        with requests.head(download_url, allow_redirects=True, timeout=10) as response:
            if response.status_code == 200:
                content_disposition = response.headers.get('Content-Disposition')
                if content_disposition:
                    filename_match = re.search(r'filename="([^"]+)"', content_disposition)
                    if filename_match:
                        return filename_match.group(1)
                    # Fallback for different Content-Disposition format
                    filename = content_disposition.split('filename=')[-1].strip('"')
                    if filename:
                        return filename
                # If no Content-Disposition, fallback to URL parsing
                return os.path.basename(download_url.split('?')[0])
            else:
                logger(f"Failed to fetch headers, status: {response.status_code} for {download_url}", error=True)
                return None
    except requests.RequestException as e:
        logger(f"Exception during HEAD request for {download_url}: {e}", error=True)
        return None

def console_logger(message, error=False, debug=False):
    """A simple logger that prints messages to the console."""
    level = "ERROR" if error else "DEBUG" if debug else "INFO"
    print(f"[{level}] {message}")

def main():
    print("--- Advanced File Renamer for Wabbajack Fast Downloader (Debug) ---")

    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        download_dir = config.get('download_dir')
        session_id = config.get('nexusmods_session', '')
        cookie_str = f"nexusmods_session={session_id}" if session_id else ""
        game_name = config.get('game_name', 'Fallout 4')
        games_list = config.get('games_list', {})
        game_id = games_list.get(game_name)

        if not download_dir:
            print("ERROR: 'download_dir' not set in config.json.")
            return
        if not game_id:
            print(f"ERROR: Game ID for '{game_name}' not found in games_list in config.json.")
            return
    except FileNotFoundError:
        print("ERROR: config.json not found.")
        return
    except json.JSONDecodeError:
        print("ERROR: Could not parse config.json.")
        return
        
    print(f"Using download directory: {download_dir}")
    print(f"Using game: {game_name} (ID: {game_id})")

    size_to_url_map = {}
    try:
        with open('output.csv', 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            print("Reading output.csv...")
            for i, row in enumerate(reader):
                # print(f"  Row {i}: {row}") # Uncomment for very verbose logging
                if row and row.get('Size') and row.get('URL'):
                    try:
                        size = int(row['Size'])
                        size_to_url_map[size] = row['URL']
                    except (ValueError, TypeError):
                        print(f"  Skipping row {i} due to invalid size: {row.get('Size')}")
                else:
                    print(f"  Skipping empty or invalid row {i}")

    except FileNotFoundError:
        print("ERROR: output.csv not found.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading CSV: {e}")
        return

    print(f"Built a map of {len(size_to_url_map)} files from output.csv.")
    if not size_to_url_map:
        print("No files to process. Exiting.")
        return
    
    renamed_count = 0
    error_count = 0
    
    local_files_by_size = {}
    try:
        for filename in os.listdir(download_dir):
            filepath = os.path.join(download_dir, filename)
            if os.path.isfile(filepath):
                try:
                    file_size = os.path.getsize(filepath)
                    if file_size not in local_files_by_size:
                        local_files_by_size[file_size] = []
                    local_files_by_size[file_size].append(filename)
                except OSError:
                    pass
    except OSError as e:
        print(f"ERROR: Could not access download directory: {e}")
        return

    print("Scanning for files to rename...")
    for size, nexus_url in size_to_url_map.items():
        if size in local_files_by_size:
            download_url = get_nexusmods_download_url(nexus_url, cookie_str, game_id, console_logger)
            correct_name = get_filename_from_download_url(download_url, console_logger)
            
            if correct_name:
                for local_filename in local_files_by_size[size]:
                    if local_filename != correct_name:
                        print(f"  Match found for size {size}:")
                        print(f"    Correct name: {correct_name}")
                        print(f"    Local file:   {local_filename}")
                        
                        source_path = os.path.join(download_dir, local_filename)
                        dest_path = os.path.join(download_dir, correct_name)

                        if os.path.exists(dest_path):
                            print(f"    Skipping rename, destination already exists: {correct_name}")
                            continue

                        try:
                            os.rename(source_path, dest_path)
                            print(f"  SUCCESS: Renamed {local_filename} to {correct_name}")
                            renamed_count += 1
                        except OSError as e:
                            print(f"  ERROR: Failed to rename {local_filename}: {e}")
                            error_count += 1
            else:
                error_count += 1

    print("\n--- Renaming Complete ---")
    print(f"Successfully renamed: {renamed_count} files.")
    if error_count > 0:
        print(f"Could not determine the correct name for {error_count} files (check logs for errors).")

if __name__ == "__main__":
    main()
