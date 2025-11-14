VMAN
==

Description
--
A simple REST server to manage virtual machines with access to local storage and network.

Technology stack
--
* QEMU/QCOW2 for virtualization (compute, network and storage)
* SQLITE (for state management)

Architecture
--
* Main service 'INTEL' will handle API requests
* Local agent 'VM_OPERATOR' will handle QEMU operation
* Local agent 'OBSERVER' will handle checks to ensure coherence between system and database, by interacting with QEMU and local filesystem
* SQLITE database 'STATES' will store objects with their attributes

Features:
--
* VM size templates management (create, list, delete)
* VM lifecycle management (create, list, stop, start, restart, delete)
* Disk lifecycle management (create, list, attach, detach, delete)

Objects and attributes:
--
* vm: vm_template, state, local_ip
* vm_template: name, cpu_count, ram_amount
* disk: size, mount_point, state

All units are integer, RAM and Disk size are in GB.
Mouting point follow /dev/xvda naming scheme.

Rules for development
--
* Langage: Python
* Convention: PEP8
* One file per service or agent
* Service interfaces use REST to communicate, except to connect to the database
* Use ORM for database interactions abstraction
* Unit tests for all functions and attributes, including incorrect parameter values
* Global service test with 80% coverage

Steps for development
--
1) Create a comprehensive openAPI description file for all public API call for the 'INTEL' service
2) Implement INTEL service following openAPI description file
3) Implement OPERATOR service to handle QEMU and files. Add interfaces to the INTEL service
4) Implement OBSERVER service to enforce database coherence (5s polling)
5) Implement test for safety and security verification
6) Implement unified logs for all services and agents
7) Implement network management based on a fixed configurable local VLAN
8) Produce README and architecture documents using UML style
