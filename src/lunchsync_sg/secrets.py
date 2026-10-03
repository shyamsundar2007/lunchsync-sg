"""Secret resolution helpers."""

import getpass
import os
import subprocess


def resolve_1password_secret(
    reference: str,
    service_account_keychain_service: str | None = None,
) -> str:
    """Resolve a 1Password secret reference without persisting its value.

    If OP_SERVICE_ACCOUNT_TOKEN is not already set, macOS users may configure a
    Keychain service that contains the token. The token is passed only to the
    child ``op`` process.
    """
    env = os.environ.copy()

    if not env.get("OP_SERVICE_ACCOUNT_TOKEN") and service_account_keychain_service:
        try:
            keychain_result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    getpass.getuser(),
                    "-s",
                    service_account_keychain_service,
                    "-w",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Unable to read the 1Password service token from Keychain") from exc

        env["OP_SERVICE_ACCOUNT_TOKEN"] = keychain_result.stdout.strip()

    try:
        result = subprocess.run(
            ["op", "read", reference],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("1Password CLI ('op') is not installed") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Unable to resolve the JEV API key from 1Password") from exc

    secret = result.stdout.strip()
    if not secret:
        raise RuntimeError("1Password returned an empty JEV API key")
    return secret
