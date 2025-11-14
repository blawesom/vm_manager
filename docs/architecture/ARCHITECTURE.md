# VMAN Architecture Documentation

This document provides comprehensive UML-style architecture documentation for the VMAN (Virtual Machine Manager) system.

## Table of Contents

1. [System Overview](#system-overview)
2. [Class Diagram](#class-diagram)
3. [Component Diagram](#component-diagram)
4. [Sequence Diagrams](#sequence-diagrams)
5. [State Diagrams](#state-diagrams)
6. [Deployment Diagram](#deployment-diagram)

## System Overview

VMAN is a REST-based virtual machine management system that provides:

- **VM Templates Management**: Define VM size templates (CPU, RAM)
- **VM Lifecycle Management**: Create, start, stop, restart, delete VMs
- **Disk Management**: Create, attach, detach, delete disk images
- **Network Management**: VLAN-based networking with automatic IP assignment
- **Coherence Monitoring**: Automatic database coherence checks

### Architecture Components

- **INTEL Service**: Main REST API service (FastAPI)
- **OPERATOR Service**: QEMU operations and filesystem management
- **OBSERVER Service**: Database coherence monitoring (5s polling)
- **NetworkManager**: VLAN-based network management
- **STATES DB**: SQLite database for state management

---

## Class Diagram

See [class-diagram.puml](class-diagram.puml) for the detailed class diagram.

### Key Classes

- **VMTemplate**: VM size template (name, cpu_count, ram_amount)
- **VM**: Virtual machine instance (id, template_name, state, local_ip)
- **Disk**: Disk image (id, size, mount_point, state, vm_id)
- **LocalOperator**: QEMU operations implementation
- **LocalObserver**: Coherence monitoring implementation
- **NetworkManager**: Network management implementation

---

## Component Diagram

See [component-diagram.puml](component-diagram.puml) for the detailed component diagram.

### Components

- **INTEL Service**: REST API endpoints
- **OPERATOR Service**: QEMU and filesystem operations
- **OBSERVER Service**: Coherence checks
- **NetworkManager**: Network resource management
- **Database**: SQLite state storage
- **QEMU**: Virtualization layer
- **Filesystem**: Storage for VM and disk images

---

## Sequence Diagrams

See the following sequence diagrams:

- [VM Creation Sequence](sequence-vm-create.puml)
- [VM Start Sequence](sequence-vm-start.puml)
- [Disk Attach Sequence](sequence-disk-attach.puml)
- [Observer Coherence Check](sequence-observer-check.puml)

---

## State Diagrams

See [state-diagram.puml](state-diagram.puml) for VM and Disk state transitions.

### VM States

- **created**: VM created but not started
- **running**: VM is running
- **stopped**: VM is stopped
- **error**: VM in error state

### Disk States

- **available**: Disk created but not attached
- **attached**: Disk attached to a VM
- **error**: Disk in error state

---

## Deployment Diagram

See [deployment-diagram.puml](deployment-diagram.puml) for the deployment architecture.

### Deployment Components

- **Application Server**: Runs INTEL, OPERATOR, OBSERVER services
- **Database**: SQLite database file
- **Storage**: Filesystem for VM and disk images
- **Network**: Bridge interface (br-vman) and TAP interfaces
- **QEMU**: Virtualization processes

---

## Diagrams

All diagrams are provided in PlantUML format (`.puml` files) which can be rendered using:

- [PlantUML Online Server](http://www.plantuml.com/plantuml/uml/)
- VS Code with PlantUML extension
- IntelliJ IDEA with PlantUML plugin
- Command-line: `plantuml *.puml`


