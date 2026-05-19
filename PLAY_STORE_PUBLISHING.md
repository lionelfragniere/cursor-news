# Publication Google Play - Cursor News

Ce projet est prêt pour une publication Google Play via Android App Bundle (`.aab`) signé, puis automatisation des mises à jour par Gradle Play Publisher.

## Cible

- Compte Play Console : `lionelfragniere`
- ID compte : `7454418178332272811`
- Package Android : `li.fragniere.cursornews`
- App : `Cursor News`
- Track automatisé par défaut : `internal`
- Politique de confidentialité : `https://cursor.fragniere.li/privacy.html`

## Limite importante

La première création de l'application et le premier upload doivent passer par la Play Console. L'API Google Play ne peut pas créer l'application à ta place. Une fois l'app créée et le premier bundle accepté, les uploads suivants peuvent être automatisés avec `scripts\publish_android_internal.cmd`.

## 1. Créer l'app dans Play Console

Dans Play Console :

1. `Accueil` > `Créer une application`
2. Nom : `Cursor News`
3. Langue par défaut : `Français (France)` ou `Français`
4. Type : `Application`
5. Prix : `Gratuite`
6. Email de contact : `lionel.fragniere@gmail.com`
7. Accepter les déclarations et Play App Signing

Attention : le package `li.fragniere.cursornews` est permanent une fois publié.

## 2. Créer la clé d'upload locale

Depuis la racine du repo :

```cmd
scripts\create_android_upload_key.cmd
```

Le script crée :

- `android\keystores\cursor-news-upload.jks`
- `android\release.properties`

Ces fichiers sont ignorés par Git. Sauvegarde-les dans un endroit privé. Sans cette clé, tu ne pourras plus signer les futures mises à jour avec la même identité d'upload.

## 3. Construire le bundle Play Store

```cmd
scripts\build_android_release.cmd
```

Sortie :

```text
android\app\build\outputs\bundle\release\app-release.aab
```

Pour une version spécifique :

```cmd
set ANDROID_VERSION_CODE=2
set ANDROID_VERSION_NAME=0.2.0
scripts\build_android_release.cmd
```

Le `versionCode` doit augmenter à chaque upload.

## 4. Premier upload manuel

Dans Play Console, crée une release de test interne et upload `app-release.aab`.

Complète aussi :

- fiche Play Store;
- catégorie : `Actualités et magazines`;
- politique de confidentialité : `https://cursor.fragniere.li/privacy.html`;
- questionnaire de sécurité des données;
- audience cible;
- classification du contenu;
- accès aux fonctionnalités de l'app : aucun login requis.

Suggestion Data Safety : l'app ne collecte pas de données personnelles directement. Elle stocke seulement les articles lus localement sur l'appareil.

## Android Auto

Depuis la version `0.2.0`, l'app déclare un support Android Auto en catégorie média. L'expérience voiture expose uniquement l'audio :

- flash en cours ;
- derniers flashs par ton ;
- contrôles lecture/pause/stop via Android Auto.

Dans Play Console, après upload du bundle :

1. Aller dans `Configuration` > `Paramètres avancés` > `Facteurs de forme`.
2. Activer `Android Auto` pour l'app.
3. Accepter les conditions Android Auto / Android for Cars.
4. Fournir les captures d'écran Android Auto si Play Console les demande.
5. Soumettre la release à l'examen. Google vérifiera les règles de qualité voiture.

Important : Android Auto ne doit pas afficher l'interface complète des articles et filtres pendant la conduite. Cursor News est donc exposée comme app média, pas comme app de lecture texte.

## 5. Activer l'automatisation API

1. Créer ou choisir un projet Google Cloud.
2. Activer `Google Play Developer API`.
3. Créer un compte de service.
4. Dans Play Console > `Users and permissions`, inviter l'email du compte de service.
5. Donner accès à l'app `Cursor News`, au minimum pour les releases de test interne et la fiche Play Store.
6. Télécharger la clé JSON et la placer localement ici :

```text
android\play-service-account.json
```

Alternative plus propre en CI :

```cmd
set ANDROID_PUBLISHER_CREDENTIALS={contenu JSON du compte de service}
```

Ne commit jamais cette clé.

## 6. Publier automatiquement en test interne

Après le premier upload manuel :

```cmd
scripts\publish_android_internal.cmd 2 0.2.0
```

Cela publie le bundle sur le track `internal` par défaut et pousse aussi les textes de fiche Play Store inclus dans le repo.

Variables utiles :

```cmd
set PLAY_TRACK=internal
set PLAY_RELEASE_STATUS=COMPLETED
set ANDROID_VERSION_CODE=2
set ANDROID_VERSION_NAME=0.2.0
```

Pour préparer sans rendre disponible aux testeurs :

```cmd
set PLAY_RELEASE_STATUS=DRAFT
scripts\publish_android_internal.cmd 2 0.2.0
```

## Métadonnées incluses

Le repo contient les textes de fiche Play Store en français :

```text
android\app\src\main\play\listings\fr-FR\
android\app\src\main\play\release-notes\fr-FR\
```

Gradle Play Publisher pourra les envoyer après configuration du compte de service.
