import React, { useEffect, useState } from "react";
import "./ControlsTable.css";

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
  isSelected?: boolean;
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

interface ControlsTableProps {
  controls: ControlItem[];
  onClose: () => void;
  onSaveSelected: (selected: ControlItem[]) => Promise<void> | void;
  isSaving?: boolean;
}

export const ControlsTable: React.FC<ControlsTableProps> = ({ controls, onClose, onSaveSelected, isSaving = false }) => {
  const [selectAll, setSelectAll] = useState(true);
  const [localControls, setLocalControls] = useState<ControlItem[]>([]);
  const [selectedRisk, setSelectedRisk] = useState<RiskItem | null>(null);
  const [isLoadingRisk, setIsLoadingRisk] = useState(false);

  useEffect(() => {
    // Initialize selection state
    const initialized = (controls || []).map((c) => ({ ...c, isSelected: c.isSelected ?? true }));
    setLocalControls(initialized);
  }, [controls]);

  const handleSelectAll = (checked: boolean) => {
    setSelectAll(checked);
    setLocalControls((prev) => prev.map((c) => ({ ...c, isSelected: checked })));
  };

  const toggleRow = (idx: number, checked: boolean) => {
    setLocalControls((prev) => prev.map((c, i) => (i === idx ? { ...c, isSelected: checked } : c)));
  };

  const fetchRiskDetails = async (riskId: string) => {
    setIsLoadingRisk(true);
    try {
      // Since there's no direct API to get a risk by ID, we'll fetch the finalized risks
      // and filter to find the one we want
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
        // Find the risk with the matching ID
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

  const selectedCount = localControls.filter((c) => c.isSelected).length;

  return (
    <div className="controls-table-overlay">
      <div className="controls-table-modal">
        <div className="controls-table-header">
          <h3>Generated Controls</h3>
          <button className="close-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="controls-table-subheader">
          <label className="select-all">
            <input type="checkbox" checked={selectAll} onChange={(e) => handleSelectAll(e.target.checked)} />
            <span>Select All</span>
          </label>
          <span className="selected-count">Selected: {selectedCount}</span>
        </div>

        {isLoadingRisk && (
          <div className="risk-loading-overlay">
            <div className="risk-loading-spinner">Loading risk details...</div>
          </div>
        )}

        {selectedRisk && <RiskDetailModal risk={selectedRisk} onClose={closeRiskModal} />}

        <div className="controls-table-wrapper">
          <table className="controls-table">
            <thead>
              <tr>
                <th></th>
                <th>ID</th>
                <th>Title</th>
                <th>Description</th>
                <th>Objective</th>
                <th>Linked Risks</th>
                <th>Annex A</th>
                <th>Owner</th>
                <th>Process Steps</th>
                <th>Evidence Samples</th>
                <th>Metrics</th>
                <th>Frequency</th>
                <th>Policy Ref</th>
                <th>Status</th>
                <th>Rationale</th>
                <th>Assumptions</th>
              </tr>
            </thead>
            <tbody>
              {localControls.map((c, idx) => {
                const annexFull = Array.isArray(c.annexA_map) ? c.annexA_map.map((a) => `${a.id}${a.title ? `: ${a.title}` : ""}`).join("; ") : "";
                const stepsFull = Array.isArray(c.process_steps) ? c.process_steps.join("; ") : "";
                const evidenceFull = Array.isArray(c.evidence_samples) ? c.evidence_samples.join("; ") : "";
                const metricsFull = Array.isArray(c.metrics) ? c.metrics.join("; ") : "";
                return (
                  <tr key={c.control_id + idx}>
                    <td>
                      <input
                        type="checkbox"
                        checked={!!c.isSelected}
                        onChange={(e) => {
                          toggleRow(idx, e.target.checked);
                        }}
                      />
                    </td>
                    <td>
                      <div className="clamp tooltip cell-id" title={c.control_id} data-full={c.control_id}>
                        {c.control_id}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-title" title={c.control_title} data-full={c.control_title}>
                        {c.control_title}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-desc" title={c.control_description} data-full={c.control_description}>
                        {c.control_description}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-obj" title={c.objective} data-full={c.objective}>
                        {c.objective}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-linked-risks">
                        {c.linked_risk_ids && c.linked_risk_ids.length > 0 ? (
                          <div className="risk-links">
                            {c.linked_risk_ids.map((riskId, i) => (
                              <span key={i} className="risk-id-link" onClick={() => fetchRiskDetails(riskId)}>
                                {riskId}
                                {i < (c.linked_risk_ids?.length || 0) - 1 ? ", " : ""}
                              </span>
                            ))}
                          </div>
                        ) : (
                          "-"
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-annex" title={annexFull} data-full={annexFull}>
                        {annexFull || "-"}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-owner" title={c.owner_role || ""} data-full={c.owner_role || ""}>
                        {c.owner_role || ""}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-steps" title={stepsFull} data-full={stepsFull}>
                        {stepsFull || "-"}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-evidence" title={evidenceFull} data-full={evidenceFull}>
                        {evidenceFull || "-"}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-metrics" title={metricsFull} data-full={metricsFull}>
                        {metricsFull || "-"}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-frequency" title={c.frequency || ""} data-full={c.frequency || ""}>
                        {c.frequency || ""}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-policy" title={c.policy_ref || ""} data-full={c.policy_ref || ""}>
                        {c.policy_ref || ""}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-status" title={c.status || "Planned"} data-full={c.status || "Planned"}>
                        {c.status || "Planned"}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-rationale" title={c.rationale || ""} data-full={c.rationale || ""}>
                        {c.rationale || ""}
                      </div>
                    </td>
                    <td>
                      <div className="clamp tooltip cell-assumptions" title={c.assumptions || ""} data-full={c.assumptions || ""}>
                        {c.assumptions || ""}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="controls-table-footer">
          <button className="close-table-btn" onClick={onClose}>
            Close
          </button>
          <button className="save-btn" onClick={() => onSaveSelected(localControls.filter((c) => c.isSelected))} disabled={selectedCount === 0 || isSaving}>
            {isSaving ? "Saving Controls..." : "Finalize Controls"}
          </button>
        </div>
      </div>
    </div>
  );
};
