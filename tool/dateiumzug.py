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
import json
import os
import queue
import re
import shutil
import struct
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Dateiumzug 2026"
APP_VERSION = "1.1"

COPY_BUFFER = 1024 * 1024        # 1 MB je Leseschritt
DEFAULT_WORKERS = 4              # gleichzeitige Kopiervorgaenge
CHUNK = 512                      # Haeppchen, damit Abbrechen zuegig greift


# ============================================================
#  Einstellungen — bleiben zwischen zwei Starts erhalten
# ============================================================

def settings_file():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Dateiumzug2026", "einstellungen.json")


def load_settings():
    try:
        with open(settings_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        path = settings_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


SETTINGS = load_settings()


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

DEFAULT_JUNK_DIRS = list(JUNK_DIRS)
DEFAULT_JUNK_EXTS = set(JUNK_EXTS)
DEFAULT_JUNK_NAMES = set(JUNK_NAMES)

# Register 2 darf diese drei Listen ersetzen; gespeicherte Fassungen gewinnen.
if isinstance(SETTINGS.get("junk_dirs"), list):
    JUNK_DIRS = list(SETTINGS["junk_dirs"])
if isinstance(SETTINGS.get("junk_exts"), list):
    JUNK_EXTS = set(SETTINGS["junk_exts"])
if isinstance(SETTINGS.get("junk_names"), list):
    JUNK_NAMES = set(SETTINGS["junk_names"])
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

    def stats(self, done, total, bytes_done, bytes_total, rate):
        self.q.put(("stats", (done, total, bytes_done, bytes_total, rate)))

    def done(self, kind, payload):
        self.q.put(("done", (kind, payload)))

    def failed(self, text):
        self.q.put(("failed", text))


# ============================================================
#  Einlesen
# ============================================================

def scan_folder(root, job, note_every=5000):
    """
    Liest einen Ordner samt Unterordnern.

    Verwendet os.scandir: Windows liefert Groesse und Datum schon beim
    Auflisten mit, eine gesonderte Abfrage je Datei entfaellt. Das ist
    rund fuenfmal schneller als der Weg ueber os.walk mit os.stat.
    """
    root = os.path.abspath(root)
    prefix = len(long_path(root).rstrip(os.sep)) + 1
    entries = []
    stack = [long_path(root)]
    while stack:
        if job.stopped:
            break
        current = stack.pop()
        try:
            it = os.scandir(current)
        except OSError:
            continue
        with it:
            for e in it:
                if job.stopped:
                    break
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                entries.append(Entry(e.name, e.path[prefix:], e.path,
                                     st.st_size, st.st_mtime))
                if len(entries) % note_every == 0:
                    job.say("Gelesen: {} Dateien".format(fmt_count(len(entries))))
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

def unique_target(folder, name, claimed=None):
    """
    Haengt eine Nummer an, statt eine vorhandene Datei zu ueberschreiben.

    claimed sammelt die Ziele, die im laufenden Vorhaben schon vergeben
    sind. Ohne diese Menge bekommen zwei gleichnamige Dateien aus
    verschiedenen Quellen dasselbe Ziel: beim Planen existiert noch keine
    von beiden, und die zweite faellt beim Ausfuehren still hinten runter.
    """
    def frei(path):
        if claimed is not None and path.lower() in claimed:
            return False
        return not os.path.exists(long_path(path))

    def nimm(path):
        if claimed is not None:
            claimed.add(path.lower())
        return path

    target = os.path.join(folder, name)
    if frei(target):
        return nimm(target)
    stem, ext = os.path.splitext(name)
    n = 2
    while True:
        cand = os.path.join(folder, "{}_{}{}".format(stem, n, ext))
        if frei(cand):
            return nimm(cand)
        n += 1


def _copy_exclusive(src, dst, size):
    """
    Legt das Ziel im Modus 'x' an: es entsteht nur, wenn es noch nicht
    existiert. Damit fallen Nachfragen und Anlegen in einem Schritt
    zusammen statt in zwei.
    """
    try:
        fdst = open(long_path(dst), "xb", buffering=0)
    except FileExistsError:
        return ("skip", 0)
    written = 0
    try:
        with open(long_path(src), "rb", buffering=0) as fsrc:
            while True:
                block = fsrc.read(COPY_BUFFER)
                if not block:
                    break
                fdst.write(block)
                written += len(block)
    finally:
        fdst.close()
    try:
        shutil.copystat(long_path(src), long_path(dst))
    except OSError:
        pass
    return ("ok", written or size)


def transfer(items, job, dry_run=True, move=False, workers=DEFAULT_WORKERS):
    """
    items: Liste von (quelle, ziel) oder (quelle, ziel, groesse)

    Kopiert oder verschiebt. Loescht nie. Gibt einen Bericht zurueck.

    Die Zielordner entstehen einmal vorab statt bei jeder Datei erneut,
    und die Dateien laufen ueber mehrere Faeden gleichzeitig — beim
    Kopieren wartet ein Faden ohnehin die meiste Zeit auf die Platte.
    """
    report = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0, "errors": []}
    total = len(items)
    if not total:
        return report
    total_bytes = sum((it[2] if len(it) > 2 else 0) for it in items)

    if not dry_run:
        job.say("Lege Zielordner an …")
        for d in sorted({os.path.dirname(i[1]) for i in items}):
            try:
                os.makedirs(long_path(d), exist_ok=True)
            except OSError:
                pass

    started = time.monotonic()
    seen = {"n": 0, "bytes": 0}

    def one(item):
        if job.stopped:
            return None
        src, dst = item[0], item[1]
        size = item[2] if len(item) > 2 else 0
        try:
            if dry_run:
                return ("skip", 0) if os.path.exists(long_path(dst)) else ("ok", size)
            if move:
                if os.path.exists(long_path(dst)):
                    return ("skip", 0)
                try:
                    os.replace(long_path(src), long_path(dst))
                except OSError:
                    shutil.move(long_path(src), long_path(dst))
                return ("ok", size)
            return _copy_exclusive(src, dst, size)
        except FileExistsError:
            return ("skip", 0)
        except Exception as exc:
            return ("fail", 0, "{} -> {}: {}".format(short_path(src), short_path(dst), exc))

    def account(res):
        if res is None:
            return
        kind = res[0]
        report[kind] += 1
        if kind == "ok":
            report["bytes"] += res[1]
            seen["bytes"] += res[1]
        elif kind == "fail" and len(res) > 2 and len(report["errors"]) < 200:
            report["errors"].append(res[2])
        seen["n"] += 1
        if seen["n"] % 25 == 0 or seen["n"] == total:
            elapsed = max(time.monotonic() - started, 0.001)
            job.stats(seen["n"], total, seen["bytes"], total_bytes,
                      seen["bytes"] / elapsed)

    workers = max(1, int(workers or 1))
    if workers == 1 or dry_run:
        for item in items:
            if job.stopped:
                break
            account(one(item))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for start in range(0, total, CHUNK):
                if job.stopped:
                    break
                for res in pool.map(one, items[start:start + CHUNK]):
                    account(res)
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


