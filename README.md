# InvitePro 🎉

Créateur d'invitations personnalisées — application web Flask.

## Lancement rapide

### 1. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 2. Lancer l'application
```bash
python app.py
```

Puis ouvrir : **http://localhost:5000**

### 3. Mot de passe par défaut
```
invite2024
```

---

## Configuration

### Changer le mot de passe
**Option A — Variable d'environnement (recommandé) :**
```bash
# Windows
set INVITEPRO_PASSWORD=MonMotDePasse

# Linux/Mac
export INVITEPRO_PASSWORD=MonMotDePasse
```

**Option B — Directement dans app.py :**
```python
PASSWORD = "votre-mot-de-passe"
```

### Clé secrète (important pour la production)
```bash
set SECRET_KEY=une-cle-tres-longue-et-aleatoire
```

---

## Structure du projet
```
invitepro/
├── app.py              # Application principale Flask
├── requirements.txt    # Dépendances Python
├── invitepro.db        # Base SQLite (créée automatiquement)
├── uploads/            # Images uploadées
└── templates/
    ├── base.html         # Template de base
    ├── login.html        # Page de connexion
    ├── dashboard.html    # Tableau de bord
    ├── create.html       # Formulaire création/édition
    ├── invite_public.html # Page publique partageable
    └── 404.html          # Page d'erreur
```

---

## Hébergement en ligne

### PythonAnywhere (gratuit)
1. Créer un compte sur pythonanywhere.com
2. Uploader les fichiers
3. Créer une web app Flask
4. Pointer vers `app.py`
5. Définir les variables d'environnement dans l'onglet "Environment variables"

### Railway / Render
1. Pousser sur GitHub
2. Connecter le dépôt à Railway ou Render
3. Définir les variables `INVITEPRO_PASSWORD` et `SECRET_KEY`
4. Déployer

> **Note production** : Pour héberger, remplacez SQLite par PostgreSQL et utilisez un stockage cloud (S3, Cloudinary) pour les uploads.

---

## Fonctionnalités
- 🔐 Accès protégé par mot de passe
- 🎨 6 styles visuels (Élégant, Festif, Minimal, Romantique, Moderne, Nature)
- 🎨 Couleur principale personnalisable
- 🖼 Upload d'image / logo
- 🔗 Lien public unique par invitation
- 📱 Design responsive mobile-first
- ✏️ Modification et suppression des invitations
- 👁 Aperçu en temps réel lors de la création
