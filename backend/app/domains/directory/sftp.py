"""Fetch the HR report from each workspace's own SFTP server.

Safety rules:
- Destination: the host is resolved once and we connect to that exact address, which must
  not be loopback, link-local (cloud metadata), multicast, reserved or unspecified, and may
  be private only when the platform lists the range in HR_SFTP_ALLOWED_NETWORKS.
- Identity: credentials are sent only after the server proves it holds the host key an
  Owner trusted. A changed key stops every fetch until an Owner trusts the new one.
- Isolation: no local SSH config, known_hosts, agent or key files are ever used, so one
  workspace's connection can never borrow this server's own credentials.
- Read-only: files are only listed and read; nothing on the customer's server is changed.
"""

import asyncio
import ipaddress
import os
import socket
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import asyncssh

from app.core.config import Settings
from app.core.secrets import decrypt_secret
from app.domains.directory.models import DirectorySftpSource
from app.domains.directory.parser import MAX_FILE_BYTES

REPORT_SUFFIXES = (".xlsx", ".csv")


class SftpError(Exception):
    """A problem worth showing to the administrator as-is."""


@dataclass
class FetchedFile:
    name: str
    content: bytes
    modified: float


def _allowed_networks(settings: Settings) -> list[ipaddress._BaseNetwork]:
    networks = []
    for raw in settings.hr_sftp_allowed_networks.split(","):
        if raw.strip():
            networks.append(ipaddress.ip_network(raw.strip(), strict=False))
    return networks