def fmt_time(seconds):
    seconds = int(max(seconds, 0))
    if seconds < 90:
        return "{} s".format(seconds)
    if seconds < 5400:
        return "{} min".format(round(seconds / 60))
    return "{:.1f} h".format(seconds / 3600).replace(".", ",")


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
        line = ttk.Frame(foot)
        line.pack(fill="x", pady=(4, 0))
        self.status = ttk.Label(line, text="Bereit.", style="Status.TLabel")
        self.status.pack(side="left")
        self.detail = ttk.Label(line, text="", style="Detail.TLabel")
        self.detail.pack(side="right")

        self._go = []          # Knoepfe, die einen Vorgang starten
        self._stop = []        # Abbrechen-Knoepfe

    # -- Knoepfe waehrend eines Vorgangs sperren ---------------------

    def wire(self, go=(), stop=()):
        self._go = list(go)
        self._stop = list(stop)
        self._set_running(False)

    def _set_running(self, running):
        for b in self._go:
            try:
                b.configure(state="disabled" if running else "normal")
            except tk.TclError:
                pass
        for b in self._stop:
            try:
                b.configure(state="normal" if running else "disabled")
            except tk.TclError:
                pass

    # -- Arbeitsfaden ------------------------------------------------

    def run(self, target, on_done):
        if self.job and not self.job.stopped:
            messagebox.showinfo(APP_NAME, "Es läuft noch ein Vorgang. Bitte abwarten oder abbrechen.")
            return
        self.job = Job(self.q)
        self._on_done = on_done
        self.bar.configure(value=0, maximum=100)
        self.detail.configure(text="")
        self._set_running(True)

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
                    self.detail.configure(text="{} von {}".format(
                        fmt_count(done), fmt_count(total)))
                elif kind == "stats":
                    done, total, bd, bt, rate = payload
                    self.bar.configure(maximum=max(total, 1), value=done)
                    self.detail.configure(text=self._detail(done, total, bd, bt, rate))
                elif kind == "failed":
                    self.say("Fehler — der Vorgang wurde abgebrochen.")
                    self._set_running(False)
                    messagebox.showerror(APP_NAME, payload)
                    alive = False
                elif kind == "done":
                    self._set_running(False)
                    self.bar.configure(value=self.bar["maximum"])
                    self._on_done(*payload)
                    alive = False
        except queue.Empty:
            pass
        if alive and self.job and not self.job.stopped:
            self.after(100, self._pump)
        elif alive and self.job and self.job.stopped:
            self.after(100, self._pump)

    @staticmethod
    def _detail(done, total, bytes_done, bytes_total, rate):
        parts = ["{} / {}".format(fmt_count(done), fmt_count(total))]
        if bytes_total:
            parts.append("{} / {}".format(fmt_size(bytes_done), fmt_size(bytes_total)))
        if rate > 0:
            parts.append("{}/s".format(fmt_size(int(rate))))
            rest = bytes_total - bytes_done
            if rest > 0 and bytes_total:
                parts.append("noch {}".format(fmt_time(rest / rate)))
        return "   ·   ".join(parts)

    def say(self, text):
        self.status.configure(text=text)


def pick_folder(title, start=None):
    kwargs = {"title": title, "mustexist": True}
    if start and os.path.isdir(start):
        kwargs["initialdir"] = start
    p = filedialog.askdirectory(**kwargs)
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
        self.var_path = tk.StringVar(value=app.recall("inventur"))
        ttk.Entry(top, textvariable=self.var_path).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(top, text="Kürzel").pack(side="left")
        self.var_id = tk.StringVar(value="PC1")
        ttk.Entry(top, textvariable=self.var_id, width=8).pack(side="left", padx=(6, 8))
        b_pick = ttk.Button(top, text="Ordner …", command=self.choose)
        b_pick.pack(side="left")
        b_go = ttk.Button(top, text="Einlesen", style="Go.TButton", command=self.start)
        b_go.pack(side="left", padx=6)
        b_stop = ttk.Button(top, text="Abbrechen", command=self.stop)
        b_stop.pack(side="left")
        self.wire(go=(b_pick, b_go), stop=(b_stop,))

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
        p = pick_folder("Quellordner wählen", self.app.recall("inventur"))
        if p:
            self.var_path.set(p)
            self.app.remember("inventur", p)

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
#  Register 2 — Regeln
# ============================================================

class RegelnTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Phase 2 · Regeln",
            "Was mitfährt und was nicht. Einmal festgelegt, gilt es für alle übrigen "
            "Register. Die Regeln bleiben gespeichert und stehen beim nächsten Start "
            "wieder da.")

        top = ttk.LabelFrame(self.body, text="Grenzen", padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Dateien höchstens").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=app.var_limit, width=7).grid(row=0, column=1, padx=6)
        ttk.Label(top, text="MB").grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(top, text="Video nicht übernehmen",
                        variable=app.var_skip_video).grid(row=0, column=3, padx=(24, 0))
        ttk.Label(top, text="Gleichzeitige Kopiervorgänge").grid(row=0, column=4, padx=(24, 6))
        ttk.Spinbox(top, from_=1, to=16, width=4,
                    textvariable=app.var_workers).grid(row=0, column=5)
        ttk.Label(top, style="Hint.TLabel",
                  text="4 ist ein guter Wert. Bei einer einzelnen älteren USB-Platte "
                       "kann 1 oder 2 schneller sein — mehr Köpfe, mehr Suchen.").grid(
            row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))

        lists = ttk.Frame(self.body)
        lists.pack(fill="both", expand=True, pady=10)
        self.boxes = {}
        specs = [
            ("dirs", "Ordner überspringen", "Ein Eintrag je Zeile. Trifft zu, wenn der "
                                            "Pfad ihn enthält."),
            ("exts", "Endungen überspringen", "Ohne Punkt, ein Eintrag je Zeile."),
            ("names", "Dateinamen überspringen", "Vollständiger Name, ein Eintrag je Zeile."),
        ]
        for i, (key, title, hint) in enumerate(specs):
            frame = ttk.LabelFrame(lists, text=title, padding=6)
            frame.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            # Der Hinweis wird zuerst gepackt: sonst nimmt er sich den Platz
            # neben der Liste statt darunter.
            ttk.Label(frame, text=hint, style="Hint.TLabel", wraplength=250).pack(
                side="bottom", anchor="w", fill="x", pady=(6, 0))
            box = tk.Text(frame, width=26, height=14, font=("Consolas", 9),
                          wrap="none", relief="solid", borderwidth=1)
            sb = ttk.Scrollbar(frame, orient="vertical", command=box.yview)
            box.configure(yscrollcommand=sb.set)
            box.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            lists.columnconfigure(i, weight=1)
            self.boxes[key] = box
        lists.rowconfigure(0, weight=1)

        row = ttk.Frame(self.body)
        row.pack(fill="x")
        b_save = ttk.Button(row, text="Regeln übernehmen", style="Go.TButton",
                            command=self.apply)
        b_save.pack(side="left")
        b_reset = ttk.Button(row, text="Auslieferungszustand", command=self.reset)
        b_reset.pack(side="left", padx=6)
        b_test = ttk.Button(row, text="An einem Ordner erproben …", command=self.probe)
        b_test.pack(side="left")
        b_stop = ttk.Button(row, text="Abbrechen", command=self.stop)
        b_stop.pack(side="left", padx=6)
        self.wire(go=(b_save, b_reset, b_test), stop=(b_stop,))

        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w", pady=(8, 0))

        self.fill(JUNK_DIRS, sorted(JUNK_EXTS), sorted(JUNK_NAMES))

    # -- Inhalt ------------------------------------------------------

    def fill(self, dirs, exts, names):
        for key, values in (("dirs", dirs), ("exts", exts), ("names", names)):
            box = self.boxes[key]
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(values))

    def read(self, key):
        raw = self.boxes[key].get("1.0", "end").splitlines()
        return [line.strip() for line in raw if line.strip()]

    def apply(self):
        global JUNK_DIRS, JUNK_EXTS, JUNK_NAMES
        JUNK_DIRS = [d.lower() for d in self.read("dirs")]
        JUNK_EXTS = {e.lstrip("*.").lower() for e in self.read("exts")}
        JUNK_NAMES = {n.lower() for n in self.read("names")}
        self.app.persist()
        self.say("Übernommen und gespeichert. Gilt ab sofort für alle Register.")
        self.summary.configure(text="{} Ordnermuster · {} Endungen · {} Dateinamen".format(
            len(JUNK_DIRS), len(JUNK_EXTS), len(JUNK_NAMES)))

    def reset(self):
        if not messagebox.askyesno(APP_NAME, "Die drei Listen auf den Auslieferungszustand "
                                             "zurücksetzen?"):
            return
        self.fill(DEFAULT_JUNK_DIRS, sorted(DEFAULT_JUNK_EXTS), sorted(DEFAULT_JUNK_NAMES))
        self.apply()

    # -- Erprobung ---------------------------------------------------

    def probe(self):
        self.apply()
        folder = pick_folder("Ordner zum Erproben wählen")
        if not folder:
            return

        def work(job):
            job.say("Lese …")
            entries = scan_folder(folder, job)
            limit = self.app.limit_bytes()
            skip_video = self.app.var_skip_video.get()
            res = {"mit": 0, "mit_bytes": 0, "junk": 0, "video": 0, "gross": 0,
                   "gesamt": len(entries), "gesamt_bytes": 0}
            for e in entries:
                res["gesamt_bytes"] += e.size
                if is_junk(e):
                    res["junk"] += 1
                elif skip_video and e.ext in VIDEO_EXTS:
                    res["video"] += 1
                elif e.size > limit:
                    res["gross"] += 1
                else:
                    res["mit"] += 1
                    res["mit_bytes"] += e.size
            job.done("probe", res)

        self.run(work, self.probe_done)

    def probe_done(self, _kind, res):
        anteil = (100.0 * res["mit"] / res["gesamt"]) if res["gesamt"] else 0
        self.summary.configure(
            text="Von {} Dateien ({}) fahren {} mit — {} Prozent, {}.".format(
                fmt_count(res["gesamt"]), fmt_size(res["gesamt_bytes"]),
                fmt_count(res["mit"]), round(anteil), fmt_size(res["mit_bytes"])))
        self.say("Zurückgehalten: {} durch die Listen · {} Video · {} über der Grenze."
                 .format(fmt_count(res["junk"]), fmt_count(res["video"]),
                         fmt_count(res["gross"])))


