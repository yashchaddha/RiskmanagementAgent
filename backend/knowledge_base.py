"""
ISO 27001:2022 Knowledge Base
Contains comprehensive information about the standard for the auditor agent
"""

# ISO 27001:2022 knowledge base
ISO_27001_KNOWLEDGE = {
  "ISO27001_2022": {
    "Clauses": [
      {
        "id": "4",
        "title": "Context of the Organization",
        "category": "Clause",
        "description": "Understanding the organization, stakeholders, and ISMS scope.",
        "subclauses": [
          {"id": "4.1", "title": "Understanding the organization and its context"},
          {"id": "4.2", "title": "Understanding the needs and expectations of interested parties"},
          {"id": "4.3", "title": "Determining the scope of the ISMS"},
          {"id": "4.4", "title": "Information security management system"}
        ]
      },
      {
        "id": "5",
        "title": "Leadership",
        "category": "Clause",
        "description": "Leadership, commitment, roles, and policy.",
        "subclauses": [
          {"id": "5.1", "title": "Leadership and commitment"},
          {"id": "5.2", "title": "Information security policy"},
          {"id": "5.3", "title": "Organizational roles, responsibilities, and authorities"}
        ]
      },
      {
        "id": "6",
        "title": "Planning",
        "category": "Clause",
        "description": "ISMS risk planning, objectives, and treatment.",
        "subclauses": [
          {"id": "6.1", "title": "Actions to address risks and opportunities"},
          {"id": "6.1.2", "title": "Information security risk assessment"},
          {"id": "6.1.3", "title": "Information security risk treatment"},
          {"id": "6.2", "title": "Information security objectives and planning to achieve them"}
        ]
      },
      {
        "id": "7",
        "title": "Support",
        "category": "Clause",
        "description": "Resources, competence, awareness, communication, and documentation.",
        "subclauses": [
          {"id": "7.1", "title": "Resources"},
          {"id": "7.2", "title": "Competence"},
          {"id": "7.3", "title": "Awareness"},
          {"id": "7.4", "title": "Communication"},
          {"id": "7.5", "title": "Documented information"}
        ]
      },
      {
        "id": "8",
        "title": "Operation",
        "category": "Clause",
        "description": "Operational planning and risk treatment.",
        "subclauses": [
          {"id": "8.1", "title": "Operational planning and control"},
          {"id": "8.2", "title": "Information security risk assessment"},
          {"id": "8.3", "title": "Information security risk treatment"}
        ]
      },
      {
        "id": "9",
        "title": "Performance Evaluation",
        "category": "Clause",
        "description": "Monitoring, auditing, and reviewing performance.",
        "subclauses": [
          {"id": "9.1", "title": "Monitoring, measurement, analysis and evaluation"},
          {"id": "9.2", "title": "Internal audit"},
          {"id": "9.3", "title": "Management review"}
        ]
      },
      {
        "id": "10",
        "title": "Improvement",
        "category": "Clause",
        "description": "Corrective actions and continual improvement.",
        "subclauses": [
          {"id": "10.1", "title": "Nonconformity and corrective action"},
          {"id": "10.2", "title": "Continual improvement"}
        ]
      }
    ],
    "Annex_A": [
      {
        "id": "A.5",
        "title": "Organizational Controls",
        "category": "Annex A",
        "description": "Policies, roles, compliance, supplier management (37 controls).",
        "controls": [
          {"id": "A.5.1", "title": "Policies for information security", "description": "Establish and review information security policies."},
          {"id": "A.5.2", "title": "Information security roles and responsibilities", "description": "Define and assign information security responsibilities."},
          {"id": "A.5.3", "title": "Segregation of duties", "description": "Reduce risk of misuse by segregating duties."},
          {"id": "A.5.4", "title": "Management responsibilities", "description": "Ensure ISMS roles are properly supported."},
          {"id": "A.5.5", "title": "Contact with authorities", "description": "Maintain contact with authorities as relevant."},
          {"id": "A.5.6", "title": "Contact with special interest groups", "description": "Maintain contact with industry and security groups."},
          {"id": "A.5.7", "title": "Threat intelligence", "description": "Gather and use threat intelligence for risk decisions."},
          {"id": "A.5.8", "title": "Information security in project management", "description": "Apply information security to project management."},
          {"id": "A.5.9", "title": "Inventory of information and assets", "description": "Identify and manage information assets."},
          {"id": "A.5.10", "title": "Acceptable use of information and assets", "description": "Define acceptable use rules for assets."},
          {"id": "A.5.11", "title": "Return of assets", "description": "Return assets upon termination or change of role."},
          {"id": "A.5.12", "title": "Classification of information", "description": "Classify information according to value and sensitivity."},
          {"id": "A.5.13", "title": "Labelling of information", "description": "Label classified information appropriately."},
          {"id": "A.5.14", "title": "Information transfer", "description": "Protect information in transfer."},
          {"id": "A.5.15", "title": "Access restrictions", "description": "Restrict access to information and assets."},
          {"id": "A.5.16", "title": "Identity management", "description": "Manage user identities securely."},
          {"id": "A.5.17", "title": "Authentication information", "description": "Protect authentication credentials."},
          {"id": "A.5.18", "title": "Access rights", "description": "Review and adjust access rights regularly."},
          {"id": "A.5.19", "title": "Information security in supplier relationships", "description": "Address security in supplier agreements."},
          {"id": "A.5.20", "title": "Managing information security in supplier relationships", "description": "Monitor and manage supplier risks."},
          {"id": "A.5.21", "title": "Addressing information security in supplier agreements", "description": "Include security requirements in contracts."},
          {"id": "A.5.22", "title": "Monitoring, review and change management of supplier services", "description": "Review supplier services for security compliance."},
          {"id": "A.5.23", "title": "Information security for use of cloud services", "description": "Ensure secure use of cloud services."},
          {"id": "A.5.24", "title": "Information security incident management planning and preparation", "description": "Plan and prepare for incidents."},
          {"id": "A.5.25", "title": "Assessment and decision on information security events", "description": "Assess events and decide if they are incidents."},
          {"id": "A.5.26", "title": "Response to information security incidents", "description": "Respond to incidents effectively."},
          {"id": "A.5.27", "title": "Learning from information security incidents", "description": "Learn and improve from incidents."},
          {"id": "A.5.28", "title": "Collection of evidence", "description": "Collect and protect evidence properly."},
          {"id": "A.5.29", "title": "Information security during disruption", "description": "Plan security during disruptions."},
          {"id": "A.5.30", "title": "ICT readiness for business continuity", "description": "Prepare ICT for business continuity."},
          {"id": "A.5.31", "title": "Legal, statutory, regulatory and contractual requirements", "description": "Identify and comply with requirements."},
          {"id": "A.5.32", "title": "Intellectual property rights", "description": "Respect and protect IPR."},
          {"id": "A.5.33", "title": "Protection of records", "description": "Protect organizational records."},
          {"id": "A.5.34", "title": "Privacy and protection of PII", "description": "Protect personally identifiable information."},
          {"id": "A.5.35", "title": "Independent review of information security", "description": "Review ISMS independently."},
          {"id": "A.5.36", "title": "Compliance with policies and standards", "description": "Ensure compliance with internal requirements."},
          {"id": "A.5.37", "title": "Documented operating procedures", "description": "Establish and maintain documented procedures."}
        ]
      },
      {
        "id": "A.6",
        "title": "People Controls",
        "category": "Annex A",
        "description": "Human resource security controls (8).",
        "controls": [
          {"id": "A.6.1", "title": "Screening", "description": "Screen employees before hiring."},
          {"id": "A.6.2", "title": "Terms and conditions of employment", "description": "Define security responsibilities in contracts."},
          {"id": "A.6.3", "title": "Information security awareness, education and training", "description": "Provide awareness and training programs."},
          {"id": "A.6.4", "title": "Disciplinary process", "description": "Establish disciplinary actions for breaches."},
          {"id": "A.6.5", "title": "Responsibilities after employment", "description": "Define security responsibilities after termination."},
          {"id": "A.6.6", "title": "Confidentiality or nondisclosure agreements", "description": "Ensure NDAs are in place."},
          {"id": "A.6.7", "title": "Remote working", "description": "Apply controls for remote working."},
          {"id": "A.6.8", "title": "Information security event reporting", "description": "Ensure staff report security events."}
        ]
      },
      {
        "id": "A.7",
        "title": "Physical Controls",
        "category": "Annex A",
        "description": "Physical and environmental security controls (14).",
        "controls": [
          {"id": "A.7.1", "title": "Physical security perimeters", "description": "Define secure perimeters."},
          {"id": "A.7.2", "title": "Physical entry controls", "description": "Restrict access to secure areas."},
          {"id": "A.7.3", "title": "Securing offices, rooms and facilities", "description": "Protect offices and rooms."},
          {"id": "A.7.4", "title": "Physical security monitoring", "description": "Monitor physical security areas."},
          {"id": "A.7.5", "title": "Protecting against physical and environmental threats", "description": "Implement protections against threats."},
          {"id": "A.7.6", "title": "Working in secure areas", "description": "Apply controls in secure areas."},
          {"id": "A.7.7", "title": "Clear desk and clear screen", "description": "Enforce clean desk and screen policy."},
          {"id": "A.7.8", "title": "Equipment siting and protection", "description": "Protect equipment from threats."},
          {"id": "A.7.9", "title": "Security of assets off-premises", "description": "Protect assets taken offsite."},
          {"id": "A.7.10", "title": "Storage media", "description": "Protect storage media."},
          {"id": "A.7.11", "title": "Supporting utilities", "description": "Protect supporting utilities."},
          {"id": "A.7.12", "title": "Cabling security", "description": "Protect power and data cabling."},
          {"id": "A.7.13", "title": "Equipment maintenance", "description": "Maintain equipment securely."},
          {"id": "A.7.14", "title": "Secure disposal or reuse of equipment", "description": "Dispose of or reuse securely."}
        ]
      },
      {
        "id": "A.8",
        "title": "Technological Controls",
        "category": "Annex A",
        "description": "Technical security measures (34).",
        "controls": [
          {"id": "A.8.1", "title": "User endpoint devices", "description": "Secure endpoint devices."},
          {"id": "A.8.2", "title": "Privileged access rights", "description": "Manage privileged rights securely."},
          {"id": "A.8.3", "title": "Information access restriction", "description": "Enforce access restrictions."},
          {"id": "A.8.4", "title": "Access to source code", "description": "Control access to source code."},
          {"id": "A.8.5", "title": "Secure authentication", "description": "Use secure authentication mechanisms."},
          {"id": "A.8.6", "title": "Capacity management", "description": "Manage system capacity for performance."},
          {"id": "A.8.7", "title": "Protection against malware", "description": "Implement anti-malware measures."},
          {"id": "A.8.8", "title": "Management of technical vulnerabilities", "description": "Identify and manage vulnerabilities."},
          {"id": "A.8.9", "title": "Configuration management", "description": "Secure system configurations."},
          {"id": "A.8.10", "title": "Information deletion", "description": "Securely delete information."},
          {"id": "A.8.11", "title": "Data masking", "description": "Apply masking to sensitive data."},
          {"id": "A.8.12", "title": "Data leakage prevention", "description": "Prevent unauthorized data leakage."},
          {"id": "A.8.13", "title": "Information backup", "description": "Perform and test backups regularly."},
          {"id": "A.8.14", "title": "Logging", "description": "Enable logging for security events."},
          {"id": "A.8.15", "title": "Monitoring activities", "description": "Monitor systems and user activities."},
          {"id": "A.8.16", "title": "Clock synchronization", "description": "Synchronize system clocks."},
          {"id": "A.8.17", "title": "Installation of software on operational systems", "description": "Control software installation."},
          {"id": "A.8.18", "title": "Vulnerability scanning", "description": "Conduct regular vulnerability scans."},
          {"id": "A.8.19", "title": "Network security", "description": "Secure network infrastructure."},
          {"id": "A.8.20", "title": "Security of network services", "description": "Secure external/internal network services."},
          {"id": "A.8.21", "title": "Segregation of networks", "description": "Segregate networks based on risk."},
          {"id": "A.8.22", "title": "Web filtering", "description": "Restrict and control web usage."},
          {"id": "A.8.23", "title": "Cryptographic controls", "description": "Use cryptography to protect data."},
          {"id": "A.8.24", "title": "Key management", "description": "Manage cryptographic keys securely."},
          {"id": "A.8.25", "title": "Secure system engineering principles", "description": "Apply secure design principles."},
          {"id": "A.8.26", "title": "Secure development lifecycle", "description": "Integrate security into development."},
          {"id": "A.8.27", "title": "Application security requirements", "description": "Define and apply application security requirements."},
          {"id": "A.8.28", "title": "Secure coding", "description": "Adopt secure coding practices."},
          {"id": "A.8.29", "title": "Security testing in development and acceptance", "description": "Perform security testing."},
          {"id": "A.8.30", "title": "Outsourced development", "description": "Manage risks in outsourced development."},
          {"id": "A.8.31", "title": "Separation of development, test and production environments", "description": "Segregate environments properly."},
          {"id": "A.8.32", "title": "Change management", "description": "Control changes securely."},
          {"id": "A.8.33", "title": "Test data", "description": "Protect and anonymize test data."},
          {"id": "A.8.34", "title": "Audit logging", "description": "Ensure audit logs are enabled and protected."}
        ]
      }
    ]
  }
}

