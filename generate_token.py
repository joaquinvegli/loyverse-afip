from __future__ import print_function
import os
from google_auth_oauthlib.flow import InstalledAppFlow

# 1) Leer variables de entorno
CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: faltan variables de entorno:")
        print("  GOOGLE_OAUTH_CLIENT_ID")
        print("  GOOGLE_OAUTH_CLIENT_SECRET")
        return

    print("Abriendo navegador para autorizar Google Drive…")

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        SCOPES,
    )

    creds = flow.run_local_server(port=0)

    print("\n===========================================")
    print("REFRESH TOKEN GENERADO:")
    print(creds.refresh_token)
    print("===========================================")

if __name__ == "__main__":
    main()
