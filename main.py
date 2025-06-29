import tkinter as tk
from tkinter import messagebox, ttk
import csv, os, datetime, time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading # Pour les opérations bloquantes en arrière-plan

# Assurez-vous que config.py existe avec client_id et client_secret
try:
    from config import client_id, client_secret
except ImportError:
    messagebox.showerror("Erreur de configuration", "Le fichier config.py est manquant ou ne contient pas client_id et client_secret.")
    exit()

DATA_DIR = "data"
ARTISTS_FILE = "data/artists.csv"
os.makedirs(DATA_DIR, exist_ok=True)

# Initialisation de Spotipy
try:
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    sp = spotipy.Spotify(auth_manager=auth_manager)
except Exception as e:
    messagebox.showerror("Erreur Spotipy", f"Impossible d'initialiser l'API Spotify. Vérifiez vos identifiants dans config.py. Erreur: {e}")
    exit()

def nettoyer_nom_fichier(nom):
    """Nettoie le nom de l'artiste pour qu'il soit compatible avec les noms de fichiers."""
    return re.sub(r'[\\/*?:"<>|]', "_", nom)

def get_artist_url(nom):
    """
    Recherche un artiste sur Spotify via l'API Spotipy.
    Renvoie le nom officiel de l'artiste et son URL Spotify.
    """
    try:
        result = sp.search(q=nom, type='artist', limit=1)
        if result["artists"]["items"]:
            artist = result["artists"]["items"][0]
            return artist["name"], artist["external_urls"]["spotify"]
        return None, None
    except Exception as e:
        print(f"Erreur lors de la recherche de l'artiste '{nom}' via Spotipy: {e}")
        return None, None

def scrape_auditeurs(url):
    """
    Ouvre la page Spotify de l'artiste avec Selenium et scrape le nombre d'auditeurs mensuels.
    """
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless') # Exécuter en mode sans tête (sans ouvrir de fenêtre de navigateur)
        options.add_argument('--log-level=3') # Supprime les messages d'erreur de Selenium
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        auditeurs = None

        # Attendre que la page se charge et que les spans soient présents
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "span")))
        time.sleep(2) # Attendre un peu plus pour le chargement dynamique du contenu

        spans = driver.find_elements(By.TAG_NAME, "span")
        for span in spans:
            if "auditeur" in span.text.lower(): # Vérifier si le texte contient "auditeur" (insensible à la casse)
                auditeurs = span.text
                break
        return auditeurs
    except Exception as e:
        print(f"Erreur lors du scraping de l'URL '{url}': {e}")
        return None
    finally:
        if driver:
            driver.quit()

