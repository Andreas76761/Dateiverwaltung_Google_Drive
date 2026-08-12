"""
Dateiumzug 2026 — Werkzeug
==========================

Ein Programm fuer den gesamten Ablauf aus dem Vorgehensplan:
Inventur, Sammeln, Dubletten, Bilder nach Jahr, Index und ein
Explorer mit zwei Ordnern.

Grundregel des Programms: es loescht nichts. Es kopiert, es verschiebt
in die Quarantaene oder in Jahresordner — mehr nicht. Jede Aktion, die
etwas auf der Platte veraendert, laeuft standardmaessig als Probelauf
und muss ausdruecklich bestaetigt werden.

Nur Standardbibliothek, damit die gebaute Datei klein und startklar ist.
"""

import csv
import hashlib
import os
import queue
import re
import shutil
import struct
import sys
import threading
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Dateiumzug 2026"
APP_VERSION = "1.0"


# ============================================================
#  Regelwerk aus dem Vorgehensplan
# ============================================================

CATS = {
    "dokument": "pdf doc docx odt rtf txt md xls xlsx ods csv ppt pptx odp",
    "bild": "jpg jpeg png heic heif webp tif tiff bmp gif psd psb xcf ai svg eps "
            "cr2 cr3 nef arw dng raf orf rw2",
    "video": "mp4 mov m4v avi mkv wmv mpg mpeg 3gp mts m2ts webm flv",
    "audio": "mp3 wav flac m4a aac ogg wma aiff",
    "archiv": "zip rar 7z tar gz bz2 iso pst ost mbox eml",
    "code": "js ts jsx tsx py java c cpp h hpp cs php rb go rs html css scss "
            "json xml yml yaml sql sh ps1",
}
EXT2CAT = {e: c for c, exts in CATS.items() for e in exts.split()}

# Phase 2 — Ausschlussliste
JUNK_DIRS = [
    "\\windows\\", "\\program files", "\\programdata\\", "\\appdata\\",
    "\\$recycle.bin\\", "\\system volume information\\", "\\recovery\\",
    "\\perflogs\\", "\\node_modules\\", "\\.git\\", "\\venv\\",
    "\\__pycache__\\", "\\build\\", "\\dist\\", "\\target\\", "\\packages\\",
    "\\temp\\", "\\tmp\\", "\\cache", "\\inetcache\\", "\\crashdumps\\",
    "\\virtual machines\\", "\\virtualbox vms\\", "\\hyper-v\\",
    "\\windowsimagebackup\\",
]
JUNK_EXTS = set(
    "dll exe sys msi cab lnk ini pyc obj class pdb tmp temp bak crdownload "
    "part log dmp vmdk vdi vhd vhdx img qcow2 wim esd regtrans-ms blf o".split()
)
JUNK_NAMES = {"thumbs.db", "desktop.ini"}
JUNK_PREFIXES = ("ntuser.dat", "~$")

VIDEO_EXTS = set(CATS["video"].split())

# Phase 5 — was in den Bilderordner wandert, was bleibt
IMAGE_MOVE_EXTS = set("jpg jpeg png heic heif webp tif tiff bmp gif".split())
EDIT_MOVE_EXTS = set("psd psb xcf ai svg eps".split())
RAW_STAY_EXTS = set("cr2 cr3 nef arw dng raf orf rw2".split())

DEFAULT_MAX_MB = 120.0
MIN_PLAUSIBLE_YEAR = 1995


# ============================================================
#  Windows-Pfade ohne Laengengrenze
# ============================================================

def long_path(path):
    """Umgeht die 260-Zeichen-Grenze von Windows."""
    if os.name != "nt":
        return path
    p = os.path.abspath(path)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def short_path(path):
    """Macht long_path fuer die Anzeige wieder lesbar."""
    if path.startswith("\\\\?\\UNC\\"):
        return "\\\\" + path[8:]
    if path.startswith("\\\\?\\"):
        return path[4:]
    return path


# ============================================================
#  Dateieintrag
# ============================================================

class Entry:
    __slots__ = ("name", "rel", "abspath", "size", "mtime", "ext", "cat", "digest")

    def __init__(self, name, rel, abspath, size, mtime):
        self.name = name
        self.rel = rel
        self.abspath = abspath
        self.size = size
        self.mtime = mtime
        dot = name.rfind(".")
        self.ext = name[dot + 1:].lower() if dot > 0 else ""
        self.cat = EXT2CAT.get(self.ext, "sonstiges")
        self.digest = None

    @property
    def reldir(self):
        i = self.rel.replace("\\", "/").rfind("/")
        return self.rel[:i] if i > 0 else ""

    @property
    def size_mb(self):
        return self.size / 1048576.0

    @property
    def date(self):
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d")


def is_junk(entry):
    low = ("\\" + entry.rel.replace("/", "\\")).lower()
    for d in JUNK_DIRS:
        if d in low:
            return True
    if entry.ext in JUNK_EXTS:
        return True
    n = entry.name.lower()
    if n in JUNK_NAMES or n.startswith(JUNK_PREFIXES):
        return True
    return False


# ============================================================
#  Abbruchsignal und Fortschritt
# ============================================================

class Job:
    """Traegt Fortschritt aus dem Arbeitsfaden zurueck in die Oberflaeche."""

    def __init__(self, out_queue):
        self.q = out_queue
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()

    @property
    def stopped(self):
        return self.cancelled.is_set()

    def say(self, text):
        self.q.put(("status", text))

    def progress(self, done, total):
        self.q.put(("progress", (done, total)))

    def done(self, kind, payload):
        self.q.put(("done", (kind, payload)))

    def failed(self, text):
        self.q.put(("failed", text))


# ============================================================
#  Einlesen
# ============================================================

def scan_folder(root, job, note_every=2000):
    """Liest einen Ordner samt Unterordnern. Gibt eine Liste von Entry zurueck."""
    root = os.path.abspath(root)
    entries = []
    walk_root = long_path(root)
    for dirpath, dirnames, filenames in os.walk(walk_root, onerror=lambda e: None):
        if job.stopped:
            break
        dirnames.sort()
        for fn in filenames:
            if job.stopped:
                break
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(short_path(full), root)
            entries.append(Entry(fn, rel, full, st.st_size, st.st_mtime))
            if len(entries) % note_every == 0:
                job.say("Gelesen: {:,} Dateien".format(len(entries)).replace(",", "."))
    return entries


# ============================================================
#  Pruefsummen und Dubletten
# ============================================================

def sha256_of(path, job, chunk=1024 * 1024):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                if job.stopped:
                    return None
                block = f.read(chunk)
                if not block:
                    break
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


