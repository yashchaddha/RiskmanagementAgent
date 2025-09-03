import React, { useEffect, useMemo, useState } from "react";
import "./ControlTable.css";

// Annex A mapping interface for ISO 27001 controls
export interface AnnexAMapping {
  id: string; // e.g., "A.5.29"
  title: string; // e.g., "Information security during disruption"
}

// Comprehensive control interface supporting new enhanced format
export interface Control {
  id: string;
  // New comprehensive format fields
  control_id?: string; // e.g., "C-001"
  control_title?: string; // Enhanced title field
  control_description?: string; // Detailed description
  objective?: string; // Business objective
  annexA_map?: AnnexAMapping[]; // Array of ISO mappings
  linked_risk_ids?: string[]; // Array of related risk IDs
  owner_role?: string; // Responsible role
  process_steps?: string[]; // Implementation steps
  evidence_samples?: string[]; // Evidence examples
  metrics?: string[]; // KPIs and metrics
  policy_ref?: string; // Policy reference
  rationale?: string; // Business justification
  assumptions?: string; // Any assumptions

  // Legacy format fields (for backward compatibility)
  risk_id?: string;
  title?: string;
  description?: string;
  annex_reference?: string;
  category?: string;
  priority?: string; // "Low" | "Medium" | "High" | "Critical"
  status?: string; // "Planned" | "In Progress" | "Implemented"
  owner?: string;
  frequency?: string; // e.g., "Monthly", "Quarterly"
  evidence?: string; // link or note

  // Common fields
  isSelected?: boolean;
}

interface ControlTableProps {
  controls: Control[];
  onFinalize: (selectedControls: Control[]) => void;
  onClose: () => void;
  title?: string;
}

