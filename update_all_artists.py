# update_all_artists.py
import csv, os, datetime, time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import concurrent.futures

# --- Fichier pour l'historique des exécutions ---
HISTORY_LOG_FILE = "execution_history.log"

# Assurez-vous que config.py est accessible
try:
    from config import client_id, client_secret
except ImportError:
    print("Erreur: Le fichier config.py est manquant ou ne contient pas client_id et client_secret.")
    exit()

DATA_DIR = "data"
ARTISTS_FILE = "data/artists.csv"
os.makedirs(DATA_DIR, exist_ok=True)

try:
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    sp = spotipy.Spotify(auth_manager=auth_manager)
except Exception as e:
    print(f"Erreur: Impossible d'initialiser l'API Spotify. Erreur: {e}")
    exit()


# Fonctions de scraping et de gestion des données
def nettoyer_nom_fichier(nom):
    return re.sub(r'[\\/*?:"<>|]', "_", nom)


def get_artist_url(nom):
    result = sp.search(q=nom, type='artist', limit=1)
    if result["artists"]["items"]:
        artist = result["artists"]["items"][0]
        return artist["name"], artist["external_urls"]["spotify"]
    return None, None


def scrape_auditeurs_for_artist(artist_data):
    """
    Scrape les auditeurs pour un artiste donné.
    Cette fonction est conçue pour être exécutée en parallèle.
    Elle retourne un dictionnaire contenant le résultat du scraping.
    """
    nom = artist_data["nom"]
    url = artist_data["url"]

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--log-level=3')
        # options.add_argument('--no-sandbox')
        # options.add_argument('--disable-gpu')
        # options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        auditeurs = None

        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "span")))
        time.sleep(2)  # Un petit délai peut toujours aider avec le JS

        spans = driver.find_elements(By.TAG_NAME, "span")
        for span in spans:
            if "auditeur" in span.text.lower():
                auditeurs = span.text
                break

        if auditeurs:
            print(f"[SCRAPING OK] {nom}: {auditeurs}")
            return {"nom": nom, "auditeurs_texte": auditeurs, "success": True}
        else:
            print(f"[SCRAPING ÉCHEC] {nom}: Auditeurs non trouvés sur la page.")
            return {"nom": nom, "success": False, "error": "Auditeurs non trouvés"}

    except Exception as e:
        print(f"[SCRAPING ERREUR] {nom}: {e}")
        return {"nom": nom, "success": False, "error": str(e)}
    finally:
        if driver:
            driver.quit()