def find_duplicates(entries, job):
    """
    Gruppiert inhaltsgleiche Dateien. Erst nach Groesse vorsortieren,
    dann nur bei Gleichstand die Pruefsumme rechnen — das spart bei
    grossen Bestaenden den groessten Teil der Rechenzeit.
    """
    by_size = {}
    for e in entries:
        if e.size > 0:
            by_size.setdefault(e.size, []).append(e)

    candidates = [grp for grp in by_size.values() if len(grp) > 1]
    total = sum(len(g) for g in candidates)
    if not total:
        return []

    job.say("{:,} Dateien haben eine gleich grosse Zweitdatei — Pruefsummen werden gerechnet."
            .format(total).replace(",", "."))

    done = 0
    groups = []
    for grp in candidates:
        by_hash = {}
        for e in grp:
            if job.stopped:
                return groups
            e.digest = sha256_of(e.abspath, job)
            done += 1
            if done % 25 == 0:
                job.progress(done, total)
            if e.digest:
                by_hash.setdefault(e.digest, []).append(e)
        for digest, same in by_hash.items():
            if len(same) > 1:
                groups.append(same)
    job.progress(total, total)
    return groups


def rank_key(entry, priority_roots):
    """
    Bestimmt, welche Kopie das Original ist. Reihenfolge der Regeln:
    Vorrang des Quellordners, dann aelteres Datum, dann kuerzerer Pfad,
    dann laengerer, also sprechenderer Dateiname.
    """
    rel_low = entry.rel.lower()
    rank = len(priority_roots)
    for i, root in enumerate(priority_roots):
        if rel_low.startswith(root.lower()):
            rank = i
            break
    return (rank, entry.mtime, entry.rel.count(os.sep), -len(entry.name))


# ============================================================
#  Aufnahmejahr
# ============================================================

_NAME_DATE = re.compile(r"(19[89]\d|20[0-4]\d)[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])")


def year_from_name(name):
    m = _NAME_DATE.search(name)
    if m:
        y = int(m.group(1))
        if MIN_PLAUSIBLE_YEAR <= y <= datetime.now().year:
            return y
    return None


def _parse_tiff_datetime(buf):
    """Liest DateTimeOriginal aus einem TIFF-Kopf (auch dem in JPEG-Dateien)."""
    try:
        if buf[:2] == b"II":
            endian = "<"
        elif buf[:2] == b"MM":
            endian = ">"
        else:
            return None
        magic, first = struct.unpack(endian + "HI", buf[2:8])
        if magic != 42:
            return None

        def read_ifd(offset):
            tags = {}
            if offset + 2 > len(buf):
                return tags
            count = struct.unpack(endian + "H", buf[offset:offset + 2])[0]
            for i in range(count):
                p = offset + 2 + i * 12
                if p + 12 > len(buf):
                    break
                tag, typ, num = struct.unpack(endian + "HHI", buf[p:p + 8])
                val = buf[p + 8:p + 12]
                if typ == 2 and num > 4:
                    off = struct.unpack(endian + "I", val)[0]
                    tags[tag] = buf[off:off + num - 1]
                elif typ == 4:
                    tags[tag] = struct.unpack(endian + "I", val)[0]
                else:
                    tags[tag] = val
            return tags

        ifd0 = read_ifd(first)
        raw = None
        exif_off = ifd0.get(0x8769)
        if isinstance(exif_off, int):
            sub = read_ifd(exif_off)
            raw = sub.get(0x9003) or sub.get(0x9004)
        if raw is None:
            raw = ifd0.get(0x0132)
        if isinstance(raw, bytes) and len(raw) >= 4:
            text = raw.decode("ascii", "ignore")
            y = int(text[:4])
            if MIN_PLAUSIBLE_YEAR <= y <= datetime.now().year:
                return y
    except Exception:
        return None
    return None


def year_from_exif(path):
    """Aufnahmejahr aus JPEG oder TIFF. Andere Formate liefern None."""
    try:
        with open(path, "rb") as f:
            head = f.read(2)
            if head in (b"II", b"MM"):
                f.seek(0)
                return _parse_tiff_datetime(f.read(65536))
            if head != b"\xff\xd8":
                return None
            while True:
                b = f.read(2)
                if len(b) < 2 or b[0] != 0xFF:
                    return None
                marker = b[1]
                if marker == 0xDA or marker == 0xD9:
                    return None
                ln_raw = f.read(2)
                if len(ln_raw) < 2:
                    return None
                ln = struct.unpack(">H", ln_raw)[0]
                if ln < 2:
                    return None
                data = f.read(ln - 2)
                if marker == 0xE1 and data[:6] == b"Exif\x00\x00":
                    return _parse_tiff_datetime(data[6:])
    except OSError:
        return None
    return None


def year_of(entry, use_exif=True):
    """Aufnahmejahr, sonst Jahr aus dem Dateinamen, sonst Dateidatum."""
    if use_exif and entry.ext in ("jpg", "jpeg", "tif", "tiff"):
        y = year_from_exif(entry.abspath)
        if y:
            return y, "exif"
    y = year_from_name(entry.name)
    if y:
        return y, "name"
    y = datetime.fromtimestamp(entry.mtime).year
    if MIN_PLAUSIBLE_YEAR <= y <= datetime.now().year:
        return y, "datei"
    return None, "unklar"


# ============================================================
#  Kopieren und Verschieben — nie loeschen
# ============================================================

def unique_target(folder, name):
    """Haengt eine Nummer an, statt eine vorhandene Datei zu ueberschreiben."""
    target = os.path.join(folder, name)
    if not os.path.exists(long_path(target)):
        return target
    stem, ext = os.path.splitext(name)
    n = 2
    while True:
        cand = os.path.join(folder, "{}_{}{}".format(stem, n, ext))
        if not os.path.exists(long_path(cand)):
            return cand
        n += 1


def transfer(items, job, dry_run=True, move=False):
    """
    items: Liste von (quell_pfad, ziel_pfad)
    Kopiert oder verschiebt. Loescht nie. Gibt einen Bericht zurueck.
    """
    report = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0, "errors": []}
    total = len(items)
    for i, (src, dst) in enumerate(items, 1):
        if job.stopped:
            break
        if i % 20 == 0 or i == total:
            job.progress(i, total)
            job.say("{} {} von {}".format("Pruefe" if dry_run else
                                          ("Verschiebe" if move else "Kopiere"), i, total))
        try:
            if os.path.exists(long_path(dst)):
                report["skip"] += 1
                continue
            if dry_run:
                report["ok"] += 1
                report["bytes"] += os.path.getsize(long_path(src))
                continue
            os.makedirs(long_path(os.path.dirname(dst)), exist_ok=True)
            if move:
                shutil.move(long_path(src), long_path(dst))
            else:
                shutil.copy2(long_path(src), long_path(dst))
            report["ok"] += 1
            report["bytes"] += os.path.getsize(long_path(dst))
        except Exception as exc:
            report["fail"] += 1
            if len(report["errors"]) < 200:
                report["errors"].append("{} -> {}: {}".format(short_path(src), short_path(dst), exc))
    return report


