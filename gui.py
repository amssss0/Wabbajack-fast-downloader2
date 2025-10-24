import logging
import os
import csv
import json
import sv_ttk
import xxhash
import requests
import base64
import struct
import threading
import queue
import zipfile
import ctypes
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional, Generator, List
from downloader import download_nexus_mods
from extract_modlist import generate_url, write_to_csv

# Theme Manager
class ThemeManager:
    COLORS = {
        'dark': { 
            'bg': '#1e1e1e',
            'fg': '#d4d4d4',
            'accent': '#3d3d3d',
            'highlight': '#007acc',
            'success': '#28a745',
            'warning': '#ffc107',
            'error': '#dc3545'
        }
    }

    @staticmethod
    def setup_theme(root: tk.Tk) -> None:
        sv_ttk.set_theme("dark")
        style = ttk.Style(root)
        colors = ThemeManager.COLORS['dark']

        style.configure('TFrame', background=colors['bg'])
        style.configure('TLabelframe', background=colors['bg'], padding=8, borderwidth=1, relief="solid")
        style.configure('TLabelframe.Label', font=('Segoe UI', 9, 'bold'),
                        background=colors['bg'], foreground=colors['highlight'])
        style.configure('TButton', padding=6, borderwidth=0, font=('Segoe UI', 9))
        style.configure('Accent.TButton', background=colors['highlight'], foreground=colors['fg'])
        style.configure('TEntry', fieldbackground=colors['accent'], borderwidth=0)
        style.configure('Horizontal.TProgressbar', thickness=4,
                       background=colors['highlight'])

