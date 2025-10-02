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
          {"id": "4.2", "title": "Understanding the needs and expectations of interested parties"}
        ]
      },
      {
        "id": "5",
        "title": "Leadership",
        "category": "Clause",
        "description": "Leadership, commitment, roles, and policy.",
        "subclauses": [
          {"id": "5.1", "title": "Leadership and commitment"}
        ]
      },
      {
        "id": "6",
        "title": "Planning",
        "category": "Clause",
        "description": "ISMS risk planning, objectives, and treatment.",
        "subclauses": [
          {"id": "6.1", "title": "Actions to address risks and opportunities"}
        ]
      },
      {
        "id": "7",
        "title": "Support",
        "category": "Clause",
        "description": "Resources, competence, awareness, communication, and documentation.",
        "subclauses": [
          {"id": "7.1", "title": "Resources"}
        ]
      },
      {
        "id": "8",
        "title": "Operation",
        "category": "Clause",
        "description": "Operational planning and risk treatment.",
        "subclauses": [
          {"id": "8.1", "title": "Operational planning and control"}
        ]
      }
    ],
    "Annex_A": [
      {
        "id": "A.5",
        "title": "Organizational Controls",
        "category": "Annex A",
        "description": "Policies, roles, compliance, supplier management (limited test set).",
        "controls": [
          {"id": "A.5.1", "title": "Policies for information security", "description": "Establish and review information security policies."},
          {"id": "A.5.2", "title": "Information security roles and responsibilities", "description": "Define and assign information security responsibilities."},
          {"id": "A.5.3", "title": "Segregation of duties", "description": "Reduce risk of misuse by segregating duties."},
          {"id": "A.5.4", "title": "Management responsibilities", "description": "Ensure ISMS roles are properly supported."},
          {"id": "A.5.5", "title": "Contact with authorities", "description": "Maintain contact with authorities as relevant."}
        ]
      }
    ]
  }
}

