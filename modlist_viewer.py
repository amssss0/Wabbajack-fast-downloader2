import json
import logging
import re
import urllib.request
import urllib.error
import csv
import time
import http.client
import math
import os
import imgui
import glfw
from imgui.integrations.glfw import GlfwRenderer
import OpenGL.GL as gl
import pyperclip

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
API_ENDPOINT_URL = "https://api-router.nexusmods.com/graphql"

# --- API Interaction ---
def query_nexus(payload, cookies_string=None):
    """
    Sends a GraphQL query to the Nexus Mods API with retries.
    Uses the globally defined API_ENDPOINT_URL.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36",
        "Content-type": "application/json",
        "Accept": "application/json",
    }
    if cookies_string:
        headers["Cookie"] = cookies_string

    json_data = json.dumps(payload).encode("utf-8")
    request_obj = urllib.request.Request(API_ENDPOINT_URL, data=json_data, headers=headers)

    max_retries = 3
    retry_delay = 7
    
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(request_obj, timeout=30) as response:
                content = response.read()
                resp = json.loads(content)
                
                if resp.get("errors"):
                    logging.error(f"GraphQL API Errors (Attempt {attempt}/{max_retries}): {resp['errors']}")
                    if attempt == max_retries: return None
                elif resp.get("data"):
                    return resp["data"]
                else:
                    logging.warning(f"No 'data' or 'errors' field (Attempt {attempt}/{max_retries}). Response: {str(resp)[:200]}")
                    if attempt == max_retries: return None
        
        except urllib.error.HTTPError as e:
            logging.error(f"HTTP Error (Attempt {attempt}/{max_retries}): {e.code} {e.reason}")
            try: logging.error(f"HTTP Error Body: {e.read().decode()[:500]}")
            except Exception: pass
            if 400 <= e.code < 500 and e.code not in [408, 429]:
                logging.warning(f"Client error {e.code}. Not retrying.")
                return None
            if attempt == max_retries: return None
        except (urllib.error.URLError, http.client.RemoteDisconnected, TimeoutError, ConnectionResetError) as e:
            logging.error(f"URL/Connection Error (Attempt {attempt}/{max_retries}): {type(e).__name__} - {e}")
            if attempt == max_retries: return None
        except json.JSONDecodeError as e:
            logging.error(f"JSON Decode Error (Attempt {attempt}/{max_retries}): {e.msg}")
            if attempt == max_retries: return None
        except Exception as e:
            logging.error(f"Unexpected error (Attempt {attempt}/{max_retries}): {type(e).__name__} - {e}")
            if attempt == max_retries: return None
        
        if attempt < max_retries:
            logging.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            
    return None

def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def find_font():
    font_paths = [
        "C:/Windows/Fonts/SegoeUI.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "C:/Windows/Fonts/Verdana.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            return path
    return None

def impl_glfw_init(window_name="Nexus Mods Collection Viewer", width=1200, height=800):
    """Initialize GLFW window"""
    if not glfw.init():
        return None, None
    
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, gl.GL_TRUE)
    
    window = glfw.create_window(width, height, window_name, None, None)
    glfw.make_context_current(window)
    
    if not window:
        glfw.terminate()
        return None, None

    imgui.create_context()
    impl = GlfwRenderer(window)
    io = imgui.get_io()

    font_path = find_font()
    if font_path:
        io.fonts.add_font_from_file_ttf(font_path, 18)
    
    impl.refresh_font_texture()
    
    return window, impl

class ModViewerApp:
    def __init__(self, mod_data):
        self.sorted_mods = sorted(mod_data, key=lambda x: x['Size'], reverse=True)
        self.current_page = 0
        self.page_size = 5
        self.total_pages = (len(self.sorted_mods) + self.page_size - 1) // self.page_size
        self.search_query = ""
        self.filtered_mods = self.sorted_mods.copy()
        self.notification = ""
        self.notification_time = 0
        self.notification_color = (0.2, 0.8, 0.2, 1.0)
        self.last_copied_index = -1
        
        # Color scheme
        self.colors = {
            'header_bg': (0.1, 0.15, 0.2, 1.0),
            'card_bg': (0.15, 0.2, 0.25, 1.0),
            'card_hover': (0.2, 0.25, 0.3, 1.0),
            'accent': (0.2, 0.8, 0.9, 1.0),
            'accent_hover': (0.3, 0.9, 1.0, 1.0),
            'text': (0.95, 0.95, 0.95, 1.0),
            'text_gray': (0.6, 0.6, 0.6, 1.0),
            'success': (0.2, 0.8, 0.2, 1.0),
            'warning': (0.9, 0.7, 0.2, 1.0),
            'size_color': (0.3, 0.9, 0.5, 1.0),
            'copied_highlight': (1.0, 0.8, 0.0, 1.0),
        }
    
    def show_notification(self, message, is_error=False):
        self.notification = message
        self.notification_time = time.time()
        self.notification_color = (0.9, 0.2, 0.2, 1.0) if is_error else (0.2, 0.8, 0.2, 1.0)
    
    def copy_to_clipboard(self, text, index):
        try:
            pyperclip.copy(text)
            self.show_notification(f"✓ URL copied to clipboard!")
            self.last_copied_index = index
        except Exception as e:
            self.show_notification(f"✗ Failed to copy: {str(e)}", True)
    
    def filter_mods(self):
        if not self.search_query:
            self.filtered_mods = self.sorted_mods.copy()
        else:
            query = self.search_query.lower()
            self.filtered_mods = [
                mod for mod in self.sorted_mods
                if query in mod.get('Name', '').lower() or 
                   query in mod.get('State_Author', '').lower()
            ]
        self.total_pages = max(1, (len(self.filtered_mods) + self.page_size - 1) // self.page_size)
        self.current_page = min(self.current_page, self.total_pages - 1)
    
    def render(self):
        imgui.set_next_window_position(0, 0)
        imgui.set_next_window_size(imgui.get_io().display_size.x, imgui.get_io().display_size.y)
        
        imgui.begin("Nexus Mods Viewer", 
                   flags=imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE | 
                         imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_COLLAPSE)
        
        # Header
        self.render_header()
        
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        
        # Search bar
        self.render_search_bar()
        
        imgui.spacing()
        
        # Statistics
        self.render_statistics()
        
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        
        # Mod cards
        self.render_mod_cards()
        
        imgui.spacing()
        imgui.separator()
        imgui.spacing()
        
        # Navigation
        self.render_navigation()
        
        # Notification
        if self.notification and (time.time() - self.notification_time) < 3:
            self.render_notification()
        
        imgui.end()
    
    def render_header(self):
        # Title
        draw_list = imgui.get_window_draw_list()
        
        title = "NEXUS MODS COLLECTION VIEWER"
        text_size = imgui.calc_text_size(title)
        window_width = imgui.get_window_width()
        cursor_pos = imgui.get_cursor_screen_pos()
        
        # Background rectangle for title
        draw_list.add_rect_filled(
            cursor_pos.x - 10, cursor_pos.y - 5,
            cursor_pos.x + window_width - 10, cursor_pos.y + text_size.y + 10,
            imgui.get_color_u32_rgba(*self.colors['header_bg'])
        )
        
        # Scale up title text
        imgui.set_cursor_pos_x((window_width - text_size.x) / 2)
        imgui.text_colored(title, *self.colors['accent'])
        
        # Subtitle
        subtitle = "Sorted by File Size"
        subtitle_size = imgui.calc_text_size(subtitle)
        imgui.set_cursor_pos_x((window_width - subtitle_size.x) / 2)
        imgui.text_colored(subtitle, *self.colors['text_gray'])
    
    def render_search_bar(self):
        imgui.text("🔍 Search:")
        imgui.same_line()
        imgui.push_item_width(400)
        changed, self.search_query = imgui.input_text("##search", self.search_query, 256)
        imgui.pop_item_width()
        
        if changed:
            self.filter_mods()
        
        imgui.same_line()
        if imgui.button("Clear"):
            self.search_query = ""
            self.filter_mods()
    
    def render_statistics(self):
        total_size = sum(mod.get('Size', 0) for mod in self.filtered_mods)
        total_mods = len(self.filtered_mods)
        avg_size = total_size / total_mods if total_mods > 0 else 0
        
        # Stats box
        draw_list = imgui.get_window_draw_list()
        cursor_pos = imgui.get_cursor_screen_pos()
        window_width = imgui.get_window_width()
        
        box_height = 50
        draw_list.add_rect_filled(
            cursor_pos.x, cursor_pos.y,
            cursor_pos.x + window_width - 20, cursor_pos.y + box_height,
            imgui.get_color_u32_rgba(*self.colors['card_bg']),
            5
        )
        
        imgui.dummy(window_width, 10)
        
        # Display stats in columns
        col_width = window_width / 3
        imgui.columns(3, "stats")
        imgui.set_column_width(0, col_width)
        imgui.set_column_width(1, col_width)
        
        imgui.text_colored("Total Mods:", *self.colors['text_gray'])
        imgui.same_line()
        imgui.text_colored(f"{total_mods}", *self.colors['accent'])
        
        imgui.next_column()
        imgui.text_colored("Total Size:", *self.colors['text_gray'])
        imgui.same_line()
        imgui.text_colored(format_size(total_size), *self.colors['size_color'])
        
        imgui.next_column()
        imgui.text_colored("Average Size:", *self.colors['text_gray'])
        imgui.same_line()
        imgui.text_colored(format_size(avg_size), *self.colors['warning'])
        
        imgui.columns(1)
        imgui.dummy(window_width, 10)
    
    def render_mod_cards(self):
        start_index = self.current_page * self.page_size
        end_index = min(start_index + self.page_size, len(self.filtered_mods))
        
        if start_index >= len(self.filtered_mods):
            imgui.text_colored("No mods found matching your search.", *self.colors['warning'])
            return
        
        for i in range(start_index, end_index):
            mod = self.filtered_mods[i]
            self.render_mod_card(i + 1, mod)
    
    def render_mod_card(self, index, mod):
        name = mod.get('Name', 'N/A')
        size = format_size(mod.get('Size', 0))
        url = mod.get('URL', 'N/A')
        author = mod.get('State_Author', 'Unknown')
        version = mod.get('State_Version', 'N/A')
        
        draw_list = imgui.get_window_draw_list()
        cursor_pos = imgui.get_cursor_screen_pos()
        window_width = imgui.get_window_width()
        
        card_height = 100
        card_width = window_width - 40
        
        # Card background
        is_hovered = imgui.is_mouse_hovering_rect(
            cursor_pos.x, cursor_pos.y,
            cursor_pos.x + card_width, cursor_pos.y + card_height
        )
        
        bg_color = self.colors['card_hover'] if is_hovered else self.colors['card_bg']
        draw_list.add_rect_filled(
            cursor_pos.x, cursor_pos.y,
            cursor_pos.x + card_width, cursor_pos.y + card_height,
            imgui.get_color_u32_rgba(*bg_color),
            8
        )
        
        # Border
        border_color = self.colors['accent']
        border_thickness = 2
        if self.last_copied_index == index:
            border_color = self.colors['copied_highlight']
            border_thickness = 3
        
        draw_list.add_rect(
            cursor_pos.x, cursor_pos.y,
            cursor_pos.x + card_width, cursor_pos.y + card_height,
            imgui.get_color_u32_rgba(*border_color),
            8, thickness=border_thickness
        )
        
        imgui.dummy(card_width, 5)
        
        # Index badge
        imgui.text_colored(f"#{index}", *self.colors['accent'])
        imgui.same_line()
        
        # Mod name
        imgui.text_colored(f"📦 {name}", *self.colors['text'])
        
        # Author and version
        imgui.indent(20)
        imgui.text_colored("by", *self.colors['text_gray'])
        imgui.same_line()
        imgui.text_colored(author, *self.colors['accent'])
        imgui.same_line()
        imgui.text_colored(" │ ", *self.colors['text_gray'])
        imgui.same_line()
        imgui.text_colored("v", *self.colors['text_gray'])
        imgui.same_line()
        imgui.text_colored(version, *self.colors['warning'])
        imgui.same_line()
        imgui.text_colored(" │ ", *self.colors['text_gray'])
        imgui.same_line()
        imgui.text_colored(size, *self.colors['size_color'])
        
        # URL with copy button
        imgui.text_colored("🔗", *self.colors['text_gray'])
        imgui.same_line()
        
        imgui.push_style_color(imgui.COLOR_BUTTON, *self.colors['accent'])
        imgui.push_style_color(imgui.COLOR_BUTTON_HOVERED, *self.colors['accent_hover'])
        imgui.push_style_color(imgui.COLOR_BUTTON_ACTIVE, *self.colors['accent'])
        
        if imgui.button(f"Copy URL##{index}"):
            self.copy_to_clipboard(url, index)
        
        imgui.pop_style_color(3)
        
        imgui.same_line()
        imgui.text_colored(url[:80] + "..." if len(url) > 80 else url, *self.colors['text_gray'])
        
        imgui.unindent(20)
        imgui.dummy(card_width, 8)
    
    def render_navigation(self):
        imgui.text_colored(f"Page {self.current_page + 1} of {self.total_pages}", *self.colors['text_gray'])
        imgui.same_line(spacing=30)
        
        # Previous button
        imgui.push_style_color(imgui.COLOR_BUTTON, *self.colors['accent'])
        imgui.push_style_color(imgui.COLOR_BUTTON_HOVERED, *self.colors['accent_hover'])
        imgui.push_style_color(imgui.COLOR_BUTTON_ACTIVE, *self.colors['accent'])
        
        if self.current_page > 0:
            if imgui.button("◀ Previous"):
                self.current_page -= 1
        else:
            imgui.push_style_var(imgui.STYLE_ALPHA, 0.5)
            imgui.button("◀ Previous")
            imgui.pop_style_var(1)
        
        imgui.same_line()
        
        # Next button
        if self.current_page < self.total_pages - 1:
            if imgui.button("Next ▶"):
                self.current_page += 1
        else:
            imgui.push_style_var(imgui.STYLE_ALPHA, 0.5)
            imgui.button("Next ▶")
            imgui.pop_style_var(1)
        
        imgui.pop_style_color(3)
        
        imgui.same_line(spacing=30)
        
        # Page jump
        imgui.text_colored("Jump to page:", *self.colors['text_gray'])
        imgui.same_line()
        imgui.push_item_width(80)
        
        changed, page_input = imgui.input_int("##page", self.current_page + 1)
        if changed:
            target_page = page_input - 1
            if 0 <= target_page < self.total_pages:
                self.current_page = target_page
        
        imgui.pop_item_width()
    
    def render_notification(self):
        # Floating notification at top center
        notification_width = 400
        notification_height = 50
        display_size = imgui.get_io().display_size
        
        imgui.set_next_window_position(
            (display_size.x - notification_width) / 2,
            20
        )
        imgui.set_next_window_size(notification_width, notification_height)
        
        imgui.begin("##notification",
                   flags=imgui.WINDOW_NO_TITLE_BAR | imgui.WINDOW_NO_RESIZE | 
                         imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_SCROLLBAR)
        
        imgui.text_colored(self.notification, *self.notification_color)
        imgui.end()

def main():
    input_csv_filename = 'output.csv'
    
    try:
        with open(input_csv_filename, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            mod_data = []
            for row in reader:
                try:
                    row['Size'] = int(row.get('Size') or 0)
                    mod_data.append(row)
                except (ValueError, TypeError):
                    logging.warning(f"Invalid or missing 'Size' value for row: {row.get('Name', 'Unknown')}. Treating as size 0.")
                    row['Size'] = 0
                    mod_data.append(row)
        
        if not mod_data:
            logging.error(f"No data found in {input_csv_filename}.")
            return
        
        # Then initialize window
        window, impl = impl_glfw_init()
        if not window:
            logging.error("Failed to initialize GLFW window")
            return
        
        # Set dark theme
        imgui.style_colors_dark()
        style = imgui.get_style()
        style.window_rounding = 10
        style.frame_rounding = 8
        style.scrollbar_rounding = 10
        style.grab_rounding = 8
        style.window_padding = (15, 15)
        style.frame_padding = (8, 6)
        style.item_spacing = (10, 8)
        
        app = ModViewerApp(mod_data)
        
        # Main loop
        while not glfw.window_should_close(window):
            glfw.poll_events()
            impl.process_inputs()
            
            imgui.new_frame()
            
            app.render()
            
            gl.glClearColor(0.1, 0.1, 0.15, 1.0)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)
            
            imgui.render()
            impl.render(imgui.get_draw_data())
            glfw.swap_buffers(window)
        
        impl.shutdown()
        glfw.terminate()
        
    except FileNotFoundError:
        logging.error(f"The file '{input_csv_filename}' was not found.")
        print(f"\nERROR: The file '{input_csv_filename}' was not found.")
        print(f"Please make sure '{input_csv_filename}' is in the same directory as this script.\n")
    except Exception as e:
        import traceback
        logging.error(f"An unexpected error occurred: {e}")
        logging.error(traceback.format_exc())
        print(f"\nAn unexpected error occurred: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()