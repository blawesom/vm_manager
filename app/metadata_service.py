"""Metadata service for cloud-init support.

This module provides an AWS EC2-compatible metadata service that runs on the bridge
interface, allowing VMs to retrieve metadata via the standard 169.254.169.254 endpoint.
"""
from __future__ import annotations

import http.server
import socketserver
import threading
import base64
import os
import re
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import urlparse, unquote

from . import logging_config, db, models

logger = logging_config.UnifiedLogger.get_logger(__name__, logging_config.UnifiedLogger.SERVICE_OPERATOR)


class MetadataRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for AWS EC2 metadata API."""
    
    def __init__(self, *args, db_session_factory, storage_path: Path, **kwargs):
        self.db_session_factory = db_session_factory
        self.storage_path = storage_path
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(f"Metadata service: {format % args}")
    
    def do_GET(self):
        """Handle GET requests for metadata API."""
        try:
            parsed = urlparse(self.path)
            path = parsed.path.strip('/')
            
            # Identify VM by source IP (most reliable method)
            client_ip = self.client_address[0]
            vm = self._get_vm_by_ip(client_ip)
            
            # If not found by IP, try MAC from path (for network interface queries)
            if not vm:
                mac = self._extract_mac_from_path(path)
                if mac:
                    vm = self._get_vm_by_mac(mac)
            
            if not vm:
                self.send_error(404, f"VM not found for IP {client_ip}")
                return
            
            # Handle metadata requests
            if path.startswith('latest/'):
                response = self._handle_metadata_request(path[7:], vm)  # Remove 'latest/'
                if response is None:
                    self.send_error(404, "Metadata path not found")
                    return
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(response.encode('utf-8'))))
                self.end_headers()
                self.wfile.write(response.encode('utf-8'))
            else:
                self.send_error(404, "Invalid metadata path")
                
        except Exception as e:
            logger.error(f"Error handling metadata request: {e}", exc_info=True)
            self.send_error(500, f"Internal server error: {e}")
    
    def _extract_mac_from_path(self, path: str) -> Optional[str]:
        """Extract MAC address from request path.
        
        For network interface queries, MAC is in the path:
        /latest/meta-data/network/interfaces/macs/{mac}/...
        """
        mac_match = re.search(r'/macs/([0-9a-f:]{17})/', path)
        if mac_match:
            return mac_match.group(1).lower()
        return None
    
    def _get_vm_by_mac(self, mac: str) -> Optional[models.VM]:
        """Find VM by MAC address.
        
        We store MAC addresses in VM directories (mac.txt) and can also
        query the database for VMs and match by reading their mac.txt files.
        """
        session = self.db_session_factory()
        try:
            # Get all VMs and check their MAC files
            vms = session.query(models.VM).all()
            for vm in vms:
                vm_dir = self.storage_path / "vms" / vm.id
                mac_file = vm_dir / "mac.txt"
                if mac_file.exists():
                    stored_mac = mac_file.read_text().strip().lower()
                    if stored_mac == mac.lower():
                        return vm
            return None
        finally:
            session.close()
    
    def _get_vm_by_ip(self, ip: str) -> Optional[models.VM]:
        """Find VM by IP address (fallback method)."""
        session = self.db_session_factory()
        try:
            vm = session.query(models.VM).filter(models.VM.local_ip == ip).first()
            return vm
        finally:
            session.close()
    
    def _get_metadata(self, vm_id: str) -> Optional[models.VMMetadata]:
        """Get metadata from database."""
        session = self.db_session_factory()
        try:
            metadata = session.query(models.VMMetadata).filter(
                models.VMMetadata.vm_id == vm_id
            ).first()
            return metadata
        finally:
            session.close()
    
    def _handle_metadata_request(self, path: str, vm: models.VM) -> Optional[str]:
        """Handle metadata API requests.
        
        Implements AWS EC2 metadata API endpoints:
        - meta-data/instance-id
        - meta-data/local-ipv4
        - meta-data/public-ipv4
        - meta-data/hostname
        - meta-data/network/interfaces/macs/{mac}/local-ipv4
        - meta-data/public-keys/0/openssh-key
        - user-data (base64 encoded)
        """
        # Handle root listing
        if path == 'meta-data/' or path == 'meta-data':
            return '\n'.join([
                'instance-id',
                'local-ipv4',
                'public-ipv4',
                'hostname',
                'network/',
                'public-keys/',
            ])
        
        if path == 'user-data':
            metadata = self._get_metadata(vm.id)
            if metadata and metadata.user_data:
                # AWS EC2 returns user-data as base64 encoded
                return base64.b64encode(metadata.user_data.encode('utf-8')).decode('utf-8')
            return ''
        
        # Meta-data endpoints
        if path == 'meta-data/instance-id':
            return vm.id
        
        if path == 'meta-data/local-ipv4':
            return vm.local_ip or ''
        
        if path == 'meta-data/public-ipv4':
            # For now, same as local IP
            return vm.local_ip or ''
        
        if path == 'meta-data/hostname':
            metadata = self._get_metadata(vm.id)
            if metadata and metadata.hostname:
                return metadata.hostname
            # Default to VM ID
            return vm.id
        
        # Network interfaces
        if path.startswith('meta-data/network/interfaces/macs/'):
            # Extract MAC from path
            mac_match = re.search(r'/macs/([0-9a-f:]{17})/', path)
            if mac_match:
                mac = mac_match.group(1).lower()
                # Verify this MAC belongs to the VM
                vm_dir = self.storage_path / "vms" / vm.id
                mac_file = vm_dir / "mac.txt"
                if mac_file.exists() and mac_file.read_text().strip().lower() == mac:
                    remaining = path.split(f'/macs/{mac}/')[-1]
                    if remaining == 'local-ipv4':
                        return vm.local_ip or ''
                    elif remaining == '' or remaining == '/':
                        return '\n'.join(['local-ipv4', 'mac'])
                    elif remaining == 'mac':
                        return mac
        
        # Public keys
        if path == 'meta-data/public-keys/':
            metadata = self._get_metadata(vm.id)
            if metadata and metadata.ssh_keys:
                # Return index for first key
                return '0=default'
            return ''
        
        if path == 'meta-data/public-keys/0/openssh-key':
            metadata = self._get_metadata(vm.id)
            if metadata and metadata.ssh_keys:
                # Return first SSH key (or all if multiple)
                keys = metadata.ssh_keys.strip().split('\n')
                return keys[0] if keys else ''
            return ''
        
        return None


class MetadataService:
    """AWS EC2-compatible metadata service for cloud-init."""
    
    def __init__(
        self,
        db_session_factory,
        storage_path: Path,
        bind_ip: str = "169.254.169.254",
        port: int = 80,
        bridge_name: str = "br-vman"
    ):
        """Initialize metadata service.
        
        Args:
            db_session_factory: SQLAlchemy session factory
            storage_path: Path to VM storage directory
            bind_ip: IP address to bind metadata service (default: 169.254.169.254)
            port: Port to listen on (default: 80)
            bridge_name: Bridge interface name
        """
        self.db_session_factory = db_session_factory
        self.storage_path = storage_path
        self.bind_ip = bind_ip
        self.port = port
        self.bridge_name = bridge_name
        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
        
        logger.info(
            f"MetadataService initialized: bind_ip={bind_ip}, port={port}, "
            f"bridge={bridge_name}, storage={storage_path}"
        )
    
    def start(self) -> None:
        """Start the metadata service HTTP server."""
        if self.running:
            logger.warning("Metadata service is already running")
            return
        
        try:
            # Create a handler class with bound dependencies
            db_factory = self.db_session_factory
            storage = self.storage_path
            
            class CustomHandler(MetadataRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(
                        *args,
                        db_session_factory=db_factory,
                        storage_path=storage,
                        **kwargs
                    )
            
            # Create server
            self.server = socketserver.TCPServer(
                (self.bind_ip, self.port),
                CustomHandler,
                bind_and_activate=False
            )
            
            # Allow address reuse
            self.server.allow_reuse_address = True
            
            # Set socket options
            self.server.socket.setsockopt(
                socketserver.socket.SOL_SOCKET,
                socketserver.socket.SO_REUSEADDR,
                1
            )
            
            # Bind and activate
            self.server.server_bind()
            self.server.server_activate()
            
            # Start server in background thread
            self.server_thread = threading.Thread(
                target=self._run_server,
                daemon=True,
                name="MetadataService"
            )
            self.server_thread.start()
            self.running = True
            
            logger.info(f"Metadata service started on {self.bind_ip}:{self.port}")
            
        except OSError as e:
            if e.errno == 13:  # Permission denied
                logger.error(
                    f"Permission denied binding to {self.bind_ip}:{self.port}. "
                    f"Metadata service requires root privileges or CAP_NET_BIND_SERVICE capability."
                )
            elif e.errno == 98:  # Address already in use
                logger.warning(f"Address {self.bind_ip}:{self.port} already in use")
            else:
                logger.error(f"Failed to start metadata service: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to start metadata service: {e}", exc_info=True)
            raise
    
    def _run_server(self) -> None:
        """Run the HTTP server (called in background thread)."""
        try:
            logger.info("Metadata service server thread started")
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Metadata service server error: {e}", exc_info=True)
        finally:
            logger.info("Metadata service server thread stopped")
    
    def stop(self) -> None:
        """Stop the metadata service."""
        if not self.running:
            return
        
        self.running = False
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)
        
        logger.info("Metadata service stopped")
    
    def is_running(self) -> bool:
        """Check if metadata service is running."""
        return self.running and self.server is not None

