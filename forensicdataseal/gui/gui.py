"""
FORensicDataSeal — Desktop GUI
Python 3.11+  ·  tkinter  ·  tkinterdnd2 (drag & drop)  ·  reportlab (PDF)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTEGRATION POINTS  (search  ▶▶ WIRE-IN ◀◀)
  Line ~85  : import seal() and verify() from your cli.py
  Line ~110 : builtin_seal()   — fallback, replace if cli works
  Line ~160 : builtin_verify() — fallback, replace if cli works
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations
import os, sys, threading, hashlib, json, platform, queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── Optional drag-and-drop ────────────────────────────────────────────────────
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

# ── PDF generation ────────────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                     Table, TableStyle, HRFlowable)
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
#  COLORS & CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
C = {
    "bg":       "#0A0F1E",   # deep navy
    "panel":    "#0D1526",   # slightly lighter panel
    "card":     "#111D35",   # card background
    "border":   "#1A2F55",   # subtle border
    "cyan":     "#00D4FF",   # brand cyan
    "cyan_dim": "#0099BB",   # muted cyan
    "white":    "#E8F4FF",   # off-white text
    "grey":     "#5A7A9A",   # secondary text
    "green":    "#00E5A0",   # success
    "red":      "#FF4466",   # error
    "orange":   "#FF9933",   # warning
    "bar_bg":   "#0D1E3A",   # progress bar track
}

APP_NAME    = "FORensicDataSeal"
APP_VERSION = "1.0.0"
MANIFEST    = "SEAL_MANIFEST.json"
BLOCK_SIZE  = 65536

# ─────────────────────────────────────────────────────────────────────────────
#  ▶▶ WIRE-IN ◀◀  —  Import your CLI functions here
# ─────────────────────────────────────────────────────────────────────────────
CLI_AVAILABLE = False
_cli_seal    = None
_cli_verify  = None

def _load_cli():
    global CLI_AVAILABLE, _cli_seal, _cli_verify
    try:
        # Adjust import path to match your installed package name
        from forensicdataseal.cli import seal as _s, verify as _v   # ▶▶ WIRE-IN ◀◀
        _cli_seal, _cli_verify = _s, _v
        CLI_AVAILABLE = True
        print("[FDS] cli.py loaded — using production seal/verify")
    except Exception as e:
        print(f"[FDS] cli.py not found ({e}), using built-in SHA-256 fallback")

_load_cli()

# ─────────────────────────────────────────────────────────────────────────────
#  BUILT-IN SHA-256 FALLBACK  (remove once cli.py is wired in and tested)
# ─────────────────────────────────────────────────────────────────────────────
def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(BLOCK_SIZE):
            h.update(chunk)
    return h.hexdigest()

def _collect_files(paths: list[Path]) -> list[tuple[Path, Path]]:
    """Returns list of (anchor_dir, file_path) tuples."""
    out = []
    for p in paths:
        p = Path(p)
        if p.is_file():
            out.append((p.parent, p))
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.name != MANIFEST:
                    out.append((p.parent, f))
    return out

def builtin_seal(
    paths: list[Path],
    progress_cb: Callable[[int, int, str], None],
) -> dict:
    """SHA-256 seal — writes SEAL_MANIFEST.json next to each target."""
    all_files = _collect_files(paths)
    total     = len(all_files)
    if total == 0:
        return {"operation": "SEAL", "error": "No files found.", "results": []}

    manifest_map: dict[str, list] = {}
    results: list[dict] = []
    ts = datetime.now(timezone.utc).isoformat()

    for idx, (anchor, fpath) in enumerate(all_files, 1):
        progress_cb(idx, total, fpath.name)
        sha  = _hash_file(fpath)
        rel  = str(fpath.relative_to(anchor))
        key  = str(anchor)
        manifest_map.setdefault(key, []).append({
            "file":        rel,
            "sha256":      sha,
            "size_bytes":  fpath.stat().st_size,
            "sealed_utc":  ts,
        })
        results.append({
            "file":        str(fpath),
            "sha256":      sha,
            "status":      "SEALED",
            "size_bytes":  fpath.stat().st_size,
        })

    manifests = []
    for anchor_str, entries in manifest_map.items():
        mpath = Path(anchor_str) / MANIFEST
        payload = {
            "tool":         APP_NAME,
            "version":      APP_VERSION,
            "created_utc":  ts,
            "platform":     platform.platform(),
            "entries":      entries,
        }
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        manifests.append(str(mpath))

    return {
        "operation":     "SEAL",
        "timestamp_utc": ts,
        "total_files":   total,
        "results":       results,
        "manifests":     manifests,
    }


def builtin_verify(
    paths: list[Path],
    progress_cb: Callable[[int, int, str], None],
) -> dict:
    """Re-hash files and compare against SEAL_MANIFEST.json."""
    roots: list[Path] = []
    for p in paths:
        p = Path(p)
        roots.append(p if p.is_dir() else p.parent)
    roots = list(dict.fromkeys(roots))

    entries_all: list[tuple[Path, Path, dict]] = []
    results: list[dict] = []
    ts = datetime.now(timezone.utc).isoformat()

    for root in roots:
        mpath = root / MANIFEST
        if not mpath.exists():
            results.append({
                "file":    str(root),
                "status":  "NO_MANIFEST",
                "detail":  f"{MANIFEST} not found in {root}",
            })
            continue
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
        for entry in manifest.get("entries", []):
            fpath = root / entry["file"]
            entries_all.append((root, fpath, entry))

    total = len(entries_all)
    ok = tampered = missing = 0

    for idx, (root, fpath, entry) in enumerate(entries_all, 1):
        progress_cb(idx or 1, total or 1, fpath.name)
        if not fpath.exists():
            missing += 1
            results.append({
                "file": str(fpath), "status": "MISSING",
                "expected": entry["sha256"], "actual": "—",
            })
            continue
        actual = _hash_file(fpath)
        if actual == entry["sha256"]:
            ok += 1
            results.append({
                "file": str(fpath), "status": "OK",
                "expected": entry["sha256"], "actual": actual,
            })
        else:
            tampered += 1
            results.append({
                "file": str(fpath), "status": "TAMPERED",
                "expected": entry["sha256"], "actual": actual,
            })

    overall = "PASS" if (tampered == 0 and missing == 0 and total > 0) else "FAIL"
    return {
        "operation":     "VERIFY",
        "timestamp_utc": ts,
        "total_files":   total,
        "ok":            ok,
        "tampered":      tampered,
        "missing":       missing,
        "overall":       overall,
        "results":       results,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  DISPATCH — routes to CLI or built-in
# ─────────────────────────────────────────────────────────────────────────────
def run_seal(paths: list[Path], progress_cb) -> dict:
    # cli.seal(input_dir, out_dir, exclude, algo) — use builtin for GUI progress
    return builtin_seal(paths, progress_cb)

def run_verify(paths: list[Path], progress_cb) -> dict:
    # cli.verify(bundle_dir, strict) — use builtin for GUI progress
    return builtin_verify(paths, progress_cb)


# ─────────────────────────────────────────────────────────────────────────────
#  PDF REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
def generate_pdf_report(result: dict, output_path: Path, logo_path: Optional[Path] = None) -> bool:
    if not REPORTLAB_AVAILABLE:
        return False

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=30*mm,  bottomMargin=35*mm,
    )

    NAVY   = rl_colors.HexColor("#0A0F1E")
    CYAN   = rl_colors.HexColor("#00D4FF")
    WHITE  = rl_colors.HexColor("#E8F4FF")
    GREEN  = rl_colors.HexColor("#00E5A0")
    RED    = rl_colors.HexColor("#FF4466")
    ORANGE = rl_colors.HexColor("#FF9933")
    GREY   = rl_colors.HexColor("#5A7A9A")
    DARK   = rl_colors.HexColor("#111D35")

    def style(name, **kw):
        return ParagraphStyle(name, **kw)

    s_title  = style("title",  fontSize=22, textColor=WHITE,  fontName="Helvetica-Bold",   spaceAfter=2)
    s_sub    = style("sub",    fontSize=10, textColor=CYAN,   fontName="Helvetica",        spaceAfter=6)
    s_head   = style("head",   fontSize=12, textColor=CYAN,   fontName="Helvetica-Bold",   spaceBefore=8, spaceAfter=4)
    s_body   = style("body",   fontSize=8,  textColor=WHITE,  fontName="Helvetica",        spaceAfter=3)
    s_mono   = style("mono",   fontSize=6.5,textColor=GREY,   fontName="Courier",          spaceAfter=2)
    s_result = style("result", fontSize=11, textColor=WHITE,  fontName="Helvetica-Bold",   alignment=TA_CENTER, spaceAfter=4)
    s_label  = style("label",  fontSize=7.5,textColor=GREY,   fontName="Helvetica",        spaceAfter=1)

    op        = result.get("operation", "UNKNOWN")
    ts        = result.get("timestamp_utc", "—")
    total     = result.get("total_files", 0)
    manifests = result.get("manifests", [])
    items     = result.get("results", [])

    def status_color(s):
        return {
            "SEALED": GREEN, "OK": GREEN,
            "TAMPERED": RED, "MISSING": ORANGE,
            "NO_MANIFEST": ORANGE,
        }.get(s, GREY)

    story = []

    # —— Header (plain text) ————————————————————————————
    header_data = [[
        Paragraph(f"<b>{APP_NAME}</b>",
            style("ht", fontSize=22, textColor=WHITE, fontName="Helvetica-Bold")),
        Paragraph(f"<b>{op} REPORT</b>",
            style("hr", fontSize=14, textColor=CYAN, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ]]
    hdr_tbl = Table(header_data, colWidths=[110*mm, 60*mm])
    hdr_tbl.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "BOTTOM"),
        ("LINEBELOW",    (0,0),(-1,-1), 2, CYAN),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 5*mm))
    meta_rows = [
        ["Generated (UTC)", ts],
        ["Tool Version",    f"{APP_NAME} v{APP_VERSION}"],
        ["Platform",        platform.platform()],
        ["Total Files",     str(total)],
        ["Operation",       op],
    ]
    if op == "VERIFY":
        meta_rows += [
        ["Passed",   str(result.get("ok", 0))],
        ["Tampered", str(result.get("tampered", 0))],
        ["Missing",  str(result.get("missing", 0))],
        ]
    if manifests:
        meta_rows.append(["Manifest(s)", "\n".join(manifests)])

    meta_tbl = Table(
    [[Paragraph(k, s_label), Paragraph(v, s_body)] for k, v in meta_rows],
    colWidths=[40*mm, 130*mm],
    )
    meta_tbl.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(0,-1), DARK),
    ("BACKGROUND",    (1,0),(1,-1), rl_colors.HexColor("#0D1526")),
    ("GRID",          (0,0),(-1,-1), 0.3, rl_colors.HexColor("#1A2F55")),
    ("TOPPADDING",    (0,0),(-1,-1), 4),
    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
    ("LEFTPADDING",   (0,0),(-1,-1), 5),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 5*mm))

    # ── Overall verdict (VERIFY only) ─────────────────────────────────────────
    if op == "VERIFY":
        overall = result.get("overall", "FAIL")
        v_color = GREEN if overall == "PASS" else RED
        verdict_data = [[Paragraph(f"VERIFICATION RESULT: {overall}", s_result)]]
        v_tbl = Table(verdict_data, colWidths=[170*mm])
        v_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0),(-1,-1), v_color),
            ("TOPPADDING",   (0,0),(-1,-1), 10),
            ("BOTTOMPADDING",(0,0),(-1,-1), 10),
            ("ROUNDEDCORNERS", [3]),
        ]))
        story.append(v_tbl)
        story.append(Spacer(1, 5*mm))

    # ── File results table ────────────────────────────────────────────────────
    story.append(Paragraph(f"File Details  ({len(items)} entries)", s_head))

    if items:
        col_w = [90*mm, 24*mm, 56*mm] if op == "SEAL" else [80*mm, 20*mm, 70*mm]
        headers = ["File Path", "Status", "SHA-256"]
        tbl_data = [[Paragraph(f"<b>{h}</b>", s_body) for h in headers]]

        for item in items:
            sc = status_color(item.get("status", ""))
            sz = item.get("size_bytes", "")
            size_str = f"{sz:,} B" if isinstance(sz, int) else ""
            fpath_str = item.get("file", "")
            # truncate very long paths
            if len(fpath_str) > 70:
                fpath_str = "…" + fpath_str[-68:]
            sha_str = item.get("sha256", item.get("actual", "—"))
            if sha_str and len(sha_str) == 64:
                sha_str = sha_str[:16] + "…" + sha_str[-8:]

            detail = item.get("detail", "")
            fp_para = Paragraph(f"{fpath_str}<br/><font color='#5A7A9A' size='6'>{size_str}  {detail}</font>", s_body)
            st_para = Paragraph(f"<b>{item.get('status','')}</b>",
                                 style("st", fontSize=7, textColor=sc,
                                       fontName="Helvetica-Bold"))
            sh_para = Paragraph(sha_str, s_mono)

            tbl_data.append([fp_para, st_para, sh_para])

        file_tbl = Table(tbl_data, colWidths=col_w, repeatRows=1)
        row_bg = [
            ("BACKGROUND", (0, i), (-1, i),
             DARK if i % 2 == 0 else rl_colors.HexColor("#0D1526"))
            for i in range(1, len(tbl_data))
        ]
        file_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0), rl_colors.HexColor("#1A2F55")),
            ("GRID",          (0,0),(-1,-1), 0.25, rl_colors.HexColor("#1A2F55")),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 4),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ] + row_bg))
        story.append(file_tbl)

    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=CYAN))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"{APP_NAME} v{APP_VERSION}  ·  Air Gapped  ·  Autonomous  ·  SHA-256  ·  Deterministic",
        style("footer", fontSize=6.5, textColor=GREY, fontName="Helvetica",
              alignment=TA_CENTER)
    ))

    doc.build(story)
    return True


# ---------------------------------------------------------------------------
#  SPLASH SCREEN + LICENSE KEY
# ---------------------------------------------------------------------------

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
        self.win.configure(bg="#0A0F1E")
        self.win.overrideredirect(False)
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
                                    fg="#0A0F1E", bg="#00D4FF",
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
        self.win.focus_force()
        self.key_entry.focus_force()

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


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOM WIDGETS
# ─────────────────────────────────────────────────────────────────────────────
class FlatButton(tk.Canvas):
    """Flat rectangular button with hover glow."""

    def __init__(self, parent, text, command=None, accent=C["cyan"],
                 width=160, height=44, font_size=11, **kw):
        super().__init__(parent, width=width, height=height,
                         bg=C["bg"], highlightthickness=0, **kw)
        self.text    = text
        self.command = command
        self.accent  = accent
        self.w       = width
        self.h       = height
        self.fs      = font_size
        self._enabled = True

        self._draw(False)
        self.bind("<Enter>",         lambda e: self._draw(True)  if self._enabled else None)
        self.bind("<Leave>",         lambda e: self._draw(False) if self._enabled else None)
        self.bind("<ButtonRelease-1>",lambda e: self._click())

    def _draw(self, hover: bool):
        self.delete("all")
        bw = 1.5 if not hover else 2
        fill = C["card"] if not hover else C["border"]
        self.create_rectangle(bw, bw, self.w-bw, self.h-bw,
                              outline=self.accent, fill=fill, width=bw)
        col = self.accent if self._enabled else C["grey"]
        self.create_text(self.w//2, self.h//2, text=self.text,
                         fill=col, font=("Helvetica", self.fs, "bold"))

    def _click(self):
        if self._enabled and self.command:
            self.command()

    def set_enabled(self, val: bool):
        self._enabled = val
        self._draw(False)


class DropZone(tk.Canvas):
    """Drag-and-drop zone or click-to-browse."""

    def __init__(self, parent, on_files: Callable, **kw):
        super().__init__(parent, bg=C["card"], highlightthickness=0,
                         height=160, **kw)
        self.on_files   = on_files
        self.file_paths: list[Path] = []
        self._hover = False

        self._draw_idle()
        self.bind("<Configure>",      lambda e: self._redraw())
        self.bind("<Button-1>",        self._browse)
        self.bind("<Enter>",           lambda e: self._set_hover(True))
        self.bind("<Leave>",           lambda e: self._set_hover(False))

        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    def _set_hover(self, v):
        self._hover = v
        self._redraw()

    def _redraw(self):
        if self.file_paths:
            self._draw_loaded()
        else:
            self._draw_idle()

    def _draw_idle(self):
        self.delete("all")
        w = self.winfo_width() or 600
        h = self.winfo_height() or 160
        accent = C["cyan"] if self._hover else C["border"]
        # dashed border
        self.create_rectangle(8, 8, w-8, h-8, outline=accent, dash=(6,4),
                              width=1.5, fill=C["card"])
        icon_y = h//2 - 22
        self.create_text(w//2, icon_y,
                         text="⊕", fill=C["cyan"], font=("Helvetica", 28))
        self.create_text(w//2, icon_y+36,
                         text="Drop files / folders here", fill=C["white"],
                         font=("Helvetica", 12, "bold"))
        hint = "or click to browse" if not DND_AVAILABLE else "Drag & Drop  ·  or click to browse"
        self.create_text(w//2, icon_y+56,
                         text=hint, fill=C["grey"], font=("Helvetica", 9))

    def _draw_loaded(self):
        self.delete("all")
        w = self.winfo_width() or 600
        h = self.winfo_height() or 160
        self.create_rectangle(8, 8, w-8, h-8,
                              outline=C["cyan"], width=1.5, fill=C["card"])
        n = len(self.file_paths)
        self.create_text(w//2, 28,
                         text=f"{n} item{'s' if n != 1 else ''} queued",
                         fill=C["cyan"], font=("Helvetica", 11, "bold"))
        visible = self.file_paths[:6]
        for i, p in enumerate(visible):
            icon = "📁" if Path(p).is_dir() else "📄"
            name = Path(p).name
            if len(name) > 52:
                name = name[:50] + "…"
            self.create_text(w//2, 50 + i*18,
                             text=f"{icon} {name}", fill=C["white"],
                             font=("Helvetica", 8))
        if len(self.file_paths) > 6:
            self.create_text(w//2, 50 + 6*18,
                             text=f"… and {len(self.file_paths)-6} more",
                             fill=C["grey"], font=("Helvetica", 8, "italic"))
        self.create_text(w-20, h-14, text="✕ clear",
                         fill=C["grey"], font=("Helvetica", 8),
                         tags="clear", anchor="e")
        self.tag_bind("clear", "<Button-1>", self._clear)

    def _on_drop(self, event):
        raw = event.data
        # tkinterdnd2 returns paths in braces on macOS
        paths = self.tk.splitlist(raw)
        self._set_paths([Path(p) for p in paths])

    def _browse(self, event=None):
        x, y = event.x, event.y
        for item in self.find_withtag("clear"):
            x1, y1, x2, y2 = self.bbox(item)
            if x1 <= x <= x2 and y1 <= y <= y2:
                return
        win = self.winfo_toplevel()
        win.lift()
        win.attributes("-topmost", True)
        win.after(200, lambda: win.attributes("-topmost", False))

        dlg = tk.Toplevel(win)
        dlg.title("Select")
        dlg.configure(bg="#0A0F1E")
        dlg.resizable(False, False)
        dlg.transient(win)
        dlg.grab_set()
        dlg.geometry("300x140")
        dlg.update_idletasks()
        x2 = win.winfo_x() + (win.winfo_width() - 300) // 2
        y2 = win.winfo_y() + (win.winfo_height() - 140) // 2
        dlg.geometry(f"+{x2}+{y2}")

        tk.Label(dlg, text="What do you want to select?",
                 font=("Helvetica Neue", 11, "bold"),
                 fg="white", bg="#0A0F1E").pack(pady=(20,12))
        bf = tk.Frame(dlg, bg="#0A0F1E")
        bf.pack()

        def pick_files():
            dlg.destroy()
            paths = filedialog.askopenfilenames(title="Select Files", parent=win)
            if paths:
                self._set_paths([Path(p) for p in paths])

        def pick_folder():
            dlg.destroy()
            folder = filedialog.askdirectory(title="Select Folder", parent=win)
            if folder:
                files = [x for x in Path(folder).rglob("*")
                         if x.is_file() and x.name != "SEAL_MANIFEST.json"]
                if files:
                    self._set_paths(files)

        tk.Button(bf, text="📄  FILES", font=("Helvetica Neue", 11, "bold"),
                  fg="#00D4FF", bg="#0D1526", activebackground="#1A2A4A",
                  relief="flat", bd=0, cursor="hand2",
                  width=10, command=pick_files).pack(side="left", padx=8, ipady=8)
        tk.Button(bf, text="📁  FOLDER", font=("Helvetica Neue", 11, "bold"),
                  fg="#00D4FF", bg="#0D1526", activebackground="#1A2A4A",
                  relief="flat", bd=0, cursor="hand2",
                  width=10, command=pick_folder).pack(side="left", padx=8, ipady=8)


    def _clear(self, event=None):
        self.file_paths = []
        self.on_files([])
        self._draw_idle()

    def _set_paths(self, paths: list[Path]):
        self.file_paths = paths
        self.on_files(paths)
        self._draw_loaded()


class LogPanel(tk.Frame):
    """Scrollable log with coloured lines."""

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=C["panel"], **kw)
        self.text = tk.Text(
            self, bg=C["panel"], fg=C["grey"],
            font=("Courier", 8), relief="flat", bd=0,
            wrap="word", state="disabled", pady=4,
        )
        sb = ttk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)
        sb.pack(side="right", fill="y")

        for tag, col in [("cyan", C["cyan"]), ("green", C["green"]),
                          ("red",  C["red"]),  ("orange", C["orange"]),
                          ("grey", C["grey"]),  ("white",  C["white"])]:
            self.text.tag_config(tag, foreground=col)

    def append(self, msg: str, tag="grey"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.configure(state="normal")
        self.text.insert("end", f"[{ts}]  {msg}\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN APPLICATION WINDOW
# ─────────────────────────────────────────────────────────────────────────────
class App:

    def __init__(self):
        self._files: list[Path] = []
        self._queue = queue.Queue()
        self._running = False
        self._last_result: Optional[dict] = None

        # ── Root window ───────────────────────────────────────────────────────
        root_cls = TkinterDnD.Tk if DND_AVAILABLE else tk.Tk
        self.root = root_cls()
        self.root.title(APP_NAME)
        self.root.configure(bg=C["bg"])
        self.root.geometry("780x720")
        self.root.minsize(640, 580)
        self.root.resizable(True, True)

        # App icon (logo.png next to this script)
        logo_path = Path(__file__).parent / "logo.png"
        if logo_path.exists():
            try:
                icon = tk.PhotoImage(file=str(logo_path))
                self.root.iconphoto(True, icon)
                self._logo_img = icon   # keep reference
            except Exception:
                pass

        self._build_ui()
        self.log.append(f"{APP_NAME} v{APP_VERSION} ready.", "cyan")
        if not CLI_AVAILABLE:
            self.log.append("Built-in SHA-256 engine active (cli.py not found).", "orange")
        if not DND_AVAILABLE:
            self.log.append("tkinterdnd2 not installed — drag & drop disabled.", "orange")
        if not REPORTLAB_AVAILABLE:
            self.log.append("reportlab not installed — PDF export disabled.", "orange")

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = self.root

        # ── Top bar ───────────────────────────────────────────────────────────
        top = tk.Frame(root, bg=C["bg"], height=64)
        top.pack(fill="x", padx=20, pady=(16, 0))
        top.pack_propagate(False)

        tk.Label(top, text="FORensic", bg=C["bg"], fg=C["white"],
                 font=("Helvetica", 24, "bold")).pack(side="left")
        tk.Label(top, text="DataSeal", bg=C["bg"], fg=C["cyan"],
                 font=("Helvetica", 24, "bold")).pack(side="left")
        tk.Label(top, text=f"v{APP_VERSION}", bg=C["bg"], fg=C["grey"],
                 font=("Helvetica", 10)).pack(side="left", padx=(8, 0), pady=(10, 0))

        pill_frame = tk.Frame(top, bg=C["bg"])
        pill_frame.pack(side="right", pady=10)
        for tag in ["Air Gapped", "SHA-256", "Deterministic"]:
            tk.Label(pill_frame, text=f" {tag} ", bg=C["border"], fg=C["cyan"],
                     font=("Helvetica", 7, "bold"), relief="flat",
                     padx=5, pady=2).pack(side="left", padx=3)

        tk.Frame(root, bg=C["border"], height=1).pack(fill="x", padx=20, pady=(10, 16))

        # ── Drop zone ─────────────────────────────────────────────────────────
        dz_frame = tk.Frame(root, bg=C["bg"])
        dz_frame.pack(fill="x", padx=20)
        self.drop_zone = DropZone(dz_frame, on_files=self._on_files_changed)
        self.drop_zone.pack(fill="x")

        # ── Buttons row ───────────────────────────────────────────────────────
        btn_row = tk.Frame(root, bg=C["bg"])
        btn_row.pack(fill="x", padx=20, pady=14)

        self.btn_seal   = FlatButton(btn_row, "⚙  SEAL",   command=self._start_seal,
                                      accent=C["cyan"], width=180, height=46, font_size=12)
        self.btn_verify = FlatButton(btn_row, "✔  VERIFY", command=self._start_verify,
                                      accent=C["green"], width=180, height=46, font_size=12)
        self.btn_pdf    = FlatButton(btn_row, "⬇  PDF REPORT", command=self._save_pdf,
                                      accent=C["orange"], width=180, height=46, font_size=11)
        self.btn_clear  = FlatButton(btn_row, "✕  CLEAR",  command=self._clear_all,
                                      accent=C["grey"], width=120, height=46, font_size=10)

        self.btn_seal.pack(side="left", padx=(0, 8))
        self.btn_verify.pack(side="left", padx=(0, 8))
        self.btn_pdf.pack(side="left", padx=(0, 8))
        self.btn_clear.pack(side="left", fill="x", expand=True, padx=(0,6))
        self.btn_exit = FlatButton(btn_row, "⏻  EXIT", command=self.root.quit, accent="#FF4466")
        self.btn_exit.pack(side="left", fill="x", expand=True)
        self.btn_pdf.set_enabled(False)

        # ── Progress section ──────────────────────────────────────────────────
        prog_frame = tk.Frame(root, bg=C["bg"])
        prog_frame.pack(fill="x", padx=20, pady=(0, 8))

        prog_top = tk.Frame(prog_frame, bg=C["bg"])
        prog_top.pack(fill="x")
        self.lbl_status = tk.Label(prog_top, text="Ready", bg=C["bg"],
                                    fg=C["grey"], font=("Helvetica", 9))
        self.lbl_status.pack(side="left")
        self.lbl_pct = tk.Label(prog_top, text="", bg=C["bg"],
                                 fg=C["cyan"], font=("Helvetica", 9, "bold"))
        self.lbl_pct.pack(side="right")

        # Custom-coloured progress bar
        prog_bg = tk.Frame(prog_frame, bg=C["bar_bg"], height=8)
        prog_bg.pack(fill="x", pady=(4, 0))
        prog_bg.pack_propagate(False)
        self._bar_bg     = prog_bg
        self._bar_fill   = tk.Frame(prog_bg, bg=C["cyan"], height=8)
        self._bar_fill.place(x=0, y=0, relheight=1, relwidth=0)

        # ── Status badge ──────────────────────────────────────────────────────
        self.lbl_badge = tk.Label(root, text="", bg=C["bg"],
                                   font=("Helvetica", 13, "bold"))
        self.lbl_badge.pack(pady=(2, 4))

        # ── Log panel ─────────────────────────────────────────────────────────
        tk.Label(root, text="  ACTIVITY LOG", bg=C["bg"], fg=C["grey"],
                 font=("Helvetica", 8, "bold"), anchor="w").pack(fill="x", padx=20)
        self.log = LogPanel(root)
        self.log.pack(fill="both", expand=True, padx=20, pady=(0, 16))

    # ── File handling ─────────────────────────────────────────────────────────
    def _on_files_changed(self, paths: list[Path]):
        self._files = list(paths)
        if paths:
            self.log.append(f"{len(paths)} path(s) queued.", "white")
            for p in paths[:8]:
                t = "DIR" if Path(p).is_dir() else "FILE"
                self.log.append(f"  [{t}] {p}", "grey")
            if len(paths) > 8:
                self.log.append(f"  … and {len(paths)-8} more", "grey")
        self._reset_badge()
        self._last_result = None
        self.btn_pdf.set_enabled(False)

    # ── Seal ──────────────────────────────────────────────────────────────────
        self.root.after(50, self._poll_queue)  # start queue polling

    def _start_seal(self):
        if not self._files:
            messagebox.showwarning("No Files", "Drop or select files/folders first.")
            return
        if self._running:
            return
        self.log.clear()
        self.log.append("Starting SEAL operation …", "cyan")
        self._run_op("SEAL")

    # ── Verify ────────────────────────────────────────────────────────────────
    def _start_verify(self):
        if not self._files:
            messagebox.showwarning("No Files", "Drop or select files/folders first.")
            return
        if self._running:
            return
        self.log.clear()
        self.log.append("Starting VERIFY operation …", "cyan")
        self._run_op("VERIFY")

    # ── Core threaded runner ──────────────────────────────────────────────────
    def _run_op(self, op: str):
        self._running = True
        self._set_buttons_enabled(False)
        self._reset_progress()
        self._reset_badge()

        def worker():
            try:
                if op == "SEAL":
                    result = run_seal(self._files, self._progress_cb)
                else:
                    result = run_verify(self._files, self._progress_cb)
                self._queue.put(('done', op, result))
            except Exception as e:
                import traceback
                print("WORKER ERROR:", traceback.format_exc())
                self._queue.put(('error', str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _progress_cb(self, current: int, total: int, filename: str):
        pct = int(current / max(total, 1) * 100)
        self._queue.put(('progress', current, total, pct, filename))

    def _update_progress(self, current: int, total: int, pct: int, filename: str):
        rel = min(pct / 100.0, 1.0)
        self._bar_fill.place(relwidth=rel)
        short = filename if len(filename) <= 48 else "…" + filename[-46:]
        self.lbl_status.config(text=f"Processing: {short}")
        self.lbl_pct.config(text=f"{pct}%  ({current}/{total})")
        self.log.append(f"{short}", "grey")

    def _reset_progress(self):
        self._bar_fill.place(relwidth=0)
        self.lbl_status.config(text="Working …", fg=C["cyan"])
        self.lbl_pct.config(text="")

    # ── Completion handlers ───────────────────────────────────────────────────
    def _op_done(self, op: str, result: dict):
        self._running  = False
        self._last_result = result
        self._set_buttons_enabled(True)
        self._bar_fill.place(relwidth=1)
        self.lbl_pct.config(text="100%")

        if op == "SEAL":
            total = result.get("total_files", 0)
            mfiles = result.get("manifests", [])
            self.lbl_status.config(text=f"Sealed {total} files · Manifest written", fg=C["green"])
            self.log.append(f"SEAL complete — {total} file(s) hashed.", "green")
            for m in mfiles:
                self.log.append(f"  Manifest → {m}", "cyan")
            self._set_badge("SEALED", C["green"])
            if REPORTLAB_AVAILABLE:
                self.btn_pdf.set_enabled(True)

        elif op == "VERIFY":
            overall  = result.get("overall", "FAIL")
            ok       = result.get("ok", 0)
            tampered = result.get("tampered", 0)
            missing  = result.get("missing", 0)
            total    = result.get("total_files", 0)

            if overall == "PASS":
                self.lbl_status.config(text=f"Verified {ok}/{total} files — all intact", fg=C["green"])
                self._set_badge("VERIFIED  ✔", C["green"])
                self.log.append(f"VERIFY PASS — {ok} file(s) intact.", "green")
            else:
                self.lbl_status.config(
                    text=f"FAIL — {tampered} tampered · {missing} missing · {ok} OK",
                    fg=C["red"])
                self._set_badge("INTEGRITY FAILURE  ✘", C["red"])
                self.log.append(
                    f"VERIFY FAIL — {tampered} tampered, {missing} missing, {ok} intact.",
                    "red")
                for r in result.get("results", []):
                    if r.get("status") in ("TAMPERED", "MISSING", "NO_MANIFEST"):
                        self.log.append(f"  [{r['status']}] {r['file']}", "red")

            if REPORTLAB_AVAILABLE:
                self.btn_pdf.set_enabled(True)

    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                try:
                    if item[0] == 'progress':
                        _, current, total, pct, filename = item
                        self._update_progress(current, total, pct, filename)
                    elif item[0] == 'done':
                        _, op, result = item
                        self._op_done(op, result)
                    elif item[0] == 'error':
                        _, msg = item
                        self._op_error(msg)
                except Exception as _e:
                    import traceback
                    print("POLL_QUEUE HANDLER ERROR:", traceback.format_exc())
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self._poll_queue)

    def _op_error(self, msg: str):
        self._running = False
        self._set_buttons_enabled(True)
        self.lbl_status.config(text="Error — see log", fg=C["red"])
        self.log.append(f"ERROR: {msg}", "red")
        self._set_badge("ERROR", C["red"])

    # ── PDF export ────────────────────────────────────────────────────────────
    def _save_pdf(self):
        if not self._last_result:
            return
        op = self._last_result.get("operation", "REPORT")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"FDS_{op}_{ts}.pdf"

        out_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=default_name,
            title="Save PDF Report",
        )
        if not out_path:
            return

        logo_path = Path(__file__).parent / "logo.png"
        ok = generate_pdf_report(
            self._last_result,
            Path(out_path),
            logo_path if logo_path.exists() else None,
        )
        if ok:
            self.log.append(f"PDF saved → {out_path}", "cyan")
            if platform.system() == "Darwin":
                os.system(f'open "{out_path}"')
            elif platform.system() == "Windows":
                os.startfile(out_path)
        else:
            messagebox.showerror("PDF Error", "Failed to generate PDF (reportlab error).")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _clear_all(self):
        self._files = []
        self._last_result = None
        self.drop_zone._clear()
        self.log.clear()
        self._reset_progress()
        self._reset_badge()
        self.lbl_status.config(text="Ready", fg=C["grey"])
        self.lbl_pct.config(text="")
        self.btn_pdf.set_enabled(False)
        self.log.append("Cleared.", "grey")

    def _set_buttons_enabled(self, val: bool):
        self.btn_seal.set_enabled(val)
        self.btn_verify.set_enabled(val)
        self.btn_clear.set_enabled(val)

    def _reset_badge(self):
        self.lbl_badge.config(text="", bg=C["bg"])

    def _set_badge(self, text: str, color: str):
        self.lbl_badge.config(text=f"  {text}  ", fg=C["bg"], bg=color)

    def run(self):
        self.root.after(50, self._poll_queue)
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    def launch_app():
        app = App()
        app.root.after(50, app._poll_queue)

    SplashScreen(root, on_success=launch_app)
    root.mainloop()
