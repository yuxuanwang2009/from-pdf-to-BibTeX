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

        self.pdf_engine = PDFEngine()
        self.llm_controller = None
        self.current_context = "" # Holds text of last ~15 pages
        
        self.current_page = 0
        self.image_ref = None # Keep reference to avoid GC
        self.citation_rects = [] # Not used in new logic but kept for safety

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
        # Layout: Fixed Frames
        self.viewer_frame = tk.Frame(self.root, bg="gray")
        self.viewer_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.control_frame = tk.Frame(self.root, padx=10, pady=10, width=450)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.control_frame.pack_propagate(False)

        # Canvas
        self.canvas = tk.Canvas(self.viewer_frame, bg="#404040") 
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Configure>", self.on_resize)
        
        self.root.bind("<Left>", lambda e: self.prev_page())
        self.root.bind("<Right>", lambda e: self.next_page())
        
        # --- Right: Controls ---
        
        # Top Controls
        btn_frame = tk.Frame(self.control_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        # Open PDF (Disabled initially)
        self.btn_open = tk.Button(btn_frame, text="Open PDF", command=self.open_pdf, state="disabled")
        self.btn_open.pack(side=tk.LEFT, padx=2)
        
        # Navigation
        tk.Button(btn_frame, text="<", command=self.prev_page).pack(side=tk.LEFT, padx=5)
        self.lbl_page = tk.Label(btn_frame, text="Page: 0/0")
        self.lbl_page.pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text=">", command=self.next_page).pack(side=tk.LEFT, padx=5)

        # Options Frame
        opt_frame = tk.LabelFrame(self.control_frame, text="Setup")
        opt_frame.pack(fill=tk.X, pady=10)
        
        # API Key Row
        key_frame = tk.Frame(opt_frame)
        key_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(key_frame, text="API Key:").grid(row=0, column=0, sticky="w", padx=(0,5))
        
        self.key_container = tk.Frame(key_frame)
        self.key_container.grid(row=0, column=1, sticky="ew")
        key_frame.columnconfigure(1, weight=1)
        
        self.key_status_label = tk.Label(key_frame, text="", font=("Arial", 9))
        self.key_status_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=5)

        self._build_key_input_state()
        
        # Disclaimer
        tk.Label(opt_frame, text="Requirement: Valid API Key is needed to unlock features.", fg="gray", font=("Arial", 9)).pack(anchor="w", padx=5)
        tk.Label(opt_frame, text="Tip: Select any citation or reference text to parse.", fg="gray", font=("Arial", 9)).pack(anchor="w", padx=5)

        # Output Text Area
        tk.Label(self.control_frame, text="Extracted BibTeX:").pack(anchor="w")
        self.output_text = scrolledtext.ScrolledText(self.control_frame, height=20)
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Context Menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy Selection", command=self.copy_selection)
        self.output_text.bind("<Button-3>", self.show_context_menu)
        self.output_text.bind("<Button-2>", self.show_context_menu)
        self.output_text.bind("<Control-Button-1>", self.show_context_menu)

        # Bottom Actions
        action_frame = tk.Frame(self.control_frame)
        action_frame.pack(fill=tk.X, pady=5)
        
        tk.Button(action_frame, text="Copy All", command=self.copy_to_clipboard).pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="Reset Output", command=self.clear_output).pack(side=tk.LEFT, padx=2)
        
        self.status_var = tk.StringVar(value="Please enter API Key.")
        tk.Label(self.control_frame, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor="w").pack(side=tk.BOTTOM, fill=tk.X)

    def _build_key_input_state(self):
        for widget in self.key_container.winfo_children():
            widget.destroy()
        
        self.key_container.columnconfigure(0, weight=1)
        self.key_container.columnconfigure(1, weight=0)
        
        self.key_entry = tk.Entry(self.key_container, textvariable=self.api_key_var, show="*", width=30)
        self.key_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        self.enter_btn = tk.Button(self.key_container, text="Verify", command=self.check_api_key, font=("Arial", 9), width=10)
        self.enter_btn.grid(row=0, column=1)

    def check_api_key(self):
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter an API Key.")
            return

        self.key_status_label.config(text="Verifying...", fg="blue")
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
        self.key_status_label.config(text=f"Error: {short_msg}", fg="red")
        print(f"Key Error: {msg}")

    def _on_key_success(self, ctrl):
        # Determine Provider and Model
        provider = getattr(ctrl.llm, 'provider', 'gemini')
        current_model = getattr(ctrl.llm, 'model_name', None) or "gemini-1.5-flash"
        
        # Get Available Models
        from llm_helper import LLMHelper
        models = LLMHelper.AVAILABLE_MODELS.get(provider, [current_model])

        self.key_status_label.config(text=f"Connected ({provider})", fg="green")
        self.llm_controller = ctrl
        
        # Save Key
        self.save_config(self.api_key_var.get().strip())
        
        # Enable UI
        self.btn_open.config(state="normal")
        self.status_var.set(f"Ready. Using {current_model}.")

        # Switch to Active UI: [Label "Model:"] [Combobox] [Button "Change Key"]
        for widget in self.key_container.winfo_children():
            widget.destroy()
        
        # 1. Label
        tk.Label(self.key_container, text="Model:", fg="green", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0,2))
        
        # 2. Combobox
        self.model_combo = ttk.Combobox(self.key_container, values=models, width=18, state="readonly")
        self.model_combo.set(current_model)
        self.model_combo.pack(side=tk.LEFT, padx=2)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_changed)
        
        # 3. Change Key Button
        btn = tk.Button(self.key_container, text="Change Key", width=10, font=("Arial", 9), command=self.reset_api_ui)
        btn.pack(side=tk.LEFT, padx=5)

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
            # Load FULL context (or smart subset handled by engine)
            self.current_context = self.pdf_engine.get_context_text(page_count=None)
            self.update_status(f"Context Loaded ({len(self.current_context)} chars). Ready.")
        except Exception as e:
            print(f"Context error: {e}")
            self.update_status("Context Load Failed (Check Console).")

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
                result = self.llm_controller.resolve_citation(text, self.current_context)
                self.append_to_output(result + "\n\n")
                self.update_status("Resolution Complete.")
            except Exception as e:
                self.append_to_output(f"% [Error] {e}\n\n")
                self.update_status(f"Error: {e}")

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