# ============================================================
#  Hilfsdarstellung
# ============================================================

def fmt_size(b):
    if b >= 1099511627776:
        return "{:.2f} TB".format(b / 1099511627776)
    if b >= 1073741824:
        return "{:.2f} GB".format(b / 1073741824)
    if b >= 1048576:
        return "{:.1f} MB".format(b / 1048576)
    if b >= 1024:
        return "{:.0f} KB".format(b / 1024)
    return "{} B".format(b)


def fmt_count(n):
    return "{:,}".format(n).replace(",", ".")


# ============================================================
#  Oberflaeche — gemeinsames Geruest
# ============================================================

class Section(ttk.Frame):
    """Ein Register mit Kopfzeile, Arbeitsflaeche, Fortschritt und Protokoll."""

    def __init__(self, master, app, title, lead):
        super().__init__(master, padding=(14, 12))
        self.app = app
        self.job = None
        self.q = queue.Queue()

        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=title, style="H1.TLabel").pack(anchor="w")
        ttk.Label(head, text=lead, style="Lead.TLabel", wraplength=980,
                  justify="left").pack(anchor="w", pady=(2, 10))

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)

        foot = ttk.Frame(self)
        foot.pack(fill="x", pady=(10, 0))
        self.bar = ttk.Progressbar(foot, mode="determinate")
        self.bar.pack(fill="x")
        self.status = ttk.Label(foot, text="Bereit.", style="Status.TLabel")
        self.status.pack(anchor="w", pady=(4, 0))

    # -- Arbeitsfaden ------------------------------------------------

    def run(self, target, on_done):
        if self.job and not self.job.stopped:
            messagebox.showinfo(APP_NAME, "Es läuft noch ein Vorgang. Bitte abwarten oder abbrechen.")
            return
        self.job = Job(self.q)
        self._on_done = on_done
        self.bar.configure(value=0, maximum=100)

        def wrapper():
            try:
                target(self.job)
            except Exception:
                self.job.failed(traceback.format_exc(limit=3))

        threading.Thread(target=wrapper, daemon=True).start()
        self.after(100, self._pump)

    def stop(self):
        if self.job:
            self.job.cancel()
            self.say("Abbruch angefordert …")

    def _pump(self):
        alive = True
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    self.say(payload)
                elif kind == "progress":
                    done, total = payload
                    self.bar.configure(maximum=max(total, 1), value=done)
                elif kind == "failed":
                    self.say("Fehler — der Vorgang wurde abgebrochen.")
                    messagebox.showerror(APP_NAME, payload)
                    alive = False
                elif kind == "done":
                    self._on_done(*payload)
                    alive = False
        except queue.Empty:
            pass
        if alive and self.job and not self.job.stopped:
            self.after(100, self._pump)
        elif alive and self.job and self.job.stopped:
            self.after(100, self._pump)

    def say(self, text):
        self.status.configure(text=text)


def pick_folder(title):
    p = filedialog.askdirectory(title=title, mustexist=True)
    return p or None


def make_tree(parent, columns, widths, height=14):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=height,
                        selectmode="extended")
    for col, w in zip(columns, widths):
        tree.heading(col, text=col)
        tree.column(col, width=w, anchor="e" if col in ("Grösse", "MB", "Anzahl") else "w")
    ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    xsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    ysb.grid(row=0, column=1, sticky="ns")
    xsb.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree


MAX_ROWS = 3000


# ============================================================
#  Register 1 — Inventur
# ============================================================

class InventurTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Phase 1 · Inventur",
            "Einen Quellordner einlesen und sehen, was darin steckt: Anzahl, Volumen, "
            "Aufteilung nach Art, und wie viel davon unter der Grenze bleibt. "
            "Es wird nur gelesen.")

        top = ttk.Frame(self.body)
        top.pack(fill="x")
        ttk.Label(top, text="Quelle").pack(side="left")
        self.var_path = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(top, text="Kürzel").pack(side="left")
        self.var_id = tk.StringVar(value="PC1")
        ttk.Entry(top, textvariable=self.var_id, width=8).pack(side="left", padx=(6, 8))
        ttk.Button(top, text="Ordner …", command=self.choose).pack(side="left")
        ttk.Button(top, text="Einlesen", style="Go.TButton", command=self.start).pack(side="left", padx=6)
        ttk.Button(top, text="Abbrechen", command=self.stop).pack(side="left")

        frame, self.tree = make_tree(
            self.body, ("Art", "Anzahl", "Grösse", "davon ≤ Grenze", "über Grenze"),
            (180, 110, 130, 150, 130), height=10)
        frame.pack(fill="both", expand=True, pady=10)

        bottom = ttk.Frame(self.body)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Inventur als CSV sichern", command=self.export).pack(side="left")
        ttk.Button(bottom, text="Register der Übergrossen sichern",
                   command=self.export_register).pack(side="left", padx=6)
        self.summary = ttk.Label(bottom, text="", style="Sum.TLabel")
        self.summary.pack(side="right")

    def choose(self):
        p = pick_folder("Quellordner wählen")
        if p:
            self.var_path.set(p)

    def start(self):
        root = self.var_path.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning(APP_NAME, "Bitte zuerst einen vorhandenen Ordner wählen.")
            return
        self.say("Lese …")
        self.run(lambda job: job.done("inv", scan_folder(root, job)), self.finish)

    def finish(self, _kind, entries):
        self.app.set_source(self.var_id.get().strip() or "PC?", self.var_path.get().strip(), entries)
        limit = self.app.limit_bytes()
        stats = {}
        for e in entries:
            junk = is_junk(e)
            key = "— davon ausgeschlossen" if junk else e.cat
            s = stats.setdefault(key, [0, 0, 0, 0])
            s[0] += 1
            s[1] += e.size
            if e.size <= limit:
                s[2] += 1
            else:
                s[3] += 1

        for row in self.tree.get_children():
            self.tree.delete(row)
        order = ["dokument", "bild", "video", "audio", "archiv", "code", "sonstiges",
                 "— davon ausgeschlossen"]
        for key in order:
            if key in stats:
                n, b, under, over = stats[key]
                self.tree.insert("", "end", values=(key, fmt_count(n), fmt_size(b),
                                                    fmt_count(under), fmt_count(over)))
        keep = [e for e in entries if not is_junk(e) and e.size <= limit]
        kb = sum(e.size for e in keep)
        self.summary.configure(
            text="{} Dateien gelesen · {} · davon fahren {} mit ({})".format(
                fmt_count(len(entries)), fmt_size(sum(e.size for e in entries)),
                fmt_count(len(keep)), fmt_size(kb)))
        self.say("Fertig. Die Zahlen stehen oben, die Auswahl ist für die nächsten Register gemerkt.")

    def export(self):
        entries = self.app.current_entries()
        if not entries:
            messagebox.showinfo(APP_NAME, "Erst einen Ordner einlesen.")
            return
        path = filedialog.asksaveasfilename(
            title="Inventur sichern", defaultextension=".csv",
            initialfile="inventur_{}.csv".format(self.app.source_id or "quelle"),
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        limit = self.app.limit_bytes()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["quelle_id", "original_pfad", "dateiname", "endung",
                        "groesse_mb", "geaendert_am", "kategorie", "faehrt_mit"])
            for e in entries:
                mit = "nein" if (is_junk(e) or e.size > limit) else "ja"
                w.writerow([self.app.source_id, e.reldir, e.name, e.ext,
                            "{:.2f}".format(e.size_mb).replace(".", ","),
                            e.date, e.cat, mit])
        self.say("Gesichert: " + path)

    def export_register(self):
        entries = self.app.current_entries()
        if not entries:
            messagebox.showinfo(APP_NAME, "Erst einen Ordner einlesen.")
            return
        path = filedialog.asksaveasfilename(
            title="Register sichern", defaultextension=".csv",
            initialfile="register_nicht_uebernommen.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        limit = self.app.limit_bytes()
        skip_video = self.app.var_skip_video.get()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["quelle_id", "original_pfad", "dateiname", "groesse_mb",
                        "geaendert_am", "grund"])
            for e in entries:
                grund = None
                if is_junk(e):
                    grund = "ausschlussliste"
                elif skip_video and e.ext in VIDEO_EXTS:
                    grund = "video"
                elif e.size > limit:
                    grund = "zu gross"
                if grund:
                    w.writerow([self.app.source_id, e.reldir, e.name,
                                "{:.2f}".format(e.size_mb).replace(".", ","), e.date, grund])
        self.say("Gesichert: " + path)


# ============================================================
#  Register 2 — Sammeln
# ============================================================

class SammelnTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Phase 3 · Sammeln",
            "Aus einem Quellordner alles auf die Sammelplatte kopieren, was den Regeln "
            "entspricht. Erst als Probelauf, dann echt. Die Quelle bleibt unangetastet.")

        g = ttk.Frame(self.body)
        g.pack(fill="x")
        self.var_src = tk.StringVar()
        self.var_dst = tk.StringVar()
        for i, (lab, var, title) in enumerate([
                ("Von", self.var_src, "Quellordner"),
                ("Nach", self.var_dst, "Zielordner auf der Sammelplatte")]):
            ttk.Label(g, text=lab, width=6).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(g, textvariable=var).grid(row=i, column=1, sticky="ew", padx=8, pady=3)
            ttk.Button(g, text="…", width=4,
                       command=lambda v=var, t=title: self._pick(v, t)).grid(row=i, column=2, pady=3)
        g.columnconfigure(1, weight=1)

        opts = ttk.Frame(self.body)
        opts.pack(fill="x", pady=(10, 0))
        ttk.Button(opts, text="Probelauf", command=lambda: self.start(True)).pack(side="left")
        ttk.Button(opts, text="Wirklich kopieren", style="Go.TButton",
                   command=lambda: self.start(False)).pack(side="left", padx=6)
        ttk.Button(opts, text="Abbrechen", command=self.stop).pack(side="left")

        frame, self.tree = make_tree(self.body, ("Datei", "Ordner", "MB", "Geändert"),
                                     (260, 380, 90, 110), height=13)
        frame.pack(fill="both", expand=True, pady=10)
        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")

    def _pick(self, var, title):
        p = pick_folder(title)
        if p:
            var.set(p)

    def _plan(self, job):
        src = self.var_src.get().strip()
        dst = self.var_dst.get().strip()
        entries = scan_folder(src, job)
        limit = self.app.limit_bytes()
        skip_video = self.app.var_skip_video.get()
        items, chosen = [], []
        for e in entries:
            if is_junk(e):
                continue
            if skip_video and e.ext in VIDEO_EXTS:
                continue
            if e.size > limit:
                continue
            chosen.append(e)
            items.append((e.abspath, os.path.join(dst, e.rel)))
        return items, chosen

    def start(self, dry):
        src, dst = self.var_src.get().strip(), self.var_dst.get().strip()
        if not os.path.isdir(src):
            messagebox.showwarning(APP_NAME, "Der Quellordner fehlt.")
            return
        if not dst:
            messagebox.showwarning(APP_NAME, "Bitte einen Zielordner wählen.")
            return
        if os.path.abspath(dst).lower().startswith(os.path.abspath(src).lower()):
            messagebox.showwarning(APP_NAME, "Das Ziel darf nicht innerhalb der Quelle liegen.")
            return
        if not dry and not messagebox.askyesno(
                APP_NAME,
                "Jetzt wirklich kopieren?\n\nVon:  {}\nNach: {}\n\n"
                "Es wird nur kopiert. In der Quelle ändert sich nichts."
                .format(src, dst)):
            return

        def work(job):
            job.say("Lese Quelle …")
            items, chosen = self._plan(job)
            if job.stopped:
                job.done("copy", (None, chosen, True))
                return
            job.say("{} Dateien vorgemerkt.".format(fmt_count(len(items))))
            rep = transfer(items, job, dry_run=dry, move=False)
            job.done("copy", (rep, chosen, dry))

        self.run(work, self.finish)

    def finish(self, _kind, payload):
        rep, chosen, dry = payload
        for row in self.tree.get_children():
            self.tree.delete(row)
        for e in chosen[:MAX_ROWS]:
            self.tree.insert("", "end", values=(e.name, e.reldir,
                                                "{:.2f}".format(e.size_mb).replace(".", ","), e.date))
        rest = len(chosen) - MAX_ROWS
        if rest > 0:
            self.tree.insert("", "end", values=("… und {} weitere".format(fmt_count(rest)), "", "", ""))

        if rep is None:
            self.say("Abgebrochen.")
            return
        total = sum(e.size for e in chosen)
        self.summary.configure(text="{} Dateien · {}".format(fmt_count(len(chosen)), fmt_size(total)))
        wort = "Probelauf" if dry else "Kopiert"
        self.say("{}: {} bereit, {} übersprungen (schon vorhanden), {} fehlgeschlagen. "
                 "Nichts gelöscht.".format(wort, fmt_count(rep["ok"]), fmt_count(rep["skip"]),
                                           fmt_count(rep["fail"])))
        if rep["errors"]:
            messagebox.showwarning(APP_NAME, "Einige Dateien gingen nicht:\n\n"
                                   + "\n".join(rep["errors"][:12]))


