// js/artistDetail.js

document.addEventListener('DOMContentLoaded', async function () {
    const urlParams = new URLSearchParams(window.location.search);
    const artistName = urlParams.get('name');
    const artistTitleElement = document.getElementById('artistNameTitle');
    const lastUpdateDateElement = document.getElementById('lastUpdateDate'); // Nouvel élément pour la date de mise à jour
    const chartContainer = document.getElementById('monthlyListenersChart');
    const noDataMessage = document.getElementById('noDataMessage');

    if (artistName) {
        if (artistTitleElement) {
            artistTitleElement.textContent = artistName;
        }
        await loadArtistHistoryAndRenderChart(artistName);
    } else {
        if (artistTitleElement) {
            artistTitleElement.textContent = "Artiste non spécifié";
        }
        if (noDataMessage) {
            noDataMessage.style.display = 'block';
            noDataMessage.textContent = "Aucun artiste spécifié dans l'URL.";
        }
        if (chartContainer) {
            chartContainer.style.display = 'none';
        }
        if (lastUpdateDateElement) {
            lastUpdateDateElement.textContent = "Dernière mise à jour : N/A"; // Pas de nom, pas de date
        }
    }

    function cleanFileName(name) {
        if (typeof name !== 'string') {
            console.error('cleanFileName a reçu une valeur non-string ou undefined:', name);
            return '';
        }
        let cleaned = name.replace(/[\\/:*?"<>|]/g, '');
        return cleaned.trim();
    }

    async function parseCSV(url) {
        const response = await fetch(url);
        if (!response.ok) {
            console.error(`Erreur de chargement du CSV: ${url} - ${response.statusText}`);
            return [];
        }
        const text = await response.text();
        const lines = text.trim().split('\n');
        if (lines.length === 0) return [];

        const headers = lines[0].split(',').map(header => header.trim());
        const data = [];
        for (let i = 1; i < lines.length; i++) {
            const values = lines[i].split(',').map(val => val.trim());
            // S'assurer que la ligne n'est pas vide et a le bon nombre de colonnes
            if (values.length === headers.length && values.some(v => v !== '')) {
                let row = {};
                headers.forEach((header, index) => {
                    row[header] = values[index];
                });
                data.push(row);
            } else {
                console.warn(`Ligne ignorée dans CSV (vide ou mal formée) : ${lines[i]}`);
            }
        }
        return data;
    }

    async function loadArtistHistoryAndRenderChart(name) {
        const cleanedName = cleanFileName(name);
        const history = await parseCSV(`./data/${cleanedName}.csv`);

        if (history.length === 0) {
            if (noDataMessage) {
                noDataMessage.style.display = 'block';
                noDataMessage.textContent = `Aucune donnée historique trouvée pour ${name}.`;
            }
            if (chartContainer) {
                chartContainer.style.display = 'none';
            }
            if (lastUpdateDateElement) {
                lastUpdateDateElement.textContent = "Dernière mise à jour : Aucune donnée";
            }
            return;
        } else {
            if (noDataMessage) {
                noDataMessage.style.display = 'none';
            }
            if (chartContainer) {
                chartContainer.style.display = 'block';
            }
        }

        // Trier l'historique par date pour le graphique
        history.sort((a, b) => new Date(a.date) - new Date(b.date));

        // Mettre à jour la date de dernière mise à jour
        if (lastUpdateDateElement && history.length > 0) {
            const lastEntryDate = new Date(history[history.length - 1].date);
            // Options de formatage pour une date esthétique
            const options = { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' };
            lastUpdateDateElement.textContent = `Dernière mise à jour : ${lastEntryDate.toLocaleDateString('fr-FR', options)}`;
        }

        const dates = history.map(entry => entry.date);
        const listeners = history.map(entry => {
            if (entry && typeof entry.auditeurs === 'string') {
                return parseInt(entry.auditeurs.replace(/\D/g, '')) || 0;
            }
            console.warn(`Donnée d'auditeurs manquante ou invalide pour l'entrée:`, entry);
            return 0;
        });

        const ctx = document.getElementById('monthlyListenersChart').getContext('2d');
        // Destruction de l'ancien graphique s'il existe pour éviter les superpositions lors du rechargement
        if (window.myArtistChart instanceof Chart) {
            window.myArtistChart.destroy();
        }
        
        window.myArtistChart = new Chart(ctx, { // Stocker l'instance du graphique dans window pour référence
            type: 'line',
            data: {
                labels: dates,
                datasets: [{
                    label: 'Auditeurs Mensuels',
                    data: listeners,
                    borderColor: '#4f8df9',
                    backgroundColor: 'rgba(79, 141, 249, 0.2)',
                    fill: true,
                    tension: 0.3,
                    pointBackgroundColor: '#4f8df9',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: '#4f8df9'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'day',
                            tooltipFormat: 'dd/MM/yyyy',
                            displayFormats: {
                                day: 'dd/MM'
                            }
                        },
                        title: {
                            display: true,
                            text: 'Date',
                            color: '#555'
                        },
                        ticks: {
                            color: '#666'
                        },
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: false,
                        title: {
                            display: true,
                            text: 'Nombre d\'auditeurs',
                            color: '#555'
                        },
                        ticks: {
                            callback: function (value) {
                                return value.toLocaleString('fr-FR');
                            },
                            color: '#666'
                        },
                        grid: {
                            color: '#eee'
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        titleFont: { size: 14, weight: 'bold' },
                        bodyFont: { size: 13 },
                        padding: 10,
                        displayColors: false,
                        callbacks: {
                            label: function (context) {
                                var label = context.dataset.label || '';
                                if (label) label += ': ';
                                if (context.parsed.y !== null) label += context.parsed.y.toLocaleString('fr-FR');
                                return label;
                            }
                        }
                    },
                    legend: { display: false }
                },
                interaction: {
                    mode: 'index',
                    intersect: false
                }
            }
        });
    }
});