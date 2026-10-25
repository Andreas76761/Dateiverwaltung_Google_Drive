"""
Gemeinsames Handwerkszeug der Pruefungen.

Hier steht, was alle Pruefskripte brauchen: wo das Programm liegt, wo der
Pruefbestand hin darf, wie ein Ergebnis festgehalten wird, und wie man
eine Oberflaeche bedient, hinter der niemand sitzt.
"""

import hashlib
import os
import sys
import tempfile
import time


def werkzeug():
    """Laedt das Programm aus dem Ordner darueber."""
    hier = os.path.dirname(os.path.abspath(__file__))
    oben = os.path.dirname(hier)
    if oben not in sys.path:
        sys.path.insert(0, oben)
    import dateiumzug
    return dateiumzug


def arbeitsordner(unterordner=""):
    """
    Wo der Pruefbestand liegt.

    Standard ist ein Ordner im Temp-Verzeichnis. Wer woanders hin will,
    setzt DATEIUMZUG_PRUEFUNG -- etwa auf eine Platte mit mehr Platz;
    gebraucht wird knapp ein halbes Gigabyte.
    """
    basis = os.environ.get("DATEIUMZUG_PRUEFUNG") or os.path.join(
        tempfile.gettempdir(), "dateiumzug-pruefung")
    pfad = os.path.join(basis, unterordner) if unterordner else basis
    return pfad


def hashe(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for stueck in iter(lambda: f.read(1 << 20), b""):
            h.update(stueck)
    return h.hexdigest()


def bestand(wurzel):
    """Alle Dateien unter wurzel: {relpfad: (groesse, geaendert)}."""
    out = {}
    for ordner, _unter, dateien in os.walk(wurzel):
        for n in dateien:
            p = os.path.join(ordner, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out[os.path.relpath(p, wurzel).replace("\\", "/")] = (
                st.st_size, int(st.st_mtime))
    return out


def unterschied(a, b):
    """(dazugekommen, verschwunden, veraendert) zwischen zwei Bestaenden."""
    dazu = len(set(b) - set(a))
    weg = len(set(a) - set(b))
    anders = sum(1 for k in set(a) & set(b) if a[k][0] != b[k][0])
    return (dazu, weg, anders)


def kurz(x, n=14):
    t = x if isinstance(x, str) else repr(x)
    return t if len(t) <= n else t[:n - 3] + "..."


class Bericht:
    """Sammelt Soll und Ist und sagt am Ende, ob etwas nicht stimmt."""

    def __init__(self, titel):
        self.titel = titel
        self.zeilen = []

    def prueft(self, bereich, was, soll, ist, hinweis=""):
        ok = soll == ist
        self.zeilen.append((bereich, was, soll, ist, ok))
        if not ok:
            print("   FEHLER  {} · {}: soll {}, ist {} {}".format(
                bereich, was, kurz(soll, 60), kurz(ist, 60), hinweis))
        return ok

    def notiz(self, bereich, was, wert):
        self.zeilen.append((bereich, was, wert, wert, None))

    def ausgeben(self):
        print()
        print("=" * 78)
        print(self.titel)
        print("-" * 78)
        for bereich, was, soll, ist, ok in self.zeilen:
            if ok is None:
                print("     {:15s} {:34s} {}".format(bereich, was, soll))
            else:
                print("{} {:15s} {:34s} soll {:>14} · ist {:>14}".format(
                    "ok  " if ok else "FEHL", bereich, was, kurz(soll), kurz(ist)))
        fehler = [z for z in self.zeilen if z[4] is False]
        gezaehlt = [z for z in self.zeilen if z[4] is not None]
        print("=" * 78)
        print("{} Prüfungen, {} Fehler".format(len(gezaehlt), len(fehler)))
        return 1 if fehler else 0


# ------------------------------------------------------------
#  Eine Oberflaeche bedienen, hinter der niemand sitzt
# ------------------------------------------------------------

class Bedienung:
    """
    Faengt die Dialoge ab und wartet auf das Ende eines Vorgangs.

    Rueckfragen werden mit Ja beantwortet, Ordner- und Speichern-Dialoge
    liefern, was vorher hineingelegt wurde. Ohne das bliebe jede Pruefung
    an einem Fenster stehen, das niemand sieht.
    """

    def __init__(self, d, laut=False):
        self.d = d
        self.meldungen = []
        self.warnungen = []
        self.ordner = None
        self.speichern = None
        d.messagebox.askyesno = lambda *a, **k: True
        d.messagebox.showinfo = lambda *a, **k: self.meldungen.append(str(a[-1]))
        d.messagebox.showwarning = lambda *a, **k: self.warnungen.append(str(a[-1]))
        d.messagebox.showerror = lambda *a, **k: print("   [Fehler]\n" + str(a[-1]))
        d.pick_folder = lambda *a, **k: self.ordner
        d.filedialog.asksaveasfilename = lambda *a, **k: self.speichern
        self.laut = laut

    def warte(self, tab, app, grenze=900):
        """
        Wartet, bis ein Register fertig ist.

        Nicht ueber job.stopped -- das steht nur fuer "abgebrochen". Die
        Oberflaeche selbst sagt es zuverlaessig: waehrend eines Vorgangs
        sind die Startknoepfe gesperrt.
        """
        t0 = time.time()
        while time.time() - t0 < grenze:
            app.update()
            if tab._go and str(tab._go[0].cget("state")) == "normal":
                break
            time.sleep(0.02)
        else:
            print("   [Zeitüberschreitung in {}]".format(type(tab).__name__))
        for _ in range(30):
            app.update()
            time.sleep(0.01)

    def kurz_durchatmen(self, app, runden=20):
        for _ in range(runden):
            app.update()
            time.sleep(0.02)