# ============================================================
#  Register 3 — Dubletten
# ============================================================

class DublettenTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Phase 4 · Dubletten",
            "Inhaltsgleiche Dateien finden — über die Prüfsumme, nicht über den Namen. "
            "Die beste Kopie bleibt liegen, die übrigen wandern in die Quarantäne. "
            "Gelöscht wird nichts.")

        g = ttk.Frame(self.body)
        g.pack(fill="x")
        self.var_root = tk.StringVar()
        self.var_quar = tk.StringVar()
        for i, (lab, var, title) in enumerate([
                ("Prüfen", self.var_root, "Sammelplatte oder Ordner"),
                ("Quarantäne", self.var_quar, "Quarantäne-Ordner")]):
            ttk.Label(g, text=lab, width=11).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(g, textvariable=var).grid(row=i, column=1, sticky="ew", padx=8, pady=3)
            ttk.Button(g, text="…", width=4,
                       command=lambda v=var, t=title: self._pick(v, t)).grid(row=i, column=2, pady=3)
        ttk.Label(g, text="Vorrang").grid(row=2, column=0, sticky="w", pady=3)
        self.var_prio = tk.StringVar()
        ttk.Entry(g, textvariable=self.var_prio).grid(row=2, column=1, sticky="ew", padx=8, pady=3)
        ttk.Label(g, text="Unterordner in Vorrangfolge, mit Komma getrennt — z. B.  PC1, PC2, EXT1",
                  style="Hint.TLabel").grid(row=3, column=1, sticky="w", padx=8)
        g.columnconfigure(1, weight=1)

        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Suchen", style="Go.TButton", command=self.start).pack(side="left")
        ttk.Button(row, text="Abbrechen", command=self.stop).pack(side="left", padx=6)
        ttk.Button(row, text="Liste sichern", command=self.export).pack(side="left")
        ttk.Button(row, text="Duplikate in Quarantäne verschieben",
                   command=self.quarantine).pack(side="left", padx=6)

        frame, self.tree = make_tree(self.body, ("Rolle", "Datei", "Ordner", "MB", "Gruppe"),
                                     (90, 260, 360, 80, 90), height=13)
        frame.pack(fill="both", expand=True, pady=10)
        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")
        self.groups = []

    def _pick(self, var, title):
        p = pick_folder(title)
        if p:
            var.set(p)

    def start(self):
        root = self.var_root.get().strip()
        if not os.path.isdir(root):
            messagebox.showwarning(APP_NAME, "Bitte einen vorhandenen Ordner wählen.")
            return
        prio = [p.strip() for p in self.var_prio.get().split(",") if p.strip()]

        def work(job):
            job.say("Lese Ordner …")
            entries = [e for e in scan_folder(root, job) if not is_junk(e)]
            job.say("{} Dateien. Suche gleich grosse …".format(fmt_count(len(entries))))
            groups = find_duplicates(entries, job)
            for grp in groups:
                grp.sort(key=lambda e: rank_key(e, prio))
            job.done("dup", groups)

        self.run(work, self.finish)

    def finish(self, _kind, groups):
        self.groups = groups
        for row in self.tree.get_children():
            self.tree.delete(row)
        shown, waste, dupes = 0, 0, 0
        for gi, grp in enumerate(groups, 1):
            for j, e in enumerate(grp):
                if j > 0:
                    dupes += 1
                    waste += e.size
                if shown < MAX_ROWS:
                    self.tree.insert("", "end", values=(
                        "Original" if j == 0 else "Duplikat", e.name, e.reldir,
                        "{:.2f}".format(e.size_mb).replace(".", ","), "G-{:04d}".format(gi)))
                    shown += 1
        if shown >= MAX_ROWS:
            self.tree.insert("", "end", values=("…", "weitere Zeilen ausgeblendet", "", "", ""))
        self.summary.configure(text="{} Gruppen · {} Duplikate · {} doppelt belegt".format(
            fmt_count(len(groups)), fmt_count(dupes), fmt_size(waste)))
        self.say("Fertig. Prüfe die Rollen stichprobenartig, bevor du verschiebst.")

    def export(self):
        if not self.groups:
            messagebox.showinfo(APP_NAME, "Erst suchen.")
            return
        path = filedialog.asksaveasfilename(
            title="Dublettenliste sichern", defaultextension=".csv",
            initialfile="dubletten.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["dup_gruppe", "dup_rolle", "original_pfad", "dateiname",
                        "groesse_mb", "geaendert_am", "pruefsumme"])
            for gi, grp in enumerate(self.groups, 1):
                for j, e in enumerate(grp):
                    w.writerow(["G-{:04d}".format(gi), "original" if j == 0 else "duplikat",
                                e.reldir, e.name, "{:.2f}".format(e.size_mb).replace(".", ","),
                                e.date, e.digest or ""])
        self.say("Gesichert: " + path)

    def quarantine(self):
        if not self.groups:
            messagebox.showinfo(APP_NAME, "Erst suchen.")
            return
        quar = self.var_quar.get().strip()
        if not quar:
            messagebox.showwarning(APP_NAME, "Bitte einen Quarantäne-Ordner wählen.")
            return
        root = os.path.abspath(self.var_root.get().strip())
        items = []
        for grp in self.groups:
            for e in grp[1:]:
                items.append((e.abspath, os.path.join(quar, e.rel)))
        if not items:
            messagebox.showinfo(APP_NAME, "Es gibt nichts zu verschieben.")
            return
        if not messagebox.askyesno(
                APP_NAME,
                "{} Duplikate in die Quarantäne verschieben?\n\nNach: {}\n\n"
                "Die Dateien bleiben vollständig erhalten und lassen sich jederzeit "
                "zurückholen. Gelöscht wird nichts.".format(fmt_count(len(items)), quar)):
            return
        if os.path.abspath(quar).lower().startswith(root.lower()):
            if not messagebox.askyesno(
                    APP_NAME,
                    "Die Quarantäne liegt innerhalb des geprüften Ordners. "
                    "Das funktioniert, aber ein erneuter Suchlauf findet die Dateien wieder.\n\n"
                    "Trotzdem fortfahren?"):
                return
        self.run(lambda job: job.done("quar", transfer(items, job, dry_run=False, move=True)),
                 self.after_move)

    def after_move(self, _kind, rep):
        self.say("Verschoben: {} · übersprungen: {} · fehlgeschlagen: {}. Nichts gelöscht."
                 .format(fmt_count(rep["ok"]), fmt_count(rep["skip"]), fmt_count(rep["fail"])))
        if rep["errors"]:
            messagebox.showwarning(APP_NAME, "\n".join(rep["errors"][:12]))


