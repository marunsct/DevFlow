import os
import hvac
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SecretsManager:
    """Manages secret retrieval from HashiCorp Vault with fallback to environment variables."""
    
    def __init__(self):
        self.vault_url = os.environ.get("VAULT_ADDR")
        self.vault_token = os.environ.get("VAULT_TOKEN")
        self.client = None
        
        if self.vault_url and self.vault_token:
            try:
                self.client = hvac.Client(url=self.vault_url, token=self.vault_token)
                if not self.client.is_authenticated():
                    logger.error("Failed to authenticate with Vault.")
                    self.client = None
            except Exception as e:
                logger.error(f"Error connecting to Vault: {e}")
                self.client = None
        else:
            logger.info("Vault credentials not found, falling back to environment variables.")

    def get_secret(self, secret_path: str, key: str) -> Optional[str]:
        """Retrieve a secret from Vault or fallback to os.environ.
        
        Args:
            secret_path (str): The logical path in Vault (e.g. 'secret/data/myapp')
            key (str): The key to retrieve.
        """
        if self.client:
            try:
                # Assuming KV v2
                read_response = self.client.secrets.kv.v2.read_secret_version(path=secret_path)
                return read_response['data']['data'].get(key)
            except hvac.exceptions.InvalidPath:
                logger.warning(f"Secret path {secret_path} not found in Vault.")
            except Exception as e:
                logger.error(f"Error reading secret from Vault: {e}")
        
        # Fallback
        env_key = key.upper()
        return os.environ.get(env_key)

secrets = SecretsManager()
