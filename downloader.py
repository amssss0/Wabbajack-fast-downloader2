import re
import os
import time
import asyncio
import aiohttp
import aiofiles
from tqdm import tqdm
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
    essential_cookies = ['nexusmods_session']
    for cookie in cookie_str.split(';'):
        if cookie.strip():
            name, value = cookie.strip().split('=', 1)
            if any(essential_cookie in name for essential_cookie in essential_cookies):
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

class DownloadManager:
    def __init__(self):
        self.downloads = {}
        self.progress_bars = {}
        self.success_status = {}
        self.results = {}
        self.running = False
        self.loop = None
        self.current_tasks = []
        
    async def download_file(self, gid, url, filepath):
        """Download a file asynchronously with progress tracking."""
        output_dir = os.path.dirname(filepath)
        os.makedirs(output_dir, exist_ok=True)
        
        display_name = os.path.basename(filepath)
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
            
        pbar = tqdm(
            total=100,
            unit='%',
            desc=f"{display_name}",
            position=len(self.progress_bars),
            leave=True,
            bar_format='{desc:<30} |{bar}| {percentage:3.0f}% {rate_fmt}{postfix}'
        )
        
        self.progress_bars[gid] = pbar
        self.success_status[gid] = False
        
        try:
            timeout = aiohttp.ClientTimeout(total=None, connect=1, sock_connect=1, sock_read=10)
            connector = aiohttp.TCPConnector(limit=16, force_close=True, enable_cleanup_closed=True)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status != 200:
                        pbar.set_postfix_str(f"Failed: HTTP {response.status}")
                        return False

                    # Determine correct filename from Content-Disposition or URL
                    correct_filename = None
                    content_disposition = response.headers.get("Content-Disposition")
                    if content_disposition:
                        filename_match = re.search(r'filename="([^"]+)"', content_disposition)
                        if filename_match:
                            correct_filename = filename_match.group(1)
                        else:
                            # Fallback for different Content-Disposition format
                            filename_part = content_disposition.split('filename=')[-1].strip('"')
                            if filename_part:
                                correct_filename = filename_part
                    
                    if not correct_filename:
                        # If no Content-Disposition, fallback to URL parsing
                        correct_filename = os.path.basename(url.split('?')[0])

                    # Reconstruct the final path with the correct filename
                    if correct_filename:
                        output_dir = os.path.dirname(filepath)
                        final_filepath = os.path.join(output_dir, correct_filename)
                    else:
                        final_filepath = filepath

                    # Get file size
                    total_size = int(response.headers.get('content-length', 0)) or None
                    if total_size:
                        downloaded = 0
                        chunk_size = 1024 * 1024  # 1MB chunks
                        
                        # Open file for writing
                        async with aiofiles.open(final_filepath, 'wb') as f:
                            start_time = time.time()
                            async for chunk in response.content.iter_chunked(chunk_size):
                                await f.write(chunk)
                                downloaded += len(chunk)
                                
                                # Update progress bar
                                if total_size:
                                    progress = int(downloaded / total_size * 100)
                                    elapsed = time.time() - start_time
                                    if elapsed > 0:
                                        speed = downloaded / elapsed / 1024 / 1024  # MB/s
                                        pbar.update(progress - pbar.n)
                                        pbar.set_postfix_str(f"Speed: {speed:.2f} MB/s")
                    else:
                        # If content-length is not available, download without progress
                        async with aiofiles.open(final_filepath, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024 * 1024):
                                await f.write(chunk)
                            pbar.update(100)
                    
                    pbar.update(100 - pbar.n)  # Ensure we reach 100%
                    pbar.set_postfix_str("Complete")
                    self.success_status[gid] = True
                    self.results[gid] = final_filepath
                    return True
                    
        except Exception as e:
            pbar.set_postfix_str(f"Failed: {str(e)}")
            self.results[gid] = False
            return False
        finally:
            pbar.close()
            # Remove from active downloads
            if gid in self.downloads:
                del self.downloads[gid]
            if gid in self.progress_bars:
                del self.progress_bars[gid]

    def add_download(self, url, filepath):
        """Add a download with specific filepath."""
        gid = f"download_{len(self.downloads) + 1}"
        self.downloads[gid] = {
            'url': url,
            'filepath': filepath,
            'display_name': os.path.basename(filepath)
        }
        self.results[gid] = False
        return gid
        
    def start_monitor(self):
        """Start downloading all queued files."""
        if self.running:
            return
            
        self.running = True
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Start all downloads
        tasks = []
        for gid, info in self.downloads.items():
            task = self.loop.create_task(self.download_file(gid, info['url'], info['filepath']))
            tasks.append(task)
            
        self.current_tasks = tasks
        
        # Run downloads in a separate thread
        import threading
        def run_loop():
            self.loop.run_until_complete(asyncio.gather(*tasks))
            self.running = False
            
        threading.Thread(target=run_loop, daemon=True).start()
        
    def wait_for_downloads(self):
        """Wait for all downloads to complete."""
        while self.running:
            time.sleep(0.5)
            
    def shutdown(self):
        """Shutdown the download manager."""
        self.running = False
        
        # Cancel any remaining tasks
        if self.loop and self.current_tasks:
            for task in self.current_tasks:
                if not task.done():
                    task.cancel()
                    
        # Close all progress bars
        for pbar in self.progress_bars.values():
            pbar.close()
            
    def get_success_status(self):
        """Get success status of all downloads."""
        return [self.success_status[gid] for gid in self.success_status]

def download_nexus_mods(urls, filepaths, cookie_str, game_id, logger):
    """
    Download multiple Nexus mods in parallel with specific filepaths.

    Args:
        urls (list): List of Nexus Mods URLs
        filepaths (list): List of complete filepaths where files should be saved
        cookie_str (str): Cookie string for authentication
        game_id (str): The Nexus Mods game ID.
        logger (function): Logger function for output.

    Returns:
        dict: Empty dictionary (for compatibility).
        list: List of success statuses (True/False) for each download.
    """
    if len(urls) != len(filepaths):
        raise ValueError("Number of URLs must match number of filepaths")

    manager = DownloadManager()
    url_to_gid = {}

    for i, url in enumerate(urls):
        download_url = get_nexusmods_download_url(url, cookie_str, game_id, logger)
        if download_url:
            gid = manager.add_download(download_url, filepaths[i])
            url_to_gid[url] = gid

    if not manager.downloads:
        return {}, [False] * len(urls)

    manager.start_monitor()

    try:
        manager.wait_for_downloads()
        logger("Batch downloads completed.")
    except KeyboardInterrupt:
        logger("Download interrupted by user.")
    finally:
        manager.shutdown()

    final_results = []
    for url in urls:
        gid = url_to_gid.get(url)
        if gid:
            final_results.append(manager.results.get(gid, False))
        else:
            final_results.append(False)

    return {}, final_results