# [MODIFIÉ] Fonction ajouter_donnee avec plus de détails de débogage et de gestion d'erreurs
def ajouter_donnee(nom, auditeurs):
    nom_fichier = nettoyer_nom_fichier(nom)
    file_path = os.path.join(DATA_DIR, f"{nom_fichier}.csv")
    now = datetime.date.today().isoformat()

    print(
        f"[DEBUG - ajouter_donnee] Tentative d'ajout pour '{nom}' ({auditeurs}) dans le fichier '{file_path}' pour la date '{now}'.")

    try:
        auditeurs_nettoye = int(''.join(filter(str.isdigit, auditeurs.replace("\u202f", "").replace(" ", ""))))
        print(f"[DEBUG - ajouter_donnee] Auditeurs nettoyés pour '{nom}': {auditeurs_nettoye}.")
    except ValueError as e:
        print(
            f"[Erreur - ajouter_donnee] Format invalide d'auditeurs pour {nom} : '{auditeurs}' -> Erreur de conversion: {e}. L'ajout ne sera PAS fait.")
        return False

    existing_data = []
    file_exists_before_check = os.path.exists(file_path)
    print(
        f"[DEBUG - ajouter_donnee] Le fichier '{file_path}' existait-il avant cette opération ? {file_exists_before_check}")

    if file_exists_before_check:
        try:
            with open(file_path, "r", encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)  # Lire l'en-tête, si présent
                print(f"[DEBUG - ajouter_donnee] En-tête du CSV lu: {header}.")
                for row in reader:
                    existing_data.append(row)
            print(f"[DEBUG - ajouter_donnee] {len(existing_data)} lignes existantes lues pour '{nom}'.")
        except Exception as e:
            print(
                f"[Avertissement - ajouter_donnee] Impossible de lire le fichier '{file_path}' pour vérifier les doublons : {e}. Le fichier sera peut-être recréé ou complété.")
            existing_data = []  # Réinitialiser les données existantes si la lecture échoue

    for row in existing_data:
        if len(row) > 0 and row[0] == now:
            print(
                f"[Info - ajouter_donnee] Données pour '{nom}' pour la date '{now}' existent DÉJÀ dans le CSV (détecté par ajouter_donnee). Ignoré l'ajout.")
            return True

    mode = "a" if file_exists_before_check else "w"
    print(f"[DEBUG - ajouter_donnee] Mode d'ouverture du fichier '{file_path}': '{mode}'.")

    try:
        with open(file_path, mode, newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists_before_check or os.path.getsize(file_path) == 0:
                writer.writerow(["date", "auditeurs"])
                print(f"[DEBUG - ajouter_donnee] En-tête 'date,auditeurs' ÉCRIT dans le fichier '{nom}'.")
            writer.writerow([now, auditeurs_nettoye])
            print(f"[OK] Données ajoutées au CSV pour {nom} ({auditeurs_nettoye}) pour la date {now} !")
        return True
    except Exception as e:
        print(
            f"[CRITIQUE ERREUR - ajouter_donnee] Impossible d'ÉCRIRE dans le fichier '{file_path}' pour '{nom}' : {e}. Vérifiez les permissions du dossier 'data' ou si le fichier est ouvert ailleurs.")
        return False


def charger_artistes_details():
    artistes = []
    if os.path.exists(ARTISTS_FILE):
        with open(ARTISTS_FILE, "r", encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                artistes.append({"nom": row["nom"], "url": row["url"]})
    return artistes


# [MODIFIÉ] Fonction donnee_existe_pour_aujourdhui avec plus de détails de débogage
def donnee_existe_pour_aujourdhui(nom_artiste):
    nom_fichier = nettoyer_nom_fichier(nom_artiste)
    file_path = os.path.join(DATA_DIR, f"{nom_fichier}.csv")
    today_iso = datetime.date.today().isoformat()

    print(f"\n[DEBUG - donnee_existe_pour_aujourdhui] Vérification pour l'artiste : '{nom_artiste}'")
    print(f"[DEBUG - donnee_existe_pour_aujourdhui] Chemin du fichier attendu : '{file_path}'")
    print(f"[DEBUG - donnee_existe_pour_aujourdhui] Date d'aujourd'hui (ISO) : '{today_iso}'")

    if not os.path.exists(file_path):
        print(f"[DEBUG - donnee_existe_pour_aujourdhui] Fichier '{file_path}' N'EXISTE PAS. Retourne False.")
        return False

    try:
        with open(file_path, "r", encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)  # Lire l'en-tête, si présent
            print(f"[DEBUG - donnee_existe_pour_aujourdhui] En-tête du CSV lu : {header}")

            found_today_entry = False
            for row_num, row in enumerate(reader):
                if not row:  # Ignorer les lignes vides
                    continue
                print(
                    f"[DEBUG - donnee_existe_pour_aujourdhui] Ligne {row_num + 2} lue dans CSV : {row}")  # +2 car 0-indexed et après l'en-tête
                if len(row) > 0 and row[0] == today_iso:
                    print(
                        f"[DEBUG - donnee_existe_pour_aujourdhui] Correspondance trouvée pour '{nom_artiste}' avec la date '{today_iso}' !")
                    found_today_entry = True
                    break

            if found_today_entry:
                print(f"[DEBUG - donnee_existe_pour_aujourdhui] Données trouvées pour aujourd'hui. Retourne True.")
                return True
            else:
                print(
                    f"[DEBUG - donnee_existe_pour_aujourdhui] Aucune entrée pour '{today_iso}' trouvée dans le fichier. Retourne False.")
                return False

    except Exception as e:
        print(
            f"[Avertissement] Erreur de lecture du fichier '{file_path}' pour vérification : {e}. Le scraping sera tenté.")
        return False


# [NOUVEAU] Fonction pour tenter les re-tentatives
def perform_retries(artists_to_retry, log_and_print_func):
    """
    Tente de scraper et d'ajouter les données pour une liste d'artistes qui ont échoué.
    Cette fonction est exécutée séquentiellement.
    """
    log_and_print_func(f"\n--- Début de la phase de re-tentative (séquentiel) ---")
    successful_retries_data = []  # Artistes dont le scraping ET l'ajout CSV ont réussi après re-tentative
    still_failed_artists_data = []  # Artistes qui échouent encore après re-tentative

    for i, artist_data in enumerate(artists_to_retry):
        nom = artist_data["nom"]
        log_and_print_func(f"[RE-TENTATIVE {i + 1}/{len(artists_to_retry)}] Pour {nom}...")

        retry_result = scrape_auditeurs_for_artist(artist_data)

        if retry_result["success"]:
            # Tenter d'ajouter la donnée si le scraping a réussi
            if ajouter_donnee(retry_result["nom"], retry_result["auditeurs_texte"]):
                successful_retries_data.append(retry_result)
            else:
                # Échec d'ajout CSV après un scraping réussi
                still_failed_artists_data.append(
                    {"nom": nom, "success": False, "error": "Échec d'ajout CSV après re-tentative"})
        else:
            # Échec du scraping même après re-tentative
            still_failed_artists_data.append(retry_result)  # Contient déjà l'erreur de scraping

    log_and_print_func(f"--- Fin de la phase de re-tentative ---")
    return successful_retries_data, still_failed_artists_data


# [MODIFIÉ] Fonction principale avec gestion des re-tentatives et logs améliorés
def actualiser_tous_les_artistes_parallele():
    start_time = time.time()
    current_datetime_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # [CORRECTIF] Initialisation de elapsed_time et end_time pour éviter UnboundLocalError
    elapsed_time = 0.0
    end_time = start_time

    # Pour collecter les messages à écrire dans l'historique (seulement les messages principaux du script)
    log_messages_for_history = []

    # Cette fonction est utilisée pour les messages qui doivent apparaître en console ET dans l'historique
    def log_and_print_to_history(message):
        print(message)
        log_messages_for_history.append(message)

    log_and_print_to_history(
        f"[{current_datetime_str}] Début de l'actualisation quotidienne des auditeurs (Parallélisée)...")

    artistes = charger_artistes_details()

    if not artistes:
        log_and_print_to_history("Aucun artiste trouvé dans la base de données. Rien à actualiser.")
        # Écrire l'historique même en cas d'absence d'artistes
        # Recalculer le temps avant de quitter dans ce cas
        end_time = time.time()
        elapsed_time = end_time - start_time
        write_execution_history(log_messages_for_history, 0, 0, 0, 0, 0, 0, elapsed_time, 0, [], [])
        return

    # 1. Pré-filtrage: Identifier les artistes à scraper
    artistes_a_scraper = []
    nb_sautes = 0
    print("\n--- Phase de Pré-filtrage des artistes ---")
    for artiste in artistes:
        if donnee_existe_pour_aujourdhui(artiste["nom"]):
            nb_sautes += 1
            print(f"[INFO] Artiste '{artiste['nom']}' a déjà des données pour aujourd'hui. Sera SKIPPÉ.")
        else:
            artistes_a_scraper.append(artiste)
            print(f"[INFO] Artiste '{artiste['nom']}' n'a pas de données pour aujourd'hui. Sera SCRAPÉ.")
    print("--- Fin de la phase de Pré-filtrage ---")

    if not artistes_a_scraper:
        total_artists = len(artistes)
        log_and_print_to_history(
            f"[{current_datetime_str}] Tous les {total_artists} artistes sont déjà à jour. Aucune opération de scraping nécessaire.")
        # Recalculer le temps avant de quitter dans ce cas
        end_time = time.time()
        elapsed_time = end_time - start_time
        write_execution_history(log_messages_for_history, total_artists, 0, 0, 0, nb_sautes, 0, elapsed_time, 0, [], [])
        return

    log_and_print_to_history(f"Préparation au scraping de {len(artistes_a_scraper)} artistes sur {len(artistes)}.")

    # 2. Configuration de la parallélisation et scraping initial
    MAX_WORKERS = 5

    initial_scraping_results = []  # Résultats bruts du premier passage
    artists_for_retry = []  # Artistes à re-tenter (échec scraping ou ajout CSV initial)

    log_and_print_to_history("\n--- Début de la phase de scraping initial (parallèle) ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_artist = {executor.submit(scrape_auditeurs_for_artist, artist): artist for artist in
                            artistes_a_scraper}

        completed_tasks = 0
        total_tasks = len(artistes_a_scraper)

        for future in concurrent.futures.as_completed(future_to_artist):
            completed_tasks += 1
            artist_data_original = future_to_artist[future]  # Données originales de l'artiste (nom, url)

            try:
                result = future.result()  # Résultat du scraping {"nom": ..., "auditeurs_texte": ..., "success": ...}
                initial_scraping_results.append(result)

                if result["success"]:
                    # Tenter d'ajouter la donnée immédiatement après un scraping réussi
                    if not ajouter_donnee(result["nom"], result["auditeurs_texte"]):
                        # Échec de l'ajout CSV pour un scraping réussi -> ajouter à la liste de re-tentative
                        artists_for_retry.append(artist_data_original)
                        # Conserver les informations sur l'erreur pour le log final
                        result["error"] = "Échec d'ajout CSV après scraping initial réussi"
                        # Mise à jour de l'état de succès pour ce cas précis (pour le comptage)
                        result["success"] = False
                else:
                    # Échec du scraping -> ajouter directement à la liste de re-tentative
                    artists_for_retry.append(artist_data_original)

            except Exception as exc:
                error_msg = f"Erreur inattendue du thread pour {artist_data_original['nom']}: {exc}"
                print(f"[ERREUR GLOBALE] {error_msg}")
                initial_scraping_results.append(
                    {"nom": artist_data_original['nom'], "success": False, "error": error_msg})
                artists_for_retry.append(artist_data_original)  # Ajouter pour re-tentative

            print(f"\rProgression globale: {completed_tasks}/{total_tasks} artistes traités par les workers...", end="",
                  flush=True)
        print()
    log_and_print_to_history("--- Fin de la phase de scraping initial ---")

    # --- Phase de re-tentative si nécessaire ---
    successful_retries_data = []  # Artistes qui ont réussi après re-tentative
    still_failed_after_retry_results = []  # Artistes qui ont toujours échoué après re-tentative

    if artists_for_retry:
        log_and_print_to_history(
            f"\n{len(artists_for_retry)} artistes ont échoué lors du scraping initial ou de l'ajout CSV. Tentative de re-traitement en séquentiel...")
        successful_retries_data, still_failed_after_retry_results = perform_retries(artists_for_retry,
                                                                                    log_and_print_to_history)
    else:
        log_and_print_to_history("\nAucun artiste à re-tenter après le scraping initial.")

    # --- 3. Traitement des résultats finaux (initial + retries) ---
    final_failed_scraping_artists_details = []
    final_failed_csv_artists_details = []

    log_and_print_to_history(f"\nDébut de la consolidation des résultats finaux...")

    # Compteurs finaux
    nb_succes_final = 0
    nb_erreurs_scraping_final = 0
    nb_erreurs_ajout_csv_final = 0

    # Compter les succès/échecs du passage initial
    for result in initial_scraping_results:
        # Si un artiste était un succès initial ET son ajout CSV a aussi marché
        if result["success"] and "error" not in result:  # Pas d'erreur d'ajout CSV ajoutée après coup
            nb_succes_final += 1
        elif result["success"] and "error" in result and "Échec d'ajout CSV" in result["error"]:
            # Cas où le scraping était OK mais ajout CSV a échoué initialement
            nb_erreurs_ajout_csv_final += 1
            final_failed_csv_artists_details.append(
                f"{result['nom']} (Initialement: {result.get('error', 'Détail non disponible.')})")
        else:  # Si le scraping initial a échoué
            nb_erreurs_scraping_final += 1
            final_failed_scraping_artists_details.append(
                f"{result['nom']} (Initialement: {result.get('error', 'Détail non disponible.')})")

    # Compter les résultats des re-tentatives
    for result in successful_retries_data:
        nb_succes_final += 1
        # Ceux qui ont réussi en re-tentative étaient des échecs initiaux
        # On peut retirer leur erreur des listes initiales si nécessaire, ou juste se baser sur les listes finales

    for result in still_failed_after_retry_results:
        if "Échec d'ajout CSV" in result.get("error", ""):
            nb_erreurs_ajout_csv_final += 1
            final_failed_csv_artists_details.append(
                f"{result['nom']} (Après re-tentative: {result.get('error', 'Détail non disponible.')})")
        else:
            nb_erreurs_scraping_final += 1
            final_failed_scraping_artists_details.append(
                f"{result['nom']} (Après re-tentative: {result.get('error', 'Détail non disponible.')})")

    end_time = time.time()
    elapsed_time = end_time - start_time

    total_artists_considered = len(artistes)

    log_and_print_to_history(f"\n[{current_datetime_str}] --- Résumé FINAL de l'Actualisation ---")
    log_and_print_to_history(f"Temps total écoulé : {elapsed_time:.2f} secondes.")

    average_time_per_scraped_artist = 0
    total_artists_actually_scraped = len(artistes_a_scraper)
    if total_artists_actually_scraped > 0:
        average_time_per_scraped_artist = elapsed_time / total_artists_actually_scraped
        log_and_print_to_history(
            f"Temps moyen par artiste SCRAPÉ (incluant re-tentatives) : {average_time_per_scraped_artist:.2f} secondes.")
    else:
        log_and_print_to_history(f"Temps moyen par artiste SCRAPÉ : N/A (aucun artiste n'a été scrappé).")

    log_and_print_to_history(f"\nStatistiques des opérations :")
    log_and_print_to_history(f"  - Artistes totaux considérés : {total_artists_considered}")
    log_and_print_to_history(f"  - Artistes déjà à jour (passés) : {nb_sautes}")
    log_and_print_to_history(f"  - Artistes réellement scrappés (initialement tentés) : {len(artistes_a_scraper)}")
    log_and_print_to_history(f"  - Re-tentatives effectuées : {len(artists_for_retry)}")
    log_and_print_to_history(f"  - Succès FINAUX (après toutes les tentatives) : {nb_succes_final}")
    log_and_print_to_history(
        f"  - Échecs de SCRAPING FINAUX (après toutes les tentatives) : {nb_erreurs_scraping_final}")
    log_and_print_to_history(
        f"  - Échecs d'AJOUT CSV FINAUX (après toutes les tentatives) : {nb_erreurs_ajout_csv_final}")

    if final_failed_scraping_artists_details:
        log_and_print_to_history("\nARTISTES AYANT ÉCHOUÉ LE SCRAPING (APRÈS TOUTES LES TENTATIVES) :")
        for error_artist in final_failed_scraping_artists_details:
            log_and_print_to_history(f"  - {error_artist}")

    if final_failed_csv_artists_details:
        log_and_print_to_history("\nARTISTES AYANT ÉCHOUÉ L'AJOUT AU CSV (APRÈS TOUTES LES TENTATIVES) :")
        for error_artist in final_failed_csv_artists_details:
            log_and_print_to_history(f"  - {error_artist}")

    write_execution_history(
        log_messages_for_history=log_messages_for_history,
        total_artists_considered=total_artists_considered,
        nb_artistes_scrapes=len(artistes_a_scraper),
        nb_succes_scraping=nb_succes_final,  # Nombre de succès finaux
        nb_erreurs_scraping=nb_erreurs_scraping_final,  # Nombre d'échecs de scraping finaux
        nb_sautes=nb_sautes,
        nb_erreurs_ajout_csv=nb_erreurs_ajout_csv_final,  # Nombre d'échecs d'ajout CSV finaux
        elapsed_time=elapsed_time,
        average_time_per_scraped_artist=average_time_per_scraped_artist,
        errors_scraping_artists=final_failed_scraping_artists_details,
        errors_csv_artists=final_failed_csv_artists_details
    )


# [MODIFIÉ] Fonction d'écriture de l'historique pour inclure plus de détails
def write_execution_history(log_messages_for_history, total_artists_considered, nb_artistes_scrapes,
                            nb_succes_scraping, nb_erreurs_scraping, nb_sautes,
                            nb_erreurs_ajout_csv, elapsed_time, average_time_per_scraped_artist,
                            errors_scraping_artists, errors_csv_artists):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(HISTORY_LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 80 + "\n")
        f.write(f"Historique d'exécution - {timestamp}\n")
        f.write("=" * 80 + "\n\n")

        for msg in log_messages_for_history:
            f.write(msg + "\n")

        f.write("\n" + "-" * 80 + "\n")
        f.write("Résumé final des statistiques:\n")
        f.write(f"  - Temps total écoulé : {elapsed_time:.2f} secondes\n")
        if average_time_per_scraped_artist > 0:
            f.write(f"  - Temps moyen par artiste SCRAPÉ : {average_time_per_scraped_artist:.2f} secondes\n")
        else:
            f.write(f"  - Temps moyen par artiste SCRAPÉ : N/A (aucun artiste n'a été scrappé)\n")
        f.write(f"  - Artistes totaux considérés : {total_artists_considered}\n")
        f.write(f"  - Artistes déjà à jour (passés) : {nb_sautes}\n")
        f.write(f"  - Artistes réellement scrappés (initialement tentés) : {nb_artistes_scrapes}\n")
        f.write(f"  - Succès FINAUX (après toutes les tentatives) : {nb_succes_scraping}\n")
        f.write(f"  - Échecs de SCRAPING FINAUX (après toutes les tentatives) : {nb_erreurs_scraping}\n")
        if errors_scraping_artists:
            f.write("    Détails des artistes avec échecs de SCRAPING FINAUX:\n")
            for artist_info in errors_scraping_artists:
                f.write(f"      - {artist_info}\n")

        f.write(f"  - Échecs d'AJOUT CSV FINAUX (après toutes les tentatives) : {nb_erreurs_ajout_csv}\n")
        if errors_csv_artists:
            f.write("    Détails des artistes avec erreurs d'AJOUT au CSV FINAUX:\n")
            for artist_info in errors_csv_artists:
                f.write(f"      - {artist_info}\n")

        f.write("\n" + "=" * 80 + "\n\n")


# Le point d'entrée du script
if __name__ == "__main__":
    actualiser_tous_les_artistes_parallele()