# ============================================================
#  Register 4 — Bilder nach Jahr
# ============================================================

class BilderTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Phase 5 · Bilder nach Jahr",
            "Alle Bilder aus allen Quellen in einen Ordner, sortiert nach Aufnahmejahr. "
            "Das Jahr kommt aus den EXIF-Daten, sonst aus dem Dateinamen, sonst aus dem "
            "Dateidatum. RAW und Schnittprojekte bleiben, wo sie sind.")

        g = ttk.Frame(self.body)
        g.pack(fill="x")
        self.var_src = tk.StringVar()
        self.var_dst = tk.StringVar()
        for i, (lab, var, title) in enumerate([
                ("Von", self.var_src, "Sammelplatte"),
                ("Nach", self.var_dst, "Zielordner für die Bilder")]):
            ttk.Label(g, text=lab, width=6).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(g, textvariable=var).grid(row=i, column=1, sticky="ew", padx=8, pady=3)
            ttk.Button(g, text="…", width=4,
                       command=lambda v=var, t=title: self._pick(v, t)).grid(row=i, column=2, pady=3)
        g.columnconfigure(1, weight=1)

        opts = ttk.Frame(self.body)
        opts.pack(fill="x", pady=(10, 0))
        self.var_edit = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Bearbeitungsdateien mitnehmen (PSD, XCF, AI, SVG, EPS)",
                        variable=self.var_edit).pack(side="left")
        self.var_copy = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="kopieren statt verschieben", variable=self.var_copy).pack(side="left", padx=14)

        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Probelauf", command=lambda: self.start(True)).pack(side="left")
        ttk.Button(row, text="Ausführen", style="Go.TButton",
                   command=lambda: self.start(False)).pack(side="left", padx=6)
        ttk.Button(row, text="Abbrechen", command=self.stop).pack(side="left")

        frame, self.tree = make_tree(self.body, ("Jahr", "Quelle", "Datei", "Ordner", "MB"),
                                     (80, 90, 260, 340, 80), height=12)
        frame.pack(fill="both", expand=True, pady=10)
        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")

    def _pick(self, var, title):
        p = pick_folder(title)
        if p:
            var.set(p)

    def start(self, dry):
        src, dst = self.var_src.get().strip(), self.var_dst.get().strip()
        if not os.path.isdir(src) or not dst:
            messagebox.showwarning(APP_NAME, "Bitte Quelle und Ziel wählen.")
            return
        move = not self.var_copy.get()
        if not dry and not messagebox.askyesno(
                APP_NAME,
                "Bilder jetzt {}?\n\nNach: {}\n\nGelöscht wird nichts."
                .format("verschieben" if move else "kopieren", dst)):
            return
        take_edit = self.var_edit.get()

        def work(job):
            job.say("Lese …")
            entries = scan_folder(src, job)
            wanted = []
            for e in entries:
                if is_junk(e):
                    continue
                if e.ext in RAW_STAY_EXTS:
                    continue
                if e.ext in IMAGE_MOVE_EXTS or (take_edit and e.ext in EDIT_MOVE_EXTS):
                    wanted.append(e)
            job.say("{} Bilder gefunden. Ermittle Aufnahmejahre …".format(fmt_count(len(wanted))))
            plan, rows = [], []
            for i, e in enumerate(wanted, 1):
                if job.stopped:
                    break
                if i % 200 == 0:
                    job.progress(i, len(wanted))
                    job.say("Jahr {} von {}".format(i, len(wanted)))
                year, source = year_of(e)
                folder = os.path.join(dst, str(year) if year else "_Jahr_unklar")
                target = unique_target(folder, e.name) if not dry \
                    else os.path.join(folder, e.name)
                plan.append((e.abspath, target))
                rows.append((str(year) if year else "unklar", source, e))
            rep = transfer(plan, job, dry_run=dry, move=move)
            job.done("img", (rep, rows, dry))

        self.run(work, self.finish)

    def finish(self, _kind, payload):
        rep, rows, dry = payload
        for r in self.tree.get_children():
            self.tree.delete(r)
        per_year = {}
        for year, source, e in rows:
            per_year[year] = per_year.get(year, 0) + 1
        for i, (year, source, e) in enumerate(rows[:MAX_ROWS]):
            self.tree.insert("", "end", values=(year, source, e.name, e.reldir,
                                                "{:.2f}".format(e.size_mb).replace(".", ",")))
        if len(rows) > MAX_ROWS:
            self.tree.insert("", "end", values=("…", "", "weitere ausgeblendet", "", ""))
        unklar = per_year.get("unklar", 0)
        self.summary.configure(text="{} Bilder · {} Jahresordner · {} ohne verwertbares Datum"
                               .format(fmt_count(len(rows)), fmt_count(len(per_year)), fmt_count(unklar)))
        self.say("{}: {} bereit, {} übersprungen, {} fehlgeschlagen."
                 .format("Probelauf" if dry else "Fertig", fmt_count(rep["ok"]),
                         fmt_count(rep["skip"]), fmt_count(rep["fail"])))


# ============================================================
#  Register 5 — Explorer
# ============================================================

