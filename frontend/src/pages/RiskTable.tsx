import React, { useState, useEffect } from "react";
import "./RiskTable.css";

interface Risk {
  id: string;
  description: string;
  category: string;
  likelihood: string;
  impact: string;
  treatmentStrategy: string;
  isSelected: boolean;
  // New user input fields
  assetValue?: string;
  department?: string;
  riskOwner?: string;
  securityImpact?: "Yes" | "No";
  targetDate?: string;
  riskProgress?: "Identified" | "Mitigated" | "Ongoing Mitigation";
  residualExposure?: "High" | "Medium" | "Low" | "Ongoing Mitigation";
}

interface RiskTableProps {
  risks: Risk[];
  onRiskSelectionChange: (riskId: string, isSelected: boolean) => void;
  onFinalize: (selectedRisks: Risk[]) => void;
  onClose: () => void;
}

interface UserPreferences {
  risks_applicable: string[];
  risk_profiles_count: number;
  likelihood: string[];
  impact: string[];
}

const RISK_CATEGORIES = ["Competition", "External", "Financial", "Innovation", "Internal", "Legal and Compliance", "Operational", "Project Management", "Reputational", "Safety", "Strategic", "Technology"];

export const RiskTable: React.FC<RiskTableProps> = ({ risks, onRiskSelectionChange, onFinalize, onClose }) => {
  const [selectAll, setSelectAll] = useState(true);
  const [userPreferences, setUserPreferences] = useState<UserPreferences>({
    risks_applicable: [],
    risk_profiles_count: 0,
    likelihood: [],
    impact: [],
  });

  const [editedRisks, setEditedRisks] = useState<{ [key: string]: Risk }>({});
  const [isFinalizing, setIsFinalizing] = useState(false);

  // Load user preferences on component mount
  useEffect(() => {
    const fetchUserPreferences = async () => {
      try {
        const token = localStorage.getItem("token");
        if (!token) return;

        const response = await fetch("http://localhost:8000/user/preferences", {
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
        });

        if (response.ok) {
          const data = await response.json();
          if (data.success) {
            setUserPreferences({
              risks_applicable: data.risks_applicable || [],
              risk_profiles_count: data.risk_profiles_count || 0,
              likelihood: data.likelihood || [],
              impact: data.impact || [],
            });
          }
        }
      } catch (error) {
        console.error("Error fetching user preferences:", error);
      }
    };

    fetchUserPreferences();
  }, []);

  // Initialize edited risks with current risks
  useEffect(() => {
    const initialEditedRisks: { [key: string]: Risk } = {};
    risks.forEach((risk) => {
      initialEditedRisks[risk.id] = { ...risk };
    });
    setEditedRisks(initialEditedRisks);
  }, [risks]);

  const handleSelectAll = (checked: boolean) => {
    setSelectAll(checked);
    risks.forEach((risk) => {
      onRiskSelectionChange(risk.id, checked);
    });
  };

  const handleFieldChange = (riskId: string, field: keyof Risk, value: string) => {
    setEditedRisks((prev) => ({
      ...prev,
      [riskId]: {
        ...prev[riskId],
        [field]: value,
      },
    }));
  };

  const handleFieldBlur = async (riskId: string, field: keyof Risk, value: string) => {
    try {
      const token = localStorage.getItem("token");
      if (!token) return;

      const riskIndex = risks.findIndex((risk) => risk.id === riskId);
      if (riskIndex === -1) return;

      // Map frontend field names to backend field names
      const fieldMapping: { [key: string]: string } = {
        assetValue: "asset_value",
        riskOwner: "risk_owner",
        securityImpact: "security_impact",
        targetDate: "target_date",
        riskProgress: "risk_progress",
        residualExposure: "residual_exposure",
      };

      const backendField = fieldMapping[field] || field;

      const response = await fetch(`http://localhost:8000/risks/${riskIndex}/update`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          risk_index: riskIndex,
          field: backendField,
          value: value,
        }),
      });

      if (!response.ok) {
        console.error("Failed to update risk field");
      } else {
        // Update the local state and notify parent component
        const updatedRisks = risks.map((risk) => (risk.id === riskId ? { ...risk, [field]: value } : risk));
        setEditedRisks((prev) => ({
          ...prev,
          [riskId]: { ...prev[riskId], [field]: value },
        }));

        console.log(`Updated field ${field} for risk ${riskId} to:`, value); // Debug log
        console.log("Updated risks array:", updatedRisks); // Debug log
      }
    } catch (error) {
      console.error("Error updating risk field:", error);
    }
  };

  const getCurrentRisk = (riskId: string): Risk => {
    return editedRisks[riskId] || risks.find((r) => r.id === riskId) || risks[0];
  };

  return (
    <div className="risk-table-modal">
      <div className="risk-table-content">
        <div className="risk-table-header">
          <h3>📊 Generated Risks Assessment</h3>
          <button onClick={onClose} className="close-btn">
            ×
          </button>
        </div>

        <div className="risk-table-controls">
          <label className="select-all-label">
            <input type="checkbox" checked={selectAll} onChange={(e) => handleSelectAll(e.target.checked)} />
            <span>Select All Risks</span>
          </label>
          <div className="risk-count">
            {risks.filter((r) => r.isSelected).length} of {risks.length} risks selected
          </div>
        </div>

        <div className="risk-table-container">
          <table className="risk-table">
            <thead>
              <tr>
                <th className="checkbox-header">
                  <input type="checkbox" checked={selectAll} onChange={(e) => handleSelectAll(e.target.checked)} />
                </th>
                <th>Risk Description</th>
                <th>Category</th>
                <th>Likelihood</th>
                <th>Impact</th>
                <th>Treatment Strategy</th>
                <th>Asset Value (USD)</th>
                <th>Department</th>
                <th>Risk Owner</th>
                <th>Security Impact</th>
                <th>Target Date</th>
                <th>Risk Progress</th>
                <th>Residual Exposure</th>
              </tr>
            </thead>
            <tbody>
              {risks.map((risk) => {
                const currentRisk = getCurrentRisk(risk.id);
                return (
                  <tr key={risk.id} className={risk.isSelected ? "selected" : ""}>
                    <td className="checkbox-cell">
                      <input type="checkbox" checked={risk.isSelected} onChange={(e) => onRiskSelectionChange(risk.id, e.target.checked)} />
                    </td>
                    <td className="description-cell">
                      <textarea className="risk-description-input" value={currentRisk.description} onChange={(e) => handleFieldChange(risk.id, "description", e.target.value)} onBlur={(e) => handleFieldBlur(risk.id, "description", e.target.value)} placeholder="Enter risk description..." />
                    </td>
                    <td className="category-cell">
                      <input type="text" className="category-input" value={currentRisk.category} onChange={(e) => handleFieldChange(risk.id, "category", e.target.value)} onBlur={(e) => handleFieldBlur(risk.id, "category", e.target.value)} placeholder="Enter category..." list="category-options" />
                      <datalist id="category-options">
                        {RISK_CATEGORIES.map((category) => (
                          <option key={category} value={category} />
                        ))}
                      </datalist>
                    </td>
                    <td className="likelihood-cell">
                      <select
                        className="likelihood-select"
                        value={currentRisk.likelihood}
                        onChange={(e) => {
                          handleFieldChange(risk.id, "likelihood", e.target.value);
                          handleFieldBlur(risk.id, "likelihood", e.target.value);
                        }}
                      >
                        {userPreferences.likelihood.map((level) => (
                          <option key={level} value={level}>
                            {level}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="impact-cell">
                      <select
                        className="impact-select"
                        value={currentRisk.impact}
                        onChange={(e) => {
                          handleFieldChange(risk.id, "impact", e.target.value);
                          handleFieldBlur(risk.id, "impact", e.target.value);
                        }}
                      >
                        {userPreferences.impact.map((level) => (
                          <option key={level} value={level}>
                            {level}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="treatment-cell">
                      <textarea className="treatment-strategy-input" value={currentRisk.treatmentStrategy} onChange={(e) => handleFieldChange(risk.id, "treatmentStrategy", e.target.value)} onBlur={(e) => handleFieldBlur(risk.id, "treatmentStrategy", e.target.value)} placeholder="Enter treatment strategy..." />
                    </td>
                    <td className="asset-value-cell">
                      <input type="text" className="asset-value-input" value={currentRisk.assetValue || ""} onChange={(e) => handleFieldChange(risk.id, "assetValue", e.target.value)} onBlur={(e) => handleFieldBlur(risk.id, "assetValue", e.target.value)} placeholder="Enter values in USD" />
                    </td>
                    <td className="department-cell">
                      <input type="text" className="department-input" value={currentRisk.department || ""} onChange={(e) => handleFieldChange(risk.id, "department", e.target.value)} onBlur={(e) => handleFieldBlur(risk.id, "department", e.target.value)} placeholder="Enter department" />
                    </td>
                    <td className="risk-owner-cell">
                      <input type="text" className="risk-owner-input" value={currentRisk.riskOwner || ""} onChange={(e) => handleFieldChange(risk.id, "riskOwner", e.target.value)} onBlur={(e) => handleFieldBlur(risk.id, "riskOwner", e.target.value)} placeholder="Enter risk owner" />
                    </td>
                    <td className="security-impact-cell">
                      <select
                        className="security-impact-select"
                        value={currentRisk.securityImpact || ""}
                        onChange={(e) => {
                          handleFieldChange(risk.id, "securityImpact", e.target.value);
                          handleFieldBlur(risk.id, "securityImpact", e.target.value);
                        }}
                      >
                        <option value="">Select</option>
                        <option value="Yes">Yes</option>
                        <option value="No">No</option>
                      </select>
                    </td>
                    <td className="target-date-cell">
                      <input type="date" className="target-date-input" value={currentRisk.targetDate || ""} onChange={(e) => handleFieldChange(risk.id, "targetDate", e.target.value)} onBlur={(e) => handleFieldBlur(risk.id, "targetDate", e.target.value)} />
                    </td>
                    <td className="risk-progress-cell">
                      <select
                        className="risk-progress-select"
                        value={currentRisk.riskProgress || "Identified"}
                        onChange={(e) => {
                          handleFieldChange(risk.id, "riskProgress", e.target.value);
                          handleFieldBlur(risk.id, "riskProgress", e.target.value);
                        }}
                      >
                        <option value="Identified">Identified</option>
                        <option value="Mitigated">Mitigated</option>
                        <option value="Ongoing Mitigation">Ongoing Mitigation</option>
                      </select>
                    </td>
                    <td className="residual-exposure-cell">
                      <select
                        className="residual-exposure-select"
                        value={currentRisk.residualExposure || ""}
                        onChange={(e) => {
                          handleFieldChange(risk.id, "residualExposure", e.target.value);
                          handleFieldBlur(risk.id, "residualExposure", e.target.value);
                        }}
                      >
                        <option value="">Select</option>
                        <option value="High">High</option>
                        <option value="Medium">Medium</option>
                        <option value="Low">Low</option>
                        <option value="Ongoing Mitigation">Ongoing Mitigation</option>
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="risk-table-footer">
          <div></div>
          <div>
            <div style={{ display: "flex", gap: "12px" }}>
              <button
                className="finalize-btn"
                onClick={async () => {
                  const selectedEditedRisks = risks
                    .map((risk) => {
                      const editedRisk = editedRisks[risk.id];
                      return editedRisk || risk;
                    })
                    .filter((r) => r.isSelected);

                  setIsFinalizing(true);
                  try {
                    const ret = (onFinalize as any)(selectedEditedRisks);
                    if (ret && typeof ret.then === "function") {
                      await ret;
                    }
                  } finally {
                    setIsFinalizing(false);
                  }
                }}
                disabled={risks.filter((r) => r.isSelected).length === 0 || isFinalizing}
              >
                {isFinalizing ? "⏳ Finalising…" : "✅ Finalise Risks"}
              </button>
              <button className="close-table-btn" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        </div>

        {isFinalizing && (
          <div className="risk-table-loading-overlay">
            <div className="risk-table-spinner"></div>
            <div>Finalising risks…</div>
          </div>
        )}
      </div>
    </div>
  );
};
