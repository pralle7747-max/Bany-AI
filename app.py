import os
import sys
import sqlite3
import threading
import re
import time
import math
import colorsys
import uuid
import json
import base64
import ctypes
import webbrowser
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
import customtkinter as ctk
import pyttsx3
import requests
from duckduckgo_search import DDGS
from google import genai
from google.genai import types
import urllib.request
import urllib.error

# --- UPDATE-HANDLER (Ganz am Anfang, um das Austauschen der EXE im Hintergrund abzuwickeln) ---
if "--apply-update" in sys.argv:
    time.sleep(2)  # Warten, bis die alte Instanz komplett beendet ist
    if len(sys.argv) > 2:
        target_exe = sys.argv[2]
        new_exe = target_exe + ".new"
        if os.path.exists(new_exe):
            try:
                os.replace(new_exe, target_exe)
            except Exception:
                pass
        subprocess.Popen([target_exe])
    sys.exit(0)

# --- WINDOWS TASKBAR ICON FIX ---
try:
    myappid = 'aether.banyai.app.2.9'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

# --- FIREBASE EINGEBAUT ---
import firebase_admin
from firebase_admin import credentials, db

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# ==========================================
# EINSTELLUNGEN & VERSTECKTE KEYS (BASE64)
# ==========================================
def decode_key(encoded_str: str) -> str:
    """Dekodiert leicht verschlüsselte Base64-Strings, damit Keys nicht in Klartext im Code stehen."""
    if not encoded_str or encoded_str.startswith("DEIN_"):
        return encoded_str
    try:
        return base64.b64decode(encoded_str.encode('utf-8')).decode('utf-8')
    except Exception:
        return encoded_str

RAW_GEMINI_KEY = "QVEuQWI4Uk42THYzR09JbjN2Z0xBLUFidUU5NVkyYVhTaEZlcFFaNmRiMHo2ZTFjRlZTbmc=" 
RAW_DISCORD_WEBHOOK = "aHR0cHM6Ly9kaXNjb3JkLmNvbS9hcGkvd2ViaG9va3MvMTU0Nzc1NDE3NzQ3NDYwMTA5MS9lT05ndVBFei1zNFBxeGJYY0pkTFE0SFltOG9aY0NyblR4MkticVFKRTE1QUVjMEgtS05mNEZwRm1BcjdYcGtuVVYyNg=="

GEMINI_API_KEY = decode_key(RAW_GEMINI_KEY)
DISCORD_WEBHOOK_URL = decode_key(RAW_DISCORD_WEBHOOK)

UPDATE_URL = "https://raw.githubusercontent.com/pralle7747-max/Bany-AI/main/version.json"
CURRENT_VERSION = "2.9.0"
SYSTEM_PROMPT_FILE = "system_prompt.txt"
SETTINGS_FILE = "settings.json"
FIREBASE_KEY_FILE = "serviceAccountKey.json"
FIREBASE_DB_URL = "https://bany-ai-default-rtdb.europe-west1.firebasedatabase.app/"
DISCORD_INVITE_URL = "https://discord.gg/8zPbwgDHwV"

