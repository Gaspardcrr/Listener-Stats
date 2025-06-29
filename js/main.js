// js/main.js

// Global variables for caching and tracking loading state
let allArtists = []; // Will hold the full processed data
let _allArtistsLoadedPromise = null; // A promise that resolves when allArtists is fully loaded and processed.
let currentDisplayLimit = 50; // Initial number of artists to show on the main page

document.addEventListener('DOMContentLoaded', async function () {
    const searchInput = document.getElementById('searchInput');
    const artistsTableBody = document.getElementById('artistsTableBody');
    const noArtistsMessage = document.getElementById('noArtistsMessage');
    const loadMoreButton = document.getElementById('loadMoreButton');
    const loadingSearchIndicator = document.getElementById('loadingSearchIndicator');

    // --- Utility functions ---
    // Fonction pour nettoyer les noms de fichiers (DOIT CORRESPONDRE EXACTEMENT À LA LOGIQUE PYTHON)
    function cleanFileName(name) {
        if (typeof name !== 'string') {
            console.error('cleanFileName a reçu une valeur non-string ou undefined:', name);
            return ''; // Retourne une chaîne vide pour éviter l'erreur .replace() sur undefined
        }
        // Reprise de votre logique originale qui correspond à celle attendue par Python
        let cleaned = name.replace(/[\\/:*?"<>|]/g, '');
        return cleaned.trim();
    }

    // Fonction pour parser un CSV
    async function parseCSV(url) {
        try {
            const response = await fetch(url);
            if (!response.ok) {
                // Si le fichier n'existe pas ou erreur serveur, renvoyer vide
                if (response.status === 404) {
                    console.warn(`Fichier non trouvé: ${url}. Il peut être normal pour un nouvel artiste.`);
                    return [];
                }
                throw new Error(`Erreur HTTP: ${response.status} - ${response.statusText}`);
            }
            const text = await response.text();
            const lines = text.trim().split('\n');
            if (lines.length === 0 || lines[0].trim() === '') return []; // Gérer les fichiers vides

            const headers = lines[0].split(',').map(header => header.trim());
            const data = [];
            for (let i = 1; i < lines.length; i++) {
                const values = lines[i].split(',').map(val => val.trim());
                if (values.length === headers.length && values.some(v => v !== '')) { // Vérifier ligne non vide
                    let row = {};
                    headers.forEach((header, index) => {
                        row[header] = values[index];
                    });
                    data.push(row);
                } else if (values.some(v => v !== '')) { // Ligne mal formée mais non vide
                    console.warn(`Ligne mal formée ignorée dans CSV: "${lines[i]}" dans ${url}`);
                }
            }
            return data;
        } catch (error) {
            console.error(`Erreur lors du chargement ou du parsing du CSV "${url}":`, error);
            return []; // Retourner un tableau vide en cas d'erreur
        }
    }

    // Fonction pour calculer un score de pertinence pour la recherche
    function getSearchRelevanceScore(artistName, query) {
        if (!query) return 0; // Pas de requête, pas de score de pertinence
        artistName = artistName.toLowerCase();
        query = query.toLowerCase();

        if (artistName === query) {
            return 3; // Correspondance exacte (score le plus élevé)
        }
        if (artistName.startsWith(query)) {
            return 2; // Commence par la requête
        }
        if (artistName.includes(query)) {
            return 1; // Contient la requête n'importe où
        }
        return 0; // Aucune correspondance directe
    }
    // --- Fin Utility functions ---


    // Fonction principale pour charger les données progressivement et gérer le cache
    async function loadArtistsProgressively() {
        const CACHE_KEY = 'cachedArtistsData';
        const CACHE_TIMESTAMP_KEY = 'cachedArtistsTimestamp';
        const ONE_DAY_IN_MS = 24 * 60 * 60 * 1000; // Durée de vie du cache: 24 heures

        // 1. Essayer de charger depuis localStorage en premier
        const cachedData = localStorage.getItem(CACHE_KEY);
        const cachedTimestamp = localStorage.getItem(CACHE_TIMESTAMP_KEY);
        const now = new Date().getTime();

        if (cachedData && cachedTimestamp && (now - parseInt(cachedTimestamp) < ONE_DAY_IN_MS)) {
            try {
                allArtists = JSON.parse(cachedData);
                console.log('Artistes chargés depuis le cache localStorage.');
                _allArtistsLoadedPromise = Promise.resolve(); // Les données sont immédiatement prêtes
                
                // Mettre à jour la barre de recherche et le displayLimit si un paramètre 'q' est dans l'URL
                const qParam = new URLSearchParams(window.location.search).get('q');
                if (qParam) {
                    searchInput.value = qParam;
                    currentDisplayLimit = allArtists.length; // Si une recherche est persistante, on affiche tout
                }
                renderArtistsTable(allArtists, searchInput.value || '');
                return; // Sortir, les données ont été chargées depuis le cache
            } catch (e) {
                console.error("Erreur en parsant le cache localStorage, rechargement des données:", e);
                localStorage.removeItem(CACHE_KEY); // Invalider le cache corrompu
                localStorage.removeItem(CACHE_TIMESTAMP_KEY);
            }
        }

        // 2. Si pas en cache, cache expiré, ou erreur de parsing, commencer le chargement depuis les CSV
        console.log('Début du chargement initial (partiel) des artistes...');
        const basicArtists = await parseCSV('./data/artists.csv'); // Chemin relatif au fichier HTML

        // Initialiser allArtists avec les infos de base (les auditeurs seront en "Chargement...")
        allArtists = basicArtists.map(artist => ({
            ...artist,
            lastListenersCount: 'Chargement...', // Placeholder
            lastUpdateDateFormatted: '...',       // Placeholder
            isUpToDateToday: false                // Default
        }));

        // Rendre immédiatement les premiers artistes (respectant la limite initiale et la recherche éventuelle)
        renderArtistsTable(allArtists, searchInput.value || '');

        // 3. Lancer le chargement des détails en arrière-plan
        _allArtistsLoadedPromise = new Promise(async (resolve) => {
            console.log('Début du chargement des détails (background) des artistes...');
            
            if (basicArtists.length === 0) {
                console.warn("Aucun artiste trouvé dans artists.csv ou fichier vide.");
                resolve(); 
                return;
            }

            // Utiliser Promise.all pour un fetching concurrent des détails d'artiste
            // Cela crée un tableau de promesses, chaque promesse charge un fichier CSV d'historique
            const detailPromises = basicArtists.map(async (artist) => {
                const cleanedName = cleanFileName(artist.nom);
                const dataFilePath = `./data/${cleanedName}.csv`; // Chemin relatif au fichier HTML
                
                let history = [];
                try {
                    history = await parseCSV(dataFilePath);
                } catch (e) {
                    console.warn(`Impossible de charger l'historique pour ${artist.nom} (${dataFilePath}): ${e.message}`);
                }

                let lastListenersCount = 'N/A';
                let lastUpdateDate = null;
                let lastUpdateDateFormatted = 'Jamais';
                let isUpToDateToday = false;

                if (history.length > 0) {
                    history.sort((a, b) => new Date(a.date) - new Date(b.date)); // Trier par date
                    const latestEntry = history[history.length - 1]; // Dernière entrée

                    if (latestEntry && typeof latestEntry.auditeurs !== 'undefined' && latestEntry.date) {
                        lastListenersCount = parseInt(latestEntry.auditeurs.replace(/\D/g, '')) || 0;
                        lastUpdateDate = new Date(latestEntry.date);
                        if (isNaN(lastUpdateDate.getTime())) {
                            console.warn(`Date invalide pour ${artist.nom}: ${latestEntry.date}`);
                            lastUpdateDate = null;
                        } else {
                            lastUpdateDateFormatted = lastUpdateDate.toLocaleDateString('fr-FR', {
                                day: '2-digit', month: '2-digit', year: 'numeric'
                            });
                            const today = new Date();
                            isUpToDateToday = (
                                lastUpdateDate.getDate() === today.getDate() &&
                                lastUpdateDate.getMonth() === today.getMonth() &&
                                lastUpdateDate.getFullYear() === today.getFullYear()
                            );
                        }
                    }
                }
                return {
                    ...artist, // Garder les infos de base (nom, url)
                    lastListenersCount: lastListenersCount,
                    lastUpdateDateFormatted: lastUpdateDateFormatted,
                    isUpToDateToday: isUpToDateToday
                };
            });

            // Attendre que TOUS les détails soient chargés
            allArtists = await Promise.all(detailPromises);
            console.log('Tous les détails des artistes chargés (background).');

            // 4. Stocker les données complètes dans localStorage
            try {
                localStorage.setItem(CACHE_KEY, JSON.stringify(allArtists));
                localStorage.setItem(CACHE_TIMESTAMP_KEY, now.toString());
                console.log('Artistes sauvegardés dans le cache localStorage.');
            } catch (e) {
                console.error("Erreur lors de l'enregistrement dans localStorage:", e);
                // Si le quota est dépassé, l'application continuera de fonctionner sans cache
            }
            
            // Re-render le tableau avec les données complètes une fois chargées
            renderArtistsTable(allArtists, searchInput.value || '');
            resolve(); // Résoudre la promesse
        });
    }

    // Fonction pour rendre le tableau des artistes
    function renderArtistsTable(artists, searchQuery = '') {
        artistsTableBody.innerHTML = ''; // Nettoyer le tableau existant
        noArtistsMessage.style.display = 'none';
        loadMoreButton.style.display = 'none'; // Cacher le bouton "Voir plus" par défaut

        let currentFilteredArtists = artists.filter(artist =>
            artist && artist.nom && artist.nom.toLowerCase().includes(searchQuery.toLowerCase())
        );

        if (currentFilteredArtists.length === 0) {
            noArtistsMessage.style.display = 'block';
            return;
        }

        // Tri complexe basé sur la pertinence de la recherche, puis les auditeurs, puis alphabétique
        currentFilteredArtists.sort((a, b) => {
            const scoreA = getSearchRelevanceScore(a.nom, searchQuery);
            const scoreB = getSearchRelevanceScore(b.nom, searchQuery);

            // 1. Tri par score de pertinence (décroissant)
            if (scoreB - scoreA !== 0) {
                return scoreB - scoreA;
            }

            // 2. Tri par auditeurs mensuels (décroissant) si les scores de pertinence sont égaux
            // Gérer "Chargement..." ou "N/A" en les traitant comme 0 pour le tri
            const listenersA = typeof a.lastListenersCount === 'number' ? a.lastListenersCount : 0;
            const listenersB = typeof b.lastListenersCount === 'number' ? b.lastListenersCount : 0;
            if (listenersB - listenersA !== 0) {
                return listenersB - listenersA;
            }

            // 3. Tri secondaire : par nom d'artiste (alphabétique) si pertinence et auditeurs sont égaux
            return a.nom.localeCompare(b.nom);
        });

        // Déterminer combien d'artistes afficher
        let artistsToDisplay = currentFilteredArtists;
        // Si pas de recherche active ET que le nombre d'artistes filtrés dépasse la limite d'affichage actuelle
        if (!searchQuery && currentFilteredArtists.length > currentDisplayLimit) {
            artistsToDisplay = currentFilteredArtists.slice(0, currentDisplayLimit);
            loadMoreButton.style.display = 'block'; // Afficher le bouton "Voir plus"
        }

        artistsToDisplay.forEach(artist => {
            const row = document.createElement('tr');
            row.classList.add('artist-row'); 
            // URL pour la page de détail. Assurez-vous que artist_detail.html peut gérer le paramètre 'name'
            row.dataset.url = `artist_detail.html?name=${encodeURIComponent(artist.nom)}`;

            // Gérer l'état "Chargement..." pour les auditeurs
            const formattedListeners = artist.lastListenersCount === 'Chargement...' ? 'Chargement...' : 
                                       (artist.lastListenersCount === 'N/A' ? 'N/A' : artist.lastListenersCount.toLocaleString('fr-FR'));

            const statusIconClass = artist.isUpToDateToday ? 'fas fa-check-circle icon-up-to-date' : 'fas fa-exclamation-triangle icon-needs-update';
            const statusTooltipText = `Dernière maj: ${artist.lastUpdateDateFormatted}`;

            // Si les données sont encore en cours de chargement pour cet artiste spécifique, ne pas afficher l'icône/tooltip
            const statusCellContent = artist.lastListenersCount === 'Chargement...' ? '...' : `
                <div class="status-tooltip">
                    <i class="${statusIconClass}"></i>
                    <span class="tooltiptext">${statusTooltipText}</span>
                </div>
            `;

            row.innerHTML = `
                <td>
                    <a href="${row.dataset.url}">${artist.nom}</a>
                </td>
                <td>${formattedListeners}</td>
                <td style="text-align: center;">${statusCellContent}</td>
            `;
            artistsTableBody.appendChild(row);

            // Rendre la ligne entière cliquable, sauf si le clic est sur un lien à l'intérieur (le nom de l'artiste)
            row.addEventListener('click', function (e) {
                if (!e.target.closest('a')) { // Si le clic n'est pas sur un élément <a> à l'intérieur
                    window.location.href = this.dataset.url;
                }
            });
        });
    }

    // --- Gestionnaire d'événements pour la recherche ---
    if (searchInput) {
        // Au chargement de la page, vérifier si un paramètre 'q' est présent dans l'URL (recherche persistante)
        const urlParams = new URLSearchParams(window.location.search);
        const qParam = urlParams.get('q');
        if (qParam) {
            searchInput.value = qParam;
            // Si une recherche est persistante, on affiche tous les résultats par défaut
            // Cela sera géré lors du premier render après le chargement de allArtists.
        }
        searchInput.focus();
        searchInput.setSelectionRange(searchInput.value.length, searchInput.value.length);

        searchInput.addEventListener('input', async function () {
            const currentSearchQuery = searchInput.value.trim(); // Utiliser trim() pour nettoyer les espaces

            // Mettre à jour l'URL pour persister la recherche (sans recharger la page)
            const newUrl = new URL(window.location.href);
            if (currentSearchQuery) {
                newUrl.searchParams.set('q', currentSearchQuery);
                currentDisplayLimit = allArtists.length; // Quand on cherche, on affiche tous les résultats correspondants
            } else {
                newUrl.searchParams.delete('q');
                currentDisplayLimit = 50; // Réinitialiser la limite quand la recherche est effacée
            }
            window.history.replaceState({}, '', newUrl); // Met à jour l'URL sans recharger

            // Vérifier si le chargement complet des données est en cours
            if (_allArtistsLoadedPromise && _allArtistsLoadedPromise !== Promise.resolve()) {
                // Si le chargement complet est en cours, afficher l'indicateur de chargement de recherche
                loadingSearchIndicator.style.display = 'block'; // Afficher le spinner
                loadingSearchIndicator.classList.add('active'); // Ajouter la classe active pour l'animation CSS (si nécessaire)
                // Attendre que toutes les données soient prêtes
                await _allArtistsLoadedPromise; 
                loadingSearchIndicator.classList.remove('active');
                loadingSearchIndicator.style.display = 'none'; // Cacher le spinner
            }
            // Rendre le tableau avec les données actuelles (complètes ou partielles selon l'état du chargement)
            renderArtistsTable(allArtists, currentSearchQuery);
        });
    }

    // --- Fonctionnalité du bouton "Voir plus" ---
    if (loadMoreButton) {
        loadMoreButton.addEventListener('click', function() {
            currentDisplayLimit = allArtists.length; // Afficher tous les artistes
            renderArtistsTable(allArtists, searchInput.value || ''); // Re-rendre le tableau
        });
    }

    // --- Lancement initial du chargement des données ---
    await loadArtistsProgressively();
});