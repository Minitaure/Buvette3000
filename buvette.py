"""Buvette3000 - caisse de buvette portable (Tkinter + SQLite)."""

import csv
import ctypes
from ctypes import wintypes
import json
import os
import re
import sqlite3
import sys
import tkinter as tk
from datetime import datetime, date
from tkinter import ttk, filedialog
import tkinter.font as tkfont

APP_NAME = "Buvette 3000"


# ---------------------------------------------------------------------------
# Emplacements : tout reste à côté de l'exécutable (mode portable)
# ---------------------------------------------------------------------------
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Haute résolution : affichage net quand Windows est en mise à l'échelle (125 %, 150 %…)
# ---------------------------------------------------------------------------
ECHELLE = 1.0


def activer_dpi():
    """À appeler avant de créer la fenêtre Tk, sinon Windows étire l'appli comme une image (flou)."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def px(n):
    """Dimension en pixels adaptée à la mise à l'échelle de l'écran."""
    return int(round(n * ECHELLE))


_ICONES = []  # handles Windows gardés en vie


def appliquer_icone(fenetre):
    """Icône nette à toute mise à l'échelle : Tk n'utilise que les images 16/32 px du .ico
    (agrandies donc floues à 125 %) ; on charge nous-mêmes la taille exacte demandée par Windows."""
    try:
        u = ctypes.windll.user32
        u.LoadImageW.restype = wintypes.HANDLE
        u.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT)
        u.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        hwnd = int(fenetre.wm_frame(), 16)
        for type_icone, metrique in ((0, 49), (1, 11)):   # ICON_SMALL / SM_CXSMICON, ICON_BIG / SM_CXICON
            t = u.GetSystemMetrics(metrique)
            h = u.LoadImageW(None, ressource("buvette.ico"), 1, t, t, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                _ICONES.append(h)
                u.SendMessageW(hwnd, 0x0080, type_icone, h)    # WM_SETICON
    except Exception:
        pass


def icone_au_affichage(fenetre):
    """Tk recrée la fenêtre Windows quand elle s'affiche : l'icône est posée à ce moment-là."""
    fenetre.bind("<Map>", lambda e: appliquer_icone(fenetre) if e.widget is fenetre else None, add="+")


def ressource(nom):
    """Fichier livré avec l'application (assets/), y compris une fois empaqueté par PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", nom)