# ============================================================
#  Register 3 — Sammeln
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
        b_dry = ttk.Button(opts, text="Probelauf", command=lambda: self.start(True))
        b_dry.pack(side="left")
        b_go = ttk.Button(opts, text="Wirklich kopieren", style="Go.TButton",
                          command=lambda: self.start(False))
        b_go.pack(side="left", padx=6)
        b_stop = ttk.Button(opts, text="Abbrechen", command=self.stop)
        b_stop.pack(side="left")
        self.wire(go=(b_dry, b_go), stop=(b_stop,))

        frame, self.tree = make_tree(self.body, ("Datei", "Ordner", "MB", "Geändert"),
                                     (260, 380, 90, 110), height=13)
        frame.pack(fill="both", expand=True, pady=10)
        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")

    def _pick(self, var, title):
        p = pick_folder(title, var.get() or self.app.recall("sammeln"))
        if p:
            var.set(p)
            self.app.remember("sammeln", p)

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
            items.append((e.abspath, os.path.join(dst, e.rel), e.size))
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
            rep = transfer(items, job, dry_run=dry, move=False, workers=self.app.workers())
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
        b_go = ttk.Button(row, text="Suchen", style="Go.TButton", command=self.start)
        b_go.pack(side="left")
        b_stop = ttk.Button(row, text="Abbrechen", command=self.stop)
        b_stop.pack(side="left", padx=6)
        b_exp = ttk.Button(row, text="Liste sichern", command=self.export)
        b_exp.pack(side="left")
        b_quar = ttk.Button(row, text="Duplikate in Quarantäne verschieben",
                            command=self.quarantine)
        b_quar.pack(side="left", padx=6)
        self.wire(go=(b_go, b_exp, b_quar), stop=(b_stop,))

        frame, self.tree = make_tree(self.body, ("Rolle", "Datei", "Ordner", "MB", "Gruppe"),
                                     (90, 260, 360, 80, 90), height=13)
        frame.pack(fill="both", expand=True, pady=10)
        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")
        self.groups = []

    def _pick(self, var, title):
        p = pick_folder(title, var.get() or self.app.recall("dubletten"))
        if p:
            var.set(p)
            self.app.remember("dubletten", p)

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
                items.append((e.abspath, os.path.join(quar, e.rel), e.size))
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
        self.run(lambda job: job.done("quar", transfer(items, job, dry_run=False, move=True,
                                           workers=self.app.workers())),
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
        b_dry = ttk.Button(row, text="Probelauf", command=lambda: self.start(True))
        b_dry.pack(side="left")
        b_go = ttk.Button(row, text="Ausführen", style="Go.TButton",
                          command=lambda: self.start(False))
        b_go.pack(side="left", padx=6)
        b_stop = ttk.Button(row, text="Abbrechen", command=self.stop)
        b_stop.pack(side="left")
        b_exp = ttk.Button(row, text="Liste sichern", command=self.export)
        b_exp.pack(side="left", padx=6)
        self.wire(go=(b_dry, b_go, b_exp), stop=(b_stop,))

        frame, self.tree = make_tree(self.body, ("Jahr", "Quelle", "Datei", "Ordner", "MB"),
                                     (80, 90, 260, 340, 80), height=12)
        frame.pack(fill="both", expand=True, pady=10)
        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")

    def _pick(self, var, title):
        p = pick_folder(title, var.get() or self.app.recall("bilder"))
        if p:
            var.set(p)
            self.app.remember("bilder", p)

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
            claimed = set()
            umbenannt = 0
            for i, e in enumerate(wanted, 1):
                if job.stopped:
                    break
                if i % 200 == 0:
                    job.progress(i, len(wanted))
                    job.say("Jahr {} von {}".format(i, len(wanted)))
                year, source = year_of(e)
                folder = os.path.join(dst, str(year) if year else "_Jahr_unklar")
                target = unique_target(folder, e.name, claimed)
                if os.path.basename(target) != e.name:
                    umbenannt += 1
                plan.append((e.abspath, target, e.size))
                rows.append((str(year) if year else "unklar", source, e))
            rep = transfer(plan, job, dry_run=dry, move=move, workers=self.app.workers())
            job.done("img", (rep, rows, dry, umbenannt))

        self.run(work, self.finish)

    def finish(self, _kind, payload):
        rep, rows, dry, umbenannt = payload
        self.rows = rows
        self.dst = self.var_dst.get().strip()
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
        self.say("{}: {} bereit, {} übersprungen, {} fehlgeschlagen{}."
                 .format("Probelauf" if dry else "Fertig", fmt_count(rep["ok"]),
                         fmt_count(rep["skip"]), fmt_count(rep["fail"]),
                         " · {} wegen Namensgleichheit nummeriert".format(fmt_count(umbenannt))
                         if umbenannt else ""))


    def export(self):
        rows = getattr(self, "rows", None)
        if not rows:
            messagebox.showinfo(APP_NAME, "Erst einen Probelauf oder Durchlauf machen.")
            return
        path = filedialog.asksaveasfilename(
            title="Bilderliste sichern", defaultextension=".csv",
            initialfile="bilder.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["quelle_id", "herkunft_pfad", "dateiname", "groesse_mb",
                        "jahr", "jahr_quelle", "ziel_ordner"])
            for jahr, quelle, e in rows:
                erste = e.rel.replace("\\", "/").split("/")[0]
                w.writerow([erste, e.reldir, e.name,
                            "{:.2f}".format(e.size_mb).replace(".", ","),
                            jahr, quelle, jahr])
        self.say("Gesichert: " + path + " — diese Datei liest Register 8 ein.")


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
        p = pick_folder("Ordner wählen", self.root or None)
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

        # Zwei Zeilen zu je drei Feldpaaren — so bleibt auch im schmalsten
        # zugelassenen Fenster jedes Feld vollstaendig sichtbar.
        fields = [
            (0, "Name enthält", self.var_name, 24),
            (0, "MB von", self.var_min, 8), (0, "bis", self.var_max, 8),
            (1, "Datum von", self.var_from, 12), (1, "bis", self.var_to, 12),
            (1, "Endungen", self.var_ext, 18),
        ]
        cols = {0: 0, 1: 0}
        for row_i, lab, var, width in fields:
            ttk.Label(f, text=lab).grid(row=row_i, column=cols[row_i], sticky="e",
                                        padx=(8, 3), pady=(0 if row_i == 0 else 6, 0))
            ttk.Entry(f, textvariable=var, width=width).grid(
                row=row_i, column=cols[row_i] + 1, sticky="w",
                pady=(0 if row_i == 0 else 6, 0))
            var.trace_add("write", lambda *a: self.refresh())
            cols[row_i] += 2

        ttk.Label(f, text="Art").grid(row=0, column=6, sticky="e", padx=(16, 3))
        cb = ttk.Combobox(f, textvariable=self.var_cat, width=13, state="readonly",
                          values=["alle"] + list(CATS.keys()) + ["sonstiges"])
        cb.grid(row=0, column=7, sticky="w")
        ttk.Label(f, text="Vergleich").grid(row=1, column=6, sticky="e", padx=(16, 3), pady=(6, 0))
        cb2 = ttk.Combobox(f, textvariable=self.var_cmp, width=18, state="readonly",
                           values=["alle zeigen", "nur hier vorhanden", "auf beiden Seiten",
                                   "Grösse weicht ab"])
        cb2.grid(row=1, column=7, sticky="w", pady=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        cb2.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # Eigene Zeile statt einer weiteren Spalte: sonst schiebt sich beides
        # im schmalen Fenster ueber den rechten Rand hinaus.
        extra = ttk.Frame(f)
        extra.grid(row=2, column=0, columnspan=8, sticky="w", padx=(8, 0), pady=(8, 0))
        ttk.Checkbutton(extra, text="Ausschlussliste anwenden", variable=self.var_junk,
                        command=self.refresh).pack(side="left")
        ttk.Button(extra, text="Voreinstellung Phase 2",
                   command=self.preset).pack(side="left", padx=(16, 0))

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
        items = [(e.abspath, os.path.join(t.root, e.rel), e.size) for e in picked]
        self.run(lambda job: job.done("cp", transfer(items, job, dry_run=False, move=False,
                                         workers=self.app.workers())),
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
#  Register 6 — Kategorien
# ============================================================

KATEGORIEN = ["01_Dokumente", "02_Bilder_RAW", "03_Audio", "04_Projekte",
              "05_Code", "06_Archive", "07_Sonstiges"]

CAT2ORDNER = {
    "dokument": "01_Dokumente",
    "audio": "03_Audio",
    "code": "05_Code",
    "archiv": "06_Archive",
    "sonstiges": "07_Sonstiges",
}


def folder_survey(entries, depth=2):
    """
    Fasst die Dateien zu Ordnern der gewuenschten Tiefe zusammen und
    schlaegt je Ordner eine Kategorie vor — die Art, die dort das meiste
    Volumen ausmacht. Volumen statt Anzahl, weil hundert Vorschaubilder
    neben zehn Vertraegen sonst die Zuordnung kippen.
    """
    buckets = {}
    for e in entries:
        parts = e.rel.replace("\\", "/").split("/")
        if len(parts) <= depth:
            key = "/".join(parts[:-1]) or "."
        else:
            key = "/".join(parts[:depth])
        b = buckets.setdefault(key, {"n": 0, "bytes": 0, "cats": {}})
        b["n"] += 1
        b["bytes"] += e.size
        cat = e.cat
        if cat == "bild":
            cat = "bild_raw" if e.ext in RAW_STAY_EXTS else "bild"
        b["cats"][cat] = b["cats"].get(cat, 0) + e.size

    rows = []
    for key in sorted(buckets):
        b = buckets[key]
        best = max(b["cats"].items(), key=lambda kv: kv[1])[0] if b["cats"] else "sonstiges"
        if best == "bild_raw":
            ziel = "02_Bilder_RAW"
        elif best in ("bild", "video"):
            ziel = "07_Sonstiges"
        else:
            ziel = CAT2ORDNER.get(best, "07_Sonstiges")
        rows.append({"pfad": key, "n": b["n"], "bytes": b["bytes"],
                     "art": best, "ziel": ziel})
    return rows


class KategorienTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Phase 7 · Kategorien",
            "Ordner statt Einzeldateien einsortieren. Das Programm schlägt je Ordner eine "
            "Kategorie vor — nach dem Volumen, nicht nach der Anzahl. Doppelklick auf eine "
            "Zeile ändert den Vorschlag, dann wird in einem Zug verschoben.")

        g = ttk.Frame(self.body)
        g.pack(fill="x")
        self.var_root = tk.StringVar()
        ttk.Label(g, text="Quelle", width=8).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(g, textvariable=self.var_root).grid(row=0, column=1, sticky="ew", padx=8, pady=3)
        ttk.Button(g, text="…", width=4,
                   command=lambda: self._pick(self.var_root)).grid(row=0, column=2, pady=3)
        ttk.Label(g, text="Der Ordner einer Quelle, z. B.  G:\\Meine Ablage\\"
                          "Andreas_2026_Dateiverwaltung\\10_PC1",
                  style="Hint.TLabel").grid(row=1, column=1, sticky="w", padx=8)
        g.columnconfigure(1, weight=1)

        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Ebene").pack(side="left")
        self.var_depth = tk.StringVar(value="2")
        ttk.Combobox(row, textvariable=self.var_depth, width=4, state="readonly",
                     values=["1", "2", "3"]).pack(side="left", padx=(4, 12))
        b_go = ttk.Button(row, text="Vorschläge berechnen",
                          style="Go.TButton", command=self.start)
        b_go.pack(side="left")
        b_stop = ttk.Button(row, text="Abbrechen", command=self.stop)
        b_stop.pack(side="left", padx=6)
        b_exp = ttk.Button(row, text="Ordnerregister sichern", command=self.export)
        b_exp.pack(side="left")
        b_mv = ttk.Button(row, text="Jetzt verschieben", command=self.apply)
        b_mv.pack(side="left", padx=6)
        self.wire(go=(b_go, b_exp, b_mv), stop=(b_stop,))

        frame, self.tree = make_tree(self.body, ("Ordner", "Dateien", "Grösse", "Art", "Ziel"),
                                     (420, 90, 110, 110, 150), height=14)
        frame.pack(fill="both", expand=True, pady=10)
        self.tree.bind("<Double-1>", self.edit_row)

        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")
        self.rows = []
        self.entries = []

    def _pick(self, var):
        p = pick_folder("Ordner wählen", var.get() or self.app.recall("kategorien"))
        if p:
            var.set(p)
            self.app.remember("kategorien", p)

    def start(self):
        root = self.var_root.get().strip()
        if not os.path.isdir(root):
            messagebox.showwarning(APP_NAME, "Bitte einen vorhandenen Ordner wählen.")
            return
        depth = int(self.var_depth.get())

        def work(job):
            job.say("Lese …")
            entries = [e for e in scan_folder(root, job) if not is_junk(e)]
            job.say("Fasse zu Ordnern zusammen …")
            job.done("kat", (entries, folder_survey(entries, depth)))

        self.run(work, self.finish)

    def finish(self, _kind, payload):
        self.entries, self.rows = payload
        self.refresh_tree()
        offen = sum(1 for r in self.rows if r["ziel"] == "07_Sonstiges")
        self.summary.configure(
            text="{} Ordner · {} landen in 07_Sonstiges und wollen angesehen werden"
            .format(fmt_count(len(self.rows)), fmt_count(offen)))
        self.say("Doppelklick auf eine Zeile ändert das Ziel. Erst dann verschieben.")

    def refresh_tree(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        for i, r in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i),
                             values=(r["pfad"], fmt_count(r["n"]), fmt_size(r["bytes"]),
                                     r["art"], r["ziel"]))

    def edit_row(self, _ev):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        cur = self.rows[idx]["ziel"]
        nxt = KATEGORIEN[(KATEGORIEN.index(cur) + 1) % len(KATEGORIEN)] \
            if cur in KATEGORIEN else KATEGORIEN[0]
        self.rows[idx]["ziel"] = nxt
        self.tree.item(sel[0], values=(self.rows[idx]["pfad"], fmt_count(self.rows[idx]["n"]),
                                       fmt_size(self.rows[idx]["bytes"]),
                                       self.rows[idx]["art"], nxt))

    def apply(self):
        if not self.rows:
            messagebox.showinfo(APP_NAME, "Erst Vorschläge berechnen.")
            return
        root = os.path.abspath(self.var_root.get().strip())
        items = []
        for r in self.rows:
            if r["pfad"] in (".", "") or r["pfad"] in KATEGORIEN:
                continue
            if r["pfad"].split("/")[0] in KATEGORIEN:
                continue
            src = os.path.join(root, r["pfad"].replace("/", os.sep))
            dst = os.path.join(root, r["ziel"], os.path.basename(r["pfad"]))
            if os.path.isdir(long_path(src)):
                items.append((src, dst))
        if not items:
            messagebox.showinfo(APP_NAME, "Es gibt nichts zu verschieben — "
                                          "vermutlich ist schon alles einsortiert.")
            return
        if not messagebox.askyesno(
                APP_NAME,
                "{} Ordner in ihre Kategorien verschieben?\n\nInnerhalb von:\n{}\n\n"
                "Die Ordner bleiben vollständig erhalten, sie liegen danach eine Ebene "
                "tiefer. Gelöscht wird nichts.".format(fmt_count(len(items)), root)):
            return

        def work(job):
            rep = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0, "errors": []}
            for i, (src, dst) in enumerate(items, 1):
                if job.stopped:
                    break
                job.progress(i, len(items))
                job.say("Verschiebe {} von {}".format(i, len(items)))
                try:
                    if os.path.exists(long_path(dst)):
                        rep["skip"] += 1
                        continue
                    os.makedirs(long_path(os.path.dirname(dst)), exist_ok=True)
                    shutil.move(long_path(src), long_path(dst))
                    rep["ok"] += 1
                except Exception as exc:
                    rep["fail"] += 1
                    if len(rep["errors"]) < 200:
                        rep["errors"].append("{}: {}".format(short_path(src), exc))
            job.done("mv", rep)

        self.run(work, lambda k, rep: self.say(
            "Verschoben: {} · übersprungen: {} · fehlgeschlagen: {}. Nichts gelöscht."
            .format(fmt_count(rep["ok"]), fmt_count(rep["skip"]), fmt_count(rep["fail"]))))

    def export(self):
        if not self.rows:
            messagebox.showinfo(APP_NAME, "Erst Vorschläge berechnen.")
            return
        path = filedialog.asksaveasfilename(
            title="Ordnerregister sichern", defaultextension=".csv",
            initialfile="ordnerregister.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["ordner_id", "ziel_pfad", "anzahl_dateien", "tags",
                        "aufbewahrung", "wichtigkeit", "geprueft_am"])
            for i, r in enumerate(self.rows, 1):
                w.writerow(["O-{:03d}".format(i),
                            "{}/{}".format(r["ziel"], os.path.basename(r["pfad"])),
                            r["n"], "", "", "", ""])
        self.say("Gesichert: " + path + " — Tags und Aufbewahrung füllst du in Sheets.")