export const ControlTable: React.FC<ControlTableProps> = ({ controls, onFinalize, onClose, title = "🔐 ISO 27001 Controls Selection" }) => {
  const [rows, setRows] = useState<Control[]>([]);
  const [selectAll, setSelectAll] = useState(false);
  // Priority filter removed per requirements
  const [selectedControlForDetails, setSelectedControlForDetails] = useState<Control | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const withSelection = (controls || []).map((c) => {
      // Normalize control format - support both new comprehensive and legacy formats
      const normalizedControl: Control = {
        ...c,
        // Use new format if available, fallback to legacy format
        title: c.control_title || c.title || "(No title provided)",
        description: c.control_description || c.description || "",
        owner: c.owner_role || c.owner || "",
        annex_reference: c.annexA_map?.map((a) => a.id).join(", ") || c.annex_reference || "",
        isSelected: !!c.isSelected,
        priority: c.priority || "Medium",
        status: c.status || "Planned",
      };
      return normalizedControl;
    });
    setRows(withSelection);
  }, [controls]);

  const filteredRows = useMemo(() => rows, [rows]);

  const totalSelected = useMemo(() => rows.filter((r) => r.isSelected).length, [rows]);

  const toggleAll = () => {
    const next = !selectAll;
    setSelectAll(next);
    setRows((prev) => prev.map((r) => ({ ...r, isSelected: next })));
  };

  const updateField = (id: string, field: keyof Control, value: any) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, [field]: value } : r)));

    // Update selectAll state based on current selection
    const updatedRows = rows.map((r) => (r.id === id ? { ...r, [field]: value } : r));
    const allSelected = updatedRows.every((r) => r.isSelected);
    setSelectAll(allSelected);
  };

  const finalize = async () => {
    const selection = rows.filter((r) => r.isSelected);
    setIsSaving(true);
    try {
      const ret = (onFinalize as any)(selection);
      if (ret && typeof ret.then === 'function') {
        await ret;
      }
    } finally {
      setIsSaving(false);
    }
  };

  const showControlDetails = (control: Control) => {
    setSelectedControlForDetails(control);
    setShowDetailModal(true);
  };

  const closeDetailModal = () => {
    setShowDetailModal(false);
    setSelectedControlForDetails(null);
  };

  if (!controls || controls.length === 0) {
    return (
      <div className="control-modal-overlay">
        <div className="control-modal-content">
          <div className="control-modal-header">
            <h2>🔐 No Controls Found</h2>
            <button className="control-close-btn" onClick={onClose}>
              ×
            </button>
          </div>
          <div className="control-empty">
            <h3>No controls available</h3>
            <p>No controls were generated for your risks.</p>
          </div>
          <div className="control-modal-footer">
            <div className="control-footer-left"></div>
            <div className="control-footer-right">
              <button className="control-cancel-btn" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="control-modal-overlay">
      <div className="control-modal-content">
        <div className="control-modal-header">
          <h2>{title}</h2>
          <button className="control-close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="control-summary-bar">
          <div className="control-summary-left">
            <label className="select-all-controls">
              <input type="checkbox" checked={selectAll} onChange={toggleAll} />
              Select All
            </label>
            <span className="control-count">
              {filteredRows.length} control{filteredRows.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="control-filters"></div>
        </div>

        <div className="control-table-container">
          <table className="control-table">
            <thead>
              <tr>
                <th className="control-checkbox-cell">Select</th>
                <th className="control-title-cell">Control Details</th>
                <th className="control-objective-cell">Business Objective</th>
                <th className="control-annex-cell">ISO Mappings</th>
                <th className="control-status-cell">Status</th>
                <th className="control-owner-cell">Owner/Role</th>
                <th className="control-frequency-cell">Review Frequency</th>
                <th className="control-evidence-cell">Evidence Required</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((control) => (
                <tr key={control.id} className={control.isSelected ? "selected" : ""}>
                  <td className="control-checkbox-cell">
                    <input type="checkbox" checked={!!control.isSelected} onChange={(e) => updateField(control.id, "isSelected", e.target.checked)} />
                  </td>

                  <td className="control-title-cell">
                    <div className="control-title-main">
                      {control.title || "(No title provided)"}
                      {(control.control_id || control.id) && <span className="control-id-badge">{control.control_id || control.id}</span>}
                      {(control.process_steps || control.evidence_samples || control.metrics) && (
                        <button className="control-details-btn" onClick={() => showControlDetails(control)} title="View comprehensive details">
                          📋 Details
                        </button>
                      )}
                    </div>
                    {control.description && <div className="control-title-desc">{control.description}</div>}
                    {control.rationale && (
                      <div className="control-rationale">
                        <strong>Rationale:</strong> {control.rationale}
                      </div>
                    )}
                  </td>

                  <td className="control-objective-cell">
                    <div className="control-objective">{control.objective || "Not specified"}</div>
                    {control.linked_risk_ids && control.linked_risk_ids.length > 0 && (
                      <div className="linked-risks">
                        <small>Linked Risks: {control.linked_risk_ids.join(", ")}</small>
                      </div>
                    )}
                  </td>

                  <td className="control-annex-cell">
                    {control.annexA_map && control.annexA_map.length > 0 ? (
                      <div className="annex-mappings">
                        {control.annexA_map.map((mapping, index) => (
                          <div key={index} className="annex-mapping">
                            <strong>{mapping.id}</strong>
                            <small>{mapping.title}</small>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <input className="control-annex-input" value={control.annex_reference || ""} onChange={(e) => updateField(control.id, "annex_reference", e.target.value)} placeholder="A.5.1" />
                    )}
                  </td>

                  <td className="control-status-cell">
                    <select className="control-status-select" value={control.status || "Planned"} onChange={(e) => updateField(control.id, "status", e.target.value)}>
                      <option value="Planned">Planned</option>
                      <option value="In Progress">In Progress</option>
                      <option value="Implemented">Implemented</option>
                    </select>
                  </td>

                  <td className="control-owner-cell">
                    <input className="control-owner-input" value={control.owner || ""} onChange={(e) => updateField(control.id, "owner", e.target.value)} placeholder={control.owner_role || "John Doe"} />
                    {control.owner_role && control.owner_role !== control.owner && <small className="suggested-owner">Suggested: {control.owner_role}</small>}
                  </td>

                  <td className="control-frequency-cell">
                    <input className="control-frequency-input" value={control.frequency || ""} onChange={(e) => updateField(control.id, "frequency", e.target.value)} placeholder="Monthly" />
                  </td>

                  <td className="control-evidence-cell">
                    {control.evidence_samples && control.evidence_samples.length > 0 ? (
                      <ul className="evidence-list">
                        {control.evidence_samples.map((ev, idx) => (
                          <li key={idx}>{ev}</li>
                        ))}
                      </ul>
                    ) : control.evidence ? (
                      <div className="evidence-text">{control.evidence}</div>
                    ) : (
                      <div className="evidence-text">Not specified</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="control-modal-footer">
          <div className="control-footer-left">
            <div className="selected-count">
              <span className="count">{totalSelected}</span> of {controls.length} controls selected
            </div>
          </div>
          <div className="control-footer-right">
            <button className="control-save-btn" onClick={finalize} disabled={totalSelected === 0 || isSaving}>
              <span>{isSaving ? '⏳' : '💾'}</span>
              {isSaving ? 'Saving…' : `Save ${totalSelected} Control${totalSelected !== 1 ? 's' : ''}`}
            </button>
            <button className="control-cancel-btn" onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>

        {/* Detailed Control Modal */}
        {showDetailModal && selectedControlForDetails && (
          <div className="control-detail-modal-overlay">
            <div className="control-detail-modal">
              <div className="control-detail-header">
                <h3>📋 Control Comprehensive Details</h3>
                <button className="control-detail-close-btn" onClick={closeDetailModal}>
                  ×
                </button>
              </div>

              <div className="control-detail-content">
                <div className="control-detail-section">
                  <h4>{selectedControlForDetails.title || selectedControlForDetails.control_title}</h4>
                  <p className="control-id">ID: {selectedControlForDetails.control_id || selectedControlForDetails.id}</p>

                  {selectedControlForDetails.objective && (
                    <div className="detail-item">
                      <strong>🎯 Business Objective:</strong>
                      <p>{selectedControlForDetails.objective}</p>
                    </div>
                  )}

                  {selectedControlForDetails.description && (
                    <div className="detail-item">
                      <strong>📝 Description:</strong>
                      <p>{selectedControlForDetails.description}</p>
                    </div>
                  )}

                  {selectedControlForDetails.rationale && (
                    <div className="detail-item">
                      <strong>💡 Rationale:</strong>
                      <p className="control-rationale-text">{selectedControlForDetails.rationale}</p>
                    </div>
                  )}

                  {selectedControlForDetails.annexA_map && selectedControlForDetails.annexA_map.length > 0 && (
                    <div className="detail-item">
                      <strong>📚 ISO 27001 Annex A Mappings:</strong>
                      <ul className="annex-list">
                        {selectedControlForDetails.annexA_map.map((mapping, index) => (
                          <li key={index}>
                            <strong>{mapping.id}:</strong> {mapping.title}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {selectedControlForDetails.linked_risk_ids && selectedControlForDetails.linked_risk_ids.length > 0 && (
                    <div className="detail-item">
                      <strong>🔗 Linked Risk IDs:</strong>
                      <p>{selectedControlForDetails.linked_risk_ids.join(", ")}</p>
                    </div>
                  )}

                  {selectedControlForDetails.process_steps && selectedControlForDetails.process_steps.length > 0 && (
                    <div className="detail-item">
                      <strong>📋 Implementation Process Steps:</strong>
                      <ol className="process-steps">
                        {selectedControlForDetails.process_steps.map((step, index) => (
                          <li key={index}>{step}</li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {selectedControlForDetails.evidence_samples && selectedControlForDetails.evidence_samples.length > 0 && (
                    <div className="detail-item">
                      <strong>📄 Evidence Samples:</strong>
                      <ul className="evidence-list">
                        {selectedControlForDetails.evidence_samples.map((evidence, index) => (
                          <li key={index}>{evidence}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {selectedControlForDetails.metrics && selectedControlForDetails.metrics.length > 0 && (
                    <div className="detail-item">
                      <strong>📊 Success Metrics/KPIs:</strong>
                      <ul className="metrics-list">
                        {selectedControlForDetails.metrics.map((metric, index) => (
                          <li key={index}>{metric}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  <div className="control-detail-meta">
                    <div className="meta-row">
                      <span>
                        <strong>👤 Owner/Role:</strong> {selectedControlForDetails.owner_role || selectedControlForDetails.owner || "Not assigned"}
                      </span>
                      <span>
                        <strong>🔄 Frequency:</strong> {selectedControlForDetails.frequency || "Not specified"}
                      </span>
                    </div>
                    <div className="meta-row">
                      <span>
                        <strong>📋 Status:</strong> {selectedControlForDetails.status || "Planned"}
                      </span>
                      <span>
                        <strong>⚡ Priority:</strong> {selectedControlForDetails.priority || "Medium"}
                      </span>
                    </div>
                    {selectedControlForDetails.policy_ref && (
                      <div className="meta-row">
                        <span>
                          <strong>📜 Policy Reference:</strong> {selectedControlForDetails.policy_ref}
                        </span>
                      </div>
                    )}
                    {selectedControlForDetails.assumptions && (
                      <div className="meta-row">
                        <span>
                          <strong>⚠️ Assumptions:</strong> {selectedControlForDetails.assumptions}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="control-detail-footer">
                <button className="control-detail-close-btn-secondary" onClick={closeDetailModal}>
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
