import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import sys
import subprocess
import threading
from pathlib import Path

# Paths to script components (handles PyInstaller temporary resource directory)
if getattr(sys, 'frozen', False):
    RESOURCE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    APP_DIR = RESOURCE_DIR

CONVERTER_SCRIPT = RESOURCE_DIR / "g7_master_converter.py"

class FTRPipelineGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FTR Exporter Pipeline")
        self.minsize(600, 500)

        # Config state
        self.config_path = APP_DIR / "pipeline_config.json"
        self.config = {
            "g7_reader_path": "",
            "blender_path": "",
            "output_dir": "",
            "invert_green": False,
            "use_log": False,
            "show_console": False,
            "geometry": "700x600"
        }
        self.load_config()

        # Apply geometry dynamically from configuration cache
        saved_geometry = self.config.get("geometry", "")
        if saved_geometry:
            self.geometry(saved_geometry)
        else:
            self.geometry("700x600")

        # Bind closing event to capture coordinate positions
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Input files
        self.input_files = []

        self.setup_ui()
        
    def on_close(self):
        # Update config geometry string and flush to disk
        self.config["geometry"] = self.geometry()
        self.save_config()
        self.destroy()
    
    def load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception as e:
                print(f"Failed to load config: {e}")

    def save_config(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def setup_ui(self):
        # Initialize variables first to avoid trace issues
        self.reader_var = tk.StringVar(value=self.config.get("g7_reader_path", ""))
        self.blender_var = tk.StringVar(value=self.config.get("blender_path", ""))
        self.invert_green_var = tk.BooleanVar(value=self.config.get("invert_green", False))
        self.use_log_var = tk.BooleanVar(value=self.config.get("use_log", False))
        self.show_console_var = tk.BooleanVar(value=self.config.get("show_console", False))
        self.dest_var = tk.StringVar(value=self.config.get("output_dir", ""))

        # Configure grid weight
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        # Style
        style = ttk.Style(self)
        style.theme_use('clam')

        # GitHub Dark Theme Colors
        bg_color = "#0d1117"
        fg_color = "#c9d1d9"
        border_color = "#30363d"
        secondary_bg = "#161b22"
        accent_color = "#58a6ff"
        button_hover = "#1f6feb"

        self.configure(bg=bg_color)

        style = ttk.Style(self)
        style.theme_use('clam')

        # Configure basic colors
        style.configure(".", background=bg_color, foreground=fg_color, bordercolor=border_color, font=("Segoe UI", 10))
        
        # TLabeledScale / LabelFrame
        style.configure("TLabelframe", background=bg_color, foreground=accent_color, bordercolor=border_color)
        style.configure("TLabelframe.Label", background=bg_color, foreground=accent_color, font=("Segoe UI", 10, "bold"))

        # Labels
        style.configure("TLabel", background=bg_color, foreground=fg_color)

        # Buttons
        style.configure("TButton", background=secondary_bg, foreground=fg_color, borderwidth=1, focuscolor=accent_color)
        style.map("TButton",
                  background=[('active', border_color), ('pressed', border_color)],
                  foreground=[('active', accent_color)])
        
        # Accent Button
        style.configure("Accent.TButton", background=accent_color, foreground=bg_color, font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[('active', button_hover)])

        # Entries
        style.configure("TEntry", fieldbackground=secondary_bg, foreground=fg_color, bordercolor=border_color, lightcolor=border_color, darkcolor=border_color)
        
        # Checkbuttons
        style.configure("TCheckbutton", background=bg_color, foreground=fg_color)
        style.map("TCheckbutton", background=[('active', bg_color)], foreground=[('active', accent_color)])

        # Progressbar
        style.configure("TProgressbar", thickness=10, background=accent_color, troughcolor=secondary_bg, bordercolor=border_color)

        # --- Frame 1: Paths ---
        paths_frame = ttk.LabelFrame(self, text="Global Settings", padding=15)
        paths_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        paths_frame.columnconfigure(1, weight=1)

        # G7Reader Path
        ttk.Label(paths_frame, text="G7Reader.exe:").grid(row=0, column=0, sticky="w")
        self.reader_var.trace_add("write", self.on_config_change)
        ttk.Entry(paths_frame, textvariable=self.reader_var).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Button(paths_frame, text="Browse", command=lambda: self.browse_file(self.reader_var, "Executable", "*.exe")).grid(row=0, column=2)

        # Blender Path
        ttk.Label(paths_frame, text="Blender.exe:").grid(row=1, column=0, sticky="w", pady=10)
        self.blender_var.trace_add("write", self.on_config_change)
        ttk.Entry(paths_frame, textvariable=self.blender_var).grid(row=1, column=1, sticky="ew", padx=10, pady=10)
        ttk.Button(paths_frame, text="Browse", command=lambda: self.browse_file(self.blender_var, "Executable", "*.exe")).grid(row=1, column=2, pady=10)

        # Output Dir
        ttk.Label(paths_frame, text="Destination:").grid(row=2, column=0, sticky="w")
        self.dest_var.trace_add("write", self.on_config_change)
        ttk.Entry(paths_frame, textvariable=self.dest_var).grid(row=2, column=1, sticky="ew", padx=10)
        ttk.Button(paths_frame, text="Browse", command=self.browse_dest).grid(row=2, column=2)

        # --- Frame 1.5: Options ---
        opts_frame = ttk.LabelFrame(self, text="Extraction Options", padding=15)
        opts_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        ttk.Checkbutton(opts_frame, text="Invert Normal Green (DirectX)", 
                        variable=self.invert_green_var, command=self.on_config_change).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Checkbutton(opts_frame, text="Create Debug Log", 
                        variable=self.use_log_var, command=self.on_config_change).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Checkbutton(opts_frame, text="Show Process Console", 
                        variable=self.show_console_var, command=self.on_config_change).pack(side=tk.LEFT)

        # --- Frame 2: Input Files ---
        input_frame = ttk.LabelFrame(self, text="Input .G7 Files", padding=15)
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        input_frame.columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(input_frame)
        btn_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(btn_frame, text="Add Files", command=self.add_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="Clear List", command=self.clear_files).pack(side=tk.LEFT)

        self.file_listbox = tk.Listbox(input_frame, height=5, selectmode=tk.EXTENDED, 
                                       bg=secondary_bg, fg=fg_color, borderwidth=1, 
                                       highlightthickness=1, highlightbackground=border_color,
                                       font=("Segoe UI Semilight", 10))
        self.file_listbox.grid(row=1, column=0, sticky="ew")

        # --- Frame 3: Run / Progress ---
        run_frame = ttk.Frame(self, padding=15)
        run_frame.grid(row=3, column=0, sticky="ew", padx=10)
        run_frame.columnconfigure(1, weight=1)

        self.run_btn = ttk.Button(run_frame, text="Run Pipeline", command=self.start_pipeline, style="Accent.TButton")
        self.run_btn.grid(row=0, column=0, ipady=10, ipadx=20)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(run_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=1, sticky="ew", padx=20)

        self.status_lbl = ttk.Label(run_frame, text="Ready.", font=("Segoe UI", 10, "italic"))
        self.status_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # --- Frame 4: Log Output ---
        log_frame = ttk.LabelFrame(self, text="Log Output", padding=15)
        log_frame.grid(row=4, column=0, sticky="nsew", padx=10, pady=5)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_txt = tk.Text(log_frame, state='disabled', wrap='word', height=10,
                               bg=secondary_bg, fg=fg_color, borderwidth=0, 
                               highlightthickness=1, highlightbackground=border_color,
                               font=("Consolas", 10))
        self.log_txt.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_txt.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.log_txt['yscrollcommand'] = scrollbar.set

    def on_config_change(self, *args):
        self.config["g7_reader_path"] = self.reader_var.get()
        self.config["blender_path"] = self.blender_var.get()
        self.config["output_dir"] = self.dest_var.get()
        self.config["invert_green"] = self.invert_green_var.get()
        self.config["use_log"] = self.use_log_var.get()
        self.config["show_console"] = self.show_console_var.get()
        self.save_config()

    def browse_file(self, var, description, extension):
        path = filedialog.askopenfilename(title=f"Select {description}", filetypes=[(description, extension)])
        if path:
            var.set(path)

    def browse_dest(self):
        path = filedialog.askdirectory(title="Select Destination Folder")
        if path:
            self.dest_var.set(path)

    def add_files(self):
        files = filedialog.askopenfilenames(title="Select .g7 files", filetypes=[("G7 Files", "*.g7"), ("All Files", "*.*")])
        for f in files:
            if f not in self.input_files:
                self.input_files.append(f)
                self.file_listbox.insert(tk.END, f)

    def clear_files(self):
        self.input_files.clear()
        self.file_listbox.delete(0, tk.END)

    def log(self, text):
        self.log_txt.configure(state='normal')
        self.log_txt.insert(tk.END, text + "\n")
        self.log_txt.see(tk.END)
        self.log_txt.configure(state='disabled')
        self.update_idletasks()

    def update_status(self, text, progress=None):
        self.status_lbl.config(text=text)
        if progress is not None:
            self.progress_var.set(progress)

    def start_pipeline(self):
        if not self.input_files:
            messagebox.showwarning("No Input", "Please add some .g7 files first.")
            return
        
        reader_exe = self.reader_var.get()
        blender_exe = self.blender_var.get()
        dest_dir = self.dest_var.get()

        if not os.path.isfile(reader_exe):
            messagebox.showerror("Error", "Valid G7Reader.exe path is required.")
            return
        if not os.path.isfile(blender_exe):
            messagebox.showerror("Error", "Valid Blender.exe path is required.")
            return
        if not dest_dir:
            messagebox.showerror("Error", "Destination folder is required.")
            return
        if not os.path.isfile(CONVERTER_SCRIPT):
            messagebox.showerror("Error", f"Could not find {CONVERTER_SCRIPT.name}.")
            return
        if len(self.input_files) == 0:
            messagebox.showerror("Error", "No .g7 files selected. Please add files first.")
            return

        self.run_btn.config(state="disabled")
        self.log_txt.configure(state='normal')
        self.log_txt.delete("1.0", tk.END)
        self.log_txt.configure(state='disabled')

        # Run process in a separate thread to keep UI responsive
        t = threading.Thread(target=self.run_pipeline_thread, args=(reader_exe, blender_exe, dest_dir))
        t.daemon = True
        t.start()

    def run_pipeline_thread(self, reader_exe, blender_exe, dest_dir):
        total_files = len(self.input_files)
        
        # 0. Initial log cleanup if enabled
        log_file = os.path.join(dest_dir, "conversion_log.txt")
        if self.use_log_var.get():
            if os.path.exists(log_file):
                try:
                    os.remove(log_file)
                except:
                    pass

        success_count = 0
        failure_count = 0

        for i, g7_file in enumerate(self.input_files):
            g7_path = Path(g7_file)
            g7_name = g7_path.stem
            out_folder = Path(dest_dir) / g7_name
            
            self.update_status(f"Processing ({i+1}/{total_files}): {g7_name}", progress=(i / total_files) * 100)
            self.log(f"\n--- Processing: {g7_name} ---")

            # 1. Create out folder
            out_folder.mkdir(parents=True, exist_ok=True)
            attach_log_path = out_folder / "attach_log.txt"

            # 2. Run G7Reader
            self.log(f"Running G7Reader on {g7_name}...")
            try:
                if self.show_console_var.get():
                    # Run in a new visible console so user can watch output.
                    subprocess.run(["cmd", "/c", reader_exe, str(g7_path), str(out_folder)], 
                                   creationflags=subprocess.CREATE_NEW_CONSOLE)
                    # Capture attach_log silently (second pass).  reader_proc
                    # is assigned here so the returncode check below is valid.
                    with open(attach_log_path, "w") as af:
                        reader_proc = subprocess.run([reader_exe, str(g7_path), str(out_folder)], stdout=af, stderr=subprocess.STDOUT)
                else:
                    with open(attach_log_path, "w") as af:
                        reader_proc = subprocess.run([reader_exe, str(g7_path), str(out_folder)],
                                                     stdout=af, stderr=subprocess.STDOUT)
                
                if reader_proc.returncode != 0:
                    self.log(f"[WARNING] G7Reader returned non-zero exit code {reader_proc.returncode}")
                else:
                    self.log("G7Reader completed successfully.")
            except Exception as e:
                self.log(f"[ERROR] Failed to run G7Reader: {e}")
                failure_count += 1
                continue

            # 3. Run Blender with converter script
            self.log(f"Running Blender Conversion on {g7_name}...")
            try:
                blender_cmd = [
                    blender_exe, 
                    "-b", 
                    "--python", str(CONVERTER_SCRIPT), 
                    "--"
                ]
                
                if self.invert_green_var.get():
                    blender_cmd.append("--invert-green")
                if not self.use_log_var.get():
                    blender_cmd.append("--no-log")
                
                blender_cmd.append(str(out_folder))
                
                # We can stream output to log window
                if self.show_command_console():
                     # Run Blender in a visible console — stdout won't be
                     # captured so skip the line-streaming loop entirely.
                     blender_proc = subprocess.Popen(blender_cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                     blender_proc = subprocess.Popen(blender_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
                
                if blender_proc.stdout is not None:
                    for line in blender_proc.stdout:
                        # Only show important lines or keep it brief
                        line_str = line.strip()
                        if line_str and not line_str.startswith("Blender"):
                            self.log(f"  {line_str}")
                
                blender_proc.wait()
                
                # --- Cleanup: remove attach_log.txt ---
                if attach_log_path.exists():
                    try: os.remove(attach_log_path)
                    except: pass

                if blender_proc.returncode != 0:
                    self.log(f"[ERROR] Blender crashed or returned exit code {blender_proc.returncode}")
                    failure_count += 1
                    continue
                else:
                    success_count += 1
            except Exception as e:
                self.log(f"[ERROR] Failed to run Blender: {e}")
                failure_count += 1
                continue


        # Finish up
        self.update_status("Completed.", progress=100.0)
        self.log("\n========================================")
        self.log("         BATCH PIPELINE REPORT")
        self.log("========================================")
        
        # Parse conversion_log.txt for blend-level and model-level stats
        log_blend_ok = 0
        log_blend_fail = 0
        log_model_ok = 0
        log_model_fail = 0
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    for line in f:
                        if line.startswith("OK [blend]"): log_blend_ok += 1
                        elif line.startswith("OK [model]"): log_model_ok += 1
                        elif line.startswith("FAIL "): log_model_fail += 1
            except:
                pass
        else:
            self.log("[WARNING] conversion_log.txt not generated by Blender script.")
        
        final_succ = max(success_count, log_blend_ok)
        final_fail = max(failure_count, log_blend_fail)

        self.log(f"Blend files created: {final_succ}")
        self.log(f"Models imported:     {log_model_ok}")
        if log_model_fail > 0:
            self.log(f"Models failed:       {log_model_fail}")
        self.log(f"Failed G7 files:     {final_fail}")
        self.log(f"Full log: {log_file}")
        
        if (final_fail > 0 or log_model_fail > 0) and os.path.exists(log_file):
            self.log("\n--- FAILED ITEMS ---")
            try:
                with open(log_file, "r") as f:
                    for line in f:
                        if line.startswith("FAIL "):
                            self.log(line.strip())
            except: pass
        self.log("========================================")
        
        # Re-enable button
        self.after(0, lambda: self.run_btn.config(state="normal"))


    def show_command_console(self):
        return self.show_console_var.get()

if __name__ == "__main__":
    app = FTRPipelineGUI()
    app.run_btn.config(style="TButton") # Revert accent if missing
    style = ttk.Style()
    if 'Accent.TButton' not in style.theme_names():
        app.run_btn.config(style="TButton")
    app.mainloop()