class Pane(ttk.Frame):
    def __init__(self, master, label, on_change):
        super().__init__(master)
        self.entries = []
        self.view = []
        self.root = ""
        self.on_change = on_change

        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text=label, style="PaneId.TLabel").pack(side="left")
        self.path_lbl = ttk.Label(head, text="kein Ordner", style="Hint.TLabel")
        self.path_lbl.pack(side="left", padx=8)
        ttk.Button(head, text="Ordner …", command=self.load).pack(side="right")

        frame, self.tree = make_tree(self, ("Datei", "Ordner", "MB", "Geändert"),
                                     (200, 260, 80, 95), height=15)
        frame.pack(fill="both", expand=True, pady=6)
        self.stats = ttk.Label(self, text="—", style="Hint.TLabel")
        self.stats.pack(anchor="w")

    def load(self):
        p = pick_folder("Ordner wählen")
        if not p:
            return
        job = Job(queue.Queue())
        self.root = p
        self.entries = scan_folder(p, job)
        self.path_lbl.configure(text="{}  ·  {} Dateien".format(
            os.path.basename(p) or p, fmt_count(len(self.entries))))
        self.on_change()

    def show(self, rows):
        self.view = rows
        for r in self.tree.get_children():
            self.tree.delete(r)
        for e in rows[:MAX_ROWS]:
            self.tree.insert("", "end", values=(e.name, e.reldir,
                                                "{:.2f}".format(e.size_mb).replace(".", ","), e.date))
        if len(rows) > MAX_ROWS:
            self.tree.insert("", "end", values=("… {} weitere".format(
                fmt_count(len(rows) - MAX_ROWS)), "", "", ""))
        self.stats.configure(text="{} von {} Dateien · {}".format(
            fmt_count(len(rows)), fmt_count(len(self.entries)),
            fmt_size(sum(e.size for e in rows))))

    def selected(self):
        idx = [self.tree.index(i) for i in self.tree.selection()]
        return [self.view[i] for i in idx if i < len(self.view)]


class ExplorerTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Explorer · zwei Ordner nebeneinander",
            "Filtern nach Name, Grösse, Datum und Art. Vergleichen, was auf welcher Seite "
            "fehlt. Auswahl von einer Seite zur anderen kopieren. Ohne Löschfunktion.")

        f = ttk.LabelFrame(self.body, text="Filter", padding=8)
        f.pack(fill="x")
        self.var_name = tk.StringVar()
        self.var_min = tk.StringVar()
        self.var_max = tk.StringVar()
        self.var_from = tk.StringVar()
        self.var_to = tk.StringVar()
        self.var_ext = tk.StringVar()
        self.var_cat = tk.StringVar(value="alle")
        self.var_cmp = tk.StringVar(value="alle zeigen")
        self.var_junk = tk.BooleanVar(value=True)

        fields = [
            ("Name enthält", self.var_name, 22),
            ("MB von", self.var_min, 7), ("bis", self.var_max, 7),
            ("Datum von", self.var_from, 11), ("bis", self.var_to, 11),
            ("Endungen", self.var_ext, 16),
        ]
        col = 0
        for lab, var, width in fields:
            ttk.Label(f, text=lab).grid(row=0, column=col, sticky="e", padx=(8, 3))
            e = ttk.Entry(f, textvariable=var, width=width)
            e.grid(row=0, column=col + 1, sticky="w")
            var.trace_add("write", lambda *a: self.refresh())
            col += 2
        ttk.Label(f, text="Art").grid(row=1, column=0, sticky="e", padx=(8, 3), pady=(6, 0))
        cb = ttk.Combobox(f, textvariable=self.var_cat, width=14, state="readonly",
                          values=["alle"] + list(CATS.keys()) + ["sonstiges"])
        cb.grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(f, text="Vergleich").grid(row=1, column=2, sticky="e", padx=(8, 3), pady=(6, 0))
        cb2 = ttk.Combobox(f, textvariable=self.var_cmp, width=20, state="readonly",
                           values=["alle zeigen", "nur hier vorhanden", "auf beiden Seiten",
                                   "Grösse weicht ab"])
        cb2.grid(row=1, column=3, columnspan=2, sticky="w", pady=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        cb2.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Checkbutton(f, text="Ausschlussliste anwenden", variable=self.var_junk,
                        command=self.refresh).grid(row=1, column=5, columnspan=2,
                                                   sticky="w", padx=8, pady=(6, 0))
        ttk.Button(f, text="Voreinstellung Phase 2", command=self.preset).grid(
            row=1, column=7, sticky="w", padx=8, pady=(6, 0))

        panes = ttk.Frame(self.body)
        panes.pack(fill="both", expand=True, pady=10)
        self.a = Pane(panes, "Seite A", self.refresh)
        self.b = Pane(panes, "Seite B", self.refresh)
        self.a.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.b.pack(side="left", fill="both", expand=True, padx=(5, 0))

        act = ttk.Frame(self.body)
        act.pack(fill="x")
        ttk.Button(act, text="Auswahl A → B kopieren", style="Go.TButton",
                   command=lambda: self.copy("a", "b")).pack(side="left")
        ttk.Button(act, text="Auswahl B → A kopieren", style="Go.TButton",
                   command=lambda: self.copy("b", "a")).pack(side="left", padx=6)
        ttk.Button(act, text="Auswahl als CSV sichern", command=self.export).pack(side="left")
        ttk.Label(act, text="Mehrfachauswahl mit Strg oder Umschalt. Gelöscht wird nie.",
                  style="Hint.TLabel").pack(side="right")

    def preset(self):
        self.var_name.set("")
        self.var_min.set("")
        self.var_max.set(str(int(self.app.limit_mb())))
        self.var_from.set("")
        self.var_to.set("")
        self.var_ext.set("")
        self.var_cat.set("alle")
        self.var_junk.set(True)
        self.refresh()

    @staticmethod
    def _num(text):
        try:
            return float(text.replace(",", ".")) * 1048576
        except ValueError:
            return None

    @staticmethod
    def _day(text):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(text.strip(), fmt).timestamp()
            except ValueError:
                continue
        return None

    def refresh(self, *_):
        name = self.var_name.get().strip().lower()
        lo, hi = self._num(self.var_min.get()), self._num(self.var_max.get())
        d1, d2 = self._day(self.var_from.get()), self._day(self.var_to.get())
        if d2:
            d2 += 86399
        exts = {x.strip().lstrip("*.").lower() for x in
                re.split(r"[\s,;]+", self.var_ext.get()) if x.strip()}
        cat = self.var_cat.get()
        cmp_mode = self.var_cmp.get()
        junk = self.var_junk.get()

        def matches(e):
            if junk and is_junk(e):
                return False
            if name:
                if "*" in name:
                    rx = "^" + ".*".join(re.escape(p) for p in name.split("*")) + "$"
                    if not re.match(rx, e.name.lower()):
                        return False
                elif name not in e.name.lower():
                    return False
            if lo is not None and e.size < lo:
                return False
            if hi is not None and e.size > hi:
                return False
            if d1 is not None and e.mtime < d1:
                return False
            if d2 is not None and e.mtime > d2:
                return False
            if exts and e.ext not in exts:
                return False
            if cat != "alle" and e.cat != cat:
                return False
            return True

        idx_a = {e.rel.lower(): e for e in self.a.entries}
        idx_b = {e.rel.lower(): e for e in self.b.entries}

        def compare(e, other):
            if cmp_mode == "alle zeigen":
                return True
            m = other.get(e.rel.lower())
            if cmp_mode == "nur hier vorhanden":
                return m is None
            if cmp_mode == "auf beiden Seiten":
                return m is not None
            if cmp_mode == "Grösse weicht ab":
                return m is not None and m.size != e.size
            return True

        self.a.show([e for e in self.a.entries if matches(e) and compare(e, idx_b)])
        self.b.show([e for e in self.b.entries if matches(e) and compare(e, idx_a)])
        self.say("Bereit.")

    def copy(self, src, dst):
        s = getattr(self, src)
        t = getattr(self, dst)
        picked = s.selected()
        if not picked:
            messagebox.showinfo(APP_NAME, "Erst Zeilen in der Liste markieren.")
            return
        if not t.root:
            messagebox.showinfo(APP_NAME, "Die Zielseite hat noch keinen Ordner.")
            return
        if not messagebox.askyesno(
                APP_NAME, "{} Dateien kopieren?\n\nNach: {}\n\nEs wird nur kopiert."
                .format(fmt_count(len(picked)), t.root)):
            return
        items = [(e.abspath, os.path.join(t.root, e.rel)) for e in picked]
        self.run(lambda job: job.done("cp", transfer(items, job, dry_run=False, move=False)),
                 lambda k, rep: self.say(
                     "Kopiert: {} · übersprungen: {} · fehlgeschlagen: {}. Nichts gelöscht."
                     .format(fmt_count(rep["ok"]), fmt_count(rep["skip"]), fmt_count(rep["fail"]))))

    def export(self):
        rows = [("A", e) for e in self.a.selected()] + [("B", e) for e in self.b.selected()]
        if not rows:
            rows = [("A", e) for e in self.a.view] + [("B", e) for e in self.b.view]
        if not rows:
            messagebox.showinfo(APP_NAME, "Nichts zu sichern.")
            return
        path = filedialog.asksaveasfilename(
            title="Auswahl sichern", defaultextension=".csv",
            initialfile="auswahl.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["seite", "ordner", "dateiname", "endung", "groesse_mb",
                        "geaendert_am", "kategorie"])
            for side, e in rows:
                w.writerow([side, e.reldir, e.name, e.ext,
                            "{:.2f}".format(e.size_mb).replace(".", ","), e.date, e.cat])
        self.say("Gesichert: " + path)


