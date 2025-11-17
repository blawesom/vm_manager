"""Network management module for VLAN-based VM networking.

This module provides network management for VMs using a configurable local VLAN.
It handles IP address assignment, TAP interface management, and bridge configuration.
"""
from __future__ import annotations

import subprocess
import ipaddress
import os
import logging
from pathlib import Path
from typing import Optional, Set
from dataclasses import dataclass

from . import logging_config

logger = logging_config.UnifiedLogger.get_logger(__name__)


@dataclass
class NetworkConfig:
    """Network configuration for VLAN-based networking."""
    vlan_id: int
    bridge_name: str
    subnet: str  # CIDR notation, e.g., "192.168.100.0/24"
    gateway: str  # Gateway IP, e.g., "192.168.100.1"
    dns: list[str]  # DNS servers


class NetworkManager:
    """Manages VLAN-based networking for VMs."""
    
    def __init__(
        self,
        vlan_id: int = 100,
        bridge_name: str = "br-vman",
        subnet: str = "192.168.100.0/24",
        gateway: Optional[str] = None,
        dns: Optional[list[str]] = None,
        dry_run: bool = False
    ):
        """Initialize network manager.
        
        Args:
            vlan_id: VLAN ID (default: 100)
            bridge_name: Bridge interface name (default: br-vman)
            subnet: Subnet in CIDR notation (default: 192.168.100.0/24)
            gateway: Gateway IP (default: first IP in subnet)
            dns: DNS servers (default: [8.8.8.8, 8.8.4.4])
        """
        self.vlan_id = vlan_id
        self.bridge_name = bridge_name
        self.subnet = ipaddress.ip_network(subnet, strict=False)
        self.gateway = gateway or str(self.subnet.network_address + 1)
        self.dns = dns or ["8.8.8.8", "8.8.4.4"]
        
        # Reserved IPs: gateway, network, broadcast
        self.reserved_ips: Set[str] = {
            str(self.subnet.network_address),  # Network address
            str(self.subnet.network_address + 1),  # Gateway
            str(self.subnet.broadcast_address),  # Broadcast
        }
        
        # Track allocated IPs
        self.allocated_ips: Set[str] = set()
        self.dry_run = dry_run
        
        logger.info(
            f"NetworkManager initialized: VLAN={vlan_id}, "
            f"bridge={bridge_name}, subnet={subnet}, gateway={self.gateway}, "
            f"dry_run={dry_run}"
        )
    
    def _run_command(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a system command."""
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            if check and result.returncode != 0:
                raise RuntimeError(f"Command failed: {' '.join(cmd)} - {result.stderr}")
            return result
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out: {' '.join(cmd)}")
    
    def _interface_exists(self, interface: str) -> bool:
        """Check if network interface exists."""
        try:
            self._run_command(["ip", "link", "show", interface], check=False)
            return True
        except RuntimeError:
            return False
    
    def ensure_bridge(self) -> None:
        """Ensure bridge interface exists and is configured."""
        if self.dry_run:
            logger.info(f"dry-run: would ensure bridge {self.bridge_name}")
            return
        
        bridge_exists = self._interface_exists(self.bridge_name)
        
        if not bridge_exists:
            # Create bridge
            logger.info(f"Creating bridge {self.bridge_name}")
            self._run_command(["ip", "link", "add", "name", self.bridge_name, "type", "bridge"])
            self._run_command(["ip", "link", "set", self.bridge_name, "up"])
        
        # Configure bridge IP (gateway)
        if not self._has_ip(self.bridge_name, self.gateway):
            logger.info(f"Configuring bridge IP: {self.gateway}")
            self._run_command([
                "ip", "addr", "add", f"{self.gateway}/{self.subnet.prefixlen}",
                "dev", self.bridge_name
            ])
        
        # Configure metadata service IP (169.254.169.254) on bridge
        metadata_ip = "169.254.169.254"
        if not self._has_ip(self.bridge_name, metadata_ip):
            logger.info(f"Configuring metadata service IP: {metadata_ip} on bridge")
            try:
                self._run_command([
                    "ip", "addr", "add", f"{metadata_ip}/32",
                    "dev", self.bridge_name
                ])
            except RuntimeError as e:
                # If IP already exists or other error, log but don't fail
                logger.warning(f"Could not add metadata IP {metadata_ip} to bridge: {e}")
    
    def _has_ip(self, interface: str, ip: str) -> bool:
        """Check if interface has the specified IP."""
        try:
            result = self._run_command(["ip", "addr", "show", interface])
            return ip in result.stdout
        except RuntimeError:
            return False
    
    def allocate_ip(self, vm_id: str) -> str:
        """Allocate an IP address for a VM.
        
        Args:
            vm_id: VM identifier
            
        Returns:
            Allocated IP address
            
        Raises:
            RuntimeError: If no IPs available
        """
        # Find first available IP in subnet
        for host in self.subnet.hosts():
            ip_str = str(host)
            if ip_str not in self.reserved_ips and ip_str not in self.allocated_ips:
                self.allocated_ips.add(ip_str)
                logger.info(f"Allocated IP {ip_str} for VM {vm_id}")
                return ip_str
        
        raise RuntimeError(f"No available IPs in subnet {self.subnet}")
    
    def release_ip(self, ip: str) -> None:
        """Release an allocated IP address.
        
        Args:
            ip: IP address to release
        """
        if ip in self.allocated_ips:
            self.allocated_ips.remove(ip)
            logger.info(f"Released IP {ip}")
    
    def create_tap_interface(self, vm_id: str) -> str:
        """Create a TAP interface for a VM.
        
        Args:
            vm_id: VM identifier
            
        Returns:
            TAP interface name
        """
        tap_name = f"tap-{vm_id[:8]}"  # Limit length for interface name
        
        if self.dry_run:
            logger.info(f"dry-run: would create TAP interface {tap_name} for VM {vm_id}")
            return tap_name
        
        if self._interface_exists(tap_name):
            logger.debug(f"TAP interface {tap_name} already exists")
            return tap_name
        
        # Create TAP interface
        logger.info(f"Creating TAP interface {tap_name} for VM {vm_id}")
        self._run_command([
            "ip", "tuntap", "add", "name", tap_name,
            "mode", "tap"
        ])
        
        # Set interface up
        self._run_command(["ip", "link", "set", tap_name, "up"])
        
        # Add to bridge
        self.ensure_bridge()
        self._run_command(["ip", "link", "set", tap_name, "master", self.bridge_name])
        
        return tap_name
    
    def delete_tap_interface(self, tap_name: str) -> None:
        """Delete a TAP interface.
        
        Args:
            tap_name: TAP interface name
        """
        if self.dry_run:
            logger.info(f"dry-run: would delete TAP interface {tap_name}")
            return
        
        if not self._interface_exists(tap_name):
            return
        
        logger.info(f"Deleting TAP interface {tap_name}")
        # Remove from bridge first
        try:
            self._run_command(["ip", "link", "set", tap_name, "nomaster"], check=False)
        except RuntimeError:
            pass
        
        # Delete interface
        try:
            self._run_command(["ip", "link", "delete", tap_name], check=False)
        except RuntimeError:
            logger.warning(f"Failed to delete TAP interface {tap_name}")
    
    def get_network_config(self) -> NetworkConfig:
        """Get current network configuration.
        
        Returns:
            NetworkConfig object
        """
        return NetworkConfig(
            vlan_id=self.vlan_id,
            bridge_name=self.bridge_name,
            subnet=str(self.subnet),
            gateway=self.gateway,
            dns=self.dns
        )
    
    def get_allocated_ips(self) -> Set[str]:
        """Get set of allocated IP addresses.
        
        Returns:
            Set of allocated IP addresses
        """
        return self.allocated_ips.copy()

