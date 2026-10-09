# Infrastructure Context and Discovery Requirements

This document outlines the architectural context of the Unicamp self-hosted cloud environment and the specific requirements for the health-check system derived from this architecture.

## 1. Knowledge Acquired: Cloud Architecture Context

### The Physical/Logical Path (Router -> Nginx -> OpenStack)
A web request traversing the Unicamp datacenter generally follows this path:
1. **The Router:** The request arrives from the internet to the public IP (e.g., `143.106.X.Y`). The datacenter edge router identifies the destination IP within Unicamp's CIDR blocks and forwards it to the correct internal hardware (often the Nginx load balancer).
2. **The Proxy (Nginx):** Nginx acts as the gateway sitting between the public internet and the private cloud. It terminates SSL connections, reads the `Host` header (e.g., `susy.ic.unicamp.br`), and proxies the request to the internal OpenStack network based on its configuration (`server_name` blocks).
3. **The Cloud Platform (OpenStack):** OpenStack manages the virtualized environment. The Nginx proxy forwards the request to an internal private IP (e.g., `192.168.X.Y`). OpenStack's networking (Neutron) routes this packet to the specific physical compute node and into the virtual switch connected to the target Virtual Machine.

### The "Shadow IT" and Rogue Domain Problem
In a large academic environment, domains and services can become scattered:
- **Dangling Subdomains:** Legacy domains pointing to obsolete or unpatched servers.
- **External Domains:** Researchers purchasing third-party domains (e.g., `mycoolresearch.com`) and pointing them to Unicamp infrastructure.
- **Hidden Services (SANs):** Multiple domains bundled into a single SSL certificate (Subject Alternative Names) for administrative convenience.

### The OpenStack Floating IP Exception
**Assumption Corrected:** Not all OpenStack hosted sites sit behind an Nginx proxy with a registered domain name.
OpenStack allows assigning direct public IPs ("Floating IPs") directly to Virtual Machines. These VMs might not be configured in Nginx and might not have a formal DNS name attached, making them accessible only via their raw IP address.

## 2. Requisites Analyzed: Health Check Approach

Based on the architectural realities, the health-check system must go beyond simple "ping" tests and act as an intelligent discovery and auditing tool.

### Requirement 1: Comprehensive Certificate Inspection (SANs)
When connecting to a target domain, the system MUST inspect the SSL/TLS certificate to extract the Subject Alternative Names (SANs).
- **Why:** This reveals other domains associated with the service that might not be formally documented but are active within the environment.

### Requirement 2: Recursive Verification
The discovery process should be recursive.
- **Workflow:**
  1. Test initial target `Domain A`.
  2. Extract `Domain B` and `Domain C` from the SSL Certificate SANs of `Domain A`.
  3. Feed `Domain B` and `Domain C` back into the testing queue to verify if they also properly resolve and respond.
- **Why:** To ensure that all configured virtual hosts (alt names) are actually routing correctly through Nginx and OpenStack.

### Requirement 3: Differentiated Approach for Domains vs. IPs
The testing logic must split depending on the nature of the target:

#### Strategy A: Target is a Domain Name
1. **DNS Resolution:** Verify the domain resolves to an IP.
2. **HTTP/HTTPS Connection:** Verify the Nginx routing and underlying OpenStack VM are responding (e.g., `200 OK`).
3. **SAN Extraction & Recursion:** Pull SANs and test them (Requirement 2).

#### Strategy B: Target is a Raw IP Address (e.g., OpenStack Floating IP)
1. **Port Probing:** Scan basic ports (80, 443, 22) to determine what services are running.
2. **Reverse DNS (PTR):** Perform a reverse lookup, though this may only yield generic compute node names.
3. **Certificate Snatching:** Attempt an HTTPS connection using the raw IP (without a specific `Host` header) to force the server to present its default certificate.
4. **SAN Extraction & Recursion:** If a certificate is presented, extract any domains listed in the SANs and feed them into the **Domain Name** testing strategy (Strategy A).

### Requirement 4: Handling CIDR Blocks (Future/Advanced)
While single-address verification is the initial focus, the system architecture should anticipate the need for CIDR-level scanning.
- **Why:** To discover rogue OpenStack Floating IPs that expose web servers directly to the internet without passing through the central Nginx proxies, effectively auditing the Unicamp IP space for shadow IT.
