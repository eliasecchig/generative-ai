import logging
import google.auth
from google.cloud import aiplatform
from google.oauth2.credentials import Credentials

def setup_gcp():
    """Initialize GCP authentication and setup."""
    try:
        aiplatform.init()
    except Exception as e:
        raise Exception(f"Failed to initialize GCP: {str(e)}")

def verify_credentials():
    """Verify GCP credentials and return current project and account."""
    try:
        # Get credentials and project
        credentials, project = google.auth.default()
        
        # Debug logging
        logging.debug(f"Credential type: {type(credentials)}")
        logging.debug(f"Credential attributes: {dir(credentials)}")
        
        # Try multiple methods to get account email
        account = None
        
        # Method 1: Try _account attribute
        if hasattr(credentials, '_account'):
            account = credentials._account
            
        # Method 2: Try service_account_email
        if not account and hasattr(credentials, 'service_account_email'):
            account = credentials.service_account_email
            
        # Method 3: Try getting from token info if available
        if not account and hasattr(credentials, 'id_token'):
            try:
                import jwt
                decoded = jwt.decode(credentials.id_token, options={"verify_signature": False})
                account = decoded.get('email')
            except:
                pass
                
        # Method 4: Try getting from gcloud config as fallback
        if not account:
            try:
                import subprocess
                result = subprocess.run(['gcloud', 'config', 'get-value', 'account'], 
                                     capture_output=True, text=True)
                account = result.stdout.strip()
            except:
                pass
        
        # Fallback if all methods fail
        if not account:
            account = "Unknown account"
            
        return {
            'project': project,
            'account': account
        }
    except Exception as e:
        raise Exception(f"Failed to verify GCP credentials: {str(e)}")
