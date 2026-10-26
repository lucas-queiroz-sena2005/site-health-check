# Product Definition: Site Health Check

## Vision
A blackbox network and infrastructure monitoring tool that tests availability and response times from the outside in. It features an interactive SPA frontend, a FastAPI backend, and an independent execution engine.

## Core Features
- **Automatic Schedules**: Run sequential tests against mapped targets at configured intervals.
- **Automated Alerts**: Deliver real-time notifications to Google Chat (Cards v2) and Slack (Block Kit) on service failures, ghost hosts, or expiring certificates, linking directly to the management dashboard.
- **Orthogonal Explorer REST API**: Dedicated, SQL-paginated and sorted endpoints for Hosts (`/hosts`), Services (`/services`), and HTTP Checks (`/checks`), plus an on-demand IP Detail Drawer endpoint (`/hosts/{ip}`).
- **Database-Agnostic IP Sorting & Pruning**: Normalized IPv4/IPv6 sort keys and configurable finalization pruning for void hosts and routine closed ports.
- **Recursive SAN Check**: Automatically extract and scan Subject Alternative Names from TLS/SSL certificates.
- **Consolidated History**: Analyze stability, recurring slowdowns, and peak-time failures.
- **Advanced Filtering**: Isolate specific services even within massive CIDR blocks.

## Target Audience
System administrators, SREs, and network engineers needing granular, agentless visibility into their infrastructure's external availability and health.