# ============================================================
#  Hauptfenster
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{} — Werkzeug".format(APP_NAME))
        self.geometry("1180x780")
        self.minsize(980, 640)

        self.source_id = ""
        self.source_path = ""
        self._entries = []

        self._styles()

        bar = ttk.Frame(self, padding=(14, 10, 14, 0))
        bar.pack(fill="x")
        ttk.Label(bar, text=APP_NAME, style="Brand.TLabel").pack(side="left")
        ttk.Label(bar, text="Andreas_2026_Dateiverwaltung   ·   Version " + APP_VERSION,
                  style="Hint.TLabel").pack(side="left", padx=12)

        ttk.Label(bar, text="Grenze MB").pack(side="left", padx=(24, 4))
        self.var_limit = tk.StringVar(value=str(int(DEFAULT_MAX_MB)))
        ttk.Entry(bar, textvariable=self.var_limit, width=6).pack(side="left")
        self.var_skip_video = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Video nicht übernehmen",
                        variable=self.var_skip_video).pack(side="left", padx=12)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_inv = InventurTab(nb, self)
        self.tab_sam = SammelnTab(nb, self)
        self.tab_dup = DublettenTab(nb, self)
        self.tab_img = BilderTab(nb, self)
        self.tab_exp = ExplorerTab(nb, self)
        nb.add(self.tab_inv, text="  1 · Inventur  ")
        nb.add(self.tab_sam, text="  3 · Sammeln  ")
        nb.add(self.tab_dup, text="  4 · Dubletten  ")
        nb.add(self.tab_img, text="  5 · Bilder  ")
        nb.add(self.tab_exp, text="  Explorer  ")

        foot = ttk.Frame(self, padding=(14, 0, 14, 10))
        foot.pack(fill="x")
        ttk.Label(foot, style="Hint.TLabel",
                  text="Dieses Programm löscht nichts. Es kopiert, oder es verschiebt in die "
                       "Quarantäne beziehungsweise in Jahresordner — und fragt vorher.").pack(anchor="w")

    def _styles(self):
        st = ttk.Style(self)
        try:
            st.theme_use("vista" if os.name == "nt" else "clam")
        except tk.TclError:
            pass
        ink, accent, muted = "#16211f", "#0d5c55", "#5b6a67"
        st.configure("Brand.TLabel", font=("Segoe UI Semibold", 13), foreground=accent)
        st.configure("H1.TLabel", font=("Segoe UI Semibold", 13), foreground=ink)
        st.configure("Lead.TLabel", font=("Segoe UI", 9), foreground=muted)
        st.configure("Hint.TLabel", font=("Segoe UI", 8), foreground=muted)
        st.configure("Status.TLabel", font=("Consolas", 9), foreground=accent)
        st.configure("Sum.TLabel", font=("Segoe UI Semibold", 9), foreground=ink)
        st.configure("PaneId.TLabel", font=("Segoe UI Semibold", 9), foreground=accent)
        st.configure("Go.TButton", font=("Segoe UI Semibold", 9))
        st.configure("Treeview", rowheight=20, font=("Consolas", 9))
        st.configure("Treeview.Heading", font=("Segoe UI", 8))

    # -- gemeinsamer Zustand ----------------------------------------

    def limit_mb(self):
        try:
            return float(self.var_limit.get().replace(",", "."))
        except ValueError:
            return DEFAULT_MAX_MB

    def limit_bytes(self):
        return self.limit_mb() * 1048576

    def set_source(self, sid, path, entries):
        self.source_id, self.source_path, self._entries = sid, path, entries

    def current_entries(self):
        return self._entries


def main():
    try:
        app = App()
        app.mainloop()
    except Exception:
        log = os.path.join(os.path.expanduser("~"), "dateiumzug-fehler.txt")
        try:
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except OSError:
            pass
        try:
            messagebox.showerror(APP_NAME, "Unerwarteter Fehler.\nProtokoll: " + log)
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)


if __name__ == "__main__":
    main()
