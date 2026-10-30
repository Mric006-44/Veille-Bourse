# Veille-Bourse V8.6 — intégration V8.5 + V8.6

## Base et installation

Kit *additif*, basé sur le dépôt `Mric006-44/Veille-Bourse` tel que lu le 30 octobre 2026.
Il n'écrase pas les rapports V8.3 existants et ne modifie pas les scripts V8.4 de cache.

Dans le dépôt GitHub, créer/remplacer **exactement** :

1. `config/analyse_v86.json` (nouveau)
2. `fondamentaux_v86.py` (nouveau)
3. `rapport_v86.py` (nouveau)
4. `tests/test_v86.py` (nouveau)
5. `.github/workflows/collecte.yml` (remplacement)

**Conserver** les fichiers existants : `collecte_v84.py`, `cache_v84.py`, `rapport_v83.py`, `fondamentaux_v8.py`, etc.

Dans GitHub Actions, `Run workflow` sans case cochée pour une exécution normale. À la première exécution, si le fichier `data/fondamentaux_v86.json` n'existe pas, la collecte financière complète est lancée une fois. Pour une actualisation forcée, cocher `refresh_financials`. Les backtests restent facultatifs.

## Rapports

- `data/fondamentaux_v86.json` : états financiers **annuels** et calculs non certifiés (éventuellement incomplets).
- `data/rapport_chatgpt_v86.json` : top 5 global, et pour chaque stratégie (`croissance_momentum`, `value_rebond`, `cassure`) une sous-liste `conformes` et une sous-liste `surveillance`, **5 noms maximum au total par stratégie**.
- `data/rapport_chatgpt_v83.json` demeure inchangé (rétrocompatibilité).

Adresse du nouveau rapport après la première publication réussie :
`https://raw.githubusercontent.com/Mric006-44/Veille-Bourse/main/data/rapport_chatgpt_v86.json`

## Intégration V8.5

- Prise en compte de la **couverture effective** des métriques disponibles : un 100/100 obtenu avec peu de critères ne doit pas avoir le même poids qu'un 100/100 complet.
- Scores sectoriels uniquement si le nombre de comparables de même secteur atteint un minimum.
- Distinction **stratégie entièrement conforme** versus **surveillance**.
- Liquidité minimum de 1M EUR / jour préservée et zéro achat autorisé.
- Scores exploratoires, pondérations heuristiques : **non validés par backtests**.

## Intégration V8.6

- Récupération annuelle Yahoo des comptes de résultat / bilan / cash-flow (généralement jusqu'à 4 ans ; selon disponibilité).
- Croissance annualisée du CA sur trois ans si quatre exercices comparables.
- ROIC indicatif (NOPAT / capital investi moyen), marge FCF, FCF positif trois ans.
- **Piotroski 9 critères : score uniquement si les neuf observations sont disponibles**.
- Altman Z-Score explicitement laissé `null` : calcul sectoriel et source comptable à approfondir.
- Pour la finance, ROIC/FCF/Piotroski industriel ne sont pas évalués dans le score de qualité.

## Sécurité & limites

Les états Yahoo peuvent être restatés, les libellés varient selon les émetteurs, des exercices peuvent manquer et le taux d'impôt peut être exceptionnel. Le modèle **ne possède pas de données comptables historiques point-in-time**. Ne pas utiliser ces séries pour affirmer un backtest historique sans biais d'anticipation.

Le programme n'invente pas de ROIC, Piotroski, Altman ni signal d'achat. Aucune validation PEA, TTF, spread ou sources officielles n'est remplacée. Les positions du portefeuille ne sont pas supposées exécutées.

Les données `data/` doivent rester suivies/commitées dans Git pour réutiliser les comptes annuels ; le workflow les publie automatiquement.

## Tests

`python -m unittest discover -s tests -p 'test_v86.py'`

Ils sont indépendants de Yahoo. Après installation : inspecter les logs et vérifier la distribution réelle des `exercices_disponibles`, la couverture du F-score, le nombre de fiches réussies, la cohérence des secteurs, les classements et les dates.
