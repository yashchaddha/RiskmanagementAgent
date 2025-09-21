import React, { useEffect, useState } from "react";
import "./ControlLibrary.css";

export interface AnnexAMapping {
  id: string;
  title: string;
}

export interface RiskItem {
  id: string;
  description: string;
  category: string;
  likelihood: string;
  impact: string;
  treatment_strategy: string;
  asset_value?: string;
  department?: string;
  risk_owner?: string;
  security_impact?: string;
  target_date?: string;
  risk_progress?: string;
  residual_exposure?: string;
}

export interface ControlItem {
  id?: string;
  control_id: string;
  control_title: string;
  control_description: string;
  objective: string;
  annexA_map: AnnexAMapping[];
  linked_risk_ids?: string[];
  owner_role: string;
  process_steps: string[];
  evidence_samples: string[];
  metrics: string[];
  frequency: string;
  policy_ref: string;
  status: string;
  rationale: string;
  assumptions: string;
  created_at?: string;
  updated_at?: string;
}

interface RiskModalProps {
  risk: RiskItem | null;
  onClose: () => void;
}

const RiskDetailModal: React.FC<RiskModalProps> = ({ risk, onClose }) => {
  if (!risk) return null;

  return (
    <div className="risk-modal-overlay">
      <div className="risk-modal">
        <div className="risk-modal-header">
          <h3>Risk Detail: {risk.id}</h3>
          <button className="close-btn-risk" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="risk-modal-content">
          <div className="risk-detail-row">
            <span className="risk-label">Description:</span>
            <span className="risk-value">{risk.description}</span>
          </div>
          <div className="risk-detail-row">
            <span className="risk-label">Category:</span>
            <span className="risk-value">{risk.category}</span>
          </div>
          <div className="risk-detail-row">
            <span className="risk-label">Likelihood:</span>
            <span className="risk-value">{risk.likelihood}</span>
          </div>
          <div className="risk-detail-row">
            <span className="risk-label">Impact:</span>
            <span className="risk-value">{risk.impact}</span>
          </div>
          <div className="risk-detail-row">
            <span className="risk-label">Treatment:</span>
            <span className="risk-value">{risk.treatment_strategy}</span>
          </div>
          {risk.risk_owner && (
            <div className="risk-detail-row">
              <span className="risk-label">Owner:</span>
              <span className="risk-value">{risk.risk_owner}</span>
            </div>
          )}
          {risk.department && (
            <div className="risk-detail-row">
              <span className="risk-label">Department:</span>
              <span className="risk-value">{risk.department}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

interface ControlLibraryProps {
  onClose: () => void;
}

export const ControlLibrary: React.FC<ControlLibraryProps> = ({ onClose }) => {
  const [controls, setControls] = useState<ControlItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<keyof ControlItem>("control_id");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [selectedRisk, setSelectedRisk] = useState<RiskItem | null>(null);
  const [isLoadingRisk, setIsLoadingRisk] = useState(false);

  useEffect(() => {
    fetchControls();
  }, []);

  const fetchControls = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("No authentication token found");
      }

      const response = await fetch("http://localhost:8000/controls", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      if (data.success && data.data) {
        setControls(data.data);
      } else {
        throw new Error(data.message || "Failed to fetch controls");
      }
    } catch (err) {
      console.error("Error fetching controls:", err);
      setError(err instanceof Error ? err.message : "Failed to fetch controls");
    } finally {
      setIsLoading(false);
    }
  };

  const filteredControls = controls.filter((control) => {
    const matchesSearch = 
      control.control_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      control.control_title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      control.control_description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      control.objective.toLowerCase().includes(searchTerm.toLowerCase()) ||
      control.owner_role.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesStatus = statusFilter === "all" || control.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const sortedControls = [...filteredControls].sort((a, b) => {
    const aValue = a[sortBy];
    const bValue = b[sortBy];
    if (aValue === undefined && bValue === undefined) return 0;
    if (aValue === undefined) return sortOrder === "asc" ? 1 : -1;
    if (bValue === undefined) return sortOrder === "asc" ? -1 : 1;
    
    if (aValue < bValue) return sortOrder === "asc" ? -1 : 1;
    if (aValue > bValue) return sortOrder === "asc" ? 1 : -1;
    return 0;
  });

  const handleSort = (column: keyof ControlItem) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }
  };

  const fetchRiskDetails = async (riskId: string) => {
    setIsLoadingRisk(true);
    try {
      const response = await fetch(`http://localhost:8000/risks/finalized`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
      });

      if (!response.ok) {
        throw new Error("Failed to fetch risks");
      }

      const data = await response.json();
      if (data.success && data.data && data.data.risks) {
        const foundRisk = data.data.risks.find((r: any) => r.id === riskId);
        if (foundRisk) {
          setSelectedRisk(foundRisk);
        } else {
          alert(`Risk with ID ${riskId} not found`);
        }
      } else {
        alert(`Error: ${data.message || "Failed to load risks"}`);
      }
    } catch (error) {
      console.error("Error fetching risk details:", error);
      alert("Failed to load risk details. Please try again.");
    } finally {
      setIsLoadingRisk(false);
    }
  };

  const closeRiskModal = () => {
    setSelectedRisk(null);
  };

  const getStatusBadge = (status: string) => {
    const statusColors = {
      "Active": "#28a745",
      "Planned": "#ffc107",
      "Inactive": "#6c757d",
      "Draft": "#17a2b8",
    };
    
    const color = statusColors[status as keyof typeof statusColors] || "#6c757d";
    
    return (
      <span 
        className="status-badge" 
        style={{ backgroundColor: color }}
      >
        {status}
      </span>
    );
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return "-";
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return "-";
    }
  };

  if (isLoading) {
    return (
      <div className="control-library-overlay">
        <div className="control-library-modal">
          <div className="loading-container">
            <div className="loading-spinner"></div>
            <p>Loading your control library...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="control-library-overlay">
        <div className="control-library-modal">
          <div className="error-container">
            <h3>Error Loading Control Library</h3>
            <p>{error}</p>
            <button onClick={fetchControls} className="retry-btn">
              Try Again
            </button>
            <button onClick={onClose} className="close-btn">
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="control-library-overlay">
      <div className="control-library-modal">
        <div className="control-library-header">
          <h3>📚 Control Library</h3>
          <button className="close-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        {isLoadingRisk && (
          <div className="risk-loading-overlay">
            <div className="risk-loading-spinner">Loading risk details...</div>
          </div>
        )}

        {selectedRisk && <RiskDetailModal risk={selectedRisk} onClose={closeRiskModal} />}

        <div className="control-library-filters">
          <div className="search-container">
            <input
              type="text"
              placeholder="Search controls..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="search-input"
            />
          </div>
          <div className="filter-container">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="status-filter"
            >
              <option value="all">All Status</option>
              <option value="Active">Active</option>
              <option value="Planned">Planned</option>
              <option value="Inactive">Inactive</option>
              <option value="Draft">Draft</option>
            </select>
          </div>
          <div className="results-count">
            {sortedControls.length} control{sortedControls.length !== 1 ? 's' : ''} found
          </div>
        </div>

        <div className="control-library-content">
          {sortedControls.length === 0 ? (
            <div className="empty-state">
              <h4>No controls found</h4>
              <p>
                {searchTerm || statusFilter !== "all" 
                  ? "Try adjusting your search or filter criteria."
                  : "You don't have any controls in your library yet. Generate some controls to get started!"
                }
              </p>
            </div>
          ) : (
            <div className="controls-table-wrapper">
              <table className="controls-table">
                <thead>
                  <tr>
                    <th 
                      className="sortable" 
                      onClick={() => handleSort("control_id")}
                    >
                      Control ID {sortBy === "control_id" && (sortOrder === "asc" ? "↑" : "↓")}
                    </th>
                    <th 
                      className="sortable" 
                      onClick={() => handleSort("control_title")}
                    >
                      Title {sortBy === "control_title" && (sortOrder === "asc" ? "↑" : "↓")}
                    </th>
                    <th>Description</th>
                    <th>Objective</th>
                    <th>Linked Risks</th>
                    <th
                      className="sortable"
                      onClick={() => handleSort("status")}
                    >
                      Status {sortBy === "status" && (sortOrder === "asc" ? "↑" : "↓")}
                    </th>
                    <th 
                      className="sortable" 
                      onClick={() => handleSort("owner_role")}
                    >
                      Owner {sortBy === "owner_role" && (sortOrder === "asc" ? "↑" : "↓")}
                    </th>
                    <th>Annex A</th>
                    <th>Evidence</th>
                    <th 
                      className="sortable" 
                      onClick={() => handleSort("created_at")}
                    >
                      Created {sortBy === "created_at" && (sortOrder === "asc" ? "↑" : "↓")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedControls.map((control, index) => {
                    const annexFull = Array.isArray(control.annexA_map) 
                      ? control.annexA_map.map((a) => `${a.id}${a.title ? `: ${a.title}` : ""}`).join("; ") 
                      : "";
                    const evidenceFull = Array.isArray(control.evidence_samples) 
                      ? control.evidence_samples.join("; ") 
                      : "";

                    return (
                      <tr key={control.control_id + index}>
                        <td>
                          <div className="clamp tooltip cell-id" title={control.control_id}>
                            {control.control_id}
                          </div>
                        </td>
                        <td>
                          <div className="clamp tooltip cell-title" title={control.control_title}>
                            {control.control_title}
                          </div>
                        </td>
                        <td>
                          <div className="clamp tooltip cell-desc" title={control.control_description}>
                            {control.control_description}
                          </div>
                        </td>
                        <td>
                          <div className="clamp tooltip cell-obj" title={control.objective}>
                            {control.objective}
                          </div>
                        </td>
                        <td>
                          <div className="clamp tooltip cell-linked-risks">
                            {control.linked_risk_ids && control.linked_risk_ids.length > 0 ? (
                              <div className="risk-links">
                                {control.linked_risk_ids.map((riskId, i) => (
                                  <span key={i} className="risk-id-link" onClick={() => fetchRiskDetails(riskId)}>
                                    {riskId}
                                    {i < (control.linked_risk_ids?.length || 0) - 1 ? ", " : ""}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              "-"
                            )}
                          </div>
                        </td>
                        <td>
                          {getStatusBadge(control.status)}
                        </td>
                        <td>
                          <div className="clamp tooltip cell-owner" title={control.owner_role}>
                            {control.owner_role}
                          </div>
                        </td>
                        <td>
                          <div className="clamp tooltip cell-annex" title={annexFull}>
                            {annexFull || "-"}
                          </div>
                        </td>
                        <td>
                          <div className="clamp tooltip cell-evidence" title={evidenceFull}>
                            {evidenceFull || "-"}
                          </div>
                        </td>
                        <td>
                          <div className="clamp tooltip cell-date" title={formatDate(control.created_at)}>
                            {formatDate(control.created_at)}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="control-library-footer">
          <button className="close-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