# Console Output
class ConsoleOutput(tk.Text):
    def __init__(self, master: tk.Widget, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.config(state="disabled")
        self.tag_configure("SUCCESS", foreground="#28a745")
        self.tag_configure("ERROR", foreground="#dc3545")
        self.tag_configure("DEBUG", foreground="#6c757d")
        self.tag_configure("INFO", foreground="#d4d4d4") # Default text color

    def print(self, text: str) -> None: 
        self.config(state="normal")
        
        tag_to_apply = "INFO" # Default to INFO tag
        if text.startswith("["):
            end_tag_index = text.find("]")
            if end_tag_index != -1:
                tag = text[1:end_tag_index]
                if tag in ["SUCCESS", "ERROR", "DEBUG", "INFO"]:
                    tag_to_apply = tag

        self.insert(tk.END, text + "\n", tag_to_apply)
        self.see(tk.END)
        self.config(state="disabled")

# Text Scroll Combo
class TextScrollCombo(tk.Frame):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setup_widget()

    def setup_widget(self) -> None:
        self.grid_propagate(False)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        text_frame = ttk.Frame(self)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.grid_columnconfigure(0, weight=1)
        text_frame.grid_rowconfigure(0, weight=1)

        self.txt = ConsoleOutput(text_frame)
        self.txt.grid(row=0, column=0, sticky="nsew")
        self.configure_text_widget()

        scrollb = ttk.Scrollbar(text_frame, command=self.txt.yview)
        scrollb.grid(row=0, column=1, sticky='nsew')
        self.txt['yscrollcommand'] = scrollb.set

    def configure_text_widget(self) -> None:
        self.txt.configure(
            bg='#1a1a1a',
            fg='#ffffff',
            font=('Consolas', 9),
            insertbackground='#ffffff',
            selectbackground='#0078d4',
            selectforeground='#ffffff',
            borderwidth=0,
            padx=8,
            pady=4
        )

    def print(self, text: str) -> None:
        self.txt.print(text)

# Downloader Class
class Downloader:
    def __init__(self, app: 'Application', queue_size: int = 5):
        self.app = app
        self.state = {}
        self.download_queue = queue.Queue()
        self.pending_verifications = []
        self.csv_file = 'output.csv'
        self.state_file = 'download_state.json'
        self.queue_size = queue_size
        self.total_files = 0
        self.processed_files = 0
        

    def calculate_file_hash_base64(self, file_path: str) -> str:
        hasher = xxhash.xxh64(seed=0)
        with open(file_path, 'rb') as f:
            while data := f.read(1024*1024):
                hasher.update(data)
        digest_bytes = struct.pack('<Q', hasher.intdigest())
        return base64.b64encode(digest_bytes).decode('utf-8')

    def load_state(self):
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
        except Exception as e:
            self.log(f"Error loading state: {e}", error=True)

    def save_state(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            self.log(f"Error saving state: {e}", error=True)

    def verify_and_update_state(self, filepath: str, expected_hash: str, expected_size: str, url: str, success: bool):
        try:
            normalized_path = os.path.abspath(filepath)
            
            if success:
                mode = self.app.verification_mode_var.get()
                verified = False
                verification_details = ""

                if mode == "Skip":
                    verified = True
                    verification_details = "skipped (assumed success)"
                elif mode == "Size":
                    if not expected_size:
                        verified = False
                        verification_details = "failed (size missing in CSV)"
                    else:
                        actual_size = os.path.getsize(normalized_path)
                        verified = actual_size == int(expected_size)
                        verification_details = f"succeeded with size check (Expected: {expected_size}, Actual: {actual_size})" if verified else f"failed size check (Expected: {expected_size}, Actual: {actual_size})"
                else: # Default to Hash
                    if not expected_hash:
                        verified = False
                        verification_details = "failed (hash missing in CSV)"
                    else:
                        actual_hash = self.calculate_file_hash_base64(normalized_path)
                        verified = actual_hash == expected_hash
                        verification_details = "succeeded with hash check" if verified else "failed hash check"

                self.log(f"Verification {verification_details} for {os.path.basename(filepath)}.", success=verified, error=not verified)
                if expected_hash:
                    self.state[expected_hash] = {
                        'path': normalized_path,
                        'verified': verified
                    }
            else:
                self.log(f"Download failed for {os.path.basename(filepath)}", error=True)
                if expected_hash:
                    self.state[expected_hash] = {'path': None, 'verified': False}
            
            self.save_state()
        
        except Exception as e:
            self.log(f"Error during verification for {os.path.basename(filepath)}: {e}", error=True)
            if expected_hash:
                self.state[expected_hash] = {'path': None, 'verified': False}
            self.save_state()

    def process_csv_row(self, row: dict):
        url = row.get('URL')
        expected_hash = row.get('Hash')
        expected_size = row.get('Size')
        name = row.get('Name')

        if not url or not name:
            self.log(f"Skipping row with missing URL or Name: {row}", debug=True)
            self.processed_files += 1
            self.app.update_progress(self.processed_files, self.total_files)
            return

        filepath = os.path.join(self.app.download_location_var.get(), name)

        if self.check_existing_file(filepath, expected_hash, expected_size):
            self.processed_files += 1
            self.app.update_progress(self.processed_files, self.total_files)
            return

        self.download_queue.put((url, filepath))
        self.pending_verifications.append((filepath, expected_hash, expected_size, url))

    def check_existing_file(self, filepath: str, expected_hash: str, expected_size: str) -> bool:
        """Check if file exists and is valid based on the selected verification mode."""
        mode = self.app.verification_mode_var.get()

        # Check for file in state using hash as key
        if expected_hash and expected_hash in self.state:
            state_entry = self.state[expected_hash]
            state_path = state_entry.get('path')
            if state_entry.get('verified') and state_path and os.path.exists(state_path):
                self.log(f"File found in state: {os.path.basename(state_path)}", debug=True)
                
                if mode == "Skip":
                    self.log(f"Verification skipped (from state): {os.path.basename(state_path)}", debug=True)
                    return True
                
                try:
                    if mode == "Size":
                        if not expected_size or not expected_size.isdigit():
                             return False # Force re-download if size is bad in CSV
                        if os.path.getsize(state_path) == int(expected_size):
                            self.log(f"Size check passed (from state): {os.path.basename(state_path)}", debug=True)
                            return True
                    elif mode == "Hash":
                        # Already verified by hash if it's in state with verified:true
                        self.log(f"Hash check passed (from state): {os.path.basename(state_path)}", debug=True)
                        return True
                except (OSError, ValueError) as e:
                    self.log(f"Error checking file from state ({state_path}): {e}. Re-checking.", debug=True)
                    # Fall through to checking the original path

        # Fallback to checking the path from the CSV (for files from old versions or state errors)
        normalized_path = os.path.abspath(filepath)
        if not os.path.exists(normalized_path):
            self.log(f"File not found at expected path: {os.path.basename(filepath)}, will download.")
            return False

        # File exists at old path, now check based on mode
        if mode == "Skip":
            self.log(f"Verification skipped, file exists: {os.path.basename(filepath)}", debug=True)
            return True

        elif mode == "Size":
            try:
                if not expected_size or not expected_size.isdigit():
                    self.log(f"Size check failed: 'Size' is missing or invalid in CSV for {os.path.basename(filepath)}. Re-downloading.")
                    return False
                actual_size = os.path.getsize(normalized_path)
                if actual_size == int(expected_size):
                    self.log(f"Size check passed for {os.path.basename(filepath)}", debug=True)
                    return True
                else:
                    self.log(f"Size mismatch for {os.path.basename(filepath)} (Expected: {expected_size}, Actual: {actual_size}). Re-downloading.")
                    return False
            except (ValueError, TypeError) as e:
                self.log(f"Size check failed for {os.path.basename(filepath)} due to error: {e}. Re-downloading.")
                return False

        else: # Default to Hash mode
            if not expected_hash:
                self.log(f"Hash check failed: 'Hash' is missing in CSV for {os.path.basename(filepath)}. Re-downloading.")
                return False
            
            actual_hash = self.calculate_file_hash_base64(normalized_path)
            if actual_hash == expected_hash:
                self.log(f"Hash check passed (re-calculated): {os.path.basename(filepath)}", debug=True)
                # Update state with the correct key
                self.state[expected_hash] = {'path': normalized_path, 'verified': True}
                self.save_state()
                return True
            else:
                self.log(f"Hash mismatch for {os.path.basename(filepath)}. Re-downloading.")
                return False
            
        return False # Default to re-download

    def download_batch(self):
        urls = []
        filepaths = []
        url_map = {}

        while not self.download_queue.empty() and len(urls) < self.queue_size:
            url, filepath = self.download_queue.get()
            urls.append(url)
            filepaths.append(filepath)
            url_map[url] = filepath

        if not urls:
            return []

        try:
            cookie = "nexusmods_session="+self.app.session_var.get()
            game_id = self.app.game_id_var.get()

            if not game_id:
                self.log(f"Game ID is not set. Please fetch game details first.", error=True)
                return [(url_map[url], False) for url in urls]

            _, results = download_nexus_mods(urls, filepaths, cookie, game_id, logger=self.log)
            return [(url_map[url], result) for url, result in zip(urls, results)]
        except Exception as e:
            self.log(f"Batch download error: {e}", error=True)
            return [(url_map[url], False) for url in urls]

    def process_results(self, results: list):
        for filepath, result in results:
            verification_info = next((v for v in self.pending_verifications if v[0] == filepath), None)
            if verification_info:
                fp, expected_hash, expected_size, url = verification_info

                is_success = bool(result)
                actual_filepath = result if is_success else fp

                self.verify_and_update_state(actual_filepath, expected_hash, expected_size, url, is_success)
                self.pending_verifications.remove(verification_info)
                self.processed_files += 1
                self.app.update_progress(self.processed_files, self.total_files)

    def run(self):
        try:
            self.log("Download process started.")
            self.queue_size = self.app.queue_size_var.get()
            self.load_state()
            os.makedirs(self.app.download_location_var.get(), exist_ok=True)

            with open(self.csv_file, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = sorted(reader, key=lambda x: int(x.get('Size') or 0))
                #rows = rows[4033+100:]
                #rows = sorted(reader, key=lambda x: int(x.get('Size', 0)), reverse=True)
                self.total_files = len(rows)
                self.app.set_total_files(self.total_files)

                for i, row in enumerate(rows):
                    self.process_csv_row(row)
                    if self.download_queue.qsize() >= self.queue_size or i == len(rows)-1:
                        results = self.download_batch()
                        self.process_results(results)
                        self.save_state()

        except Exception as e:
            self.log(f"Download process failed: {e}", error=True)
        finally:
            self.save_state()
            self.app.download_complete()

    def log(self, message: str, error: bool = False, debug: bool = False, success: bool = False):
        """Centralized logging to GUI and file with level control"""
        # 1. Log to file
        if error:
            logging.error(message)
        elif debug:
            if self.app.debug_mode.get():
                logging.debug(message)
        else: # Includes success messages
            logging.info(message)

        # 2. Log to GUI console
        if debug and not self.app.debug_mode.get():
            return
        
        level = "INFO"
        if error:
            level = "ERROR"
        elif success:
            level = "SUCCESS"
        elif debug:
            level = "DEBUG"
            
        formatted_msg = f"[{level}] {message}"
        self.app.queue_put(('log', formatted_msg))

# Main Application
class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.setup_logging()
        self.output_file_path = 'output.csv'
        self.links_amount = 0
        self.processed_links = tk.IntVar()
        self.generator: Optional[Generator[List[str], None, None]] = None
        self.queue = queue.Queue()
        self.downloader: Optional[Downloader] = None
        self.queue_size_var = tk.IntVar(value=5)
        self.session_var = tk.StringVar(value="YOUR NEXUS SESSIONID")
        self.download_location_var = tk.StringVar(value="downloads")
        self.verification_mode_var = tk.StringVar(value="Size")
        self.game_domain_var = tk.StringVar(value="")
        self.game_name_var = tk.StringVar()
        self.game_id_var = tk.StringVar()
        
        self.config_data = {}
        self.load_data() # Load data first
        
        self.protocol("WM_DELETE_WINDOW", self.save_and_exit)

        self.setup_window() # Then setup window with loaded data
        self.create_widgets()
        self.check_output_file()
        self.set_game_domain_from_csv()
        
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filename='downloader.log',
            filemode='w' # Overwrite log on each run
        )
        logging.info("Logging initialized.")

    def load_data(self):
        try:
            with open('config.json', 'r') as f:
                self.config_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config_data = {}

        data = self.config_data
        self.session_var.set(data.get('nexusmods_session', self.session_var.get()))
        self.download_location_var.set(data.get('download_dir', self.download_location_var.get()))
        self.queue_size_var.set(data.get('parallel_queue_size', self.queue_size_var.get()))
        self.verification_mode_var.set(data.get('verification_mode', self.verification_mode_var.get()))
        self.game_domain_var.set(data.get('game_domain', self.game_domain_var.get()))

    def save_data(self):
        data = {
            'nexusmods_session': self.session_var.get(),
            'download_dir': self.download_location_var.get(),
            'parallel_queue_size': self.queue_size_var.get(),
            'verification_mode': self.verification_mode_var.get(),
            'game_domain': self.game_domain_var.get(),
            'window_geometry': self.geometry(),
        }
        with open('config.json', 'w') as f:
            json.dump(data, f, indent=2)

    def save_and_exit(self):
        self.save_data()
        self.quit()
        self.destroy()

    def set_game_domain_from_csv(self):
        if not os.path.exists(self.output_file_path):
            return

        try:
            with open(self.output_file_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                first_row = next(reader, None)
                if first_row:
                    url = first_row.get('URL')
                    if url:
                        try:
                            game_domain = url.split('/')[3]
                            self.game_domain_var.set(game_domain)
                            self.console.print(f"[INFO] Found game domain from CSV: {game_domain}")
                            self.fetch_game_details() # Automatically fetch details
                        except IndexError:
                            self.console.print("[ERROR] Could not parse game domain from the first URL in output.csv.")
        except Exception as e:
            self.console.print(f"[ERROR] Error reading output.csv to determine game domain: {e}")

    def setup_window(self) -> None:
        self.setup_windows_specific()
        ThemeManager.setup_theme(self)

        self.title('Wabbajack Fast Downloader2')
        self.geometry('1000x600')  # Set default
        self.minsize(800, 500)

        # Apply saved geometry if it exists, overriding the default
        if geometry := self.config_data.get('window_geometry'):
            self.geometry(geometry)
        

    def setup_windows_specific(self) -> None:
        if sys.platform != 'win32':
            return
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            self.iconbitmap(default="icon.ico")

            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            hwnd = self.winfo_id()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(2)),
                ctypes.sizeof(ctypes.c_int)
            )
        except Exception:
            pass

    def create_widgets(self):
        self.main_container = ttk.Frame(self, padding=8)
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_container.grid_columnconfigure(0, weight=2)
        self.main_container.grid_columnconfigure(1, weight=1)

        self.create_file_section()
        self.create_progress_section()
        self.create_console_section()
        self.create_right_panel()
        self.create_settings_section()  # Renamed method

    def create_file_section(self):
        file_frame = ttk.LabelFrame(self.main_container, text="Mod List Selection", padding=5)
        file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        file_frame.grid_columnconfigure(0, weight=1)

        self.file_path_entry = ttk.Entry(file_frame)
        self.file_path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        browse_btn = ttk.Button(file_frame, text="Browse", command=self.browse_file, width=8)
        browse_btn.grid(row=0, column=1, padx=(0, 2))

        extract_btn = ttk.Button(file_frame, text="Extract", command=self.extract_file, width=8, style="Accent.TButton")
        extract_btn.grid(row=0, column=2)

    def create_progress_section(self):
        progress_frame = ttk.LabelFrame(self.main_container, text="Download Progress", padding=5)
        progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(
            progress_frame,
            orient=tk.HORIZONTAL,
            style='text.Horizontal.TProgressbar',
            length=200
        )
        self.progress.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))

        self.progress_label = ttk.Label(progress_frame, text="0/0 files")
        self.progress_label.grid(row=0, column=1, padx=5)

        # Combined controls frame
        controls_frame = ttk.Frame(progress_frame)
        controls_frame.grid(row=1, column=0, columnspan=2, pady=(5, 0), sticky="ew")

        # Parallel downloads control
        settings_frame = ttk.Frame(controls_frame)
        settings_frame.pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(settings_frame, text="Parallel downloads:").pack(side=tk.LEFT, padx=(0, 5))
        self.queue_size_spin = ttk.Spinbox(
            settings_frame,
            from_=1,
            to=15,
            textvariable=self.queue_size_var,
            width=3
        )
        self.queue_size_spin.pack(side=tk.LEFT)

        # Session input section
        session_frame = ttk.Frame(controls_frame)
        session_frame.pack(side=tk.LEFT)

        ttk.Label(session_frame, text="NexusMods Session:").pack(side=tk.LEFT)
        self.entry = ttk.Entry(session_frame, textvariable=self.session_var, width=25)
        self.entry.pack(side=tk.LEFT, padx=5)

        # Button and download location container
        button_location_frame = ttk.Frame(progress_frame)
        button_location_frame.grid(row=2, column=0, columnspan=2, pady=(5, 0), sticky="ew")
        button_location_frame.grid_columnconfigure(1, weight=1)

        # Download button
        download_btn = ttk.Button(
            button_location_frame,
            text="Download Batch",
            command=self.start_download,
            width=15,
            style="Accent.TButton"
        )
        download_btn.grid(row=0, column=0, padx=(0, 10))

        # Download location input
        download_location_frame = ttk.Frame(button_location_frame)
        download_location_frame.grid(row=0, column=1, sticky="ew")
        download_location_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(download_location_frame, text="Download Location:").grid(row=0, column=0, padx=(0, 5))
        self.download_location_entry = ttk.Entry(
            download_location_frame,
            textvariable=self.download_location_var
        )
        self.download_location_entry.grid(row=0, column=1, sticky="ew")

    def create_console_section(self):
        console_frame = ttk.LabelFrame(self.main_container, text="Output", padding=5)
        console_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 0))
        console_frame.grid_columnconfigure(0, weight=1)
        console_frame.grid_rowconfigure(0, weight=1)

        self.console = TextScrollCombo(console_frame, width=600, height=300)
        self.console.grid(row=0, column=0, sticky="nsew")

    def create_right_panel(self):
        right_panel_frame = ttk.LabelFrame(self.main_container, text="Information", padding=5)
        right_panel_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=8, pady=(0, 0))
        right_panel_frame.grid_columnconfigure(0, weight=1)
        right_panel_frame.grid_rowconfigure(0, weight=1)

        self.info_text = ConsoleOutput(right_panel_frame)
        self.info_text.grid(row=0, column=0, sticky="nsew")

    def create_settings_section(self):
        settings_frame = ttk.Frame(self.main_container)
        settings_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # --- Verification Method ---
        verify_frame = ttk.LabelFrame(settings_frame, text="Verification Method")
        verify_frame.pack(side=tk.LEFT, padx=(0, 10), fill="y", anchor="n")

        ttk.Radiobutton(verify_frame, text="Hash Check", variable=self.verification_mode_var, value="Hash").pack(anchor="w", padx=5)
        ttk.Radiobutton(verify_frame, text="File Size Check", variable=self.verification_mode_var, value="Size").pack(anchor="w", padx=5)
        ttk.Radiobutton(verify_frame, text="Skip (File Exists)", variable=self.verification_mode_var, value="Skip").pack(anchor="w", padx=5)

        # --- Game Settings ---
        game_frame = ttk.LabelFrame(settings_frame, text="Game Selection")
        game_frame.pack(side=tk.LEFT, padx=(0, 10), fill="y", anchor="n")

        # Entry for game domain
        domain_frame = ttk.Frame(game_frame)
        domain_frame.pack(pady=5, padx=5, fill=tk.X)
        ttk.Label(domain_frame, text="Game Domain:").grid(row=0, column=0, sticky="w")
        ttk.Entry(domain_frame, textvariable=self.game_domain_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(domain_frame, text="Fetch", command=self.fetch_game_details, style="Accent.TButton").grid(row=0, column=2, padx=(5,0))
        domain_frame.columnconfigure(1, weight=1)

        # Display for fetched details
        details_frame = ttk.Frame(game_frame)
        details_frame.pack(pady=5, padx=5, fill=tk.X)
        ttk.Label(details_frame, text="Game Name:").grid(row=0, column=0, sticky="w")
        ttk.Label(details_frame, textvariable=self.game_name_var).grid(row=0, column=1, sticky="w")
        ttk.Label(details_frame, text="Game ID:").grid(row=1, column=0, sticky="w")
        ttk.Label(details_frame, textvariable=self.game_id_var).grid(row=1, column=1, sticky="w")


        # --- Other Settings ---
        other_frame = ttk.Frame(settings_frame)
        other_frame.pack(side=tk.LEFT, anchor="n")

        self.debug_mode = tk.BooleanVar(value=False)
        debug_check = ttk.Checkbutton(other_frame, text="Debug Mode", variable=self.debug_mode)
        debug_check.pack(side=tk.LEFT, anchor="n")

    def fetch_game_details(self):
        game_domain = self.game_domain_var.get().strip()
        if not game_domain:
            messagebox.showerror("Input Error", "Game Domain Name cannot be empty.")
            return

        self.console.print(f"Fetching details for game: {game_domain}...")
        try:
            query = '''
                query GetGameIdByDomainName($domainName: String!) {
                    game(domainName: $domainName) {
                        id
                        name
                    }
                }
            '''
            payload = {
                "query": query,
                "variables": {"domainName": game_domain},
                "operationName": "GetGameIdByDomainName"
            }
            headers = {"accept": "*/*", "content-type": "application/json"}
            api_url = "https://api-router.nexusmods.com/graphql"

            response = requests.post(api_url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            data = response.json()

            game_data = data.get('data', {}).get('game')
            if game_data and game_data.get('id'):
                game_id = str(game_data['id'])
                game_name = game_data['name']
                self.game_id_var.set(game_id)
                self.game_name_var.set(game_name)
                self.console.print(f"Successfully fetched details: {game_name} (ID: {game_id})")
            else:
                self.game_id_var.set("")
                self.game_name_var.set("")
                messagebox.showerror("API Error", f"Could not find game with domain: {game_domain}")
        except Exception as e:
            self.game_id_var.set("")
            self.game_name_var.set("")
            messagebox.showerror("Request Error", f"An error occurred: {e}")

    def browse_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Wabbajack mod list file", "*.wabbajack")])
        if filename:
            self.file_path_entry.delete(0, tk.END)
            self.file_path_entry.insert(tk.END, filename)

    def extract_file(self):
        try:
            filename = self.file_path_entry.get()
            if filename != "":
                with zipfile.ZipFile(filename, 'r') as zipObj:
                    metadata_name = "modlist"
                    with zipObj.open(metadata_name, 'r') as metadata:
                        self.extract_modlist(json.loads(metadata.read().decode('utf-8').replace("'", '"')))
        except Exception as e:
            self.console.print(f"Error extracting file: {e}")
            
    def extract_modlist(self, modlist_file):
        self.console.print("Processing JSON data...")
        
        processed_entries = []
        
        for entry in modlist_file.get("Archives", []):
            url = generate_url(entry)
            if url:
                entry_copy = entry.copy()  # Create a copy to avoid modifying original
                entry_copy['URL'] = url
                processed_entries.append(entry_copy)

        print(f"Processed {len(processed_entries)} entries.")
        
        if os.path.exists(self.output_file_path):
            answer = messagebox.askokcancel("Overwrite", "Do you want to overwrite the output file?")
            if not answer:
                self.console.print("Aborted by user.")
                return

        # Write all data to CSV file
        write_to_csv(processed_entries, self.output_file_path)
        self.console.print("Successfully wrote csv file.")
        #self.import_links()
        

    def check_output_file(self):
        if os.path.exists(self.output_file_path):
            self.console.print(f"Found output.csv file.")
            #self.import_links()

    def import_links(self):
        self.processed_links.set(0)
        try:
            self.console.print("Importing URLs from output.txt file...")
            self.links_amount = self.count_lines(self.output_file_path)
            if self.links_amount == 0:
                self.console.print("No URLs found in output.txt file.")
                return

            self.generator = self.read_links_in_batches(self.output_file_path, 20)
            self.progress['maximum'] = self.links_amount
            self.update_progress(0, self.links_amount)
            self.console.print(f"Imported {self.links_amount} URLs.")
        except FileNotFoundError:
            self.console.print(f"Error: The file {self.output_file_path} was not found.")
        except Exception as e:
            self.console.print(f"Error importing URLs: {e}")

    def count_lines(self, filename: str) -> int:
        with open(filename, 'r') as f:
            return sum(1 for _ in f)

    def read_links_in_batches(self, filename: str, batch_size: int) -> Generator[List[str], None, None]:
        with open(filename, 'r') as f:
            batch = []
            for line in f:
                batch.append(line.strip())
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            if batch:
                yield batch

    def start_download(self):
        download_dir = self.download_location_var.get()
        
        # Validate the download directory before starting the thread
        try:
            os.makedirs(download_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Invalid Path", f"Could not create download directory:\n{download_dir}\n\nError: {e}")
            self.console.print(f"ERROR: Invalid download directory: {download_dir}")
            return

        if not self.downloader:
            self.downloader = Downloader(self, queue_size=self.queue_size_var.get())
        threading.Thread(target=self.downloader.run, daemon=True).start()

    def update_progress(self, processed: int, total: int):
        self.progress['value'] = processed
        self.progress['maximum'] = total
        self.progress_label.config(text=f"{processed}/{total} files")
        self.info_text.print(f"[INFO] Processed: {processed}/{total} files")

    def set_total_files(self, total: int):
        self.links_amount = total
        self.update_progress(0, total)

    def download_complete(self):
        messagebox.showinfo("Complete", "Download process finished")
        self.info_text.print("[SUCCESS] Download process completed")

    def queue_put(self, item):
        self.queue.put(item)

    def process_queue(self):
        while not self.queue.empty():
            msg = self.queue.get()
            if msg[0] == 'log':
                self.console.print(msg[1])
        self.after(100, self.process_queue)

    def mainloop(self):
        self.process_queue()
        super().mainloop()

def main():
    app = Application()
    app.mainloop()

if __name__ == "__main__":
    main()