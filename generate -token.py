import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# The scopes for uploading and checking analytics
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']

def main():
    # Path to your client_secrets.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    client_secrets_file = os.path.join(script_dir, 'client_secrets.json')
    
    if not os.path.exists(client_secrets_file):
        import glob
        matches = glob.glob(os.path.join(script_dir, 'client_secret*.json'))
        if matches:
            client_secrets_file = matches[0]
            print(f"Using client secrets file found: {client_secrets_file}")
        else:
            print(f"Error: client_secrets.json not found in {script_dir}.")
            print("Please download your OAuth 2.0 Client ID JSON from Google Cloud Console.")
            return

    # Create the flow using the client secrets file
    # This requires 'google-auth-oauthlib' to be installed
    try:
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
        
        # Try to extract port from client secrets redirect URIs to avoid mismatch
        port = 0
        try:
            with open(client_secrets_file, 'r') as f:
                data = json.load(f)
            for key in ['web', 'installed']:
                if key in data and 'redirect_uris' in data[key]:
                    for uri in data[key]['redirect_uris']:
                        if 'localhost:' in uri:
                            port = int(uri.split('localhost:')[1].split('/')[0])
                            break
                        elif '127.0.0.1:' in uri:
                            port = int(uri.split('127.0.0.1:')[1].split('/')[0])
                            break
        except Exception as e:
            print(f"Note: Could not parse redirect URI port from client secrets: {e}")
        
        # Run the local server to complete the auth flow
        # Note: This will open your default web browser for login.
        print(f"\nAttempting to open browser for authentication on port {port}...")
        credentials = flow.run_local_server(port=port, prompt='consent')
        
        # Convert credentials to a JSON format that m2.py expects
        # This format is compatible with Credentials.from_authorized_user_file
        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Save to youtube_token.json
        output_file = os.path.join(script_dir, 'youtube_token.json')
        with open(output_file, 'w') as f:
            json.dump(creds_data, f, indent=4)
        
        print("\n" + "="*40)
        print("SUCCESS: YouTube Token Generated!")
        print("="*40)
        print(f"Token saved to: {output_file}")
        print("\nINSTRUCTIONS:")
        print("1. Keep this 'youtube_token.json' in the same folder as m2.py.")
        print("2. OR: Copy the text inside 'youtube_token.json' and set it as an")
        print("   environment variable named 'YOUTUBE_TOKEN' for the bot to use.")
        print("="*40)

    except Exception as e:
        print(f"\nError during token generation: {e}")
        print("Make sure you have installed the requirements: pip install google-auth-oauthlib google-auth-httplib2")

if __name__ == '__main__':
    main()