DATA_DIR = os.path.join(app_dir(), "data")
DB_PATH = os.path.join(DATA_DIR, "buvette.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
MOT_DE_PASSE_DEFAUT = "bbc67"


# ---------------------------------------------------------------------------
# Mémorisation de la position des fenêtres (data/config.json)
# ---------------------------------------------------------------------------
def lire_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def ecrire_config(cle, valeur):
    config = lire_config()
    config[cle] = valeur
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass


def ecran_virtuel():
    """(x, y, largeur, hauteur) de l'ensemble des écrans."""
    try:
        m = ctypes.windll.user32.GetSystemMetrics
        return m(76), m(77), m(78), m(79)
    except Exception:
        return 0, 0, 10000, 10000


def memoriser_position(fenetre, cle):
    try:
        zoom = fenetre.state() == "zoomed"
        if zoom:
            fenetre.state("normal")
        l, h, x, y = map(int, re.match(r"(\d+)x(\d+)\+?(-?\d+)\+?(-?\d+)", fenetre.geometry()).groups())
        ecrire_config(cle, {"x": x, "y": y, "largeur": l, "hauteur": h, "zoom": zoom, "echelle": ECHELLE})
    except (tk.TclError, AttributeError):
        pass


def restaurer_position(fenetre, cle, taille=True):
    pos = lire_config().get(cle)
    if not pos:
        return False
    # Position mémorisée à une autre échelle d'écran : on la convertit
    f = ECHELLE / pos.get("echelle", 1.0)
    pos = {k: int(round(v * f)) if k in ("x", "y", "largeur", "hauteur") else v for k, v in pos.items()}
    ex, ey, el, eh = ecran_virtuel()
    # Fenêtre hors écran (autre PC, écran débranché) : on garde la position par défaut
    if not (ex - 50 <= pos["x"] <= ex + el - 100 and ey <= pos["y"] <= ey + eh - 100):
        return False
    if taille:
        fenetre.geometry(f"{pos['largeur']}x{pos['hauteur']}+{pos['x']}+{pos['y']}")
        if pos.get("zoom"):
            fenetre.state("zoomed")
    else:
        fenetre.geometry(f"+{pos['x']}+{pos['y']}")
    return True


def demander_mot_de_passe(parent):
    """Accès limité (historique, produits). Mot de passe en clair dans data/config.json."""
    config = lire_config()
    if "mot_de_passe" not in config:
        ecrire_config("mot_de_passe", MOT_DE_PASSE_DEFAUT)
        config["mot_de_passe"] = MOT_DE_PASSE_DEFAUT
    saisie = Dialogue(parent, "Accès protégé", "Mot de passe :",
                      [("ANNULER", False, NUIT_CLAIR), ("VALIDER", True, VERT)], saisie_masquee=True).resultat
    if saisie is None:
        return False
    if saisie != config["mot_de_passe"]:
        informer(parent, "Accès protégé", "Mot de passe incorrect.")
        return False
    return True

# ---------------------------------------------------------------------------
# Charte graphique
# ---------------------------------------------------------------------------
NUIT = "#0b2532"            # bleu nuit (fond)
NUIT_CLAIR = "#173d50"
NUIT_FONCE = "#06171f"
CYAN = "#2a9cc8"
CYAN_FONCE = "#1f7fa6"
CIEL = "#dff1fa"
FOND = "#f2f9fc"            # fond des fenêtres secondaires
MAGENTA = "#e6007e"
JAUNE = "#f7c600"
VERT = "#3aaa35"
VERT_FONCE = "#2a7f26"
VERT_LIVRE = "#cdeec9"
ORANGE = "#f39200"
VIOLET = "#6f3d96"
GRIS = "#9aa7ae"
GRIS_CLAIR = "#e3e8eb"
GRIS_TEXTE = "#5b6b75"

F_TITRE = "Bahnschrift SemiBold Condensed"   # police de titre condensée
F_TITRE_LEGER = "Bahnschrift Condensed"
F_TEXTE = "Segoe UI"

# Couleurs proposées pour les boutons produits (même ordre que l'ancienne palette)
COULEURS_PRODUITS = ["#e6007e", "#f06aa9", "#6f3d96", "#a685c4", "#1f6f99", "#2a9cc8", "#7cc7e8",
                     "#3aaa35", "#8fd18b", "#fbe17a", "#f7c600", "#f39200", "#c8641e", "#f8bd6b",
                     "#9fb3bd"]
ANCIENNES_COULEURS = ["#e57373", "#f06292", "#ba68c8", "#9575cd", "#7986cb", "#4fc3f7",
                      "#4db6ac", "#81c784", "#aed581", "#dce775", "#ffd54f", "#ffb74d",
                      "#8d6e63", "#a1887f", "#90a4ae"]

PRODUITS_DEFAUT = [
    ("Café", 100, "Boissons chaudes", "#c8641e"),
    ("Thé", 100, "Boissons chaudes", "#f8bd6b"),
    ("Eau", 100, "Boissons", "#2a9cc8"),
    ("Soda", 200, "Boissons", "#e6007e"),
    ("Jus de fruit", 200, "Boissons", "#f39200"),
    ("Bière", 250, "Boissons", "#f7c600"),
    ("Sandwich", 350, "Salé", "#3aaa35"),
    ("Hot-dog", 300, "Salé", "#8fd18b"),
    ("Chips", 100, "Salé", "#fbe17a"),
    ("Crêpe", 200, "Sucré", "#f06aa9"),
    ("Gâteau", 150, "Sucré", "#6f3d96"),
    ("Bonbons", 50, "Sucré", "#a685c4"),
]


def assombrir(couleur, facteur=0.85):
    r, g, b = (int(couleur[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * facteur), int(g * facteur), int(b * facteur))


def texte_sur(couleur):
    """Couleur de texte lisible sur le fond donné."""
    r, g, b = (int(couleur[i:i + 2], 16) for i in (1, 3, 5))
    return NUIT if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


def bouton(parent, texte, commande, fond, police=None, **options):
    """Bouton plat aux couleurs de la charte, avec effet de survol."""
    fg = options.pop("fg", texte_sur(fond))
    b = tk.Button(parent, text=texte, command=commande, bg=fond, fg=fg, activebackground=assombrir(fond),
                  activeforeground=fg, disabledforeground=GRIS, relief="flat", bd=0, cursor="hand2",
                  font=police or (F_TEXTE, 11), **options)
    survol = assombrir(fond, 0.92)
    b.bind("<Enter>", lambda e: b.config(bg=survol) if str(b["state"]) != "disabled" else None)
    b.bind("<Leave>", lambda e: b.config(bg=fond))
    return b


def tronquer(texte, police, largeur):
    """Texte raccourci avec « … » pour tenir sur une ligne de la largeur donnée (pixels)."""
    if police.measure(texte) <= largeur:
        return texte
    while texte and police.measure(texte + "…") > largeur:
        texte = texte[:-1]
    return texte.rstrip() + "…"


def bandeau_couleurs(parent, hauteur=5):
    """Liseré multicolore sous les en-têtes."""
    f = tk.Frame(parent, height=hauteur, bg=NUIT)
    for c in (CYAN, MAGENTA, JAUNE, VERT, ORANGE, VIOLET):
        tk.Frame(f, bg=c, height=hauteur).pack(side="left", fill="x", expand=True)
    return f


def appliquer_styles(racine):
    s = ttk.Style(racine)
    s.theme_use("clam")
    s.configure(".", background=FOND, foreground=NUIT, font=(F_TEXTE, 10), bordercolor="#c5d9e3",
                lightcolor=FOND, darkcolor=FOND, troughcolor=FOND, focuscolor=CYAN, fieldbackground="white")
    s.configure("TButton", background=CIEL, foreground=NUIT, padding=6, borderwidth=0)
    s.map("TButton", background=[("disabled", GRIS_CLAIR), ("pressed", "#b9e0f2"), ("active", "#c9e8f6")],
          foreground=[("disabled", GRIS)])
    s.configure("Accent.TButton", background=CYAN, foreground="white", font=(F_TEXTE, 10, "bold"))
    s.map("Accent.TButton", background=[("pressed", CYAN_FONCE), ("active", CYAN_FONCE)])
    s.configure("TEntry", padding=4)
    s.configure("TCheckbutton", background=FOND)
    s.configure("TLabelframe", background=FOND, bordercolor="#c5d9e3")
    s.configure("TLabelframe.Label", background=FOND, foreground=CYAN_FONCE, font=(F_TITRE, 13))
    s.configure("Treeview", background="white", fieldbackground="white", foreground=NUIT,
                rowheight=px(28), font=(F_TEXTE, 11), borderwidth=0)
    s.map("Treeview", background=[("selected", CYAN)], foreground=[("selected", "white")])
    s.configure("Treeview.Heading", background=NUIT, foreground="white", font=(F_TITRE, 12),
                relief="flat", padding=4, borderwidth=0)
    s.map("Treeview.Heading", background=[("active", NUIT_CLAIR)])
    s.configure("Vertical.TScrollbar", background=NUIT_CLAIR, troughcolor=NUIT, arrowcolor="white",
                bordercolor=NUIT, lightcolor=NUIT_CLAIR, darkcolor=NUIT_CLAIR)
    s.map("Vertical.TScrollbar", background=[("active", CYAN)])
    s.configure("TPanedwindow", background=FOND)
    s.configure("Total.TLabel", font=(F_TITRE, 36), foreground=NUIT)
    s.configure("Rendu.TLabel", font=(F_TITRE, 20), foreground=NUIT)
    s.configure("Petit.TLabel", font=(F_TEXTE, 10), foreground=GRIS_TEXTE)


def euros(cents):
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")


def parse_euros(texte):
    """'2,50' / '2.5' / '2' -> 250 centimes. Lève ValueError si invalide."""
    texte = texte.strip().replace("€", "").replace(" ", "").replace(",", ".")
    valeur = round(float(texte) * 100)
    if valeur < 0:
        raise ValueError("montant négatif")
    return valeur


def grouper_par_categorie(lignes):
    """Lignes (dicts avec categorie/ordre/nom) -> [(categorie, [lignes])],
    catégories dans l'ordre d'affichage des produits."""
    rang = {}
    for l in lignes:
        rang[l["categorie"]] = min(rang.get(l["categorie"], l["ordre"]), l["ordre"])
    groupes = []
    for l in sorted(lignes, key=lambda l: (rang[l["categorie"]], l["categorie"], l["ordre"], l["nom"])):
        if not groupes or groupes[-1][0] != l["categorie"]:
            groupes.append((l["categorie"], []))
        groupes[-1][1].append(l)
    return groupes


# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------
class Base:
    def __init__(self, chemin):
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        self.cx = sqlite3.connect(chemin)
        self.cx.row_factory = sqlite3.Row
        self.cx.execute("PRAGMA foreign_keys = ON")
        self._creer()

    def _creer(self):
        self.cx.executescript(
            """
            CREATE TABLE IF NOT EXISTS produit (
                id        INTEGER PRIMARY KEY,
                nom       TEXT    NOT NULL,
                prix      INTEGER NOT NULL,
                categorie TEXT    NOT NULL DEFAULT '',
                couleur   TEXT    NOT NULL DEFAULT '#90a4ae',
                ordre     INTEGER NOT NULL DEFAULT 0,
                actif     INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS vente (
                id     INTEGER PRIMARY KEY,
                date   TEXT    NOT NULL,
                total  INTEGER NOT NULL,
                recu   INTEGER NOT NULL,
                rendu  INTEGER NOT NULL,
                annule INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS ligne (
                id       INTEGER PRIMARY KEY,
                vente_id INTEGER NOT NULL REFERENCES vente(id),
                produit  TEXT    NOT NULL,
                prix     INTEGER NOT NULL,
                qte      INTEGER NOT NULL
            );
            """
        )
        # Colonnes ajoutées avec la gestion des commandes (migration des anciennes bases)
        self._colonne("vente", "numero", "INTEGER NOT NULL DEFAULT 0")
        self._colonne("vente", "statut", "TEXT NOT NULL DEFAULT 'terminee'")
        self._colonne("ligne", "produit_id", "INTEGER")
        self._colonne("ligne", "categorie", "TEXT NOT NULL DEFAULT ''")
        self._colonne("ligne", "ordre", "INTEGER NOT NULL DEFAULT 0")
        self._colonne("ligne", "livre", "INTEGER NOT NULL DEFAULT 0")
        self._colonne("produit", "lie", "TEXT NOT NULL DEFAULT ''")   # nom du produit ajouté avec (consigne…)
        if self._colonne("vente", "encaisse", "INTEGER NOT NULL DEFAULT 0"):
            # Avant cette colonne, toute vente était encaissée à la validation
            self.cx.execute("UPDATE vente SET encaisse = 1")
        if self.cx.execute("SELECT COUNT(*) FROM produit").fetchone()[0] == 0:
            self.cx.executemany(
                "INSERT INTO produit (nom, prix, categorie, couleur, ordre) VALUES (?, ?, ?, ?, ?)",
                [(n, p, c, col, i + 1) for i, (n, p, c, col) in enumerate(PRODUITS_DEFAUT)],
            )
        self._renumeroter()
        # Ancienne palette -> couleurs de la charte
        self.cx.executemany("UPDATE produit SET couleur = ? WHERE couleur = ?",
                            list(zip(COULEURS_PRODUITS, ANCIENNES_COULEURS)))
        self.cx.commit()

    def _colonne(self, table, colonne, definition):
        existantes = {r[1] for r in self.cx.execute(f"PRAGMA table_info({table})")}
        if colonne in existantes:
            return False
        self.cx.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {definition}")
        return True

    # Produits
    def produits(self, actifs_seuls=True):
        sql = "SELECT * FROM produit"
        if actifs_seuls:
            sql += " WHERE actif = 1"
        return self.cx.execute(sql + " ORDER BY ordre, nom").fetchall()

    def _renumeroter(self, pid=None, position=None):
        """Ordres consécutifs 1..n ; le produit pid est placé à la position demandée,
        les autres se décalent."""
        ids = [r["id"] for r in self.cx.execute("SELECT id FROM produit ORDER BY ordre, nom")
               if r["id"] != pid]
        if pid is not None:
            ids.insert(min(max(position, 1), len(ids) + 1) - 1, pid)
        self.cx.executemany("UPDATE produit SET ordre = ? WHERE id = ?",
                            [(i + 1, x) for i, x in enumerate(ids)])

    def produit_par_nom(self, nom):
        if not nom:
            return None
        return self.cx.execute("SELECT * FROM produit WHERE nom = ? COLLATE NOCASE ORDER BY actif DESC LIMIT 1",
                               (nom.strip(),)).fetchone()

    def enregistrer_produit(self, pid, nom, prix, categorie, couleur, ordre, actif, lie=""):
        if pid is None:
            pid = self.cx.execute(
                "INSERT INTO produit (nom, prix, categorie, couleur, ordre, actif, lie) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nom, prix, categorie, couleur, ordre, actif, lie),
            ).lastrowid
        else:
            ancien = self.cx.execute("SELECT nom FROM produit WHERE id = ?", (pid,)).fetchone()["nom"]
            self.cx.execute(
                "UPDATE produit SET nom=?, prix=?, categorie=?, couleur=?, actif=?, lie=? WHERE id=?",
                (nom, prix, categorie, couleur, actif, lie, pid),
            )
            if ancien != nom:  # renommage : les liens vers ce produit suivent
                self.cx.execute("UPDATE produit SET lie = ? WHERE lie = ? COLLATE NOCASE", (nom, ancien))
        self._renumeroter(pid, ordre)
        self.cx.commit()
        return pid

    def importer_produits(self, produits, remplacer):
        """produits : dicts nom/prix/categorie/couleur/ordre/actif/lie (déjà validés).
        remplacer=True : les produits absents du fichier sont supprimés.
        Retourne la liste des liens ignorés (produit lié introuvable)."""
        with self.cx:
            if remplacer:
                self.cx.execute("DELETE FROM produit")
            for p in produits:
                existant = self.produit_par_nom(p["nom"])
                defaut = existant or {"categorie": "", "couleur": COULEURS_PRODUITS[-1], "actif": 1,
                                      "ordre": 10000 + p["ligne"]}
                v = {k: defaut[k] if p[k] is None else p[k] for k in ("categorie", "couleur", "actif", "ordre")}
                if existant is None:
                    self.cx.execute(
                        "INSERT INTO produit (nom, prix, categorie, couleur, ordre, actif) VALUES (?, ?, ?, ?, ?, ?)",
                        (p["nom"], p["prix"], v["categorie"], v["couleur"], v["ordre"], v["actif"]))
                else:
                    self.cx.execute(
                        "UPDATE produit SET nom=?, prix=?, categorie=?, couleur=?, ordre=?, actif=? WHERE id=?",
                        (p["nom"], p["prix"], v["categorie"], v["couleur"], v["ordre"], v["actif"], existant["id"]))
            # Liens résolus une fois tous les produits présents
            ignores = []
            for p in produits:
                if p["lie"] is None:
                    continue  # colonne absente : lien existant conservé
                cible = self.produit_par_nom(p["lie"]) if p["lie"] else None
                if p["lie"] and (cible is None or cible["nom"].lower() == p["nom"].lower()):
                    ignores.append(f"{p['nom']} → {p['lie']}")
                    cible = None
                self.cx.execute("UPDATE produit SET lie = ? WHERE nom = ? COLLATE NOCASE",
                                (cible["nom"] if cible else "", p["nom"]))
            self._renumeroter()
        return ignores

    def supprimer_produit(self, pid):
        self.cx.execute("DELETE FROM produit WHERE id=?", (pid,))
        self._renumeroter()
        self.cx.commit()

    # Commandes
    def _inserer_lignes(self, vente_id, lignes, livres=None):
        livres = livres or {}
        self.cx.executemany(
            "INSERT INTO ligne (vente_id, produit_id, produit, prix, qte, categorie, ordre, livre)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(vente_id, l["id"], l["nom"], l["prix"], l["qte"], l["categorie"], l["ordre"],
              livres.get((l["id"], l["nom"], l["prix"], l["qte"]), 0)) for l in lignes],
        )

    def creer_commande(self, lignes):
        maintenant = datetime.now().isoformat(timespec="seconds")
        numero = self.cx.execute(
            "SELECT COALESCE(MAX(numero), 0) + 1 FROM vente WHERE substr(date, 1, 10) = ?",
            (maintenant[:10],),
        ).fetchone()[0]
        total = sum(l["prix"] * l["qte"] for l in lignes)
        cur = self.cx.execute(
            "INSERT INTO vente (date, numero, statut, total, recu, rendu, encaisse)"
            " VALUES (?, ?, 'en_cours', ?, 0, 0, 0)",
            (maintenant, numero, total),
        )
        self._inserer_lignes(cur.lastrowid, lignes)
        self.cx.commit()
        return cur.lastrowid

    def modifier_commande(self, vente_id, lignes):
        """Remplace les lignes et efface l'encaissement éventuel."""
        # Une ligne déjà livrée le reste si elle n'a pas changé
        livres = {(l["produit_id"], l["produit"], l["prix"], l["qte"]): l["livre"]
                  for l in self.lignes_vente(vente_id)}
        self.cx.execute("DELETE FROM ligne WHERE vente_id = ?", (vente_id,))
        self._inserer_lignes(vente_id, lignes, livres)
        total = sum(l["prix"] * l["qte"] for l in lignes)
        self.cx.execute(
            "UPDATE vente SET total = ?, recu = 0, rendu = 0, encaisse = 0 WHERE id = ?",
            (total, vente_id),
        )
        self.cx.commit()

    def encaisser_commande(self, vente_id, recu):
        self.cx.execute(
            "UPDATE vente SET recu = ?, rendu = ? - total, encaisse = 1 WHERE id = ?",
            (recu, recu, vente_id),
        )
        self.cx.commit()

    def commande(self, vente_id):
        return self.cx.execute("SELECT * FROM vente WHERE id = ?", (vente_id,)).fetchone()

    def commandes_en_cours(self):
        return self.cx.execute(
            "SELECT * FROM vente WHERE statut = 'en_cours' AND annule = 0 ORDER BY date, numero"
        ).fetchall()

    def lignes_vente(self, vente_id):
        return self.cx.execute(
            "SELECT * FROM ligne WHERE vente_id = ? ORDER BY id", (vente_id,)
        ).fetchall()

    def basculer_livraison(self, ligne_id):
        self.cx.execute("UPDATE ligne SET livre = 1 - livre WHERE id = ?", (ligne_id,))
        self.cx.commit()

    def terminer_commande(self, vente_id):
        self.cx.execute("UPDATE vente SET statut = 'terminee' WHERE id = ?", (vente_id,))
        self.cx.commit()

    def remettre_en_cours(self, vente_id):
        self.cx.execute("UPDATE vente SET statut = 'en_cours', annule = 0 WHERE id = ?", (vente_id,))
        self.cx.commit()

    def annuler_vente(self, vente_id):
        self.cx.execute("UPDATE vente SET annule = 1 WHERE id = ?", (vente_id,))
        self.cx.commit()

    # Historique
    def ventes_du_jour(self, jour):
        return self.cx.execute(
            "SELECT * FROM vente WHERE substr(date, 1, 10) = ? ORDER BY date DESC",
            (jour,),
        ).fetchall()

    def recap_jour(self, jour):
        return self.cx.execute(
            """
            SELECT l.produit, SUM(l.qte) AS qte, SUM(l.qte * l.prix) AS montant
            FROM ligne l JOIN vente v ON v.id = l.vente_id
            WHERE substr(v.date, 1, 10) = ? AND v.annule = 0
            GROUP BY l.produit ORDER BY montant DESC
            """,
            (jour,),
        ).fetchall()


