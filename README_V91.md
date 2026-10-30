# Veille Bourse V9.1 — V8.9 + V9.0 + V9.1

## Installation
Copier les fichiers du ZIP au même emplacement dans le dépôt `Mric006-44/Veille-Bourse`; remplacer uniquement `.github/workflows/collecte.yml`. Garder tous les scripts V8.8 existants.

### Exécution GitHub Actions
- Par défaut : collecte et rapports V8.3, V8.6, V8.8, V9.0 et V9.1 ; pas de backtest long.
- `run_v89=true` : simule un portefeuille historique avec caisse commune (2000 EUR), 3 positions maximum, 2 par secteur, 20 EUR de risque initial/ligne, 60 EUR cumulé. Produit `data/backtest_v89.json`.
- `run_v87=true` et `run_backtests=true` : lancent indépendamment les anciennes simulations.
- `refresh_financials=true` : actualisation Yahoo des comptes annuels V8.6.

### V9.0 catalyseurs
`config/catalyseurs_v90.json` contient une liste vide par défaut. Pour intégrer un événement, fournir un objet :
`{"ticker":"IPN.PA","evenement":"Publication de resultats","source":"Site relations investisseurs","url_source":"https://...","date_publication":"2026-10-20","date_reexamen":"2026-11-20","impact_attendu":"A analyser","risque_associe":"A analyser"}`.
Ce n'est PAS une validation automatique du contenu de l'URL. Les catalyseurs non documentés restent absents, pas inventés.

### V9.1 valorisation
La V9.1 conserve les comparaisons des multiples PER / EV/EBITDA / FCF yield, ROIC et percentiles sectoriels. Elle refuse d'inventer un objectif DCF ou un historique de multiples qui ne figure pas dans les sources. `objectif_unique_indicatif` est pris du rapport V7.3 et reste un niveau technique, non un consensus d'analystes.

### Décision utilisateur sur le ratio gain/risque
Le R/R brut reste affiché, sans seuil éliminatoire. La V9.1 exécute `plans_v91.py` pour produire le rapport de plans V8.8 en retirant uniquement la mention `RATIO_BRUT_INSUFFISANT` des blocages, avec note explicative. Aucun stop n'est déplacé.

### Limites importantes du backtest V8.9
- Récalcule exclusivement des indicateurs techniques à chaque date, sans anticiper les cours futurs.
- Utilise l'univers actuel (biais de survivance) et la classification sectorielle actuelle ; pas de vérité point-in-time.
- Historique ajusté Yahoo / application du barème de TTF 2026 à des exercices antérieurs : approximation.
- Les frais et glissements sont hypothétiques, et les gaps peuvent dépasser les stops.
- Signaux à J-1, achat à J ; sortie stop/gap ou 60 séances, pas d'objectif artificiel ni de filtrage R/R.
- Stratégie priorisée par règle puis ticker, ce qui n'est pas une allocation optimale ou backtest du score fondamental V8.6.
- Courbe de capital et métriques calculées sur simulation et non résultats d'investissement.

## Rapports
- `data/backtest_v89.json` (seulement si run_v89 activé).
- `data/catalyseurs_v90.json` (quotidien).
- `data/rapport_chatgpt_v91.json` (quotidien).
- Rapports V8.x conservés.

Aucun ordre automatique ; toute position doit être déclarée explicitement. Tester la publication et la cohérence des chiffres sur GitHub avant de les employer pour des décisions.