# --- ICON CONFIGURATION ---
def get_resource_path(relative_path):
    """Gibt den absoluten Pfad zur Ressource zurück (funktioniert für Dev und für PyInstaller OneFile)."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

ICON_FILE = get_resource_path("icon.ico")

# --- FIREBASE INITIALISIERUNG ---
def init_firebase():
    key_path = get_resource_path(FIREBASE_KEY_FILE)
    if os.path.exists(key_path):
        try:
            if not firebase_admin._apps:
                cred = credentials.Certificate(key_path)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': FIREBASE_DB_URL
                })
            return db.reference('knowledge')
        except Exception as e:
            print(f"Firebase Fehler beim Starten: {e}")
            return None
    else:
        print(f"Hinweis: '{key_path}' nicht gefunden. Firebase wird übersprungen.")
        return None

firebase_ref = init_firebase()

def clean_firebase_key(text: str) -> str:
    return text.lower().strip().replace('.', '_').replace('#', '_').replace('$', '_').replace('[', '_').replace(']', '_')

def get_firebase_answer(frage: str):
    if not firebase_ref:
        return None
    try:
        key = clean_firebase_key(frage)
        data = firebase_ref.child(key).get()
        if data and isinstance(data, dict):
            return data.get("antwort")
    except Exception as e:
        print(f"Fehler beim Lesen aus Firebase: {e}")
    return None

def save_firebase_answer(frage: str, antwort: str):
    if not firebase_ref:
        return
    try:
        key = clean_firebase_key(frage)
        firebase_ref.child(key).set({
            "frage_original": frage,
            "antwort": antwort
        })
    except Exception as e:
        print(f"Fehler beim Speichern in Firebase: {e}")

def setup_system_prompt():
    prompt_path = get_resource_path(SYSTEM_PROMPT_FILE)
    if not os.path.exists(prompt_path):
        default_prompt = (
            "Du bist ein intelligenter, freundlicher und hilfsbereiter KI-Assistent namens Bany AI für das System 'Aether OS'. "
            "Antworte stets präzise, gut strukturiert und höflich auf Deutsch."
        )
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(default_prompt)

def load_system_prompt():
    setup_system_prompt()
    prompt_path = get_resource_path(SYSTEM_PROMPT_FILE)
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"Fehler beim Laden des System-Prompts: {e}")
        return "Du bist Bany AI, ein hilfreicher KI-Assistent."

# --- AUTO-UPDATE SYSTEM (JSON & EXE-SUPPORT) ---
def check_and_apply_update():
    if "DEIN_USER" in UPDATE_URL or not UPDATE_URL.startswith("http"):
        return

    try:
        req = urllib.request.Request(UPDATE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
        remote_version = data.get("version")
        download_url = data.get("url")
        
        if remote_version and remote_version != CURRENT_VERSION:
            download_and_apply_update(download_url)
    except Exception as e:
        print(f"Update-Prüfung übersprungen: {e}")

def download_and_apply_update(url):
    try:
        if getattr(sys, 'frozen', False):
            real_exe_path = sys.executable
        else:
            real_exe_path = os.path.abspath(__file__)
            
        new_exe_path = real_exe_path + ".new"
        
        # Neue Version herunterladen
        urllib.request.urlretrieve(url, new_exe_path)
        
        # App im Update-Modus neu starten
        subprocess.Popen([real_exe_path, "--apply-update", real_exe_path], creationflags=subprocess.DETACHED_PROCESS if os.name == 'nt' else 0)
        sys.exit(0)
    except Exception as e:
        print(f"Fehler beim Download des Updates: {e}")

# Automatischer Aufruf im Hintergrund beim Start
threading.Thread(target=check_and_apply_update, daemon=True).start()

# --- CONFIG & DESIGNS ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

THEMES = {
    "BANY THEME 🍋": {
        "bg": "#121212",
        "sidebar_bg": "#181818",
        "accent": "#FFE01B",
        "text": "#ffffff",
        "card": "#1E1E1E",
        "secondary_accent": "#3FB34F",
        "blue_accent": "#1C75BC"
    },
    "Neon-Gelb": {
        "bg": "#1c2005",
        "sidebar_bg": "#121403",
        "accent": "#ccff00",
        "text": "#ffffff",
        "card": "#121403"
    },
    "Gold-Gelb": {
        "bg": "#2b2515",
        "sidebar_bg": "#1e1a0e",
        "accent": "#d4af37",
        "text": "#ffffff",
        "card": "#1e1a0e"
    }
}

# --- DATENBANK SETUP ---
def init_db():
    conn = sqlite3.connect("ki_gedaechtnis.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anfragen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frage TEXT NOT NULL,
            antwort TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_pinned INTEGER DEFAULT 0
        )
    """)
    try:
        cursor.execute("ALTER TABLE chats ADD COLUMN is_pinned INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

def save_chat_message(chat_id, role, content):
    conn = sqlite3.connect("ki_gedaechtnis.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_pinned FROM chats WHERE chat_id = ? LIMIT 1", (chat_id,))
    row = cursor.fetchone()
    is_pinned = row[0] if row else 0

    cursor.execute("INSERT INTO chats (chat_id, role, content, is_pinned) VALUES (?, ?, ?, ?)", (chat_id, role, content, is_pinned))
    conn.commit()
    conn.close()

def load_chat_history(chat_id):
    conn = sqlite3.connect("ki_gedaechtnis.db")
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM chats WHERE chat_id = ? ORDER BY id ASC", (chat_id,))
    rows = cursor.fetchall()
    conn.close()
    
    contents = []
    for role, content in rows:
        contents.append(types.Content(
            role=role,
            parts=[types.Part.from_text(text=content)]
        ))
    return contents

def get_all_chat_sessions():
    conn = sqlite3.connect("ki_gedaechtnis.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id, content, timestamp, MAX(is_pinned) as pinned
        FROM chats 
        WHERE role = 'user' 
        GROUP BY chat_id 
        ORDER BY pinned DESC, MAX(id) DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def toggle_pin_chat(chat_id):
    conn = sqlite3.connect("ki_gedaechtnis.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_pinned FROM chats WHERE chat_id = ? LIMIT 1", (chat_id,))
    row = cursor.fetchone()
    if row:
        new_status = 0 if row[0] == 1 else 1
        cursor.execute("UPDATE chats SET is_pinned = ? WHERE chat_id = ?", (new_status, chat_id))
        conn.commit()
    conn.close()

def delete_chat_session(chat_id):
    conn = sqlite3.connect("ki_gedaechtnis.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

init_db()

# --- START-ANIMATION (SPLASHSCREEN) ---
class NeonSplashScreen(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.overrideredirect(True)
        
        width, height = 600, 350
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w // 2) - (width // 2)
        y = (screen_h // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.configure(bg="#0a0a02")

        frame = tk.Frame(self, bg="#0a0a02")
        frame.pack(expand=True, fill="both")

        self.lbl_title = tk.Label(
            frame, 
            text="Bany AI 🍋", 
            font=("Arial", 42, "bold"), 
            fg="#FFE01B", 
            bg="#0a0a02"
        )
        self.lbl_title.pack(pady=(80, 10))

        self.lbl_sub = tk.Label(
            frame, 
            text="Powered by Aether Software", 
            font=("Arial", 16, "bold"), 
            fg="#eeff88", 
            bg="#0a0a02"
        )
        self.lbl_sub.pack(pady=(0, 30))

        self.lbl_secured = tk.Label(
            frame, 
            text="Secured by VAULT", 
            font=("Arial", 10, "bold"), 
            fg="#3FB34F", 
            bg="#0a0a02"
        )
        self.lbl_secured.pack(side="bottom", pady=15)

        self.start_time = time.time()
        self.animate_neon()

    def animate_neon(self):
        elapsed = time.time() - self.start_time
        if elapsed < 3.0:
            colors = ["#FFE01B", "#3FB34F", "#1C75BC", "#FFCA00"]
            current_color = colors[int(elapsed * 6) % len(colors)]
            self.lbl_title.configure(fg=current_color)
            self.after(100, self.animate_neon)
        else:
            self.destroy()
            self.parent.on_splash_done()

# --- HAUPTANWENDUNG ---
class AetherOSAssistant(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.withdraw()
        self.title(f"Bany AI (v{CURRENT_VERSION})")
        self.geometry("1100x750")
        self.minsize(900, 600)

        if os.path.exists(ICON_FILE):
            try:
                self.iconbitmap(ICON_FILE)
            except Exception as e:
                print(f"Icon konnte nicht geladen werden: {e}")

        self.api_key = GEMINI_API_KEY
        if not self.api_key or self.api_key.startswith("DEIN_"):
            self.api_key = self.ask_api_key()

        if not self.api_key:
            messagebox.showerror("Fehler", "Ohne Gemini API-Key kann Bany AI nicht gestartet werden.")
            self.destroy()
            return

        self.client = genai.Client(api_key=self.api_key)
        self.current_chat_id = str(uuid.uuid4())
        self.is_admin_logged_in = False
        self.anim_step = 0

        # Standard-Einstellungen vor dem Laden setzen
        self.animated_mode = tk.BooleanVar(value=True)
        self.tts_enabled = tk.BooleanVar(value=False)
        self.tts_volume = 1.0
        self.current_theme_name = "BANY THEME 🍋"
        self.current_theme = THEMES[self.current_theme_name]
        self.yellow_hue_val = 55
        self.current_font_size = 14

        self.load_settings()

        self.setup_ui()
        self.apply_theme(self.current_theme_name)
        if self.yellow_hue_val != 55:
            self.change_yellow_hue_event(self.yellow_hue_val)

        self.after(50, self.animate_background_loop)

        NeonSplashScreen(self)

    # --- SETTINGS SPEICHERN & LADEN ---
    def load_settings(self):
        settings_path = get_resource_path(SETTINGS_FILE)
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.animated_mode.set(data.get("animated_mode", True))
                    self.tts_enabled.set(data.get("tts_enabled", False))
                    self.tts_volume = data.get("tts_volume", 1.0)
                    self.current_theme_name = data.get("theme_name", "BANY THEME 🍋")
                    if self.current_theme_name in THEMES:
                        self.current_theme = THEMES[self.current_theme_name]
                    self.yellow_hue_val = data.get("yellow_hue", 55)
                    self.current_font_size = data.get("font_size", 14)
            except Exception as e:
                print(f"Fehler beim Laden der Einstellungen: {e}")

    def save_settings(self):
        settings_path = get_resource_path(SETTINGS_FILE)
        data = {
            "animated_mode": self.animated_mode.get(),
            "tts_enabled": self.tts_enabled.get(),
            "tts_volume": self.tts_volume,
            "theme_name": self.current_theme_name,
            "yellow_hue": self.yellow_hue_val,
            "font_size": self.current_font_size
        }
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Fehler beim Speichern der Einstellungen: {e}")

    def open_external_discord_app(self):
        ans = messagebox.askyesno(
            "Weiterleitung zu Discord", 
            "Achtung! Du wirst zu Discord weitergeleitet.\n\nMöchtest du fortfahren?"
        )
        if ans:
            webbrowser.open(DISCORD_INVITE_URL)

    def on_splash_done(self):
        self.deiconify()
        self.focus_force()

    def ask_api_key(self):
        root = tk.Tk()
        root.withdraw()
        key = simpledialog.askstring("Gemini API Key", "Bitte gib deinen Gemini API-Key ein:", show='*')
        root.destroy()
        return key

    def play_error_sound(self):
        if HAS_WINSOUND:
            try:
                winsound.MessageBeep(winsound.MB_ICONHAND)
            except Exception:
                pass

    def speak_text(self, text):
        if not self.tts_enabled.get():
            return

        def _speak():
            try:
                engine = pyttsx3.init()
                engine.setProperty('volume', self.tts_volume)
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"TTS Fehler: {e}")

        threading.Thread(target=_speak, daemon=True).start()

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.bg_canvas = tk.Canvas(self, highlightthickness=0, bg="#121212")
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.sidebar_frame = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color="#181818")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        brand_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        brand_frame.grid(row=0, column=0, padx=15, pady=(20, 10), sticky="w")

        self.logo_label = ctk.CTkLabel(brand_frame, text="✨ Bany Stinkt AI", font=("Arial", 18, "bold"), text_color="#FFE01B")
        self.logo_label.pack(side="left")

        self.sublogo_label = ctk.CTkLabel(brand_frame, text=" by Aether", font=("Arial", 11), text_color="#888888")
        self.sublogo_label.pack(side="left", padx=(3, 0), pady=(3, 0))

        self.btn_new_chat = ctk.CTkButton(
            self.sidebar_frame, text="✏️  Neuer Chat", anchor="w", fg_color="transparent", 
            text_color="#ffffff", hover_color="#2b2b2b", font=("Arial", 13), command=self.start_new_chat
        )
        self.btn_new_chat.grid(row=1, column=0, sticky="ew", padx=10, pady=2)

        self.btn_search_chat = ctk.CTkButton(
            self.sidebar_frame, text="🔍  Chats durchsuchen", anchor="w", fg_color="transparent", 
            text_color="#ffffff", hover_color="#2b2b2b", font=("Arial", 13), command=self.search_chats_dialog
        )
        self.btn_search_chat.grid(row=2, column=0, sticky="ew", padx=10, pady=2)

        # NEUER DISCORD BUTTON
        self.btn_aether_apps = ctk.CTkButton(
            self.sidebar_frame, text="🚀  Weitere Aether Apps", anchor="w", fg_color="transparent", 
            text_color="#FFE01B", hover_color="#2b2b2b", font=("Arial", 13, "bold"), command=self.open_external_discord_app
        )
        self.btn_aether_apps.grid(row=3, column=0, sticky="ew", padx=10, pady=2)

        self.btn_images = ctk.CTkButton(
            self.sidebar_frame, text="🖼️  Bilder (Coming Soon)", anchor="w", fg_color="transparent", 
            text_color="#666666", hover_color="#2b2b2b", font=("Arial", 13), command=lambda: self.show_coming_soon("Bilder")
        )
        self.btn_images.grid(row=4, column=0, sticky="ew", padx=10, pady=2)

        self.btn_mediathek = ctk.CTkButton(
            self.sidebar_frame, text="📦  Mediathek (Coming Soon)", anchor="w", fg_color="transparent", 
            text_color="#666666", hover_color="#2b2b2b", font=("Arial", 13), command=lambda: self.show_coming_soon("Mediathek")
        )
        self.btn_mediathek.grid(row=5, column=0, sticky="ew", padx=10, pady=2)

        self.btn_kicut = ctk.CTkButton(
            self.sidebar_frame, text="✂️  KI CUT (Coming Soon)", anchor="w", fg_color="transparent", 
            text_color="#666666", hover_color="#2b2b2b", font=("Arial", 13), command=lambda: self.show_coming_soon("KI CUT")
        )
        self.btn_kicut.grid(row=6, column=0, sticky="ew", padx=10, pady=2)

        self.lbl_history_header = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Verlauf", 
            font=("Arial", 12, "bold"), 
            text_color="#aaaaaa", 
            anchor="w"
        )
        self.lbl_history_header.grid(row=7, column=0, sticky="w", padx=15, pady=(15, 2))

        self.scroll_history = ctk.CTkScrollableFrame(self.sidebar_frame, fg_color="transparent")
        self.scroll_history.grid(row=8, column=0, sticky="nsew", padx=5, pady=(2, 2))
        self.scroll_history.grid_columnconfigure(0, weight=1)

        bottom_menu_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        bottom_menu_frame.grid(row=9, column=0, sticky="ew", padx=10, pady=(5, 10))

        self.btn_export = ctk.CTkButton(
            bottom_menu_frame, text="💾  Chat Exportieren", anchor="w", fg_color="transparent", 
            text_color="#3FB34F", hover_color="#2b2b2b", font=("Arial", 12), command=self.export_chat
        )
        self.btn_export.pack(fill="x", pady=1)

        self.btn_import = ctk.CTkButton(
            bottom_menu_frame, text="📂  Chat Importieren", anchor="w", fg_color="transparent", 
            text_color="#1C75BC", hover_color="#2b2b2b", font=("Arial", 12), command=self.import_chat
        )
        self.btn_import.pack(fill="x", pady=1)

        self.refresh_sidebar_history()

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=(5, 0))
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self.main_container)
        self.tabview.grid(row=0, column=0, sticky="nsew")

        self.tab_main = self.tabview.add("Chat")
        self.tab_admin = self.tabview.add("Admin-Panel 🛠️")
        self.tab_settings = self.tabview.add("Einstellungen ⚙️")
        self.tab_legal = self.tabview.add("Impressum & Rechtliches ⚖️")

        self.setup_main_tab()
        self.setup_admin_tab()
        self.setup_settings_tab()
        self.setup_legal_tab()

        footer_frame = ctk.CTkFrame(self.main_container, fg_color="transparent", height=25)
        footer_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        lbl_footer_branding = ctk.CTkLabel(
            footer_frame, 
            text="Bany AI | Powered by Aether Software | Secured by VAULT", 
            font=("Arial", 11, "bold"), 
            text_color="#3FB34F"
        )
        lbl_footer_branding.pack(side="left")

    def show_coming_soon(self, feature):
        messagebox.showinfo("Coming Soon", f"Die Funktion '{feature}' befindet sich aktuell in Entwicklung und wird bald verfügbar sein!")

    def refresh_sidebar_history(self):
        for widget in self.scroll_history.winfo_children():
            widget.destroy()

        sessions = get_all_chat_sessions()
        for chat_id, first_msg, timestamp, is_pinned in sessions:
            title = first_msg if len(first_msg) <= 22 else first_msg[:20] + "..."
            icon = "📌 " if is_pinned == 1 else "💬 "
            
            is_active = (chat_id == self.current_chat_id)
            btn_bg = "#2b2b2b" if is_active else "transparent"

            btn_chat = ctk.CTkButton(
                self.scroll_history, 
                text=f"{icon}{title}", 
                anchor="w", 
                fg_color=btn_bg, 
                text_color="#FFE01B" if is_pinned == 1 else "#ffffff", 
                hover_color="#333333", 
                font=("Arial", 12, "bold" if is_pinned == 1 else "normal"),
                command=lambda c_id=chat_id: self.load_selected_chat(c_id)
            )
            btn_chat.pack(fill="x", pady=2)
            btn_chat.bind("<Button-3>", lambda event, c_id=chat_id, pinned=is_pinned: self.show_history_context_menu(event, c_id, pinned))

    def show_history_context_menu(self, event, chat_id, is_pinned):
        menu = tk.Menu(self, tearoff=0, bg="#181818", fg="#ffffff", activebackground="#FFE01B", activeforeground="#000000")
        pin_label = "📌 Vom Anfang lösen" if is_pinned == 1 else "📌 Oben anheften"
        menu.add_command(label=pin_label, command=lambda: self.action_toggle_pin(chat_id))
        menu.add_separator()
        menu.add_command(label="🗑️ Chat löschen", command=lambda: self.action_delete_chat(chat_id))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def action_toggle_pin(self, chat_id):
        toggle_pin_chat(chat_id)
        self.refresh_sidebar_history()

    def action_delete_chat(self, chat_id):
        if messagebox.askyesno("Chat löschen", "Möchtest du diesen Chatverlauf wirklich unwiderruflich löschen?"):
            delete_chat_session(chat_id)
            if self.current_chat_id == chat_id:
                self.start_new_chat()
            else:
                self.refresh_sidebar_history()

    def load_selected_chat(self, chat_id):
        self.current_chat_id = chat_id
        self.txt_output.delete("1.0", tk.END)

        conn = sqlite3.connect("ki_gedaechtnis.db")
        cursor = conn.cursor()
        cursor.execute("SELECT role, content FROM chats WHERE chat_id = ? ORDER BY id ASC", (chat_id,))
        rows = cursor.fetchall()
        conn.close()

        for role, content in rows:
            prefix = "👤 Du:\n" if role == "user" else "🤖 Bany AI:\n"
            self.txt_output.insert(tk.END, f"\n{prefix}{content}\n\n" + "-"*50 + "\n")

        self.txt_output.see(tk.END)
        self.refresh_sidebar_history()

    def animate_background_loop(self):
        if self.animated_mode.get():
            self.anim_step += 0.05
            w = self.winfo_width()
            h = self.winfo_height()

            if w > 10 and h > 10:
                self.bg_canvas.delete("anim_wave")
                accent_color = self.current_theme["accent"]

                points = []
                for x in range(0, w + 40, 40):
                    y = (h * 0.85) + math.sin(self.anim_step + (x * 0.005)) * 25 + math.cos(self.anim_step * 0.5) * 15
                    points.extend([x, y])

                points.extend([w, h, 0, h])
                try:
                    self.bg_canvas.create_polygon(points, fill=accent_color, outline="", tags="anim_wave", stipple="gray25")
                except Exception:
                    pass

        self.after(50, self.animate_background_loop)

    def setup_main_tab(self):
        self.tab_main.grid_columnconfigure(0, weight=1)
        self.tab_main.grid_rowconfigure(1, weight=1)

        status_frame = ctk.CTkFrame(self.tab_main, fg_color="transparent")
        status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 0))
        status_frame.grid_columnconfigure(1, weight=1)

        self.lbl_status = ctk.CTkLabel(status_frame, text="", font=("Arial", 12, "italic"))
        self.lbl_status.grid(row=0, column=0, sticky="w")

        lbl_support_hint = ctk.CTkLabel(
            status_frame, 
            text="🐛 Bug melden: Support (dein Fehler)", 
            font=("Arial", 11, "bold"), 
            text_color="#888888"
        )
        lbl_support_hint.grid(row=0, column=1, sticky="e")

        self.txt_output = ctk.CTkTextbox(self.tab_main, font=("Arial", self.current_font_size), wrap="word")
        self.txt_output.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 5))

        # Bottom Bar mit Input und TTS-Switch
        chat_bottom_frame = ctk.CTkFrame(self.tab_main, fg_color="transparent")
        chat_bottom_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        chat_bottom_frame.grid_columnconfigure(0, weight=1)

        input_frame = ctk.CTkFrame(chat_bottom_frame, fg_color="transparent")
        input_frame.grid(row=0, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.entry_query = ctk.CTkEntry(input_frame, placeholder_text="Frage an Bany AI stellen oder: Support (dein Fehler)...", height=45, font=("Arial", 14))
        self.entry_query.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry_query.bind("<Return>", lambda event: self.start_search_thread())

        self.btn_search = ctk.CTkButton(
            input_frame, text="Senden", height=45, width=100, 
            font=("Arial", 14, "bold"), fg_color="#FFE01B", text_color="black", command=self.start_search_thread
        )
        self.btn_search.grid(row=0, column=1)

        # UNTEN RECHTS: TTS AN / AUS SWITCH
        tts_frame = ctk.CTkFrame(chat_bottom_frame, fg_color="transparent")
        tts_frame.grid(row=1, column=0, sticky="e", pady=(5, 0))

        self.switch_tts = ctk.CTkSwitch(
            tts_frame, 
            text="TTS an/aus", 
            variable=self.tts_enabled,
            command=self.toggle_tts_switch,
            font=("Arial", 12, "bold")
        )
        self.switch_tts.pack(side="right")

    def toggle_tts_switch(self):
        self.save_settings()

    def start_new_chat(self):
        self.current_chat_id = str(uuid.uuid4())
        self.txt_output.delete("1.0", tk.END)
        self.refresh_sidebar_history()

    def export_chat(self):
        conn = sqlite3.connect("ki_gedaechtnis.db")
        cursor = conn.cursor()
        cursor.execute("SELECT role, content, timestamp FROM chats WHERE chat_id = ? ORDER BY id ASC", (self.current_chat_id,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            messagebox.showwarning("Export Fehler", "Der aktuelle Chat ist leer!")
            return

        chat_data = [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        folder_selected = filedialog.askdirectory(title="Ordner für Chat-Export auswählen", initialdir=desktop_path)
        
        if folder_selected:
            filepath = os.path.join(folder_selected, f"bany_chat_{self.current_chat_id[:8]}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(chat_data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("Export erfolgreich", f"Chat wurde gespeichert unter:\n{filepath}")

    def import_chat(self):
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = filedialog.askopenfilename(title="Chat-Datei auswählen", initialdir=desktop_path, filetypes=[("JSON Datei", "*.json")])
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    chat_data = json.load(f)

                self.current_chat_id = str(uuid.uuid4())
                self.txt_output.delete("1.0", tk.END)

                for item in chat_data:
                    role = item.get("role")
                    content = item.get("content")
                    save_chat_message(self.current_chat_id, role, content)

                self.load_selected_chat(self.current_chat_id)
                messagebox.showinfo("Import erfolgreich", "Der Chatverlauf wurde geladen!")
            except Exception as e:
                messagebox.showerror("Import Fehler", f"Datei konnte nicht gelesen werden: {e}")

    def search_chats_dialog(self):
        query = simpledialog.askstring("Chats durchsuchen", "Suchbegriff in bisherigen Chats eingeben:")
        if query:
            conn = sqlite3.connect("ki_gedaechtnis.db")
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM chats WHERE content LIKE ? LIMIT 5", (f"%{query}%",))
            results = cursor.fetchall()
            conn.close()

            if results:
                res_text = "\n\n".join([f"- {r[0][:100]}..." for r in results])
                messagebox.showinfo("Suchergebnisse", f"Gefundene Nachrichten:\n\n{res_text}")
            else:
                messagebox.showinfo("Suchergebnisse", "Keine passenden Treffer gefunden.")

    def send_discord_bug_report(self, bug_description):
        if "DEIN_DISCORD_WEBHOOK" in DISCORD_WEBHOOK_URL or not DISCORD_WEBHOOK_URL.startswith("http"):
            self.txt_output.insert(tk.END, "\n❌ Fehler: Discord Webhook URL ist im Code noch nicht hinterlegt!\n")
            self.btn_search.configure(state="normal")
            return

        payload = {
            "embeds": [{
                "title": "🚨 Neuer Bug-Report (Bany AI)",
                "description": bug_description,
                "color": 16769051,
                "footer": {"text": f"Bany AI v{CURRENT_VERSION} | Secured by VAULT"}
            }]
        }

        try:
            res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
            if res.status_code in [200, 204]:
                self.txt_output.insert(tk.END, f"\n✅ Bug-Report erfolgreich gesendet:\n\"{bug_description}\"\n\nVielen Dank für deine Hilfe!\n")
            else:
                self.txt_output.insert(tk.END, f"\n❌ Discord Webhook Fehler (Code {res.status_code}).\n")
        except Exception as e:
            self.txt_output.insert(tk.END, f"\n❌ Fehler beim Senden des Bug-Reports: {e}\n")

        self.btn_search.configure(state="normal")
        self.lbl_status.configure(text="✅ Abgeschlossen")
        self.entry_query.delete(0, tk.END)

    def start_search_thread(self):
        query = self.entry_query.get().strip()
        if not query:
            return

        support_match = re.match(r"^Support\s*\((.+)\)$", query, re.IGNORECASE)
        if support_match:
            bug_text = support_match.group(1).strip()
            self.btn_search.configure(state="disabled")
            self.lbl_status.configure(text="📡 Sende Bug-Report an Discord...")
            threading.Thread(target=self.send_discord_bug_report, args=(bug_text,), daemon=True).start()
            return

        self.btn_search.configure(state="disabled")
        self.lbl_status.configure(text="🔍 Suche im Web & erstelle KI-Antwort...")
        threading.Thread(target=self.process_query, args=(query,), daemon=True).start()

    def process_query(self, query):
        try:
            fb_antwort = get_firebase_answer(query)
            if fb_antwort:
                answer = fb_antwort + "\n\n✨ (Aus dem globalen Team-Gedächtnis geladen)"
            else:
                history = load_chat_history(self.current_chat_id)
                search_results = ""
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=3))
                    for r in results:
                        search_results += f"- {r.get('body', '')}\n"

                system_instruction = load_system_prompt()
                if search_results:
                    system_instruction += f"\n\nAktuelle Web-Suchergebnisse als Kontext:\n{search_results}"

                history.append(types.Content(role="user", parts=[types.Part.from_text(text=query)]))
                config = types.GenerateContentConfig(system_instruction=system_instruction)
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash", contents=history, config=config
                )
                answer = response.text

            save_chat_message(self.current_chat_id, "user", query)
            save_chat_message(self.current_chat_id, "model", answer)

            conn = sqlite3.connect("ki_gedaechtnis.db")
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO anfragen (frage, antwort, status) VALUES (?, ?, ?)",
                (query, answer, "Gelernt" if fb_antwort else "Ungeprüft")
            )
            conn.commit()
            conn.close()

            self.after(0, self.update_query_ui, query, answer)
            self.speak_text(answer)

        except Exception as e:
            self.play_error_sound()
            self.after(0, self.update_query_ui, query, f"Fehler: {str(e)}", True)

    def update_query_ui(self, query, answer, is_error=False):
        if not is_error:
            self.txt_output.insert(tk.END, f"\n👤 Du:\n{query}\n\n🤖 Bany AI:\n{answer}\n\n" + "-"*50 + "\n")
            self.lbl_status.configure(text="✅ Fertig")
            self.refresh_sidebar_history()
        else:
            self.txt_output.insert(tk.END, f"\n❌ Fehler:\n{answer}\n\n")
            self.lbl_status.configure(text="❌ Fehler aufgetreten")

        self.txt_output.see(tk.END)
        self.btn_search.configure(state="normal")
        if not is_error:
            self.entry_query.delete(0, tk.END)
        if self.is_admin_logged_in:
            self.load_admin_dashboard()

    def setup_admin_tab(self):
        self.tab_admin.grid_columnconfigure(0, weight=1)
        self.tab_admin.grid_rowconfigure(0, weight=1)

        self.frame_login = ctk.CTkFrame(self.tab_admin)
        self.frame_login.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.frame_login.grid_columnconfigure(0, weight=1)

        lbl_title = ctk.CTkLabel(self.frame_login, text="Admin-Login 🛠️", font=("Arial", 20, "bold"))
        lbl_title.pack(pady=(40, 20))

        self.entry_user = ctk.CTkEntry(self.frame_login, placeholder_text="Benutzername", width=250, height=40)
        self.entry_user.pack(pady=10)

        self.entry_pass = ctk.CTkEntry(self.frame_login, placeholder_text="Passwort", show="*", width=250, height=40)
        self.entry_pass.pack(pady=10)

        btn_login = ctk.CTkButton(self.frame_login, text="Einloggen", command=self.check_login, height=40, width=250, text_color="black")
        btn_login.pack(pady=20)

        self.frame_dashboard = ctk.CTkFrame(self.tab_admin, fg_color="transparent")
        self.frame_dashboard.grid_columnconfigure(0, weight=1)
        self.frame_dashboard.grid_rowconfigure(1, weight=1)

        lbl_dash_title = ctk.CTkLabel(self.frame_dashboard, text="Gedächtnis-Verwaltung & Feedbackschleife", font=("Arial", 18, "bold"))
        lbl_dash_title.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        self.scroll_admin = ctk.CTkScrollableFrame(self.frame_dashboard)
        self.scroll_admin.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.scroll_admin.grid_columnconfigure(0, weight=1)

    def check_login(self):
        user = self.entry_user.get().strip()
        pwd = self.entry_pass.get().strip()

        if user == "Pralle" and pwd == "4459":
            self.is_admin_logged_in = True
            self.frame_login.grid_forget()
            self.frame_dashboard.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            self.load_admin_dashboard()
        else:
            self.play_error_sound()
            messagebox.showerror("Zugriff verweigert", "Benutzername oder Passwort falsch!")

    def load_admin_dashboard(self):
        for widget in self.scroll_admin.winfo_children():
            widget.destroy()

        conn = sqlite3.connect("ki_gedaechtnis.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id, frage, antwort, status FROM anfragen ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            req_id, frage, antwort, status = row
            
            card = ctk.CTkFrame(self.scroll_admin, fg_color=self.current_theme["card"])
            card.pack(fill="x", expand=True, pady=5, padx=5)
            card.grid_columnconfigure(0, weight=1)

            header_text = f"ID #{req_id} | Status: {status}"
            lbl_header = ctk.CTkLabel(card, text=header_text, font=("Arial", 12, "bold"), anchor="w")
            lbl_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 0))

            content_text = f"Frage: {frage}\nAntwort: {antwort}"
            lbl_content = ctk.CTkLabel(card, text=content_text, font=("Arial", 11), justify="left", anchor="w", wraplength=650)
            lbl_content.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

            if status == "Ungeprüft":
                btn_correct = ctk.CTkButton(
                    card, 
                    text="✅ Stimmt", 
                    fg_color="#3FB34F", 
                    hover_color="#2e853a",
                    text_color="white",
                    width=100,
                    command=lambda r_id=req_id, f=frage, a=antwort: self.set_status_correct(r_id, f, a)
                )
                btn_correct.grid(row=2, column=0, sticky="w", padx=10, pady=5)

                btn_wrong = ctk.CTkButton(
                    card, 
                    text="❌ Stimmt nicht", 
                    fg_color="#cc3333", 
                    hover_color="#990000",
                    text_color="white",
                    width=120,
                    command=lambda r_id=req_id, f=frage, a=antwort: self.open_correction_dialog(r_id, f, a)
                )
                btn_wrong.grid(row=2, column=1, sticky="w", padx=10, pady=5)

    def set_status_correct(self, req_id, frage, antwort):
        save_firebase_answer(frage, antwort)
        conn = sqlite3.connect("ki_gedaechtnis.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE anfragen SET status = 'Korrekt' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        self.load_admin_dashboard()

    def open_correction_dialog(self, req_id, frage, alte_antwort):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Korrektur-Optionen")
        dialog.geometry("500x260")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        dialog.geometry(f"+{(sw-500)//2}+{(sh-260)//2}")

        lbl = ctk.CTkLabel(dialog, text="Wie möchtest du diese Antwort korrigieren?", font=("Arial", 15, "bold"))
        lbl.pack(pady=(25, 15))

        btn_web = ctk.CTkButton(
            dialog, 
            text="🌐 Internet länger & genauer durchsuchen", 
            fg_color="#1C75BC", 
            hover_color="#135487",
            height=45,
            font=("Arial", 13, "bold"),
            command=lambda: [dialog.destroy(), self.start_deep_search(req_id, frage)]
        )
        btn_web.pack(fill="x", padx=30, pady=10)

        btn_prompt = ctk.CTkButton(
            dialog, 
            text="✏️ Antwort / Prompt selber eingeben & verbessern", 
            fg_color="#FFE01B", 
            hover_color="#d6ba0d",
            text_color="black",
            height=45,
            font=("Arial", 13, "bold"),
            command=lambda: [dialog.destroy(), self.open_custom_prompt_input(req_id, frage, alte_antwort)]
        )
        btn_prompt.pack(fill="x", padx=30, pady=5)

    def open_custom_prompt_input(self, req_id, frage, alte_antwort):
        input_window = ctk.CTkToplevel(self)
        input_window.title("Eigene Korrektur / Prompt eingeben")
        input_window.geometry("550x350")
        input_window.transient(self)
        input_window.grab_set()

        sw = input_window.winfo_screenwidth()
        sh = input_window.winfo_screenheight()
        input_window.geometry(f"+{(sw-550)//2}+{(sh-350)//2}")

        lbl = ctk.CTkLabel(input_window, text="Gib die richtige Antwort oder Korrektur-Anweisungen ein:", font=("Arial", 13, "bold"))
        lbl.pack(pady=(15, 5), padx=15, anchor="w")

        txt_prompt = ctk.CTkTextbox(input_window, height=200)
        txt_prompt.pack(fill="both", expand=True, padx=15, pady=5)
        txt_prompt.insert("1.0", f"Die Antwort sollte folgendermaßen angepasst werden:\n")

        def submit_custom_prompt():
            user_instruction = txt_prompt.get("1.0", tk.END).strip()
            if not user_instruction:
                return
            input_window.destroy()
            
            conn = sqlite3.connect("ki_gedaechtnis.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE anfragen SET status = 'Verbessere Antwort...' WHERE id = ?", (req_id,))
            conn.commit()
            conn.close()
            self.load_admin_dashboard()

            threading.Thread(target=self.process_custom_prompt_improvement, args=(req_id, frage, user_instruction), daemon=True).start()

        btn_submit = ctk.CTkButton(
            input_window, 
            text="✨ Antwort von KI verbessern lassen", 
            fg_color="#3FB34F", 
            hover_color="#2e853a",
            text_color="white",
            height=40,
            font=("Arial", 13, "bold"),
            command=submit_custom_prompt
        )
        btn_submit.pack(fill="x", padx=15, pady=15)

    def process_custom_prompt_improvement(self, req_id, frage, user_instruction):
        try:
            system_instruction = load_system_prompt()
            prompt = (
                f"SYSTEM-INSTRUCTION:\n{system_instruction}\n\n"
                f"Ursprüngliche Frage: {frage}\n"
                f"Korrektur-Vorgabe des Admins: {user_instruction}\n\n"
                f"Formuliere basierend auf den Vorgaben des Admins eine perfekte, finale Antwort."
            )
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            new_answer = response.text
            save_firebase_answer(frage, new_answer)

            conn = sqlite3.connect("ki_gedaechtnis.db")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE anfragen SET antwort = ?, status = 'Manuell korrigiert' WHERE id = ?",
                (new_answer, req_id)
            )
            conn.commit()
            conn.close()

            self.after(0, self.load_admin_dashboard)

        except Exception as e:
            self.play_error_sound()
            print(f"Fehler bei Prompt-Verbesserung: {e}")

    def start_deep_search(self, req_id, frage):
        conn = sqlite3.connect("ki_gedaechtnis.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE anfragen SET status = 'Faktenprüfung läuft...' WHERE id = ?", (req_id,))
        conn.commit()
        conn.close()
        self.load_admin_dashboard()

        threading.Thread(target=self.process_deep_search, args=(req_id, frage), daemon=True).start()

    def process_deep_search(self, req_id, frage):
        try:
            search_results = ""
            with DDGS() as ddgs:
                results = list(ddgs.text(frage, max_results=7))
                for r in results:
                    search_results += f"- {r.get('body', '')}\n"

            system_instruction = load_system_prompt()
            prompt = (
                f"SYSTEM-INSTRUCTION:\n{system_instruction}\n\n"
                f"WARNUNG: Vorherige Antwort war falsch! Führe genaue Faktenprüfung durch.\n"
                f"Erweiterte Suchergebnisse:\n{search_results}\n\n"
                f"Frage: {frage}"
            )

            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            new_answer = response.text
            save_firebase_answer(frage, new_answer)

            conn = sqlite3.connect("ki_gedaechtnis.db")
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE anfragen SET antwort = ?, status = 'Korrigiert via Web' WHERE id = ?",
                (new_answer, req_id)
            )
            conn.commit()
            conn.close()

            self.after(0, self.load_admin_dashboard)

        except Exception as e:
            self.play_error_sound()
            print(f"Fehler bei Deep Search: {e}")

    def setup_settings_tab(self):
        self.tab_settings.grid_columnconfigure(0, weight=1)

        frame = ctk.CTkFrame(self.tab_settings, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        lbl_anim = ctk.CTkLabel(frame, text="✨ Animationen & UI-Effekte:", font=("Arial", 14, "bold"))
        lbl_anim.pack(anchor="w", pady=(10, 5))

        self.switch_anim = ctk.CTkSwitch(
            frame, 
            text="Animated Mode (Fluide Hintergründe & Transitions)", 
            variable=self.animated_mode,
            command=self.toggle_anim_mode
        )
        self.switch_anim.pack(anchor="w", pady=(0, 20))

        lbl_theme = ctk.CTkLabel(frame, text="Preset Theme auswählen:", font=("Arial", 14, "bold"))
        lbl_theme.pack(anchor="w", pady=(10, 5))

        self.combo_theme = ctk.CTkOptionMenu(
            frame, 
            values=list(THEMES.keys()), 
            command=self.change_theme_event,
            text_color="black"
        )
        self.combo_theme.set(self.current_theme_name)
        self.combo_theme.pack(anchor="w", pady=(0, 20))

        lbl_yellow_slider = ctk.CTkLabel(frame, text="🟡 Gelb-Farbton Feineinstellung (Slider):", font=("Arial", 14, "bold"))
        lbl_yellow_slider.pack(anchor="w", pady=(10, 5))

        self.slider_yellow = ctk.CTkSlider(
            frame, 
            from_=40, 
            to=70, 
            number_of_steps=30, 
            command=self.change_yellow_hue_event
        )
        self.slider_yellow.set(self.yellow_hue_val)
        self.slider_yellow.pack(anchor="w", pady=(0, 20))

        lbl_font = ctk.CTkLabel(frame, text="Textgröße Output-Feld (px):", font=("Arial", 14, "bold"))
        lbl_font.pack(anchor="w", pady=(10, 5))

        self.slider_font = ctk.CTkSlider(
            frame, 
            from_=10, 
            to=24, 
            number_of_steps=14, 
            command=self.change_font_size_event
        )
        self.slider_font.set(self.current_font_size)
        self.slider_font.pack(anchor="w", pady=(0, 20))

        lbl_vol = ctk.CTkLabel(frame, text="TTS Sprach-Lautstärke:", font=("Arial", 14, "bold"))
        lbl_vol.pack(anchor="w", pady=(10, 5))

        self.slider_vol = ctk.CTkSlider(
            frame, 
            from_=0.0, 
            to=1.0, 
            command=self.change_volume_event
        )
        self.slider_vol.set(self.tts_volume)
        self.slider_vol.pack(anchor="w", pady=(0, 20))

    def toggle_anim_mode(self):
        if not self.animated_mode.get():
            self.bg_canvas.delete("anim_wave")
        self.save_settings()

    def setup_legal_tab(self):
        self.tab_legal.grid_columnconfigure(0, weight=1)
        self.tab_legal.grid_rowconfigure(0, weight=1)

        txt_legal = ctk.CTkTextbox(self.tab_legal, font=("Arial", 12), wrap="word")
        txt_legal.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)

        legal_text = (
            "===========================================================\n"
            "                 IMPRESSUM & RECHTLICHE HINWEISE          \n"
            "===========================================================\n\n"
            "1. IMPRESSUM (Angaben gemäß § 5 DDG / TMG)\n"
            "-----------------------------------------------------------\n"
            "Anbieter / Herausgeber:\n"
            "Aether Software Development\n"
            "Inhaber: Pralle\n"
            "Kontakt: support@aether-software.local\n\n"
            "Sicherheit & Schutz:\n"
            "Secured by VAULT Architecture\n\n"
            "2. HAFTUNGSAUSSCHLUSS (DISCLAIMER)\n"
            "-----------------------------------------------------------\n"
            "Haftung für Inhalte:\n"
            "Die Inhalte dieser Software (Bany AI) werden mit größter Sorgfalt generiert.\n"
            "Da es sich um eine künstliche Intelligenz auf Basis von Large Language Models\n"
            "handelt, übernehmen wir keine Gewähr für die Richtigkeit, Vollständigkeit\n"
            "und Aktualität der bereitgestellten Antworten.\n\n"
            "3. DATENSCHUTZERKLÄRUNG (DSGVO)\n"
            "-----------------------------------------------------------\n"
            "- Lokale Speicherung: Alle Konversationen werden in einer lokalen SQLite-Datenbank\n"
            "  (ki_gedaechtnis.db) auf dem Gerät des Nutzers gespeichert.\n"
            "- API-Verarbeitung: Anfragen werden zur Generierung der Antwort an die Server\n"
            "  von Google (Gemini API) übermittelt. Es gelten die Datenschutzbestimmungen von Google.\n"
            "- Bug-Reports: Beim Senden von Support-Anfragen wird die Fehlerbeschreibung\n"
            "  an einen internen Discord-Webhook weitergeleitet.\n\n"
            "4. URHEBERRECHT & LIZENZEN\n"
            "-----------------------------------------------------------\n"
            "© 2026 Aether Software. Alle Rechte vorbehalten.\n"
            "Nutzt Open-Source-Komponenten: CustomTkinter, Google GenAI SDK, DuckDuckGo Search."
        )

        txt_legal.insert("1.0", legal_text)
        txt_legal.configure(state="disabled")

    def change_theme_event(self, choice):
        self.current_theme_name = choice
        self.apply_theme(choice)
        self.save_settings()

    def change_yellow_hue_event(self, value):
        self.yellow_hue_val = float(value)
        hue = self.yellow_hue_val / 360.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
        hex_color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        self.current_theme["accent"] = hex_color
        self.update_accent_colors(hex_color)
        self.save_settings()

    def change_font_size_event(self, value):
        self.current_font_size = int(value)
        self.txt_output.configure(font=("Arial", self.current_font_size))
        self.save_settings()

    def change_volume_event(self, value):
        self.tts_volume = float(value)
        self.save_settings()

    def update_accent_colors(self, accent_color):
        self.tabview.configure(
            segmented_button_selected_color=accent_color,
            segmented_button_selected_hover_color=accent_color
        )
        self.btn_search.configure(fg_color=accent_color, text_color="black")
        self.combo_theme.configure(fg_color=accent_color, button_color=accent_color, text_color="black")
        self.slider_yellow.configure(progress_color=accent_color, button_color=accent_color)
        if hasattr(self, 'switch_anim'):
            self.switch_anim.configure(progress_color=accent_color)
        if hasattr(self, 'switch_tts'):
            self.switch_tts.configure(progress_color=accent_color)

    def apply_theme(self, theme_name):
        theme = THEMES.get(theme_name, THEMES["BANY THEME 🍋"])
        self.current_theme = theme

        bg = theme["bg"]
        sidebar_bg = theme.get("sidebar_bg", "#181818")
        accent = theme["accent"]

        self.configure(fg_color=bg)
        self.sidebar_frame.configure(fg_color=sidebar_bg)
        self.bg_canvas.configure(bg=bg)
        self.update_accent_colors(accent)

        if self.is_admin_logged_in:
            self.load_admin_dashboard()

if __name__ == "__main__":
    app = AetherOSAssistant()
    app.mainloop()