"""App settings declared in the A2C request (generated; edit the request, not this file).

load_settings() reads each setting once from the environment and fails at start-up,
naming every missing required setting. A secret is read from NAME, or on AWS Lambda from
the secret store through NAME_SECRET_ARN.
"""
import os
from typing import Dict, Optional

DECLARED: Dict[str, Optional[str]] = {
    'TABLE_NAME': None,
    'SETTLEMENT_API_URL': 'http://settlement-service.internal:8080',
    'RECON_TENANT': 'acme'
}
SECRETS = []


class MissingSettings(RuntimeError):
    """Required settings are not set."""


def _secret_from_arn(name: str) -> Optional[str]:
    arn = os.getenv(f"{name}_SECRET_ARN")
    if not arn:
        return None
    import boto3                                   # only on AWS
    return boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]


def load_settings(environ=None) -> Dict[str, str]:
    environ = os.environ if environ is None else environ
    values, missing = {}, []
    for name, default in DECLARED.items():
        value = environ.get(name) or (_secret_from_arn(name) if name in SECRETS and environ is os.environ
                                      else None) or default
        if value is None:
            missing.append(name)
        else:
            values[name] = value
    if missing:
        raise MissingSettings("missing required settings: " + ", ".join(missing))
    return values
