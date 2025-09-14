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
  const [editedControls, setEditedControls] = useState<{[key: string]: Partial<ControlItem>}>({});

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

  const updateControlField = (controlId: string, field: keyof ControlItem, value: any) => {
    setEditedControls(prev => ({
      ...prev,
      [controlId]: {
        ...prev[controlId],
        [field]: value
      }
    }));
  };

  const getControlFieldValue = (control: ControlItem, field: keyof ControlItem) => {
    const edited = editedControls[control.control_id];
    return edited && edited[field] !== undefined ? edited[field] : control[field];
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
                const currentAnnexA = getControlFieldValue(c, 'annexA_map') as AnnexAMapping[];
                const currentProcessSteps = getControlFieldValue(c, 'process_steps') as string[];
                const currentEvidenceSamples = getControlFieldValue(c, 'evidence_samples') as string[];
                const currentMetrics = getControlFieldValue(c, 'metrics') as string[];

                const annexFull = Array.isArray(currentAnnexA) ? currentAnnexA.map((a) => `${a.id}${a.title ? `: ${a.title}` : ""}`).join("; ") : "";
                const stepsFull = Array.isArray(currentProcessSteps) ? currentProcessSteps.join("; ") : "";
                const evidenceFull = Array.isArray(currentEvidenceSamples) ? currentEvidenceSamples.join("; ") : "";
                const metricsFull = Array.isArray(currentMetrics) ? currentMetrics.join("; ") : "";

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
                      <textarea
                        className="editable-field cell-title-input"
                        value={getControlFieldValue(c, 'control_title') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'control_title', e.target.value)}
                        rows={2}
                      />
                    </td>
                    <td>
                      <textarea
                        className="editable-field cell-desc-input"
                        value={getControlFieldValue(c, 'control_description') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'control_description', e.target.value)}
                        rows={3}
                      />
                    </td>
                    <td>
                      <textarea
                        className="editable-field cell-obj-input"
                        value={getControlFieldValue(c, 'objective') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'objective', e.target.value)}
                        rows={2}
                      />
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
                      <textarea
                        className="editable-field cell-annex-input"
                        value={annexFull}
                        onChange={(e) => {
                          const value = e.target.value;
                          const annexMappings = value ? value.split(';').map(item => {
                            const trimmed = item.trim();
                            const colonIndex = trimmed.indexOf(':');
                            if (colonIndex > 0) {
                              return {
                                id: trimmed.substring(0, colonIndex).trim(),
                                title: trimmed.substring(colonIndex + 1).trim()
                              };
                            }
                            return { id: trimmed, title: '' };
                          }) : [];
                          updateControlField(c.control_id, 'annexA_map', annexMappings);
                        }}
                        rows={2}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="editable-field cell-owner-input"
                        value={getControlFieldValue(c, 'owner_role') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'owner_role', e.target.value)}
                      />
                    </td>
                    <td>
                      <textarea
                        className="editable-field cell-steps-input"
                        value={stepsFull}
                        onChange={(e) => {
                          const steps = e.target.value ? e.target.value.split(';').map(s => s.trim()).filter(s => s) : [];
                          updateControlField(c.control_id, 'process_steps', steps);
                        }}
                        rows={2}
                      />
                    </td>
                    <td>
                      <textarea
                        className="editable-field cell-evidence-input"
                        value={evidenceFull}
                        onChange={(e) => {
                          const evidence = e.target.value ? e.target.value.split(';').map(s => s.trim()).filter(s => s) : [];
                          updateControlField(c.control_id, 'evidence_samples', evidence);
                        }}
                        rows={2}
                      />
                    </td>
                    <td>
                      <textarea
                        className="editable-field cell-metrics-input"
                        value={metricsFull}
                        onChange={(e) => {
                          const metrics = e.target.value ? e.target.value.split(';').map(s => s.trim()).filter(s => s) : [];
                          updateControlField(c.control_id, 'metrics', metrics);
                        }}
                        rows={2}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="editable-field cell-frequency-input"
                        value={getControlFieldValue(c, 'frequency') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'frequency', e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        className="editable-field cell-policy-input"
                        value={getControlFieldValue(c, 'policy_ref') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'policy_ref', e.target.value)}
                      />
                    </td>
                    <td>
                      <select
                        className="editable-field cell-status-input"
                        value={getControlFieldValue(c, 'status') as string || 'Planned'}
                        onChange={(e) => updateControlField(c.control_id, 'status', e.target.value)}
                      >
                        <option value="Planned">Planned</option>
                        <option value="In Progress">In Progress</option>
                        <option value="Implemented">Implemented</option>
                        <option value="Under Review">Under Review</option>
                        <option value="Approved">Approved</option>
                      </select>
                    </td>
                    <td>
                      <textarea
                        className="editable-field cell-rationale-input"
                        value={getControlFieldValue(c, 'rationale') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'rationale', e.target.value)}
                        rows={2}
                      />
                    </td>
                    <td>
                      <textarea
                        className="editable-field cell-assumptions-input"
                        value={getControlFieldValue(c, 'assumptions') as string || ''}
                        onChange={(e) => updateControlField(c.control_id, 'assumptions', e.target.value)}
                        rows={2}
                      />
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
          <button className="save-btn" onClick={() => {
            const selectedControls = localControls.filter((c) => c.isSelected).map(control => {
              const edits = editedControls[control.control_id];
              return edits ? { ...control, ...edits } : control;
            });
            onSaveSelected(selectedControls);
          }} disabled={selectedCount === 0 || isSaving}>
            {isSaving ? "Saving Controls..." : "Finalize Controls"}
          </button>
        </div>
      </div>
    </div>
  );
};
