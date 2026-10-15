# Buvette 3000

Caisse de buvette portable pour Windows.
L'exécutable et ses données tiennent dans un seul dossier : on le copie sur un autre PC et on le lance, sans installation.

## Fonctionnalités

- **Saisie de commande** : grille de boutons produits colorés, commande regroupée par catégorie, Entrée pour valider, double clic sur une ligne pour retirer 1.
- **Commandes en cours** : cartes côte à côte ; clic sur un article = livré (vert) ; boutons Modifier, Encaisser, Terminer.
- **Encaissement** : montant reçu, billets rapides, calcul du rendu. Une commande doit être encaissée pour être terminée ; encaissée et entièrement livrée, elle propose de se terminer.
- **Produits liés** : un produit peut en ajouter un autre au clic (ex. une consigne de gobelet).
- **Historique** : commandes du jour, récapitulatif par produit, remise en cours, export CSV.
- **Produits** : gestion, ordre cohérent, import / export CSV (compatible Excel).
- Accès à l'historique et aux produits protégé par mot de passe (`data/config.json`).
- Positions des fenêtres mémorisées, affichage net en haute résolution (125 %, 150 %…).

Raccourcis : **F2** nouvelle commande, **F3** historique, **F4** produits.

## Utilisation

Télécharger le zip de la dernière [release](../../releases), le décompresser et lancer `Buvette3000.exe`.
Les données sont créées dans `data\` à côté de l'exécutable (supprimer ce dossier pour repartir de zéro).
Mot de passe par défaut : voir `MOT_DE_PASSE_DEFAUT` dans `buvette.py`.

## Construire l'exécutable

Prérequis : Python 3 sur Windows.

```bat
build.bat
```

Le résultat est dans `dist\Buvette3000\`. Les données existantes de `dist\Buvette3000\data` sont conservées.

## Fichiers

| Fichier | Rôle |
|---|---|
| `buvette.py` | Application (Tkinter + SQLite) |
| `build.bat` | Construction de l'exécutable portable (PyInstaller) |
| `assets/` | Logo, icône et images embarqués |
| `produits_*.csv` | Listes de produits prêtes à importer |