async def resolve_destination(host: str, port: int, settings: Settings) -> str:
    """The single IP address we will connect to, after the destination checks."""
    host = host.strip()
    if not host:
        raise SftpError("Enter the SFTP server's address.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise SftpError(f"{host} could not be resolved.") from error
    allowed = _allowed_networks(settings)
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if any(address in network for network in allowed):
            return str(address)
        if (
            address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise SftpError(f"{host} points to {address}, which is not allowed.")
        if address.is_private:
            raise SftpError(
                f"{host} points to the private address {address}. Ask the platform team to "
                "allow this network (HR_SFTP_ALLOWED_NETWORKS) if it is reached over a VPN."
            )
        return str(address)
    raise SftpError(f"{host} has no usable address.")


def _isolated(settings: Settings) -> dict[str, object]:
    """Connection options that never touch this server's own SSH files or agent."""
    return {
        "config": None,
        "agent_path": None,
        "agent_forwarding": False,
        "connect_timeout": settings.hr_sftp_timeout_seconds,
        "login_timeout": settings.hr_sftp_timeout_seconds,
    }


async def scan_host_key(source: DirectorySftpSource, settings: Settings) -> tuple[str, str]:
    """Ask the server for its public key without logging in. Returns (key, fingerprint)."""
    address = await resolve_destination(source.host, source.port, settings)
    try:
        key = await asyncio.wait_for(
            asyncssh.get_server_host_key(address, source.port, config=None),
            timeout=settings.hr_sftp_timeout_seconds,
        )
    except (OSError, asyncssh.Error, TimeoutError) as error:
        raise SftpError(f"Could not reach {source.host}:{source.port} ({error}).") from error
    if key is None:
        raise SftpError("The server did not present a host key.")
    return key.export_public_key("openssh").decode().strip(), key.get_fingerprint("sha256")


def fingerprint(public_key: str | None) -> str | None:
    if not public_key:
        return None
    return asyncssh.import_public_key(public_key).get_fingerprint("sha256")


async def _connect(source: DirectorySftpSource, settings: Settings) -> asyncssh.SSHClientConnection:
    if not source.trusted_host_key:
        raise SftpError("Check the server and trust its key before connecting.")
    if not source.username or not source.encrypted_secret:
        raise SftpError("Enter the username and the password or private key.")
    address = await resolve_destination(source.host, source.port, settings)
    secret = decrypt_secret(source.encrypted_secret, settings)
    credentials: dict[str, object]
    if source.auth_method == "private_key":
        try:
            credentials = {"client_keys": [asyncssh.import_private_key(secret)], "password": None}
        except (asyncssh.KeyImportError, ValueError) as error:
            raise SftpError("The stored private key cannot be read. Upload it again.") from error
    else:
        credentials = {"client_keys": None, "password": secret}
    trusted = asyncssh.import_public_key(source.trusted_host_key)
    try:
        return await asyncssh.connect(
            address,
            source.port,
            username=source.username,
            known_hosts=([trusted], [], []),
            **credentials,
            **_isolated(settings),
        )
    except asyncssh.HostKeyNotVerifiable as error:
        raise SftpError(
            "The server's key has changed since it was trusted. Nothing was sent. "
            "Confirm the change with the customer, then check and trust the server again."
        ) from error
    except asyncssh.PermissionDenied as error:
        raise SftpError("The server rejected the username or credentials.") from error
    except (OSError, asyncssh.Error, TimeoutError) as error:
        raise SftpError(f"Could not connect to {source.host}:{source.port} ({error}).") from error


async def _pick_file(sftp: asyncssh.SFTPClient, remote_path: str) -> tuple[str, float, int]:
    path = remote_path.strip() or "."
    try:
        attrs = await sftp.stat(path)
    except asyncssh.SFTPError as error:
        raise SftpError(f"{path} was not found on the server.") from error
    if attrs.permissions is not None and stat.S_ISDIR(attrs.permissions):
        candidates = [
            entry
            for entry in await sftp.readdir(path)
            if entry.filename.casefold().endswith(REPORT_SUFFIXES)
            and not entry.filename.startswith(".")
            and (entry.attrs.permissions is None or stat.S_ISREG(entry.attrs.permissions))
        ]
        if not candidates:
            raise SftpError(f"No .xlsx or .csv report was found in {path}.")
        newest = max(candidates, key=lambda entry: entry.attrs.mtime or 0)
        return (
            f"{path.rstrip('/')}/{newest.filename}",
            float(newest.attrs.mtime or 0),
            int(newest.attrs.size or 0),
        )
    if not path.casefold().endswith(REPORT_SUFFIXES):
        raise SftpError("The path must be a folder or an .xlsx or .csv file.")
    return path, float(attrs.mtime or 0), int(attrs.size or 0)


async def test_connection(source: DirectorySftpSource, settings: Settings) -> str:
    """Log in and find the report without downloading it. Returns a readable result."""
    async with (
        await _connect(source, settings) as connection,
        connection.start_sftp_client() as sftp,
    ):
        path, modified, size = await _pick_file(sftp, source.remote_path)
    stamp = datetime.fromtimestamp(modified, UTC).strftime("%d %b %Y %H:%M UTC")
    return f"Connected. Latest report: {Path(path).name} ({size:,} bytes, modified {stamp})."


async def fetch_latest(source: DirectorySftpSource, settings: Settings) -> FetchedFile:
    async with (
        await _connect(source, settings) as connection,
        connection.start_sftp_client() as sftp,
    ):
        path, modified, size = await _pick_file(sftp, source.remote_path)
        if size > MAX_FILE_BYTES:
            raise SftpError(f"{Path(path).name} is larger than 10 MB.")
        async with sftp.open(path, "rb") as remote:
            content = await remote.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise SftpError(f"{Path(path).name} is larger than 10 MB.")
    return FetchedFile(name=Path(path).name, content=content, modified=modified)


def archive_copy(folder: Path, fetched: FetchedFile, status: str) -> None:
    """Keep the fetched file next to inbox drops, readable only by the service account."""
    destination = folder / ("processed" if status in ("applied", "duplicate") else "rejected")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{datetime.now(UTC):%Y%m%dT%H%M%S}-sftp-{fetched.name}"
    target.write_bytes(fetched.content)
    os.chmod(target, 0o600)
