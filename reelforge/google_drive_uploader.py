"""
Google Drive upload helpers for ReelForge artifacts.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


@dataclass
class DriveUploadResult:
    status: str
    parent_folder_id: str
    run_folder_id: Optional[str]
    run_folder_path: Optional[str]
    video_file_id: Optional[str]
    video_link: Optional[str]
    metadata_file_id: Optional[str]
    metadata_link: Optional[str]
    error: Optional[str]


def _extract_folder_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Google Drive folder id is empty.")

    # Accept full URL or plain folder id.
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", raw)
    if match:
        return match.group(1)

    if re.match(r"^[a-zA-Z0-9_-]{10,}$", raw):
        return raw
    raise ValueError("Could not parse Google Drive folder id from value.")


class GoogleDriveUploader:
    def __init__(
        self,
        *,
        parent_folder_id: str,
        token_path: str,
        client_secret_path: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 2.0,
    ) -> None:
        self.parent_folder_id = _extract_folder_id(parent_folder_id)
        self.token_path = Path(token_path)
        self.client_secret_path = Path(client_secret_path) if client_secret_path else None
        self.scopes = scopes or list(DEFAULT_SCOPES)
        self.max_attempts = max(1, int(max_attempts))
        self.retry_backoff_seconds = max(0.1, float(retry_backoff_seconds))

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "GoogleDriveUploader":
        drive_cfg = config.get("integrations", {}).get("google_drive", {})
        oauth_cfg = drive_cfg.get("oauth", {})
        retry_cfg = drive_cfg.get("retries", {})

        return cls(
            parent_folder_id=str(drive_cfg.get("parent_folder_id", "")).strip(),
            token_path=str(oauth_cfg.get("token_path", ".secrets/google_drive_token.json")),
            client_secret_path=oauth_cfg.get("client_secret_path"),
            scopes=drive_cfg.get("scopes", DEFAULT_SCOPES),
            max_attempts=int(retry_cfg.get("max_attempts", 3)),
            retry_backoff_seconds=float(retry_cfg.get("backoff_seconds", 2.0)),
        )

    def authenticate_interactive(self) -> Path:
        if not self.client_secret_path:
            raise ValueError("Missing oauth.client_secret_path for Google Drive auth flow.")

        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_path), self.scopes)
        creds = flow.run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return self.token_path

    def _build_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)

        if not creds:
            raise FileNotFoundError(
                f"Google Drive token not found at {self.token_path}. Run drive-auth first."
            )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("drive", "v3", credentials=creds)

    def _retry(self, operation):
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                time.sleep(self.retry_backoff_seconds * attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _safe_name(name: str) -> str:
        return name.replace("'", "\\'")

    def _find_folder(self, service, *, parent_id: str, name: str) -> Optional[str]:
        query = (
            f"mimeType='application/vnd.google-apps.folder' and trashed=false and "
            f"name='{self._safe_name(name)}' and '{parent_id}' in parents"
        )
        response = self._retry(
            lambda: service.files().list(
                q=query,
                spaces="drive",
                fields="files(id,name)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
        )
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def _create_folder(self, service, *, parent_id: str, name: str) -> str:
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        created = self._retry(
            lambda: service.files().create(
                body=metadata,
                fields="id",
                supportsAllDrives=True,
            ).execute()
        )
        return created["id"]

    def ensure_folder(self, service, *, parent_id: str, name: str) -> str:
        existing = self._find_folder(service, parent_id=parent_id, name=name)
        if existing:
            return existing
        return self._create_folder(service, parent_id=parent_id, name=name)

    def _upload_single_file(self, service, *, file_path: Path, parent_id: str, mime_type: str) -> Dict[str, str]:
        from googleapiclient.http import MediaFileUpload

        if not file_path.exists():
            raise FileNotFoundError(f"File not found for Drive upload: {file_path}")

        media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
        body = {"name": file_path.name, "parents": [parent_id]}
        uploaded = self._retry(
            lambda: service.files().create(
                body=body,
                media_body=media,
                fields="id,webViewLink",
                supportsAllDrives=True,
            ).execute()
        )
        return {
            "id": uploaded.get("id"),
            "webViewLink": uploaded.get("webViewLink"),
        }

    @staticmethod
    def _date_parts_for_run(run_dir: Path) -> tuple[str, str, str]:
        match = re.search(r"run_(\d{8})_(\d{6})", run_dir.name)
        if match:
            date_token = match.group(1)
            return date_token[0:4], date_token[4:6], date_token[6:8]
        now = datetime.now()
        return now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")

    def upload_run_artifacts(
        self,
        *,
        run_dir: Path,
        run_folder_name: str,
        video_path: Path,
        metadata_path: Path,
        upload_files: List[str],
    ) -> DriveUploadResult:
        service = self._build_service()
        year, month, day = self._date_parts_for_run(run_dir)

        year_id = self.ensure_folder(service, parent_id=self.parent_folder_id, name=year)
        month_id = self.ensure_folder(service, parent_id=year_id, name=month)
        day_id = self.ensure_folder(service, parent_id=month_id, name=day)
        run_id = self.ensure_folder(service, parent_id=day_id, name=run_folder_name)

        video_result = None
        metadata_result = None
        if "video" in upload_files:
            video_result = self._upload_single_file(
                service,
                file_path=video_path,
                parent_id=run_id,
                mime_type="video/mp4",
            )
        if "metadata" in upload_files:
            metadata_result = self._upload_single_file(
                service,
                file_path=metadata_path,
                parent_id=run_id,
                mime_type="application/json",
            )

        return DriveUploadResult(
            status="success",
            parent_folder_id=self.parent_folder_id,
            run_folder_id=run_id,
            run_folder_path=f"{year}/{month}/{day}/{run_folder_name}",
            video_file_id=(video_result or {}).get("id"),
            video_link=(video_result or {}).get("webViewLink"),
            metadata_file_id=(metadata_result or {}).get("id"),
            metadata_link=(metadata_result or {}).get("webViewLink"),
            error=None,
        )

    @staticmethod
    def to_metadata_dict(result: DriveUploadResult) -> Dict[str, Any]:
        return {
            "drive_upload_status": result.status,
            "drive_parent_folder_id": result.parent_folder_id,
            "drive_run_folder_id": result.run_folder_id,
            "drive_run_folder_path": result.run_folder_path,
            "drive_video_file_id": result.video_file_id,
            "drive_video_link": result.video_link,
            "drive_metadata_file_id": result.metadata_file_id,
            "drive_metadata_link": result.metadata_link,
            "drive_upload_error": result.error,
        }


def default_drive_metadata(parent_folder_id: Optional[str] = None) -> Dict[str, Any]:
    parsed_parent = None
    if parent_folder_id:
        try:
            parsed_parent = _extract_folder_id(parent_folder_id)
        except ValueError:
            parsed_parent = parent_folder_id
    return {
        "drive_upload_status": "skipped",
        "drive_parent_folder_id": parsed_parent,
        "drive_run_folder_id": None,
        "drive_run_folder_path": None,
        "drive_video_file_id": None,
        "drive_video_link": None,
        "drive_metadata_file_id": None,
        "drive_metadata_link": None,
        "drive_upload_error": None,
    }
