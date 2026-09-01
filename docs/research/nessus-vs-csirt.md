# Nessus vs. CSIRT

This document explains what Nessus and CSIRT are, their differences, and how they relate to the `site-health-check` project.

## Nessus
**Nessus** is a widely used vulnerability assessment solution and vulnerability scanner developed by Tenable, Inc. [1] It is designed to proactively identify, prioritize, and remediate security weaknesses (such as missing patches, software flaws, and misconfigurations) across IT infrastructure. [2]
* **Nature:** It is a software tool / platform.
* **Purpose:** Proactive security assessment and auditing.

## CSIRT (Computer Security Incident Response Team)
A **CSIRT** is a formal organization or team of IT and cybersecurity professionals responsible for receiving, reviewing, and responding to computer security incidents. [3] Their operations and service frameworks are often defined by global organizations like FIRST (Forum of Incident Response and Security Teams) [4] and national agencies like CISA (Cybersecurity & Infrastructure Security Agency). [5]
* **Nature:** It is a human team and organizational capability.
* **Purpose:** Reactive incident response, threat containment, and recovery (along with proactive monitoring).

## Comparison in the Context of a `site-health-check` Tool
While both Nessus and a CSIRT deal with cybersecurity and IT infrastructure, they occupy completely different layers of an organization's security posture, and interact with a custom `site-health-check` tool in distinct ways:

1. **Tool vs. Team:** Nessus is an automated software tool that scans for vulnerabilities. A CSIRT is the team of human experts that manages and responds to incidents. 
2. **Relationship to `site-health-check`:**
   * **Nessus:** A `site-health-check` tool performs basic operational and health monitoring (e.g., uptime, basic TLS validity, simple configuration). Nessus is a much heavier, specialized security scanner. They are complementary; a health check ensures the site is running properly, while Nessus ensures the underlying infrastructure is free of known CVEs.
   * **CSIRT:** The CSIRT would be the **consumer** of the data produced by the `site-health-check` tool. If the tool detects a site defacement, unexpected downtime, or unauthorized configuration changes, it would trigger an alert to the CSIRT, which would then investigate and mitigate the incident.

## Sources
[1] Tenable Official Documentation - Nessus Overview
[2] TechTarget - What is Tenable Nessus?
[3] Akamai - What is a CSIRT?
[4] FIRST - CSIRT Services Framework
[5] CISA - Cybersecurity Incident Response
