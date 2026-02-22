from pathlib import Path

f = Path('/Volumes/WD_DATA/ForensicDataSeal_Tool/forensicdataseal/gui/gui.py')
txt = f.read_text()

SPLASH_CODE = """
VALID_KEYS = {
    "FDS-2847-9A3C-X721",
    "FDS-3F91-B2D4-K835",
    "FDS-7C52-E8A1-M294",
    "FDS-4A83-D6F2-P517",
    "FDS-9B14-C7E3-R068",
}

LOAD_STEPS = [
    "Initializing SHA-256 Engine",
    "Verifying System Integrity",
    "Loading Forensic Modules",
    "Ready",
]

class SplashScreen:
    def __init__(self, root, on_success):
        self.root = root
        self.on_success = on_success
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg="#0A0F1E")
        W, H = 520, 400
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        self.win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.win.lift()
        self.win.attributes("-topmost", True)
        self._build()
        self._step = 0
        self._animate()

    def _build(self):
        tk.Label(self.win, text="FORensic DataSeal",
                 font=("Helvetica Neue", 26, "bold"),
                 fg="white", bg="#0A0F1E").pack(pady=(40, 2))
        tk.Label(self.win, text="v1.0.0  -  Air Gapped  -  SHA-256",
                 font=("Helvetica Neue", 10),
                 fg="#00D4FF", bg="#0A0F1E").pack(pady=(0, 30))
        self.steps_frame = tk.Frame(self.win, bg="#0A0F1E")
        self.steps_frame.pack(fill="x", padx=60)
        self.step_labels = []
        for step in LOAD_STEPS:
            row = tk.Frame(self.steps_frame, bg="#0A0F1E")
            row.pack(fill="x", pady=3)
            dot = tk.Label(row, text="o", font=("Helvetica Neue", 11),
                           fg="#334466", bg="#0A0F1E", width=2)
            dot.pack(side="left")
            lbl = tk.Label(row, text=step, font=("Helvetica Neue", 10),
                           fg="#334466", bg="#0A0F1E", anchor="w")
            lbl.pack(side="left")
            self.step_labels.append((dot, lbl))
        self.key_frame = tk.Frame(self.win, bg="#0A0F1E")
        tk.Label(self.key_frame, text="License Key",
                 font=("Helvetica Neue", 10),
                 fg="#8899AA", bg="#0A0F1E").pack(pady=(20, 4))
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(self.key_frame,
                                  textvariable=self.key_var,
                                  font=("Courier", 13, "bold"),
                                  fg="#00D4FF", bg="#0D1526",
                                  insertbackground="#00D4FF",
                                  relief="flat", bd=0,
                                  width=22, justify="center")
        self.key_entry.pack(ipady=8)
        tk.Frame(self.key_frame, bg="#00D4FF", height=1).pack(fill="x", padx=4)
        self.msg_lbl = tk.Label(self.key_frame, text="",
                                 font=("Helvetica Neue", 9),
                                 bg="#0A0F1E")
        self.msg_lbl.pack(pady=4)
        self.start_btn = tk.Button(self.key_frame, text="  START  ",
                                    font=("Helvetica Neue", 11, "bold"),
                                    fg="white", bg="#00D4FF",
                                    activebackground="#0099BB",
                                    relief="flat", bd=0, cursor="hand2",
                                    command=self._validate_key)
        self.start_btn.pack(pady=(4, 0), ipady=8, ipadx=20)
        self.key_entry.bind("<Return>", lambda e: self._validate_key())

    def _animate(self):
        if self._step < len(self.step_labels):
            dot, lbl = self.step_labels[self._step]
            dot.config(text="v", fg="#00FF88")
            lbl.config(fg="white")
            self._step += 1
            self.win.after(600, self._animate)
        else:
            self.win.after(300, self._show_key_entry)

    def _show_key_entry(self):
        self.key_frame.pack(pady=(10, 20))
        self.key_entry.focus_set()

    def _validate_key(self):
        key = self.key_var.get().strip().upper()
        if key in VALID_KEYS:
            self.msg_lbl.config(text="Valid", fg="#00FF88")
            self.win.after(500, self._launch)
        else:
            self.msg_lbl.config(text="Invalid key", fg="#FF4466")
            self.key_entry.config(fg="#FF4466")
            self.win.after(800, lambda: self.key_entry.config(fg="#00D4FF"))

    def _launch(self):
        self.win.destroy()
        self.on_success()

"""

marker = "\\n# " + "-"*75 + "\\n#  CUSTOM WIDGETS"
if marker in txt:
    if "VALID_KEYS" not in txt:
        txt = txt.replace(marker, SPLASH_CODE + marker)
        print("Splash inserted OK")
    else:
        print("Splash already present")
else:
    print("ERROR: marker not found")
    idx = txt.find("CUSTOM WIDGETS")
    print(repr(txt[max(0,idx-80):idx+20]))

old_main = "    root = tk.Tk()\n    app  = App(root)\n    root.mainloop()"
new_main = "    root = tk.Tk()\n    root.withdraw()\n\n    def launch_app():\n        root.deiconify()\n        App(root)\n\n    SplashScreen(root, on_success=launch_app)\n    root.mainloop()"

if old_main in txt:
    txt = txt.replace(old_main, new_main)
    print("Startup patched OK")
elif "root.withdraw()" in txt:
    print("Startup already patched")
else:
    idx = txt.find("root = tk.Tk()")
    print(f"Not found at {idx}:")
    print(repr(txt[idx:idx+100]))

f.write_text(txt)
print("Done")