# ============================================================
#  Register 7 — Index zusammenführen
# ============================================================

def read_csv_rows(path):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, "r", newline="", encoding=enc) as f:
                sample = f.read(4096)
                f.seek(0)
                delim = ";" if sample.count(";") >= sample.count(",") else ","
                return list(csv.DictReader(f, delimiter=delim))
        except (UnicodeDecodeError, OSError):
            continue
    return []


class IndexTab(Section):
    def __init__(self, master, app):
        super().__init__(
            master, app, "Phase 8 · Index",
            "Aus dem fertigen Archiv und den Listen der vorherigen Register eine einzige "
            "Index-Datei bauen — mit allen sechzehn Spalten. Was von Hand kommt, bleibt leer: "
            "Tags, Aufbewahrung, Status und Notiz füllst du danach in Sheets.")

        g = ttk.Frame(self.body)
        g.pack(fill="x")
        self.var_root = tk.StringVar()
        self.var_dup = tk.StringVar()
        self.var_img = tk.StringVar()
        rows = [
            ("Archiv", self.var_root, "folder", "Der fertige Zielordner — Sammelplatte oder Drive"),
            ("Dubletten", self.var_dup, "file", "dubletten.csv aus Register 4 — freiwillig"),
            ("Bilder", self.var_img, "file", "bilder.csv aus Register 5 — freiwillig"),
        ]
        for i, (lab, var, kind, hint) in enumerate(rows):
            ttk.Label(g, text=lab, width=10).grid(row=i * 2, column=0, sticky="w", pady=(3, 0))
            ttk.Entry(g, textvariable=var).grid(row=i * 2, column=1, sticky="ew", padx=8, pady=(3, 0))
            ttk.Button(g, text="…", width=4,
                       command=lambda v=var, k=kind: self._pick(v, k)).grid(row=i * 2, column=2, pady=(3, 0))
            ttk.Label(g, text=hint, style="Hint.TLabel").grid(row=i * 2 + 1, column=1, sticky="w", padx=8)
        g.columnconfigure(1, weight=1)

        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(10, 0))
        b_go = ttk.Button(row, text="Index bauen", style="Go.TButton", command=self.start)
        b_go.pack(side="left")
        b_stop = ttk.Button(row, text="Abbrechen", command=self.stop)
        b_stop.pack(side="left", padx=6)
        b_exp = ttk.Button(row, text="Index sichern", command=self.export)
        b_exp.pack(side="left")
        self.wire(go=(b_go, b_exp), stop=(b_stop,))

        frame, self.tree = make_tree(
            self.body, ("datei_id", "quelle_id", "dateiname", "kategorie", "MB", "dup_rolle"),
            (90, 90, 280, 130, 80, 100), height=13)
        frame.pack(fill="both", expand=True, pady=10)
        self.summary = ttk.Label(self.body, text="", style="Sum.TLabel")
        self.summary.pack(anchor="w")
        self.index = []

    def _pick(self, var, kind):
        p = pick_folder("Ordner wählen") if kind == "folder" else \
            filedialog.askopenfilename(title="CSV wählen", filetypes=[("CSV", "*.csv"), ("Alle", "*.*")])
        if p:
            var.set(p)

    def start(self):
        root = self.var_root.get().strip()
        if not os.path.isdir(root):
            messagebox.showwarning(APP_NAME, "Bitte den Archivordner wählen.")
            return
        dup_csv, img_csv = self.var_dup.get().strip(), self.var_img.get().strip()

        def work(job):
            job.say("Lese Archiv …")
            entries = [e for e in scan_folder(root, job) if not is_junk(e)]

            dup_by_key, dup_hits = {}, 0
            if dup_csv and os.path.isfile(dup_csv):
                job.say("Lese Dublettenliste …")
                for r in read_csv_rows(dup_csv):
                    k = (r.get("dateiname", "").lower(),
                         (r.get("groesse_mb") or "").replace(",", "."))
                    dup_by_key[k] = r

            img_by_name = {}
            if img_csv and os.path.isfile(img_csv):
                job.say("Lese Bilderliste …")
                for r in read_csv_rows(img_csv):
                    img_by_name[r.get("dateiname", "").lower()] = r

            job.say("Baue Index …")
            out = []
            for i, e in enumerate(entries, 1):
                if job.stopped:
                    break
                if i % 2000 == 0:
                    job.progress(i, len(entries))
                parts = e.rel.replace("\\", "/").split("/")
                quelle = parts[0] if len(parts) > 1 else ""
                mb = "{:.2f}".format(e.size_mb)
                d = dup_by_key.get((e.name.lower(), mb))
                img = img_by_name.get(e.name.lower())
                if d:
                    dup_hits += 1
                out.append({
                    "datei_id": "{:06d}".format(i),
                    "quelle_id": (img.get("quelle_id") if img else "") or quelle,
                    "original_pfad": (img.get("herkunft_pfad") if img else "") or e.reldir,
                    "dateiname": e.name,
                    "endung": e.ext,
                    "groesse_mb": mb.replace(".", ","),
                    "geaendert_am": e.date,
                    "pruefsumme": (d.get("pruefsumme") if d else ""),
                    "dup_gruppe": (d.get("dup_gruppe") if d else ""),
                    "dup_rolle": (d.get("dup_rolle") if d else ""),
                    "kategorie": e.cat,
                    "ziel_pfad": e.reldir,
                    "tags": "", "aufbewahrung": "", "status": "neu", "notiz": "",
                })
            job.done("idx", (out, dup_hits, bool(img_by_name)))

        self.run(work, self.finish)

    def finish(self, _kind, payload):
        self.index, dup_hits, had_img = payload
        for r in self.tree.get_children():
            self.tree.delete(r)
        for r in self.index[:MAX_ROWS]:
            self.tree.insert("", "end", values=(r["datei_id"], r["quelle_id"], r["dateiname"],
                                                r["kategorie"], r["groesse_mb"], r["dup_rolle"]))
        if len(self.index) > MAX_ROWS:
            self.tree.insert("", "end", values=("…", "", "weitere ausgeblendet", "", "", ""))
        self.summary.configure(
            text="{} Zeilen · {} mit Dubletten-Angabe{}".format(
                fmt_count(len(self.index)), fmt_count(dup_hits),
                " · Bilderherkunft eingespielt" if had_img else ""))
        self.say("Fertig. Sichern, in Sheets importieren, dann Tags und Aufbewahrung füllen.")

    def export(self):
        if not self.index:
            messagebox.showinfo(APP_NAME, "Erst den Index bauen.")
            return
        path = filedialog.asksaveasfilename(
            title="Index sichern", defaultextension=".csv",
            initialfile="Dateiindex_2026.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        cols = ["datei_id", "quelle_id", "original_pfad", "dateiname", "endung",
                "groesse_mb", "geaendert_am", "pruefsumme", "dup_gruppe", "dup_rolle",
                "kategorie", "ziel_pfad", "tags", "aufbewahrung", "status", "notiz"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
            w.writeheader()
            for r in self.index:
                w.writerow(r)
        self.say("Gesichert: " + path)


# ============================================================
#  Hauptfenster
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("{} — Werkzeug".format(APP_NAME))
        self.geometry("1240x840")
        self.minsize(1040, 760)

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
        self.var_limit = tk.StringVar(value=str(SETTINGS.get("limit_mb", int(DEFAULT_MAX_MB))))
        ttk.Entry(bar, textvariable=self.var_limit, width=6).pack(side="left")
        self.var_skip_video = tk.BooleanVar(value=bool(SETTINGS.get("skip_video", True)))
        ttk.Checkbutton(bar, text="Video nicht übernehmen",
                        variable=self.var_skip_video).pack(side="left", padx=12)
        ttk.Label(bar, text="Fäden").pack(side="left", padx=(12, 4))
        self.var_workers = tk.StringVar(value=str(SETTINGS.get("workers", DEFAULT_WORKERS)))
        ttk.Spinbox(bar, from_=1, to=16, width=3,
                    textvariable=self.var_workers).pack(side="left")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self.tab_inv = InventurTab(nb, self)
        self.tab_reg = RegelnTab(nb, self)
        self.tab_sam = SammelnTab(nb, self)
        self.tab_dup = DublettenTab(nb, self)
        self.tab_img = BilderTab(nb, self)
        self.tab_kat = KategorienTab(nb, self)
        self.tab_idx = IndexTab(nb, self)
        self.tab_exp = ExplorerTab(nb, self)
        nb.add(self.tab_inv, text="  1 · Inventur  ")
        nb.add(self.tab_reg, text="  2 · Regeln  ")
        nb.add(self.tab_sam, text="  3 · Sammeln  ")
        nb.add(self.tab_dup, text="  4 · Dubletten  ")
        nb.add(self.tab_img, text="  5 · Bilder  ")
        nb.add(self.tab_kat, text="  7 · Kategorien  ")
        nb.add(self.tab_idx, text="  8 · Index  ")
        nb.add(self.tab_exp, text="  Explorer  ")

        foot = ttk.Frame(self, padding=(14, 0, 14, 10))
        foot.pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

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
        st.configure("Detail.TLabel", font=("Consolas", 9), foreground=muted)
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

    def workers(self):
        try:
            return max(1, min(16, int(self.var_workers.get())))
        except ValueError:
            return DEFAULT_WORKERS

    def set_source(self, sid, path, entries):
        self.source_id, self.source_path, self._entries = sid, path, entries

    def current_entries(self):
        return self._entries

    # -- Einstellungen ----------------------------------------------

    def remember(self, key, value):
        """Merkt sich einen zuletzt benutzten Pfad."""
        if value:
            SETTINGS.setdefault("pfade", {})[key] = value

    def recall(self, key):
        return SETTINGS.get("pfade", {}).get(key, "")

    def persist(self):
        SETTINGS["limit_mb"] = self.limit_mb()
        SETTINGS["skip_video"] = bool(self.var_skip_video.get())
        SETTINGS["workers"] = self.workers()
        SETTINGS["junk_dirs"] = list(JUNK_DIRS)
        SETTINGS["junk_exts"] = sorted(JUNK_EXTS)
        SETTINGS["junk_names"] = sorted(JUNK_NAMES)
        save_settings(SETTINGS)

    def on_close(self):
        self.persist()
        self.destroy()


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
