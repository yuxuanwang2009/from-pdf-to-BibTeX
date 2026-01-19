import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
import fitz
from PIL import Image, ImageTk
import threading
import os

from pdf_engine import PDFEngine
from llm_controller import LLMController

class BibApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Bib Extractor (LLM-Only)")
        self.root.geometry("1400x900")

        # --- Visual Style & Theme ---
        self.colors = {
            "bg_root": "#2E2E2E",      # Dark grey window background
            "bg_panel": "#383838",     # Slightly lighter control panel
            "fg_text": "#E0E0E0",      # Light grey text
            "accent": "#61AFEF",       # Blue accent
            "btn_bg": "#444444",       # Button background
            "btn_fg": "#FFFFFF",       # Button text
            "entry_bg": "#252525",     # Entry/Text background
            "canvas_bg": "#404040",    # PDF Canvas background
            "success": "#98C379",      # Green
            "error": "#E06C75"         # Red
        }

        self.root.configure(bg=self.colors["bg_root"])
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Common Styles
        self.style.configure("TFrame", background=self.colors["bg_panel"])
        self.style.configure("Root.TFrame", background=self.colors["bg_root"])
        
        self.style.configure("TLabel", background=self.colors["bg_panel"], foreground=self.colors["fg_text"], font=("Helvetica", 11))
        self.style.configure("Header.TLabel", font=("Helvetica", 12, "bold"), foreground=self.colors["accent"])
        self.style.configure("Status.TLabel", font=("Helvetica", 10, "italic"), foreground="gray")
        
        self.style.configure("TButton", 
                             font=("Helvetica", 11), 
                             background=self.colors["btn_bg"], 
                             foreground=self.colors["btn_fg"], 
                             borderwidth=1, 
                             focusthickness=3, 
                             focuscolor="none")
        self.style.map("TButton", background=[("active", "#555555"), ("pressed", "#222222")])
        
        self.style.configure("TLabelframe", background=self.colors["bg_panel"], foreground=self.colors["fg_text"], borderwidth=1)
        self.style.configure("TLabelframe.Label", background=self.colors["bg_panel"], foreground=self.colors["accent"], font=("Helvetica", 10, "bold"))
        
        self.style.configure("TEntry", fieldbackground=self.colors["entry_bg"], foreground=self.colors["fg_text"], insertcolor="white", borderwidth=0)
        
        # ----------------------------

        self.pdf_engine = PDFEngine()
        self.llm_controller = None
        self.current_context = "" # Holds text of last ~15 pages
        
        self.current_page = 0
        self.image_ref = None # Keep reference to avoid GC
        self.current_page = 0
        self.image_ref = None # Keep reference to avoid GC
        self.citation_rects = [] # Not used in new logic but kept for safety
        self.citation_style_hint = None # Stores detected style (e.g. "Numeric")

        # State
        self.output_dir = os.path.expanduser("~/Documents/BibExtractor")
        self.config_file = os.path.join(os.path.expanduser("~"), ".bib_extractor_config.json")
        
        # Load Key Priority: Env Var -> Config File -> Empty
        initial_key = os.getenv("GOOGLE_API_KEY", "")
        if not initial_key:
            initial_key = self.load_config().get("api_key", "")
            
        self.api_key_var = tk.StringVar(value=initial_key) 
        self.selection_start = None
        self.zoom_level = 1.5
        
        self._setup_ui()

    def load_config(self):
        import json
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_config(self, key):
        import json
        try:
            with open(self.config_file, "w") as f:
                json.dump({"api_key": key}, f)
        except Exception as e:
            print(f"Failed to save config: {e}")


    def _setup_ui(self):
        # --- Left: PDF Viewer (Canvas) ---
        self.viewer_frame = tk.Frame(self.root, bg=self.colors["bg_root"])
        self.viewer_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.viewer_frame, bg=self.colors["canvas_bg"], highlightthickness=0) 
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", self.on_resize)
        
        self.root.bind("<Left>", lambda e: self.prev_page())
        self.root.bind("<Right>", lambda e: self.next_page())
        
        # --- Right: Controls ---
        self.control_frame = tk.Frame(self.root, width=400, bg=self.colors["bg_panel"])
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.control_frame.pack_propagate(False)
        
        # Padding Container
        content_box = ttk.Frame(self.control_frame, style="TFrame")
        content_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 1. Navigation & Open
        nav_frame = ttk.Frame(content_box)
        nav_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.btn_open = ttk.Button(nav_frame, text="Open PDF", command=self.open_pdf, state="disabled", width=12)
        self.btn_open.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(nav_frame, text="<", width=3, command=self.prev_page).pack(side=tk.LEFT)
        self.lbl_page = ttk.Label(nav_frame, text="Page: 0/0", width=12, anchor="center")
        self.lbl_page.pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_frame, text=">", width=3, command=self.next_page).pack(side=tk.LEFT)

        # 2. Setup / API Key
        setup_frame = ttk.LabelFrame(content_box, text="Connection Setup", padding=15)
        setup_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.key_container = ttk.Frame(setup_frame)
        self.key_container.pack(fill=tk.X)
        self._build_key_input_state()
        
        self.key_status_label = ttk.Label(setup_frame, text="", font=("Helvetica", 9))
        self.key_status_label.pack(anchor="w", pady=(5,0))
        
        ttk.Label(setup_frame, text="Valid API Key required.", style="Status.TLabel").pack(anchor="w", pady=(10,0))

        # 3. Output Area
        ttk.Label(content_box, text="Extracted BibTeX", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        
        self.output_text = scrolledtext.ScrolledText(content_box, height=20, bg=self.colors["entry_bg"], fg=self.colors["fg_text"], insertbackground="white", borderwidth=0, font=("Consolas", 10))
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Context Menu
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=self.colors["bg_panel"], fg=self.colors["fg_text"])
        self.context_menu.add_command(label="Copy Selection", command=self.copy_selection)
        self.output_text.bind("<Button-3>", self.show_context_menu)
        self.output_text.bind("<Button-2>", self.show_context_menu)
        self.output_text.bind("<Control-Button-1>", self.show_context_menu)

        # 4. Action Buttons
        action_frame = ttk.Frame(content_box)
        action_frame.pack(fill=tk.X)
        
        ttk.Button(action_frame, text="Copy All", command=self.copy_to_clipboard, width=15).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(action_frame, text="Clear", command=self.clear_output, width=10).pack(side=tk.LEFT)
        
        # 5. Global Status Bar
        self.status_var = tk.StringVar(value="Please enter API Key.")
        self.status_bar = tk.Label(self.control_frame, textvariable=self.status_var, bg=self.colors["bg_root"], fg="gray", anchor="w", padx=10, pady=5, font=("Helvetica", 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_key_input_state(self):
        for widget in self.key_container.winfo_children():
            widget.destroy()
            
        ttk.Label(self.key_container, text="API Key:").pack(side=tk.LEFT, padx=(0,5))
        
        self.key_entry = ttk.Entry(self.key_container, textvariable=self.api_key_var, show="*", width=20)
        self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.enter_btn = ttk.Button(self.key_container, text="Connect", command=self.check_api_key, width=8)
        self.enter_btn.pack(side=tk.LEFT)

    def check_api_key(self):
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter an API Key.")
            return

        self.key_status_label.config(text="Verifying...", foreground=self.colors["accent"])
        self.root.update_idletasks()

        def verify_wrapper():
            result = {}
            def target():
                try:
                    # Test connection via LLMController -> Helper
                    ctrl = LLMController(api_key=key)
                    # We access the helper directly for validation
                    success, msg = ctrl.llm.validate_connection()
                    result['res'] = (success, msg, ctrl)
                except Exception as e:
                    result['error'] = str(e)

            t = threading.Thread(target=target)
            t.start()
            t.join(timeout=10)
            
            if t.is_alive():
                self.root.after(0, lambda: self._on_key_error("Timeout (10s). Check Network."))
                return

            if 'error' in result:
                self.root.after(0, lambda: self._on_key_error(result['error']))
            elif 'res' in result:
                success, msg, ctrl = result['res']
                if success:
                    self.root.after(0, lambda: self._on_key_success(ctrl))
                else:
                    self.root.after(0, lambda: self._on_key_error(msg))
            else:
                self.root.after(0, lambda: self._on_key_error("Unknown Error"))

        threading.Thread(target=verify_wrapper, daemon=True).start()

    def _on_key_error(self, msg):
        short_msg = (msg[:40] + '...') if len(msg) > 40 else msg
        self.key_status_label.config(text=f"Error: {short_msg}", foreground=self.colors["error"])
        print(f"Key Error: {msg}")

    def _on_key_success(self, ctrl):
        # Determine Provider and Model
        provider = getattr(ctrl.llm, 'provider', 'gemini')
        current_model = getattr(ctrl.llm, 'model_name', None) or "gemini-1.5-flash"
        
        # Get Available Models
        from llm_helper import LLMHelper
        models = LLMHelper.AVAILABLE_MODELS.get(provider, [current_model])

        self.key_status_label.config(text=f"Connected ({provider})", foreground=self.colors["success"])
        self.llm_controller = ctrl
        
        # Save Key
        self.save_config(self.api_key_var.get().strip())
        
        # Enable UI
        self.btn_open.config(state="normal")
        self.status_var.set(f"Ready. Using {current_model}.")

        # Switch to Active UI: [Label "Model:"] [Combobox] [Button "Change Key"]
        for widget in self.key_container.winfo_children():
            widget.destroy()
        
        ttk.Label(self.key_container, text="Model:").pack(side=tk.LEFT, padx=(0,5))
        
        self.model_combo = ttk.Combobox(self.key_container, values=models, width=18, state="readonly")
        self.model_combo.set(current_model)
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_changed)
        
        btn = ttk.Button(self.key_container, text="Change", width=8, command=self.reset_api_ui)
        btn.pack(side=tk.LEFT)

    def on_model_changed(self, event):
        if self.llm_controller:
            new_model = self.model_combo.get()
            self.llm_controller.llm.set_model(new_model)
            self.status_var.set(f"Switched to {new_model}")

    def reset_api_ui(self):
        self.api_key_var.set("")
        self.llm_controller = None
        self.btn_open.config(state="disabled")
        self.key_status_label.config(text="")
        self._build_key_input_state()

    def open_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if path:
            self.status_var.set(f"Loading {os.path.basename(path)}...")
            self.root.update()
            try:
                self.pdf_engine.load_pdf(path)
                self.current_page = 0
                self.fit_to_page()
                self.update_page_label()
                self.status_var.set("PDF Loaded. Pre-loading context...")
                
                # Fetch Context in Background
                threading.Thread(target=self._fetch_context_thread, daemon=True).start()
                
            except Exception as e:
                self.status_var.set(f"Error loading PDF: {e}")

    def _fetch_context_thread(self):
        try:
            # Load FULL context, then ask the LLM to locate the bibliography range.
            full_text = self.pdf_engine.get_context_text(page_count=None, force_full=True)
            if not full_text:
                self.update_status("Context Load Failed (Empty).")
                return

            self.update_status(f"Context Loaded ({len(full_text)} chars). Locating bibliography...")
            
            # DEFAULT to full text immediately, so we are robust against LLM failures
            self.current_context = full_text
            
            try:
                narrowed_context = ""
                if self.llm_controller:
                    range_info = self.llm_controller.resolve_bibliography_range(full_text)
                    if range_info:
                        start_page = range_info.get("start_page")
                        end_page = range_info.get("end_page")
                        if isinstance(start_page, int) and isinstance(end_page, int):
                            narrowed_context = self.pdf_engine.get_context_text_range(start_page, end_page)

                        if narrowed_context:
                            self.current_context = narrowed_context
                            self.update_status(f"Context narrowed to pages {start_page}-{end_page}. Ready.")
            except Exception as e:
                print(f"[WARN] Bibliography narrowing failed: {e}")
                self.update_status(f"Bibliography Auto-Locate Failed (Using Full Text).")

            # --- New: Detect Style from Page 1 ---
            self._detect_style_in_background()
        except Exception as e:
            print(f"Context error: {e}")
            self.update_status("Context Load Failed (Check Console).")

    def _detect_style_in_background(self):
        try:
            # Extract text from first few pages (up to 5) to find Main Text
            page_limit = min(5, self.pdf_engine.get_page_count())
            first_pages_text = self.pdf_engine.get_context_text_range(1, page_limit) 
            
            if first_pages_text and self.llm_controller:
                style = self.llm_controller.detect_citation_style(first_pages_text)
                self.citation_style_hint = style
                # Update UI Status if possible, or log it
                print(f"[DEBUG] Detected Citation Style: {style}")
                self.update_status(f"{self.status_var.get()} [Style: {style}]")
        except Exception as e:
            print(f"[WARN] Style detection failed: {e}")

    def render_page(self):
        pix = self.pdf_engine.get_page_pixmap(self.current_page, zoom=self.zoom_level)
        if not pix: return

        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        self.image_ref = ImageTk.PhotoImage(img)

        self.canvas.delete("all")
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        self.canvas.create_image(canvas_w // 2, canvas_h // 2, anchor=tk.CENTER, image=self.image_ref)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.fit_to_page()
            self.update_page_label()

    def next_page(self):
        if self.current_page < self.pdf_engine.get_page_count() - 1:
            self.current_page += 1
            self.fit_to_page()
            self.update_page_label()
            
    def update_page_label(self):
        count = self.pdf_engine.get_page_count()
        self.lbl_page.config(text=f"Page: {self.current_page + 1}/{count}")

    def on_resize(self, event):
        self.fit_to_page()

    def fit_to_page(self):
        if not self.pdf_engine.doc: return
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w > 10 and canvas_h > 10:
            try:
                page = self.pdf_engine.doc[self.current_page]
                scale_w = (canvas_w - 20) / page.rect.width
                scale_h = (canvas_h - 20) / page.rect.height
                self.zoom_level = min(scale_w, scale_h)
                if self.zoom_level < 0.1: self.zoom_level = 0.1
                self.render_page()
            except: pass

    def on_canvas_click(self, event):
        self.selection_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def on_canvas_drag(self, event):
        if not self.selection_start: return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.canvas.delete("selection_box")
        self.canvas.create_rectangle(self.selection_start[0], self.selection_start[1], x, y, outline="red", width=2, tags="selection_box")

    def on_canvas_release(self, event):
        if not self.selection_start: return
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        start_x, start_y = self.selection_start
        
        if abs(x - start_x) > 5 or abs(y - start_y) > 5:
            # Calculate coordinates
            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            if self.image_ref:
                img_w = self.image_ref.width()
                img_h = self.image_ref.height()
                offset_x = (canvas_w - img_w) // 2
                offset_y = (canvas_h - img_h) // 2
            else:
                offset_x = 0; offset_y = 0

            x0 = (min(start_x, x) - offset_x) / self.zoom_level
            y0 = (min(start_y, y) - offset_y) / self.zoom_level
            x1 = (max(start_x, x) - offset_x) / self.zoom_level
            y1 = (max(start_y, y) - offset_y) / self.zoom_level
            
            rect = fitz.Rect(x0, y0, x1, y1)
            text = self.pdf_engine.get_text_in_rect(self.current_page, rect)
            
            if text and text.strip():
                print(f"[DEBUG] User Selection: '{text}'")
                self.status_var.set("Resolving selection with LLM...")
                self._process_selection(text)
            else:
                self.status_var.set("Empty selection.")
            
        self.canvas.delete("selection_box")
        self.selection_start = None

    def _process_selection(self, text):
        if not self.llm_controller:
            return

        def task():
            try:
                # LLM Call
                result = self.llm_controller.resolve_citation(
                    text, 
                    self.current_context, 
                    style_hint=self.citation_style_hint
                )
                if result:
                    self.append_to_output(str(result) + "\n\n")
                    self.update_status("Resolution Complete.")
                else:
                     self.append_to_output("% No result returned.\n\n")
                     self.update_status("Resolution Complete (Empty).")
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                    msg = "% [Error] LLM rate limit exceeded. Please wait a moment."
                else:
                    msg = f"% [Error] {e}"
                
                self.append_to_output(msg + "\n\n")
                self.update_status("Error: Rate Limit Exceeded" if "rate limit" in err_str or "429" in err_str else f"Error: {e}")

        threading.Thread(target=task).start()

    def append_to_output(self, text):
        self.root.after_idle(lambda: self._insert_text(text))

    def _insert_text(self, text):
        self.output_text.insert(tk.END, text)
        self.output_text.see(tk.END)

    def update_status(self, text):
        self.root.after_idle(lambda: self.status_var.set(text))

    def copy_to_clipboard(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.output_text.get("1.0", tk.END))
        self.status_var.set("Copied to clipboard.")

    def clear_output(self):
        self.output_text.delete("1.0", tk.END)

    def show_context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_selection(self):
        try:
            sel = self.output_text.selection_get()
            self.root.clipboard_clear()
            self.root.clipboard_append(sel)
        except tk.TclError: pass

if __name__ == "__main__":
    root = tk.Tk()
    app = BibApp(root)
    root.mainloop()
