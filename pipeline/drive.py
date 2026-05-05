"""
pipeline/drive.py
Lecture / écriture des parquets sur Google Drive via un Service Account.
Les credentials sont stockés dans la variable d'environnement GOOGLE_CREDENTIALS (JSON).
"""

import io
import json
import os
import tempfile

import pandas as pd


# ── Identifiant du dossier Google Drive partagé ──────────────────────────────
# À définir dans les variables d'environnement Render : DRIVE_FOLDER_ID
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID', '')

# Noms des fichiers parquet sur Drive
PARQUET_FILES = {
    'mq':  'mq_metriques.parquet',
    'act': 'act_metriques.parquet',
    'ca':  'ca_metriques.parquet',
    'cp':  'cp_metriques.parquet',
    'mq_prix':  'mq_prix_journaliers.parquet',
    'act_prix': 'act_prix_journaliers.parquet',
    'ca_prix':  'ca_prix_journaliers.parquet',
    'cp_prix':  'cp_prix_journaliers.parquet',
    'brent':    'brent.parquet',
}


def _get_drive():
    """Initialise et retourne un client GoogleDrive authentifié via Service Account."""
    try:
        from pydrive2.auth import GoogleAuth
        from pydrive2.drive import GoogleDrive
        from oauth2client.service_account import ServiceAccountCredentials
    except ImportError:
        raise ImportError(
            "pydrive2 et oauth2client sont requis. "
            "Ajouter dans requirements.txt : pydrive2 oauth2client"
        )

    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise EnvironmentError(
            "Variable d'environnement GOOGLE_CREDENTIALS manquante. "
            "Ajouter le JSON du service account dans Render > Environment."
        )

    creds_dict = json.loads(creds_json)

    scope = [
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file',
    ]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    gauth = GoogleAuth()
    gauth.credentials = credentials

    return GoogleDrive(gauth)


def _find_file(drive, filename: str, folder_id: str) -> dict | None:
    """Cherche un fichier par nom dans le dossier Drive. Retourne le GDriveFile ou None."""
    query = f"title='{filename}' and '{folder_id}' in parents and trashed=false"
    file_list = drive.ListFile({'q': query}).GetList()
    return file_list[0] if file_list else None


# ══════════════════════════════════════════════════════════════════════════════
# LECTURE
# ══════════════════════════════════════════════════════════════════════════════

def load_parquet(key: str, folder_id: str = DRIVE_FOLDER_ID) -> pd.DataFrame | None:
    """
    Télécharge et retourne un DataFrame depuis Google Drive.
    Retourne None si le fichier n'existe pas encore.
    """
    if not folder_id:
        raise EnvironmentError("DRIVE_FOLDER_ID non défini.")

    filename = PARQUET_FILES.get(key)
    if not filename:
        raise ValueError(f"Clé inconnue : {key}. Valides : {list(PARQUET_FILES)}")

    try:
        drive    = _get_drive()
        gf       = _find_file(drive, filename, folder_id)
        if gf is None:
            return None

        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
            tmp_path = tmp.name

        gf.GetContentFile(tmp_path)
        df = pd.read_parquet(tmp_path)
        os.unlink(tmp_path)
        return df

    except Exception as e:
        print(f"[drive.load_parquet] Erreur pour '{key}': {e}")
        return None


def load_parquet_bytes(key: str, folder_id: str = DRIVE_FOLDER_ID) -> bytes | None:
    """Retourne le contenu brut (bytes) du parquet — utile pour mise en cache mémoire."""
    if not folder_id:
        raise EnvironmentError("DRIVE_FOLDER_ID non défini.")

    filename = PARQUET_FILES.get(key)
    if not filename:
        return None

    try:
        drive = _get_drive()
        gf    = _find_file(drive, filename, folder_id)
        if gf is None:
            return None

        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
            tmp_path = tmp.name

        gf.GetContentFile(tmp_path)
        with open(tmp_path, 'rb') as f:
            data = f.read()
        os.unlink(tmp_path)
        return data

    except Exception as e:
        print(f"[drive.load_parquet_bytes] Erreur pour '{key}': {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# ÉCRITURE
# ══════════════════════════════════════════════════════════════════════════════

def save_parquet(
    df: pd.DataFrame,
    key: str,
    folder_id: str = DRIVE_FOLDER_ID,
) -> bool:
    """
    Sauvegarde un DataFrame en parquet sur Google Drive.
    Écrase le fichier existant si présent.
    Retourne True si succès.
    """
    if not folder_id:
        raise EnvironmentError("DRIVE_FOLDER_ID non défini.")

    filename = PARQUET_FILES.get(key)
    if not filename:
        raise ValueError(f"Clé inconnue : {key}")

    try:
        drive = _get_drive()

        # Écriture locale temporaire
        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp:
            tmp_path = tmp.name
        df.to_parquet(tmp_path, index=False)

        # Recherche d'un fichier existant (pour mise à jour plutôt que duplication)
        existing = _find_file(drive, filename, folder_id)

        if existing:
            existing.SetContentFile(tmp_path)
            existing.Upload()
        else:
            gf = drive.CreateFile({
                'title': filename,
                'parents': [{'id': folder_id}],
                'mimeType': 'application/octet-stream',
            })
            gf.SetContentFile(tmp_path)
            gf.Upload()

        os.unlink(tmp_path)
        print(f"[drive.save_parquet] '{filename}' sauvegardé sur Drive ✓")
        return True

    except Exception as e:
        print(f"[drive.save_parquet] Erreur pour '{key}': {e}")
        return False


def save_parquet_from_bytes(
    data: bytes,
    key: str,
    folder_id: str = DRIVE_FOLDER_ID,
) -> bool:
    """Variante qui accepte des bytes directement."""
    df = pd.read_parquet(io.BytesIO(data))
    return save_parquet(df, key, folder_id)


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def list_drive_parquets(folder_id: str = DRIVE_FOLDER_ID) -> list[str]:
    """Liste les fichiers parquet présents dans le dossier Drive."""
    try:
        drive = _get_drive()
        query = f"'{folder_id}' in parents and trashed=false"
        files = drive.ListFile({'q': query}).GetList()
        return [f['title'] for f in files if f['title'].endswith('.parquet')]
    except Exception as e:
        print(f"[drive.list_drive_parquets] Erreur: {e}")
        return []


def drive_is_configured() -> bool:
    """Vérifie que les variables d'environnement nécessaires sont définies."""
    return bool(
        os.environ.get('GOOGLE_CREDENTIALS')
        and os.environ.get('DRIVE_FOLDER_ID')
    )