# ---------------------------------------------------------------------------
# Boîtes de dialogue aux couleurs de l'application (saisie et suivi des commandes)
# ---------------------------------------------------------------------------
class Dialogue(tk.Toplevel):
    """Question ou information en grand. boutons : [(texte, valeur, couleur)] de gauche à droite ;
    Entrée = dernier bouton (action principale), Échap = fermer sans choix (resultat None)."""

    def __init__(self, parent, titre, message, boutons, saisie_masquee=False):
        super().__init__(parent)
        icone_au_affichage(self)
        self.title(titre)
        self.configure(bg="white")
        self.resizable(False, False)
        self.transient(parent)
        self.resultat = None

        bandeau_couleurs(self).pack(fill="x")
        corps = tk.Frame(self, bg="white", padx=px(22), pady=px(16))
        corps.pack(fill="both", expand=True)
        tk.Label(corps, text=titre.upper(), font=(F_TITRE, 20), fg=NUIT, bg="white", anchor="w").pack(fill="x")
        tk.Label(corps, text=message, font=(F_TEXTE, 12), fg=NUIT, bg="white", anchor="w", justify="left",
                 wraplength=px(440)).pack(fill="x", pady=(px(6), px(18)))
        self.var_saisie = tk.StringVar()
        self.saisie_masquee = saisie_masquee
        if saisie_masquee:
            champ = ttk.Entry(corps, textvariable=self.var_saisie, show="•", font=(F_TEXTE, 14))
            champ.pack(fill="x", pady=(0, px(18)))
            self.after_idle(champ.focus_set)
        tk.Frame(corps, width=px(380), height=0, bg="white").pack()   # largeur minimale
        bas = tk.Frame(corps, bg="white")
        bas.pack(anchor="e")
        for i, (texte, valeur, couleur) in enumerate(boutons):
            bouton(bas, texte, lambda v=valeur: self._fermer(v), couleur, police=(F_TITRE, 14),
                   padx=px(18), pady=px(5)).pack(side="left", padx=(px(8) if i else 0, 0))

        defaut = boutons[-1][1]
        self.bind("<Return>", lambda e: self._fermer(defaut))
        self.bind("<KP_Enter>", lambda e: self._fermer(defaut))
        self.bind("<Escape>", lambda e: self._fermer(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self._fermer(None))

        # Centrée sur la fenêtre parente
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        precedent = self.grab_current()      # fenêtre modale en dessous (saisie, encaissement…)
        self.grab_set()
        self.focus_force()
        if saisie_masquee:
            champ.focus_set()
        self.wait_window()
        if precedent is not None and precedent.winfo_exists():
            precedent.grab_set()

    def _fermer(self, valeur):
        # Avec un champ de saisie : resultat = texte saisi si validé, None sinon
        self.resultat = self.var_saisie.get() if self.saisie_masquee and valeur is True else valeur
        if self.saisie_masquee and valeur is not True:
            self.resultat = None
        self.destroy()


def demander(parent, titre, message, oui="OUI", non="NON", couleur_oui=VERT):
    return Dialogue(parent, titre, message, [(non, False, NUIT_CLAIR), (oui, True, couleur_oui)]).resultat is True


def informer(parent, titre, message):
    Dialogue(parent, titre, message, [("OK", True, CYAN)])


# ---------------------------------------------------------------------------
# Fenêtre d'encaissement
# ---------------------------------------------------------------------------
class Encaissement(tk.Toplevel):
    def __init__(self, parent, total, libelle="À payer"):
        super().__init__(parent)
        icone_au_affichage(self)
        self.title("Encaisser")
        self.configure(bg=FOND)
        self.resizable(False, False)
        self.transient(parent)
        self.total = total
        self.resultat = None

        bandeau_couleurs(self).pack(fill="x")
        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)
        f.columnconfigure((0, 1, 2, 3), weight=1, uniform="billet")

        ttk.Label(f, text=libelle.upper(), style="Petit.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(f, text=euros(total), style="Total.TLabel").grid(row=1, column=0, columnspan=4, sticky="w")

        ttk.Label(f, text="Montant reçu", style="Petit.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.var_recu = tk.StringVar()
        self.var_recu.trace_add("write", lambda *_: self._maj())
        saisie = ttk.Entry(f, textvariable=self.var_recu, font=(F_TITRE, 24), width=10, justify="right")
        saisie.grid(row=3, column=0, columnspan=4, sticky="we")
        saisie.focus_set()

        billets = [("Compte juste", total), ("+0,50", 50), ("+1", 100), ("+2", 200),
                   ("+5", 500), ("+10", 1000), ("+20", 2000), ("+50", 5000)]
        for i, (lib, val) in enumerate(billets):
            b = bouton(f, lib, (lambda v=val, l=lib: self._ajouter(v, l == "Compte juste")),
                       JAUNE if i == 0 else CIEL, police=(F_TITRE, 15), pady=6)
            b.grid(row=4 + i // 4, column=i % 4, sticky="we", padx=2, pady=2)
        ttk.Button(f, text="Effacer", command=lambda: self.var_recu.set("")).grid(
            row=6, column=0, columnspan=4, sticky="we", pady=(2, 0))

        ttk.Label(f, text="À rendre", style="Petit.TLabel").grid(row=7, column=0, sticky="w", pady=(12, 0))
        self.lbl_rendu = ttk.Label(f, text="-", style="Rendu.TLabel")
        self.lbl_rendu.grid(row=8, column=0, columnspan=4, sticky="w")

        bas = ttk.Frame(f)
        bas.grid(row=9, column=0, columnspan=4, sticky="e", pady=(16, 0))
        bouton(bas, "VALIDER  (Entrée)", self._valider, VERT, police=(F_TITRE, 14), padx=14, pady=6).pack(
            side="right", padx=(6, 0))
        bouton(bas, "ANNULER", self.destroy, NUIT_CLAIR, police=(F_TITRE, 14), padx=14, pady=6).pack(
            side="right")

        self.bind("<Return>", lambda e: self._valider())
        self.bind("<Escape>", lambda e: self.destroy())
        self._maj()
        restaurer_position(self, "encaissement", taille=False)
        self.grab_set()
        self.wait_window()

    def destroy(self):
        memoriser_position(self, "encaissement")
        super().destroy()

    def _lire_recu(self):
        if not self.var_recu.get().strip():
            return 0
        return parse_euros(self.var_recu.get())

    def _ajouter(self, valeur, remplacer):
        try:
            base = 0 if remplacer else self._lire_recu()
        except ValueError:
            base = 0
        self.var_recu.set(f"{(base + valeur) / 100:.2f}".replace(".", ","))

    def _maj(self):
        try:
            recu = self._lire_recu()
        except ValueError:
            self.lbl_rendu.config(text="Montant invalide", foreground=MAGENTA)
            return
        if recu == 0:
            self.lbl_rendu.config(text="-", foreground="")
        elif recu < self.total:
            self.lbl_rendu.config(text=f"Manque {euros(self.total - recu)}", foreground=MAGENTA)
        else:
            self.lbl_rendu.config(text=euros(recu - self.total), foreground=VERT_FONCE)

    def _valider(self):
        try:
            recu = self._lire_recu()
        except ValueError:
            informer(self, "Encaisser", "Le montant reçu est invalide.")
            return
        if recu == 0:
            recu = self.total  # pas de saisie = compte juste
        if recu < self.total:
            informer(self, "Encaisser", "Le montant reçu est insuffisant.")
            return
        self.resultat = recu
        self.destroy()


# ---------------------------------------------------------------------------
# Import / export CSV des produits (séparateur « ; », ouvrable dans Excel)
# ---------------------------------------------------------------------------
COLONNES_CSV = ["Nom", "Prix", "Catégorie", "Ordre", "Actif", "Couleur", "Lié à"]


def exporter_produits_csv(base, chemin):
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLONNES_CSV)
        for p in base.produits(actifs_seuls=False):
            w.writerow([p["nom"], f"{p['prix'] / 100:.2f}".replace(".", ","), p["categorie"], p["ordre"],
                        "oui" if p["actif"] else "non", p["couleur"], p["lie"]])


def _cle(texte):
    """En-tête normalisé : minuscules, sans accents ni espaces."""
    import unicodedata
    t = unicodedata.normalize("NFD", texte.strip().lower())
    return "".join(c for c in t if c.isalnum())


def lire_produits_csv(chemin):
    """Retourne (produits, erreurs). Accepte « ; », « , » ou tabulation, UTF-8 ou ANSI (Excel)."""
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            with open(chemin, encoding=encodage) as f:
                texte = f.read()
            break
        except UnicodeDecodeError:
            continue
    try:
        dialecte = csv.Sniffer().sniff(texte[:2048], delimiters=";,\t")
    except csv.Error:
        dialecte = csv.excel
        dialecte.delimiter = ";"
    lignes = list(csv.reader(texte.splitlines(), dialecte))
    if not lignes:
        return [], ["Le fichier est vide."]
    entetes = {_cle(e): i for i, e in enumerate(lignes[0])}
    colonnes = {"nom": "nom", "prix": "prix", "categorie": "categorie", "ordre": "ordre",
                "actif": "actif", "couleur": "couleur", "lie": "lie", "liea": "lie"}
    index = {colonnes[k]: i for k, i in entetes.items() if k in colonnes}
    if "nom" not in index or "prix" not in index:
        return [], ["Colonnes « Nom » et « Prix » obligatoires dans la première ligne."]

    produits, erreurs, vus = [], [], set()
    for n, ligne in enumerate(lignes[1:], start=2):
        if not any(c.strip() for c in ligne):
            continue
        val = lambda col, defaut="": ligne[index[col]].strip() if col in index and index[col] < len(ligne) else defaut
        nom = val("nom")
        if not nom:
            erreurs.append(f"Ligne {n} : nom vide.")
            continue
        if nom.lower() in vus:
            erreurs.append(f"Ligne {n} : « {nom} » en double.")
            continue
        vus.add(nom.lower())
        try:
            prix = parse_euros(val("prix"))
        except ValueError:
            erreurs.append(f"Ligne {n} : prix invalide « {val('prix')} ».")
            continue
        try:
            ordre = int(val("ordre")) if val("ordre") else None
        except ValueError:
            ordre = None
        couleur = val("couleur").lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", couleur):
            couleur = None
        actif = None
        if val("actif"):
            actif = int(_cle(val("actif")) not in ("non", "0", "n", "false", "faux", "inactif"))
        # None : colonne absente ou vide -> valeur existante conservée (ou valeur par défaut si nouveau)
        produits.append({"nom": nom, "prix": prix,
                         "categorie": val("categorie") if "categorie" in index else None,
                         "couleur": couleur, "ordre": ordre, "actif": actif,
                         "lie": val("lie") if "lie" in index else None, "ligne": n})
    return produits, erreurs


# ---------------------------------------------------------------------------
# Gestion des produits
# ---------------------------------------------------------------------------
class GestionProduits(tk.Toplevel):
    COULEURS = COULEURS_PRODUITS

    def __init__(self, parent, base):
        super().__init__(parent)
        icone_au_affichage(self)
        self.title("Produits")
        self.configure(bg=FOND)
        self.geometry(f"{px(900)}x{px(720)}")
        self.transient(parent)
        self.base = base
        self.pid = None

        gauche = ttk.Frame(self, padding=8)
        gauche.pack(side="left", fill="both", expand=True)
        cols = ("nom", "prix", "categorie", "ordre", "actif", "lie")
        self.tree = ttk.Treeview(gauche, columns=cols, show="headings", selectmode="browse")
        for c, lib, w in zip(cols, ("Nom", "Prix", "Catégorie", "Ordre", "Actif", "Lié à"),
                             (170, 70, 120, 50, 50, 110)):
            self.tree.heading(c, text=lib)
            self.tree.column(c, width=px(w), anchor="e" if c in ("prix", "ordre") else "w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._selection)

        droite = ttk.Frame(self, padding=8)
        droite.pack(side="right", fill="y")
        self.v_nom = tk.StringVar()
        self.v_prix = tk.StringVar()
        self.v_cat = tk.StringVar()
        self.v_ordre = tk.StringVar(value="0")
        self.v_actif = tk.BooleanVar(value=True)
        self.v_couleur = tk.StringVar(value=self.COULEURS[-1])
        self.v_lie = tk.StringVar()
        for i, (lib, var) in enumerate((("Nom", self.v_nom), ("Prix (€)", self.v_prix),
                                        ("Catégorie", self.v_cat), ("Ordre", self.v_ordre))):
            ttk.Label(droite, text=lib).grid(row=i * 2, column=0, sticky="w")
            ttk.Entry(droite, textvariable=var, width=24).grid(row=i * 2 + 1, column=0, sticky="we", pady=(0, 6))
        ttk.Label(droite, text="Produit lié (ajouté avec, ex. consigne)").grid(row=8, column=0, sticky="w")
        self.cb_lie = ttk.Combobox(droite, textvariable=self.v_lie, width=22)
        self.cb_lie.grid(row=9, column=0, sticky="we", pady=(0, 6))
        ttk.Checkbutton(droite, text="Actif (visible en caisse)", variable=self.v_actif).grid(row=10, column=0, sticky="w")

        ttk.Label(droite, text="Couleur").grid(row=11, column=0, sticky="w", pady=(6, 0))
        palette = ttk.Frame(droite)
        palette.grid(row=12, column=0, sticky="w")
        self.apercu = tk.Label(droite, text="Aperçu", width=20, height=2, font=(F_TITRE, 14))
        for i, c in enumerate(self.COULEURS):
            tk.Button(palette, bg=c, activebackground=c, width=2, relief="flat", cursor="hand2",
                      command=lambda c=c: self._couleur(c)).grid(row=i // 5, column=i % 5, padx=1, pady=1)
        self.apercu.grid(row=13, column=0, pady=6)

        btns = ttk.Frame(droite)
        btns.grid(row=14, column=0, sticky="we", pady=(8, 0))
        ttk.Button(btns, text="Nouveau", command=self._nouveau).pack(fill="x", pady=1)
        ttk.Button(btns, text="Enregistrer", style="Accent.TButton", command=self._enregistrer).pack(fill="x", pady=1)
        ttk.Button(btns, text="Supprimer", command=self._supprimer).pack(fill="x", pady=1)
        ttk.Button(btns, text="Importer CSV…", command=self._importer).pack(fill="x", pady=(12, 1))
        ttk.Button(btns, text="Exporter CSV…", command=self._exporter).pack(fill="x", pady=1)
        ttk.Button(btns, text="Fermer", command=self.destroy).pack(fill="x", pady=(12, 1))

        self._couleur(self.v_couleur.get())
        self._charger()
        self._nouveau()
        restaurer_position(self, "produits")
        self.grab_set()

    def destroy(self):
        memoriser_position(self, "produits")
        super().destroy()

    def _couleur(self, c):
        self.v_couleur.set(c)
        self.apercu.config(bg=c, fg=texte_sur(c))

    def _charger(self):
        self.tree.delete(*self.tree.get_children())
        produits = self.base.produits(actifs_seuls=False)
        for p in produits:
            self.tree.insert("", "end", iid=str(p["id"]),
                             values=(p["nom"], euros(p["prix"]), p["categorie"], p["ordre"],
                                     "oui" if p["actif"] else "non", p["lie"]))
        self.cb_lie["values"] = [""] + [p["nom"] for p in produits]

    def _selection(self, _):
        sel = self.tree.selection()
        if not sel:
            return
        p = next(x for x in self.base.produits(actifs_seuls=False) if x["id"] == int(sel[0]))
        self.pid = p["id"]
        self.v_nom.set(p["nom"])
        self.v_prix.set(f"{p['prix'] / 100:.2f}".replace(".", ","))
        self.v_cat.set(p["categorie"])
        self.v_ordre.set(str(p["ordre"]))
        self.v_actif.set(bool(p["actif"]))
        self.v_lie.set(p["lie"])
        self._couleur(p["couleur"])

    def _nouveau(self):
        self.pid = None
        self.tree.selection_remove(*self.tree.selection())
        for v in (self.v_nom, self.v_prix, self.v_cat, self.v_lie):
            v.set("")
        self.v_ordre.set(str(len(self.tree.get_children()) + 1))
        self.v_actif.set(True)

    def _enregistrer(self):
        nom = self.v_nom.get().strip()
        if not nom:
            informer(self, "Produits", "Le nom est obligatoire.")
            return
        try:
            prix = parse_euros(self.v_prix.get())
            ordre = int(self.v_ordre.get() or 0)
        except ValueError:
            informer(self, "Produits", "Prix ou ordre invalide.")
            return
        lie = self.v_lie.get().strip()
        if lie:
            cible = self.base.produit_par_nom(lie)
            if cible is None:
                informer(self, "Produits", f"Produit lié « {lie} » introuvable.")
                return
            if lie.lower() == nom.lower():
                informer(self, "Produits", "Un produit ne peut pas être lié à lui-même.")
                return
            lie = cible["nom"]
        self.pid = self.base.enregistrer_produit(self.pid, nom, prix, self.v_cat.get().strip(),
                                                 self.v_couleur.get(), ordre, int(self.v_actif.get()), lie)
        self._charger()
        self.tree.selection_set(str(self.pid))
        self.tree.see(str(self.pid))

    def _exporter(self):
        chemin = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialdir=DATA_DIR,
                                              initialfile="produits.csv", filetypes=[("CSV", "*.csv")])
        if not chemin:
            return
        try:
            exporter_produits_csv(self.base, chemin)
        except OSError as e:
            informer(self, "Exporter", f"Impossible d'écrire le fichier :\n{e}")
            return
        informer(self, "Exporter", f"Produits exportés :\n{chemin}")

    def _importer(self):
        chemin = filedialog.askopenfilename(parent=self, initialdir=DATA_DIR,
                                            filetypes=[("CSV", "*.csv"), ("Tous les fichiers", "*.*")])
        if not chemin:
            return
        try:
            produits, erreurs = lire_produits_csv(chemin)
        except OSError as e:
            informer(self, "Importer", f"Impossible de lire le fichier :\n{e}")
            return
        if erreurs:
            liste = "\n".join(erreurs[:15]) + ("\n…" if len(erreurs) > 15 else "")
            informer(self, "Importer", f"Import annulé, le fichier contient des erreurs :\n\n{liste}")
            return
        if not produits:
            informer(self, "Importer", "Aucun produit dans le fichier.")
            return
        choix = Dialogue(
            self, "Importer", f"{len(produits)} produits dans le fichier.\n\n"
            "Remplacer : toute la liste est remplacée (les produits absents du fichier sont supprimés).\n"
            "Mettre à jour : les produits de même nom sont mis à jour, les nouveaux ajoutés.",
            [("ANNULER", None, NUIT_CLAIR), ("REMPLACER", True, MAGENTA), ("METTRE À JOUR", False, VERT)]).resultat
        if choix is None:
            return
        ignores = self.base.importer_produits(produits, remplacer=choix)
        self._nouveau()
        self._charger()
        message = f"{len(produits)} produits importés."
        if ignores:
            message += "\n\nProduits liés introuvables (lien retiré) :\n" + "\n".join(ignores)
        informer(self, "Importer", message)

    def _supprimer(self):
        if self.pid is None:
            return
        if demander(self, "Supprimer", f"Supprimer « {self.v_nom.get()} » ?\n"
                    "(l'historique des ventes est conservé)", oui="SUPPRIMER", non="GARDER", couleur_oui=MAGENTA):
            self.base.supprimer_produit(self.pid)
            self._nouveau()
            self._charger()


# ---------------------------------------------------------------------------
# Historique / récapitulatif du jour
# ---------------------------------------------------------------------------
class Historique(tk.Toplevel):
    def __init__(self, parent, base):
        super().__init__(parent)
        icone_au_affichage(self)
        self.title("Historique des commandes")
        self.configure(bg=FOND)
        self.geometry(f"{px(960)}x{px(560)}")
        self.transient(parent)
        self.base = base

        haut = ttk.Frame(self, padding=8)
        haut.pack(fill="x")
        ttk.Label(haut, text="Jour (AAAA-MM-JJ) :").pack(side="left")
        self.v_jour = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(haut, textvariable=self.v_jour, width=12).pack(side="left", padx=4)
        ttk.Button(haut, text="Afficher", command=self._charger).pack(side="left")
        ttk.Button(haut, text="Exporter CSV", command=self._exporter).pack(side="right")
        ttk.Button(haut, text="Annuler la commande", command=self._annuler).pack(side="right", padx=4)
        ttk.Button(haut, text="Remettre en cours", style="Accent.TButton",
                   command=self._remettre).pack(side="right", padx=4)

        corps = ttk.PanedWindow(self, orient="horizontal")
        corps.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        g = ttk.Labelframe(corps, text="Commandes", padding=4)
        self.t_ventes = ttk.Treeview(g, columns=("numero", "heure", "total", "recu", "rendu", "etat"),
                                     show="headings", selectmode="browse")
        for c, lib, w in (("numero", "N°", 50), ("heure", "Heure", 60), ("total", "Total", 80),
                          ("recu", "Reçu", 80), ("rendu", "Rendu", 80), ("etat", "État", 80)):
            self.t_ventes.heading(c, text=lib)
            self.t_ventes.column(c, width=px(w), anchor="e" if c in ("numero", "total", "recu", "rendu") else "w")
        self.t_ventes.tag_configure("annule", foreground="#9e9e9e")
        self.t_ventes.pack(fill="both", expand=True)
        self.t_ventes.bind("<<TreeviewSelect>>", self._detail)
        self.t_detail = ttk.Treeview(g, columns=("produit", "qte", "montant", "livre"), show="headings", height=5)
        for c, lib, w in (("produit", "Produit", 180), ("qte", "Qté", 50), ("montant", "Montant", 80),
                          ("livre", "Livré", 50)):
            self.t_detail.heading(c, text=lib)
            self.t_detail.column(c, width=px(w), anchor="w" if c in ("produit", "livre") else "e")
        self.t_detail.pack(fill="x", pady=(6, 0))
        corps.add(g, weight=3)

        d = ttk.Labelframe(corps, text="Récapitulatif par produit", padding=4)
        self.t_recap = ttk.Treeview(d, columns=("produit", "qte", "montant"), show="headings")
        for c, lib, w in (("produit", "Produit", 160), ("qte", "Qté", 50), ("montant", "Montant", 90)):
            self.t_recap.heading(c, text=lib)
            self.t_recap.column(c, width=px(w), anchor="w" if c == "produit" else "e")
        self.t_recap.pack(fill="both", expand=True)
        self.lbl_total = ttk.Label(d, style="Rendu.TLabel")
        self.lbl_total.pack(anchor="e", pady=(6, 0))
        corps.add(d, weight=2)

        self._charger()
        restaurer_position(self, "historique")

    def destroy(self):
        memoriser_position(self, "historique")
        super().destroy()

    def _charger(self):
        jour = self.v_jour.get().strip()
        self.t_ventes.delete(*self.t_ventes.get_children())
        self.t_detail.delete(*self.t_detail.get_children())
        ventes = self.base.ventes_du_jour(jour)
        for v in ventes:
            etat = "annulée" if v["annule"] else ("en cours" if v["statut"] == "en_cours" else "terminée")
            self.t_ventes.insert("", "end", iid=str(v["id"]),
                                 values=(f"{v['numero']:03d}", v["date"][11:16], euros(v["total"]),
                                         euros(v["recu"]) if v["encaisse"] else "non encaissé",
                                         euros(v["rendu"]) if v["encaisse"] else "", etat),
                                 tags=("annule",) if v["annule"] else ())
        self.t_recap.delete(*self.t_recap.get_children())
        total = nb = 0
        for r in self.base.recap_jour(jour):
            self.t_recap.insert("", "end", values=(r["produit"], r["qte"], euros(r["montant"])))
            total += r["montant"]
            nb += r["qte"]
        nb_ventes = sum(1 for v in ventes if not v["annule"])
        self.lbl_total.config(text=f"{nb_ventes} commandes · {nb} articles · {euros(total)}")

    def _detail(self, _):
        self.t_detail.delete(*self.t_detail.get_children())
        sel = self.t_ventes.selection()
        if sel:
            for l in self.base.lignes_vente(int(sel[0])):
                self.t_detail.insert("", "end", values=(l["produit"], l["qte"], euros(l["prix"] * l["qte"]),
                                                        "oui" if l["livre"] else ""))

    def _remettre(self):
        sel = self.t_ventes.selection()
        if not sel:
            return
        v = self.base.commande(int(sel[0]))
        if v["statut"] == "en_cours" and not v["annule"]:
            informer(self, "Remettre en cours", "Cette commande est déjà en cours.")
            return
        if demander(self, "Remettre en cours", f"Remettre la commande {v['numero']:03d} dans les "
                    "commandes en cours ?", oui="REMETTRE EN COURS", non="NON"):
            self.base.remettre_en_cours(v["id"])
            self._charger()
            self.t_ventes.selection_set(str(v["id"]))
            self.master.rafraichir(f"Commande {v['numero']:03d} remise en cours")

    def _annuler(self):
        sel = self.t_ventes.selection()
        if not sel:
            return
        if demander(self, "Annuler la commande", "Annuler cette commande ? Elle ne comptera plus dans le "
                    "récapitulatif.", oui="ANNULER LA COMMANDE", non="NON", couleur_oui=MAGENTA):
            self.base.annuler_vente(int(sel[0]))
            self._charger()
            self.master.rafraichir()

    def _exporter(self):
        jour = self.v_jour.get().strip()
        chemin = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv", initialdir=DATA_DIR,
            initialfile=f"buvette_{jour}.csv", filetypes=[("CSV", "*.csv")])
        if not chemin:
            return
        with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Produit", "Quantité", "Montant"])
            for r in self.base.recap_jour(jour):
                w.writerow([r["produit"], r["qte"], f"{r['montant'] / 100:.2f}".replace(".", ",")])
            w.writerow([])
            w.writerow(["N° commande", "Date", "Produit", "Quantité", "Prix unitaire", "Annulée"])
            for v in reversed(self.base.ventes_du_jour(jour)):
                for l in self.base.lignes_vente(v["id"]):
                    w.writerow([v["numero"], v["date"].replace("T", " "), l["produit"], l["qte"],
                                f"{l['prix'] / 100:.2f}".replace(".", ","), "oui" if v["annule"] else ""])
        informer(self, "Export", f"Fichier enregistré :\n{chemin}")


# ---------------------------------------------------------------------------
# Écran de saisie d'une commande (nouvelle ou modification)
# ---------------------------------------------------------------------------
class SaisieCommande(tk.Toplevel):
    def __init__(self, parent, base, vente_id=None):
        super().__init__(parent)
        icone_au_affichage(self)
        self.base = base
        self.vente_id = vente_id
        self.panier = []  # [{"id", "nom", "prix", "qte", "categorie", "ordre"}]
        if vente_id is not None:
            v = base.commande(vente_id)
            self.title(f"Modifier la commande {v['numero']:03d}")
            for l in base.lignes_vente(vente_id):
                self.panier.append({"id": l["produit_id"], "nom": l["produit"], "prix": l["prix"],
                                    "qte": l["qte"], "categorie": l["categorie"] or "Divers",
                                    "ordre": l["ordre"]})
        else:
            self.title("Nouvelle commande")
        self.panier_initial = [dict(l) for l in self.panier]

        self.geometry(f"{px(1100)}x{px(700)}")
        self.minsize(px(900), px(560))
        self.transient(parent)
        self._ecran()
        self._produits()
        self.maj_panier()
        self.bind("<Return>", lambda e: self.valider())
        self.bind("<KP_Enter>", lambda e: self.valider())
        self.bind("<Delete>", lambda e: self.retirer_ligne())
        self.bind("<Escape>", lambda e: self.annuler())
        self.protocol("WM_DELETE_WINDOW", self.annuler)
        restaurer_position(self, "saisie")
        self.grab_set()
        self.focus_set()

    def _ecran(self):
        self.configure(bg=NUIT)
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)
        bandeau_couleurs(self).grid(row=0, column=0, columnspan=2, sticky="we")

        self.zone_produits = tk.Frame(self, bg=NUIT, padx=10, pady=10)
        self.zone_produits.grid(row=1, column=0, sticky="nsew")

        droite = tk.Frame(self, bg="white", padx=14, pady=10)
        droite.grid(row=1, column=1, sticky="nsew")
        droite.rowconfigure(1, weight=1)
        droite.columnconfigure(0, weight=1)

        tk.Label(droite, text=self.title().upper(), font=(F_TITRE, 20), fg=NUIT, bg="white").grid(
            row=0, column=0, sticky="w")
        self.t_panier = ttk.Treeview(droite, columns=("produit", "qte", "montant"), show="headings",
                                     selectmode="browse")
        for c, lib, w in (("produit", "Produit", 200), ("qte", "Qté", 50), ("montant", "Montant", 90)):
            self.t_panier.heading(c, text=lib)
            self.t_panier.column(c, width=px(w), anchor="w" if c == "produit" else "e")
        self.t_panier.tag_configure("categorie", font=(F_TITRE, 11), foreground=CYAN_FONCE, background=CIEL)
        self.t_panier.bind("<<TreeviewSelect>>", self._sel_panier)
        self.t_panier.bind("<Double-1>", self._double_clic)
        self.t_panier.grid(row=1, column=0, sticky="nsew", pady=6)

        actions = tk.Frame(droite, bg="white")
        actions.grid(row=2, column=0, sticky="we")
        for i, (lib, cmd) in enumerate((("− 1", self.retirer_ligne), ("+ 1", self.ajouter_ligne),
                                        ("VIDER", self.vider))):
            actions.columnconfigure(i, weight=1, uniform="a")
            bouton(actions, lib, cmd, CIEL, police=(F_TITRE, 16), pady=4).grid(row=0, column=i, sticky="we", padx=2)

        self.lbl_total = tk.Label(droite, font=(F_TITRE, 40), fg=NUIT, bg="white")
        self.lbl_total.grid(row=3, column=0, sticky="e", pady=(8, 4))

        bas = tk.Frame(droite, bg="white")
        bas.grid(row=4, column=0, sticky="we")
        bas.columnconfigure(0, weight=1)
        bas.columnconfigure(1, weight=2)
        bouton(bas, "ANNULER  (Échap)", self.annuler, NUIT_CLAIR, police=(F_TITRE, 16), height=2).grid(
            row=0, column=0, sticky="we", padx=(0, 6))
        bouton(bas, "VALIDER  (Entrée)", self.valider, VERT, police=(F_TITRE, 22), height=2).grid(
            row=0, column=1, sticky="we")

    def _produits(self):
        produits = self.base.produits()
        nb_col = 4
        for c in range(nb_col):
            self.zone_produits.columnconfigure(c, weight=1, uniform="p")
        for i, p in enumerate(produits):
            r, c = divmod(i, nb_col)
            self.zone_produits.rowconfigure(r, weight=1, uniform="p")
            bouton(self.zone_produits, f"{p['nom'].upper()}\n{euros(p['prix'])}",
                   lambda p=dict(p): self.clic_produit(p), p["couleur"], police=(F_TITRE, 19),
                   wraplength=px(200)).grid(row=r, column=c, sticky="nsew", padx=5, pady=5)
        if not produits:
            tk.Label(self.zone_produits, text="Aucun produit actif.\nBouton Produits (F4) de l'écran principal.",
                     font=(F_TEXTE, 12), fg=CIEL, bg=NUIT).grid()

    # --- panier ---
    def clic_produit(self, p):
        """Bouton produit : ajoute le produit et son produit lié éventuel (consigne…).
        Dans la liste, chaque ligne se modifie ensuite indépendamment."""
        i = self._ajouter_au_panier(p)
        lie = self.base.produit_par_nom(p.get("lie", ""))
        if lie is not None and lie["id"] != p["id"]:
            self._ajouter_au_panier(dict(lie))
        self.maj_panier(selection=i)

    def ajouter(self, p):
        self.maj_panier(selection=self._ajouter_au_panier(p))

    def _ajouter_au_panier(self, p):
        for i, l in enumerate(self.panier):
            if l["id"] == p["id"] and l["prix"] == p["prix"]:
                l["qte"] += 1
                return i
        self.panier.append({"id": p["id"], "nom": p["nom"], "prix": p["prix"], "qte": 1,
                            "categorie": p["categorie"] or "Divers", "ordre": p["ordre"]})
        return len(self.panier) - 1

    def _sel_panier(self, _):
        # Un clic sur un titre de catégorie sélectionne son premier produit
        sel = self.t_panier.selection()
        if sel and sel[0].startswith("cat:"):
            suivant = self.t_panier.next(sel[0])
            if suivant:
                self.t_panier.selection_set(suivant)

    def _double_clic(self, event):
        # Double clic sur un article : -1
        ligne = self.t_panier.identify_row(event.y)
        if ligne and not ligne.startswith("cat:"):
            self.t_panier.selection_set(ligne)
            self.retirer_ligne()
        return "break"

    def _index_sel(self):
        sel = self.t_panier.selection()
        if sel and not sel[0].startswith("cat:"):
            return int(sel[0])
        return len(self.panier) - 1 if self.panier else None

    def ajouter_ligne(self):
        i = self._index_sel()
        if i is not None:
            self.panier[i]["qte"] += 1
            self.maj_panier(selection=i)

    def retirer_ligne(self):
        i = self._index_sel()
        if i is None:
            return
        self.panier[i]["qte"] -= 1
        if self.panier[i]["qte"] <= 0:
            del self.panier[i]
            i = min(i, len(self.panier) - 1) if self.panier else None
        self.maj_panier(selection=i)

    def vider(self):
        if self.panier and demander(self, "Vider", "Retirer tous les articles de la commande ?",
                                    oui="VIDER", non="GARDER", couleur_oui=MAGENTA):
            self.panier.clear()
            self.maj_panier()

    def total(self):
        return sum(l["prix"] * l["qte"] for l in self.panier)

    def maj_panier(self, selection=None):
        self.t_panier.delete(*self.t_panier.get_children())
        index = {id(l): i for i, l in enumerate(self.panier)}
        for categorie, lignes in grouper_par_categorie(self.panier):
            self.t_panier.insert("", "end", iid=f"cat:{categorie}", values=(categorie.upper(), "", ""),
                                 tags=("categorie",))
            for l in lignes:
                self.t_panier.insert("", "end", iid=str(index[id(l)]),
                                     values=(f"    {l['nom']}", l["qte"], euros(l["prix"] * l["qte"])))
        if selection is not None and selection >= 0:
            self.t_panier.selection_set(str(selection))
            self.t_panier.see(str(selection))
        self.lbl_total.config(text=euros(self.total()))

    # --- validation / abandon ---
    def valider(self):
        if self.vente_id is None:
            if not self.panier:
                return
            self.base.creer_commande(self.panier)
            self._fermer("Commande enregistrée")
            return

        if not self.panier:
            if demander(self, "Commande vide", "La commande ne contient plus aucun article.\nL'annuler ?",
                        oui="ANNULER LA COMMANDE", non="RETOUR", couleur_oui=MAGENTA):
                self.base.annuler_vente(self.vente_id)
                self._fermer("Commande annulée")
            return
        # Valider une modification efface toujours l'encaissement, même sans changement
        encaissee = self.base.commande(self.vente_id)["encaisse"]
        self.base.modifier_commande(self.vente_id, self.panier)
        self._fermer("Commande modifiée · encaissement effacé" if encaissee else "Commande modifiée")

    def annuler(self):
        modifie = self.panier != self.panier_initial
        question = "Abandonner la commande ?" if self.vente_id is None else "Abandonner les modifications ?"
        if modifie and not demander(self, "Annuler", question, oui="ABANDONNER", non="CONTINUER",
                                    couleur_oui=MAGENTA):
            return
        self.destroy()

    def destroy(self):
        memoriser_position(self, "saisie")
        super().destroy()

    def _fermer(self, message):
        self.destroy()
        self.master.rafraichir(message)


# ---------------------------------------------------------------------------
# Fenêtre principale : les commandes en cours
# ---------------------------------------------------------------------------
class Principal(tk.Tk):
    def __init__(self):
        global ECHELLE
        activer_dpi()
        super().__init__()
        ECHELLE = self.winfo_fpixels("1i") / 96
        self.LARGEUR_CARTE = px(300)
        self.title(APP_NAME)
        self.geometry(f"{px(1200)}x{px(750)}")
        self.minsize(px(700), px(500))
        if not restaurer_position(self, "principal"):
            try:
                self.state("zoomed")
            except tk.TclError:
                pass
        self.base = Base(DB_PATH)
        self.cartes = []
        self.nb_col = 0
        self._styles()
        try:
            self.iconbitmap(default=ressource("buvette.ico"))  # toutes les fenêtres
        except tk.TclError:
            pass
        icone_au_affichage(self)
        self._ecran()
        self.rafraichir()
        self.bind("<F2>", lambda e: self.nouvelle_commande())
        self.bind("<F3>", lambda e: self.historique())
        self.bind("<F4>", lambda e: self.produits())

    def _styles(self):
        appliquer_styles(self)
        self.option_add("*Toplevel.background", FOND)

    def _ecran(self):
        self.configure(bg=NUIT)
        haut = tk.Frame(self, bg=NUIT, padx=16, pady=10)
        haut.pack(fill="x")
        marque = tk.Frame(haut, bg=NUIT)
        marque.pack(side="left")
        tk.Label(marque, text="BUVETTE 3000", font=(F_TITRE, 36), fg=CYAN, bg=NUIT).pack(side="left")
        try:
            # Logo pré-calculé pour 100 %, 125 %, 150 %, 175 % et 200 %
            taille = min((78, 98, 117, 137, 156), key=lambda t: abs(t - px(78)))
            self.logo = tk.PhotoImage(file=ressource(f"logo_{taille}.png"))
            tk.Label(marque, image=self.logo, bg=NUIT).pack(side="left", padx=(14, 0))
        except tk.TclError:
            pass
        bouton(haut, "+  NOUVELLE COMMANDE  (F2)", self.nouvelle_commande, MAGENTA, police=(F_TITRE, 20),
               padx=22, pady=10).pack(side="right")
        bouton(haut, "HISTORIQUE  (F3)", self.historique, NUIT_CLAIR, police=(F_TITRE, 16),
               padx=18, pady=10).pack(side="right", padx=8)
        bouton(haut, "PRODUITS  (F4)", self.produits, NUIT_CLAIR, police=(F_TITRE, 16),
               padx=18, pady=10).pack(side="right")
        bandeau_couleurs(self).pack(fill="x")

        self.statut = tk.Label(self, anchor="w", padx=12, pady=5, font=(F_TEXTE, 10), bg=NUIT_FONCE,
                               fg="#9fc3d3")
        self.statut.pack(side="bottom", fill="x")

        tk.Label(self, text="COMMANDES EN COURS", font=(F_TITRE, 15), fg=CYAN, bg=NUIT, anchor="w",
                 padx=18).pack(fill="x", pady=(10, 0))
        cadre = tk.Frame(self, bg=NUIT, padx=10, pady=4)
        cadre.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(cadre, highlightthickness=0, bg=NUIT)
        barre = ttk.Scrollbar(cadre, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=barre.set)
        barre.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.tableau = tk.Frame(self.canvas, bg=NUIT)
        self.fen_tableau = self.canvas.create_window((0, 0), window=self.tableau, anchor="nw")
        self.tableau.bind("<Configure>", lambda e: self._maj_defilement())
        self.canvas.bind("<Configure>", self._redimensionner)
        self.bind_all("<MouseWheel>", self._molette)

    def _deborde(self):
        return self.tableau.winfo_reqheight() > self.canvas.winfo_height()

    def _maj_defilement(self):
        # Zone de défilement jamais plus petite que la zone visible : pas de vide au-dessus des cartes
        hauteur = max(self.tableau.winfo_reqheight(), self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), hauteur))
        if not self._deborde():
            self.canvas.yview_moveto(0)

    def _molette(self, event):
        if str(event.widget).startswith(str(self.canvas)) and self._deborde():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _redimensionner(self, event):
        self.canvas.itemconfigure(self.fen_tableau, width=event.width)
        nb_col = max(1, event.width // (self.LARGEUR_CARTE + px(12)))
        if nb_col != self.nb_col:
            self.nb_col = nb_col
            self._placer_cartes()
        self._maj_defilement()

    def _placer_cartes(self):
        for i, carte in enumerate(self.cartes):
            carte.grid(row=i // max(self.nb_col, 1), column=i % max(self.nb_col, 1),
                       sticky="nw", padx=6, pady=6)

    # --- cartes de commande ---
    def rafraichir(self, message=""):
        for carte in self.cartes:
            carte.destroy()
        self.cartes = [self._carte(v) for v in self.base.commandes_en_cours()]
        if not self.cartes:
            vide = tk.Label(self.tableau, text="Aucune commande en cours.\nF2 pour en saisir une.",
                            font=(F_TEXTE, 14), fg="#7fa7b8", bg=NUIT, justify="left")
            self.cartes.append(vide)
        self._placer_cartes()
        self.maj_statut(message)

    def _carte(self, v):
        lignes = [dict(l) | {"nom": l["produit"], "categorie": l["categorie"] or "Divers"}
                  for l in self.base.lignes_vente(v["id"])]
        carte = tk.Frame(self.tableau, bg="white", width=self.LARGEUR_CARTE)

        entete = tk.Frame(carte, bg=CYAN)
        entete.pack(fill="x")
        tk.Label(entete, text=f"COMMANDE {v['numero']:03d}", font=(F_TITRE, 19),
                 bg=CYAN, fg="white", padx=10, pady=3).pack(side="left")
        tk.Label(entete, text=v["date"][11:16], font=(F_TITRE_LEGER, 14), bg=CYAN, fg=NUIT,
                 padx=10).pack(side="right")

        corps = tk.Frame(carte, bg="white", padx=6, pady=4)
        corps.pack(fill="x")
        for categorie, groupe in grouper_par_categorie(lignes):
            tk.Label(corps, text=categorie.upper(), font=(F_TITRE, 11), fg=CYAN_FONCE,
                     bg="white", anchor="w").pack(fill="x", pady=(4, 0))
            for l in groupe:
                fond = VERT_LIVRE if l["livre"] else "white"
                ligne = tk.Frame(corps, bg=fond, cursor="hand2")
                ligne.pack(fill="x", pady=1)
                ligne.columnconfigure(0, weight=1)
                # Une seule ligne par article : nom tronqué avec « … » s'il est trop long
                montant = euros(l["prix"] * l["qte"])
                police, police_prix = tkfont.Font(font=(F_TEXTE, 12)), tkfont.Font(font=(F_TEXTE, 11))
                dispo = self.LARGEUR_CARTE - px(12) - 16 - police_prix.measure(montant) - px(10)
                # Aligné sur les catégories : pas de retrait, la coche n'apparaît qu'une fois livré
                texte = tronquer(f"{'✔ ' if l['livre'] else ''}{l['qte']} × {l['nom']}", police, dispo)
                lbl = tk.Label(ligne, text=texte, font=police, fg=NUIT, bg=fond, anchor="w", padx=0, pady=2)
                lbl.grid(row=0, column=0, sticky="w")
                prix = tk.Label(ligne, text=montant, font=police_prix,
                                fg=NUIT, bg=fond, anchor="e", padx=4)
                prix.grid(row=0, column=1, sticky="e")
                for w in (ligne, lbl, prix):
                    w.bind("<Button-1>", lambda e, lid=l["id"], vid=v["id"]: self.basculer_livraison(vid, lid))

        tk.Frame(carte, bg=CIEL, height=1).pack(fill="x", padx=8, pady=(4, 0))
        pied = tk.Frame(carte, bg="white", padx=8, pady=2)
        pied.pack(fill="x")
        if v["encaisse"]:
            tk.Label(pied, text=f"✔ Encaissé · rendu {euros(v['rendu'])}", font=(F_TEXTE, 10),
                     fg=VERT_FONCE, bg="white").pack(side="left")
        else:
            tk.Label(pied, text="Non encaissé", font=(F_TEXTE, 10, "bold"), fg=MAGENTA,
                     bg="white").pack(side="left")
        tk.Label(pied, text=euros(v["total"]), font=(F_TITRE, 20), fg=NUIT, bg="white").pack(side="right")

        boutons = tk.Frame(carte, bg="white", padx=8, pady=8)
        boutons.pack(fill="x")
        boutons.columnconfigure((0, 1, 2), weight=1, uniform="b")
        police = (F_TITRE, 13)
        bouton(boutons, "MODIFIER", lambda: self.modifier_commande(v["id"]), CIEL, police=police,
               pady=5).grid(row=0, column=0, sticky="we", padx=(0, 3))
        if v["encaisse"]:
            bouton(boutons, "ENCAISSÉ", None, GRIS_CLAIR, police=police, pady=5, state="disabled").grid(
                row=0, column=1, sticky="we", padx=3)
        else:
            bouton(boutons, "ENCAISSER", lambda: self.encaisser_commande(v["id"]), JAUNE, police=police,
                   pady=5).grid(row=0, column=1, sticky="we", padx=3)
        # Terminer n'est possible qu'une fois la commande encaissée
        bouton(boutons, "TERMINER", lambda: self.terminer_commande(v["id"]),
               NUIT if v["encaisse"] else GRIS_CLAIR, police=police, pady=5,
               state="normal" if v["encaisse"] else "disabled").grid(row=0, column=2, sticky="we", padx=(3, 0))
        # Largeur fixe des cartes : les lignes s'adaptent, pas la carte
        tk.Frame(carte, width=self.LARGEUR_CARTE, height=0, bg="white").pack()
        return carte

    # --- actions ---
    def nouvelle_commande(self):
        SaisieCommande(self, self.base)

    def modifier_commande(self, vente_id):
        SaisieCommande(self, self.base, vente_id)

    def encaisser_commande(self, vente_id):
        v = self.base.commande(vente_id)
        recu = Encaissement(self, v["total"], f"Commande {v['numero']:03d} · à payer").resultat
        if recu is not None:
            self.base.encaisser_commande(vente_id, recu)
            self.rafraichir(f"Commande {v['numero']:03d} encaissée · rendu {euros(recu - v['total'])}")
            self._terminer_si_complete(vente_id)

    def destroy(self):
        memoriser_position(self, "principal")
        super().destroy()

    def historique(self):
        if demander_mot_de_passe(self):
            Historique(self, self.base)

    def produits(self):
        if demander_mot_de_passe(self):
            GestionProduits(self, self.base)

    def terminer_commande(self, vente_id):
        v = self.base.commande(vente_id)
        numero = v["numero"]
        if not v["encaisse"]:
            informer(self, "Terminer", f"La commande {numero:03d} doit être encaissée avant d'être terminée.")
            return
        if demander(self, "Terminer", f"Terminer la commande {numero:03d} ?", oui="TERMINER", non="NON"):
            self.base.terminer_commande(vente_id)
            self.rafraichir(f"Commande {numero:03d} terminée")

    def basculer_livraison(self, vente_id, ligne_id):
        self.base.basculer_livraison(ligne_id)
        self.rafraichir()
        self._terminer_si_complete(vente_id)

    def _terminer_si_complete(self, vente_id):
        """Encaissée et toutes les lignes livrées : on propose de terminer (comme un clic sur Terminer)."""
        if self.base.commande(vente_id)["encaisse"] and all(l["livre"] for l in self.base.lignes_vente(vente_id)):
            self.terminer_commande(vente_id)

    def maj_statut(self, message=""):
        jour = date.today().isoformat()
        ventes = [v for v in self.base.ventes_du_jour(jour) if not v["annule"]]
        total = sum(v["total"] for v in ventes)
        encaisse = sum(v["total"] for v in ventes if v["encaisse"])
        en_cours = sum(1 for c in self.base.commandes_en_cours())
        texte = (f"En cours : {en_cours}     Aujourd'hui : {len(ventes)} commandes · {euros(total)}"
                 f" · encaissé {euros(encaisse)}"
                 f"     Données : {DB_PATH}")
        if message:
            texte = f"{message}     |     {texte}"
        self.statut.config(text=texte)


if __name__ == "__main__":
    Principal().mainloop()
