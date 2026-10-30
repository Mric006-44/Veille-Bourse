# Kit V8.4 — collecte incrémentale sur 5 ans

## Installation

Dans `Mric006-44/Veille-Bourse`, copier **en conservant les chemins** :

1. `cache_v84.py` (nouveau)
2. `collecte_v84.py` (nouveau)
3. `config/cache_v84.json` (nouveau)
4. `tests/test_cache_v84.py` (nouveau)
5. `.github/workflows/collecte.yml` (remplacer l'actuel)

Ne pas remplacer `collecte.py`, `fiabilisation.py`, `screening.py`, `plans_v73.py`, `rapport_v83.py`, etc. Ces scripts demeurent exécutés, avec leur téléchargement Yahoo intercepté uniquement par le lanceur V8.4.

La V8.3 doit être déjà installée (`rapport_v83.py`, `tests/test_v83.py`, `config/analyse_v83.json`). Si elle n'est pas installée, conserver l'ancien workflow et installer V8.3 d'abord.

## Fonctionnement

- Stockage : `data/historique_long/<ticker>.csv`, réutilise les CSV V6.3 déjà présents.
- Au premier passage : télécharge cinq ans si le cache est absent/invalide.
- Chaque jour : demande depuis **dix jours calendaires avant la dernière séance** ; les lignes communes sont remplacées par les données nouvelles, sans doublons.
- S'il détecte une modification du facteur `Adj Close / Close` sur les séances communes, retélécharge cinq ans : cela peut signaler un dividende, split ou une correction importante (sans les certifier).
- Le **premier samedi de chaque mois**, force un rafraîchissement intégral des cinq ans.
- Le lanceur `python collecte_v84.py pipeline` exécute V4 → V5 → V6.3 dans le **même processus**, avec un cache mémoire partagé : une seule requête incrémentale par ticker et par exécution, sauf repli de sécurité vers cinq ans.
- En cas de panne ou données incorrectes, un titre échoue explicitement : l'ancien cache reste présent sur disque, mais la collecte ne l'annonce pas comme actualisé.
- Les sorties V4, V5, V6.3, V7, V7.3, V8 et V8.3 sont conservées.

## Limites connues

1. L'historique de cinq ans devient la source de calcul V4 (et donc des backtests V6) : les résultats historiques peuvent changer, indépendamment des signaux récents.
2. Les cours bruts et ajustés proviennent toujours de Yahoo Finance, **pas d'une deuxième source indépendante**.
3. Les fichiers CSV génèrent des commits GitHub réguliers ; contrôler la taille du dépôt à long terme.
4. Les valeurs intrajournalières seront écrasées au rafraîchissement suivant ; programmer de préférence la veille après la clôture de Paris.
5. Les éventuelles corrections historiques hors de la fenêtre de dix jours peuvent rester indétectées jusqu'au prochain rafraîchissement intégral.
6. Le script n'implémente pas encore de téléchargement groupé. Il réduit la quantité de données téléchargées, mais conserve un appel Yahoo par titre et par exécution (hors repli).
7. Les indicateurs, scores et rapports restent exploratoires : **0 achat automatique**.

## Vérification

Lancer le workflow via GitHub Actions > Veille Bourse V8.4 > Run workflow.

- Étapes : tous les tests, la collecte, l'audit et la publication doivent réussir.
- `data/indicateurs.json` : `nombre_configure` / `nombre_reussi` attendus proches de 120 (selon état des données).
- `data/fiabilisation.json` : comparer `titres_audites` et les anomalies.
- `data/cache_v84_stats.json` : `full`, `incremental`, `fallback` ; ce fichier résume tout le pipeline V4 + V5 + V6.3.
- `data/rapport_chatgpt_v83.json` : top 5 global et listes de cinq par stratégie ; aucun achat autorisé.

Ne pas modifier les automatisations ChatGPT avant vérification d'une publication réussie.
