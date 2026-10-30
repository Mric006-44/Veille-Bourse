# Veille-Bourse V8.8 intégrant V8.7 — Kit additif

## Installation

Copier les chemins du ZIP à la racine du dépôt `Mric006-44/Veille-Bourse` en conservant leurs sous-dossiers :

- `config/v88.json` (créer)
- `backtest_v87.py` (créer)
- `plans_v88.py` (créer)
- `tests/test_v88.py` (créer)
- `.github/workflows/collecte.yml` (remplacer)

Les anciens scripts et sorties V8.6 restent inchangés. Le cache V8.4 est conservé.

## Déclenchement

Dans GitHub Actions > Veille Bourse V8.8 > Run workflow :

- `run_v87 = false` par défaut : collecte, analyse V8.6 et plans V8.8, sans backtest long.
- `run_v87 = true` : calcule aussi le backtest V8.7 (peut durer davantage).
- `run_backtests = true` : active les trois anciens backtests V6.
- `refresh_financials = true` : force l'actualisation des comptes V8.6.

Le samedi, la collecte des comptes reste prévue. La V8.7 n'est jamais exécutée automatiquement dans cette version.

## Fichiers produits

- `data/rapport_chatgpt_v88.json` : jusqu'à 5 dossiers de recherche enrichis en niveaux candidats, quantités **théoriques** et blocages. Aucune validation d'achat.
- `data/backtest_v87.json` : résultats historiques techniques **par valeur**, uniquement lorsque `run_v87 = true`.

## Limitations majeures

### V8.7

- Ce n'est **pas** un backtest de V8.6 : les historiques fondamentaux « disponibles à la date du signal » n'existent pas dans le dépôt. Il serait invalide d'appliquer les scores actuels au passé.
- Signaux techniques calculés à J, entrée au plus tôt J+1, sans fuite de données futures.
- Simulations **par titre indépendantes**, pas de portefeuille multi-lignes. Les gains cumulés par titre ne sont pas une performance réellement atteignable sur un capital commun de 2 000 € : ne pas produire de CAGR, Sharpe, Sortino ni Calmar à partir de ces sommes.
- Univers de titres actuel : biais de survivance. Fiscalité historique, dividendes, spreads et opérations sur titres approximatifs. La TTF par ticker est une hypothèse 2026, non un historique fiscal.
- Les titres à TTF indéterminée sont exclus des simulations de coûts plutôt qu'assignés arbitrairement à 0 %.
- La stop technique est heuristique ; les backtests ne constituent pas une preuve statistique de rentabilité future.

### V8.8

- Top 5 du rapport V8.6 uniquement. Les candidats d'autres stratégies restent visibles dans V8.6, mais ne font pas l'objet d'un dossier V8.8 supplémentaire, conformément à la limite de cinq nouveaux dossiers par screening.
- Résistances et supports mécaniques non confirmés, objectifs candidats non validés par catalyseurs.
- **Toutes les valeurs restent SURVEILLANCE ou REJETE_RECHERCHE.** Aucun achat confirmé ni aucune transaction enregistrée.
- Le statut français PEA et TTF doit être validé par ISIN. Le statut de TTF par ticker n'est qu'indicatif.
- Si le registre des positions réelles n'a pas été fourni explicitement, l'outil marque le risque cumulé **inconnu**. Un portefeuille vide n'est jamais supposé.
- Le registre d'opérations n'est pas fabriqué par le script et aucune position n'est comptabilisée sans confirmation de l'utilisateur.
- Les coûts théoriques incluent 0,35 % de courtage aller/retour, la TTF sur achat lorsque supposée applicable, et 0,1 % de glissement par côté.
- Le calcul de taille n'est qu'un scénario : il ne remplace pas la vérification du spread, de l'ISIN, des frais réels ou du registre.

## Tests

`python -m unittest discover -s tests -p 'test_v88.py'`

## Après le premier run

Vérifier la publication des deux fichiers, les exclusions, l'exécution des tests et comparer les échantillons de V8.7. Un premier run réussi est un contrôle technique, **pas** une validation financière.