def enregistrer_artist(nom, url):
    """
    Ajoute l'artiste à artists.csv s'il n'est pas déjà enregistré.
    """
    artistes_existants = charger_artistes_details() # Charge les détails pour éviter les doublons
    if any(row["nom"].lower() == nom.lower() for row in artistes_existants):
        print(f"Artiste '{nom}' déjà enregistré.")
        return False

    nouveau = not os.path.exists(ARTISTS_FILE)
    mode = "a" if not nouveau else "w" # 'w' pour écrire l'en-tête si c'est un nouveau fichier
    with open(ARTISTS_FILE, mode, newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if nouveau:
            writer.writerow(["nom", "url"])
        writer.writerow([nom, url])
    return True

def ajouter_donnee(nom, auditeurs):
    """
    Crée ou met à jour le fichier data/{nom}.csv avec la date et le nombre d'auditeurs.
    """
    nom_fichier = nettoyer_nom_fichier(nom)
    file_path = os.path.join(DATA_DIR, f"{nom_fichier}.csv")
    now = datetime.date.today().isoformat()

    try:
        # Nettoyage robuste du nombre d'auditeurs
        auditeurs_nettoye = int(''.join(filter(str.isdigit, auditeurs.replace("\u202f", "").replace(" ", ""))))
    except ValueError:
        print(f"[Erreur] Format invalide d'auditeurs pour {nom} : '{auditeurs}'")
        return False

    fichier_existant = os.path.exists(file_path)
    with open(file_path, "a", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not fichier_existant:
            writer.writerow(["date", "auditeurs"])
        writer.writerow([now, auditeurs_nettoye])
        print(f"[OK] Données ajoutées pour {nom} ({auditeurs_nettoye})")
    return True

def artiste_suivi(nom):
    """Vérifie si un artiste est déjà dans artists.csv."""
    if not os.path.exists(ARTISTS_FILE):
        return False
    with open(ARTISTS_FILE, "r", encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["nom"].lower() == nom.lower():
                return True
    return False

def get_url_artiste(nom):
    """Récupère l'URL Spotify d'un artiste suivi."""
    if not os.path.exists(ARTISTS_FILE):
        return None
    with open(ARTISTS_FILE, "r", encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["nom"].lower() == nom.lower():
                return row["url"]
    return None

def charger_artistes():
    """Charge seulement les noms des artistes suivis."""
    artistes = []
    if os.path.exists(ARTISTS_FILE):
        with open(ARTISTS_FILE, "r", encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                artistes.append(row["nom"])
    return artistes

def charger_artistes_details():
    """Charge les noms et URLs des artistes suivis."""
    artistes = []
    if os.path.exists(ARTISTS_FILE):
        with open(ARTISTS_FILE, "r", encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                artistes.append({"nom": row["nom"], "url": row["url"]})
    return artistes

class SpotifyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Suivi des Auditeurs Spotify")
        self.root.geometry("600x650") # Taille ajustée pour les onglets

        self.style = ttk.Style()
        self.style.theme_use('clam') # Un thème plus moderne

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(pady=10, expand=True, fill="both")

        self.frame_recherche = ttk.Frame(self.notebook)
        self.frame_suivi = ttk.Frame(self.notebook)
        self.frame_masse = ttk.Frame(self.notebook)

        self.notebook.add(self.frame_recherche, text="Rechercher / Ajouter")
        self.notebook.add(self.frame_suivi, text="Artistes Suivis")
        self.notebook.add(self.frame_masse, text="Ajout en Masse")

        self._creer_interface_recherche()
        self._creer_interface_suivi()
        self._creer_interface_masse()

        self.status_bar = ttk.Label(root, text="Prêt.", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.mettre_a_jour_liste_artistes()

    def _update_status(self, message):
        """Met à jour le message dans la barre de statut."""
        self.status_bar.config(text=message)
        self.root.update_idletasks() # Force l'affichage immédiat

    def _enable_buttons(self):
        """Active tous les boutons après une opération."""
        self.btn_chercher.config(state=tk.NORMAL)
        self.btn_ajouter_masse.config(state=tk.NORMAL)
        self.btn_refresh_selected.config(state=tk.NORMAL)

    def _disable_buttons(self):
        """Désactive les boutons pendant une opération."""
        self.btn_chercher.config(state=tk.DISABLED)
        self.btn_ajouter_masse.config(state=tk.DISABLED)
        self.btn_refresh_selected.config(state=tk.DISABLED)

    def _creer_interface_recherche(self):
        """Crée l'interface pour la recherche et l'ajout d'un artiste."""
        pad_y = 10
        pad_x = 10

        ttk.Label(self.frame_recherche, text="Rechercher un artiste Spotify :", font=("Helvetica", 12)).pack(pady=pad_y)

        self.entry_recherche = ttk.Entry(self.frame_recherche, width=40, font=("Helvetica", 10))
        self.entry_recherche.pack(pady=5, padx=pad_x)
        self.entry_recherche.bind("<Return>", lambda event: self._thread_rechercher_artiste())

        self.btn_chercher = ttk.Button(self.frame_recherche, text="Chercher et Mettre à Jour", command=self._thread_rechercher_artiste)
        self.btn_chercher.pack(pady=5, padx=pad_x)

        self.result_label = ttk.Label(self.frame_recherche, text="", wraplength=400, justify=tk.CENTER)
        self.result_label.pack(pady=pad_y, padx=pad_x)

    def _creer_interface_suivi(self):
        """Crée l'interface pour la liste des artistes suivis."""
        pad_y = 10
        pad_x = 10

        ttk.Label(self.frame_suivi, text="Artistes suivis :", font=("Helvetica", 12)).pack(pady=pad_y)

        self.search_artist_entry = ttk.Entry(self.frame_suivi, width=35, font=("Helvetica", 10))
        self.search_artist_entry.pack(pady=5, padx=pad_x)
        self.search_artist_entry.bind("<KeyRelease>", self._filter_artist_list)
        ttk.Label(self.frame_suivi, text="Rechercher dans la liste :").pack()

        frame_listbox = ttk.Frame(self.frame_suivi)
        frame_listbox.pack(pady=5, padx=pad_x, fill=tk.BOTH, expand=True)

        self.liste_artistes_suivis = tk.Listbox(frame_listbox, height=15, width=50, font=("Helvetica", 10))
        self.liste_artistes_suivis.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame_listbox, orient="vertical", command=self.liste_artistes_suivis.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.liste_artistes_suivis.config(yscrollcommand=scrollbar.set)

        self.liste_artistes_suivis.bind("<<ListboxSelect>>", self._on_artist_select)

        button_frame = ttk.Frame(self.frame_suivi)
        button_frame.pack(pady=10, padx=pad_x)

        self.btn_afficher_graphique = ttk.Button(button_frame, text="Afficher Graphique", command=self._thread_afficher_graphique)
        self.btn_afficher_graphique.pack(side=tk.LEFT, padx=5)

        self.btn_refresh_selected = ttk.Button(button_frame, text="Mettre à Jour Sélectionné", command=self._thread_update_selected_artist)
        self.btn_refresh_selected.pack(side=tk.LEFT, padx=5)

        self.btn_supprimer_artiste = ttk.Button(button_frame, text="Supprimer l'artiste", command=self._supprimer_artiste)
        self.btn_supprimer_artiste.pack(side=tk.LEFT, padx=5)

    def _creer_interface_masse(self):
        """Crée l'interface pour l'ajout en masse d'artistes."""
        pad_y = 10
        pad_x = 10

        ttk.Label(self.frame_masse, text="Ajouter plusieurs artistes (un par ligne) :", font=("Helvetica", 12)).pack(pady=pad_y)

        self.zone_artistes_masse = tk.Text(self.frame_masse, height=12, width=60, font=("Helvetica", 10))
        self.zone_artistes_masse.pack(pady=5, padx=pad_x)

        self.btn_ajouter_masse = ttk.Button(self.frame_masse, text="Ajouter en Masse", command=self._thread_ajouter_en_masse)
        self.btn_ajouter_masse.pack(pady=5, padx=pad_x)

    def mettre_a_jour_liste_artistes(self):
        """Met à jour la Listbox des artistes suivis."""
        self.liste_artistes_suivis.delete(0, tk.END)
        self.artistes_suivis_data = charger_artistes() # Stocke la liste complète
        for nom in self.artistes_suivis_data:
            self.liste_artistes_suivis.insert(tk.END, nom)

    def _filter_artist_list(self, event=None):
        """Filtre la liste des artistes en fonction du texte entré."""
        search_term = self.search_artist_entry.get().lower()
        self.liste_artistes_suivis.delete(0, tk.END)
        for artist in self.artistes_suivis_data:
            if search_term in artist.lower():
                self.liste_artistes_suivis.insert(tk.END, artist)

    def _on_artist_select(self, event):
        """Gère la sélection d'un artiste dans la liste."""
        # Activez ou désactivez les boutons pertinents si un artiste est sélectionné
        selection = self.liste_artistes_suivis.curselection()
        if selection:
            self.btn_afficher_graphique.config(state=tk.NORMAL)
            self.btn_refresh_selected.config(state=tk.NORMAL)
            self.btn_supprimer_artiste.config(state=tk.NORMAL)
        else:
            self.btn_afficher_graphique.config(state=tk.DISABLED)
            self.btn_refresh_selected.config(state=tk.DISABLED)
            self.btn_supprimer_artiste.config(state=tk.DISABLED)

    def _thread_rechercher_artiste(self):
        """Démarre la fonction rechercher_artiste dans un thread séparé."""
        self._disable_buttons()
        self._update_status("Recherche en cours...")
        threading.Thread(target=self.rechercher_artiste).start()

    def rechercher_artiste(self):
        """
        Cherche un artiste entré par l'utilisateur.
        S'il est déjà suivi -> récupère les nouveaux auditeurs et les enregistre.
        Sinon -> propose de l'ajouter.
        """
        nom_recherche = self.entry_recherche.get().strip()
        self.result_label.config(text="") # Clear previous result

        if not nom_recherche:
            self._update_status("Entrez un nom d'artiste.")
            messagebox.showwarning("Attention", "Entrez un nom d'artiste.")
            self._enable_buttons()
            return

        if artiste_suivi(nom_recherche):
            self._update_status(f"'{nom_recherche}' est déjà suivi. Récupération des données...")
            url = get_url_artiste(nom_recherche)
            if url:
                auditeurs = scrape_auditeurs(url)
                if auditeurs:
                    ajouter_donnee(nom_recherche, auditeurs)
                    self._update_status(f"'{nom_recherche}' mis à jour. Auditeurs aujourd'hui : {auditeurs}")
                    self.result_label.config(text=f"{nom_recherche} est suivi. Auditeurs aujourd'hui : {auditeurs}")
                else:
                    self._update_status(f"Impossible de récupérer les auditeurs pour '{nom_recherche}'.")
                    messagebox.showerror("Erreur", f"Impossible de récupérer les auditeurs pour {nom_recherche}.")
            else:
                self._update_status(f"URL introuvable pour l'artiste '{nom_recherche}'.")
                messagebox.showerror("Erreur", f"URL introuvable pour l'artiste {nom_recherche}.")
        else:
            self._update_status(f"'{nom_recherche}' non suivi. Recherche sur Spotify...")
            vrai_nom, url = get_artist_url(nom_recherche)
            if url:
                self.result_label.config(text=f"Trouvé : {vrai_nom}. Voulez-vous l'ajouter ?")
                if messagebox.askyesno("Nouvel artiste", f"{vrai_nom} a été trouvé. L’ajouter et récupérer les auditeurs ?"):
                    self._update_status(f"Ajout de '{vrai_nom}' et récupération des auditeurs...")
                    enregistre = enregistrer_artist(vrai_nom, url)
                    if enregistre:
                        auditeurs = scrape_auditeurs(url)
                        if auditeurs:
                            ajouter_donnee(vrai_nom, auditeurs)
                            self.mettre_a_jour_liste_artistes()
                            self._update_status(f"'{vrai_nom}' a été ajouté. Auditeurs aujourd'hui : {auditeurs}")
                            self.result_label.config(text=f"{vrai_nom} a été ajouté. Auditeurs aujourd'hui : {auditeurs}")
                        else:
                            self._update_status(f"'{vrai_nom}' ajouté mais impossible de récupérer les auditeurs.")
                            messagebox.showerror("Erreur", f"{vrai_nom} a été ajouté mais impossible de récupérer les auditeurs.")
                    else:
                        self._update_status(f"Erreur lors de l'enregistrement de '{vrai_nom}'.")
                        messagebox.showerror("Erreur", f"Erreur lors de l'enregistrement de {vrai_nom}.")
            else:
                self._update_status(f"Artiste '{nom_recherche}' introuvable sur Spotify.")
                self.result_label.config(text=f"Artiste '{nom_recherche}' introuvable sur Spotify.")
                messagebox.showerror("Erreur", "Artiste introuvable sur Spotify.")
        self._enable_buttons()

    def _thread_ajouter_en_masse(self):
        """Démarre la fonction ajouter_en_masse dans un thread séparé."""
        self._disable_buttons()
        self._update_status("Ajout en masse en cours...")
        threading.Thread(target=self.ajouter_en_masse).start()

    def ajouter_en_masse(self):
        """Permet d’ajouter plusieurs artistes à la fois."""
        noms = self.zone_artistes_masse.get("1.0", tk.END).strip().split('\n')
        nb_succes = 0
        erreurs = []
        total_artistes = len(noms)
        if total_artistes == 0:
            self._update_status("Aucun artiste à ajouter.")
            messagebox.showwarning("Ajout en masse", "Aucun artiste à ajouter.")
            self._enable_buttons()
            return

        for i, nom in enumerate(noms):
            nom = nom.strip()
            if not nom:
                continue

            self._update_status(f"Traitement : {nom} ({i+1}/{total_artistes})...")
            try:
                if artiste_suivi(nom):
                    print(f"'{nom}' déjà suivi. Ignoré.")
                    continue

                vrai_nom, url = get_artist_url(nom)
                if not (vrai_nom and url):
                    erreurs.append(f"{nom} (introuvable sur Spotify)")
                    continue

                if artiste_suivi(vrai_nom): # Vérifier le vrai nom si différent
                    print(f"'{vrai_nom}' déjà suivi. Ignoré.")
                    continue

                auditeurs_texte = scrape_auditeurs(url)
                if not auditeurs_texte:
                    erreurs.append(f"{vrai_nom} (pas d'auditeurs trouvés ou erreur de scraping)")
                    continue

                if enregistrer_artist(vrai_nom, url):
                    if ajouter_donnee(vrai_nom, auditeurs_texte):
                        nb_succes += 1
                    else:
                        erreurs.append(f"{vrai_nom} (erreur d'enregistrement des données)")
                else:
                    erreurs.append(f"{vrai_nom} (erreur d'enregistrement de l'artiste)")

            except Exception as e:
                erreurs.append(f"{nom} (erreur inattendue: {e})")
                continue

        self.mettre_a_jour_liste_artistes()
        summary_message = f"{nb_succes} artiste(s) ajouté(s)."
        if erreurs:
            summary_message += f"\n{len(erreurs)} erreur(s) :\n" + "\n".join(erreurs[:5]) # Afficher les 5 premières erreurs
            if len(erreurs) > 5:
                summary_message += "\n..."
        self._update_status("Ajout en masse terminé.")
        messagebox.showinfo("Ajout en masse", summary_message)
        self._enable_buttons()

    def _thread_afficher_graphique(self):
        """Démarre la fonction afficher_graphique dans un thread séparé."""
        selection = self.liste_artistes_suivis.curselection()
        if selection:
            nom_artiste = self.liste_artistes_suivis.get(selection[0])
            self._disable_buttons()
            self._update_status(f"Affichage du graphique pour '{nom_artiste}'...")
            threading.Thread(target=self.afficher_graphique, args=(nom_artiste,)).start()
        else:
            messagebox.showwarning("Sélection requise", "Veuillez sélectionner un artiste dans la liste.")

    def afficher_graphique(self, nom_artiste):
        """Ouvre une nouvelle fenêtre avec un graphe matplotlib de l'évolution des auditeurs."""
        chemin = os.path.join(DATA_DIR, f"{nettoyer_nom_fichier(nom_artiste)}.csv")
        if not os.path.exists(chemin):
            self._update_status(f"Aucune donnée trouvée pour {nom_artiste}.")
            messagebox.showerror("Erreur", f"Aucune donnée trouvée pour {nom_artiste}")
            self._enable_buttons()
            return

        dates, auditeurs = [], []
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader) # Skip header
                for row in reader:
                    if len(row) == 2:
                        try:
                            # Convertir la date en objet datetime pour un meilleur affichage
                            dates.append(datetime.datetime.strptime(row[0], "%Y-%m-%d"))
                            auditeurs.append(int(row[1]))
                        except ValueError:
                            print(f"Skipping invalid data row: {row}")
                            continue
        except Exception as e:
            self._update_status(f"Erreur lors de la lecture des données pour {nom_artiste}.")
            messagebox.showerror("Erreur", f"Erreur lors de la lecture des données pour {nom_artiste}: {e}")
            self._enable_buttons()
            return

        if not dates:
            self._update_status(f"Pas de données valides pour {nom_artiste}.")
            messagebox.showwarning("Avertissement", f"Pas de données valides pour {nom_artiste}")
            self._enable_buttons()
            return

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(dates, auditeurs, marker='o', linestyle='-', color='skyblue')
        ax.set_title(f"Évolution des auditeurs de {nom_artiste}", fontsize=14)
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("Nombre d'auditeurs", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.7)
        fig.autofmt_xdate() # Formate les dates sur l'axe X

        plt.tight_layout()

        fenetre_graph = tk.Toplevel(self.root)
        fenetre_graph.title(f"{nom_artiste} - Auditeurs")
        canvas = FigureCanvasTkAgg(fig, master=fenetre_graph)
        canvas.draw()
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        toolbar_frame = ttk.Frame(fenetre_graph)
        toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
        # Vous pouvez ajouter des contrôles Matplotlib ici si vous le souhaitez
        # from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        # toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
        # toolbar.update()

        self._update_status(f"Graphique pour '{nom_artiste}' affiché.")
        self._enable_buttons()


    def _thread_update_selected_artist(self):
        """Démarre la mise à jour de l'artiste sélectionné dans un thread séparé."""
        selection = self.liste_artistes_suivis.curselection()
        if selection:
            nom_artiste = self.liste_artistes_suivis.get(selection[0])
            self._disable_buttons()
            self._update_status(f"Mise à jour de '{nom_artiste}' en cours...")
            threading.Thread(target=self._update_artist_data, args=(nom_artiste,)).start()
        else:
            messagebox.showwarning("Sélection requise", "Veuillez sélectionner un artiste à mettre à jour.")

    def _update_artist_data(self, nom_artiste):
        """Met à jour les données d'auditeurs pour un artiste spécifique."""
        url = get_url_artiste(nom_artiste)
        if url:
            auditeurs = scrape_auditeurs(url)
            if auditeurs:
                ajouter_donnee(nom_artiste, auditeurs)
                self._update_status(f"Données de '{nom_artiste}' mises à jour. Auditeurs aujourd'hui : {auditeurs}")
                messagebox.showinfo("Mise à jour réussie", f"Données de {nom_artiste} mises à jour. Auditeurs aujourd'hui : {auditeurs}")
            else:
                self._update_status(f"Impossible de récupérer les auditeurs pour '{nom_artiste}'.")
                messagebox.showerror("Erreur de mise à jour", f"Impossible de récupérer les auditeurs pour {nom_artiste}.")
        else:
            self._update_status(f"URL introuvable pour l'artiste '{nom_artiste}'.")
            messagebox.showerror("Erreur de mise à jour", f"URL introuvable pour l'artiste {nom_artiste}.")
        self._enable_buttons()

    def _supprimer_artiste(self):
        """Supprime l'artiste sélectionné de la liste et ses données."""
        selection = self.liste_artistes_suivis.curselection()
        if not selection:
            messagebox.showwarning("Sélection requise", "Veuillez sélectionner un artiste à supprimer.")
            return

        nom_artiste_a_supprimer = self.liste_artistes_suivis.get(selection[0])
        if messagebox.askyesno("Confirmer la suppression", f"Voulez-vous vraiment supprimer '{nom_artiste_a_supprimer}' et toutes ses données ?"):
            try:
                # Supprimer de artists.csv
                artistes_restants = []
                if os.path.exists(ARTISTS_FILE):
                    with open(ARTISTS_FILE, "r", encoding='utf-8') as f_in:
                        reader = csv.DictReader(f_in)
                        for row in reader:
                            if row["nom"].lower() != nom_artiste_a_supprimer.lower():
                                artistes_restants.append(row)

                with open(ARTISTS_FILE, "w", newline='', encoding='utf-8') as f_out:
                    fieldnames = ["nom", "url"]
                    writer = csv.DictWriter(f_out, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(artistes_restants)

                # Supprimer le fichier de données de l'artiste
                chemin_donnees = os.path.join(DATA_DIR, f"{nettoyer_nom_fichier(nom_artiste_a_supprimer)}.csv")
                if os.path.exists(chemin_donnees):
                    os.remove(chemin_donnees)

                self.mettre_a_jour_liste_artistes()
                messagebox.showinfo("Suppression réussie", f"'{nom_artiste_a_supprimer}' et ses données ont été supprimés.")
                self._update_status(f"'{nom_artiste_a_supprimer}' supprimé.")
            except Exception as e:
                messagebox.showerror("Erreur de suppression", f"Une erreur est survenue lors de la suppression : {e}")
                self._update_status(f"Erreur lors de la suppression de '{nom_artiste_a_supprimer}'.")

if __name__ == "__main__":
    root = tk.Tk()
    app = SpotifyApp(root)
    root.mainloop()