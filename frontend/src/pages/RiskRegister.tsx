import React, { useState, useEffect } from "react";
import "./RiskRegister.css";

interface FinalizedRisk {
  id: string;
  description: string;
  category: string;
  likelihood: string;
  impact: string;
  treatmentStrategy: string;
  // User input fields
  assetValue?: string;
  department?: string;
  riskOwner?: string;
  securityImpact?: "Yes" | "No";
  targetDate?: string;
  riskProgress?: "Identified" | "Mitigated" | "Ongoing Mitigation";
  residualExposure?: "High" | "Medium" | "Low" | "Ongoing Mitigation";
  createdAt?: string;
  updatedAt?: string;
}

interface RiskRegisterProps {
  onClose: () => void;
}

export const RiskRegister: React.FC<RiskRegisterProps> = ({ onClose }) => {
  const [finalizedRisks, setFinalizedRisks] = useState<FinalizedRisk[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterProgress, setFilterProgress] = useState("");

  const RISK_CATEGORIES = ["Competition", "External", "Financial", "Innovation", "Internal", "Legal and Compliance", "Operational", "Project Management", "Reputational", "Safety", "Strategic", "Technology"];

  const PROGRESS_OPTIONS = ["Identified", "Mitigated", "Ongoing Mitigation"];

  useEffect(() => {
    fetchFinalizedRisks();
  }, []);

  const fetchFinalizedRisks = async (): Promise<FinalizedRisk[]> => {
    try {
      setIsLoading(true);
      setError(null);

      const token = localStorage.getItem("token");
      if (!token) {
        setError("No authentication token found");
        return [];
      }

      const response = await fetch("https://api.agentic.complynexus.com/risks/finalized", {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success && data.data && data.data.risks) {
          // Transform the risks to match our interface
          const transformedRisks = data.data.risks.map((risk: any) => ({
            id: risk.id || `risk-${Date.now()}`,
            description: risk.description,
            category: risk.category,
            likelihood: risk.likelihood,
            impact: risk.impact,
            treatmentStrategy: risk.treatment_strategy,
            assetValue: risk.asset_value,
            department: risk.department,
            riskOwner: risk.risk_owner,
            securityImpact: risk.security_impact,
            targetDate: risk.target_date,
            riskProgress: risk.risk_progress,
            residualExposure: risk.residual_exposure,
            createdAt: risk.created_at,
            updatedAt: risk.updated_at,
          }));
          setFinalizedRisks(transformedRisks);
        } else {
          setFinalizedRisks([]);
          return [];
        }
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.message || "Failed to fetch finalized risks");
        return [];
      }
    } catch (error) {
      console.error("Error fetching finalized risks:", error);
      setError("An error occurred while fetching finalized risks");
      return [];
    } finally {
      setIsLoading(false);
    }
    return finalizedRisks;
  };

  const deleteRisk = async (riskIndex: number) => {
    const token = localStorage.getItem("token");
    if (!token) {
      setError("No authentication token found");
      return;
    }
    try {
      const response = await fetch(`https://api.agentic.complynexus.com/risks/finalized/index/${riskIndex}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      const result = await response.json();
      if (response.ok && result.success) {
        // Check if any risks remain
        if (result.data && result.data.risks && result.data.risks.length > 0) {
          // Update state with remaining risks
          const updatedList = result.data.risks.map((risk: any) => ({
            id: risk.id || "",
            description: risk.description,
            category: risk.category,
            likelihood: risk.likelihood,
            impact: risk.impact,
            treatmentStrategy: risk.treatment_strategy,
            assetValue: risk.asset_value,
            department: risk.department,
            riskOwner: risk.risk_owner,
            securityImpact: risk.security_impact,
            targetDate: risk.target_date,
            riskProgress: risk.risk_progress,
            residualExposure: risk.residual_exposure,
            createdAt: risk.created_at,
            updatedAt: risk.updated_at,
          }));
          setFinalizedRisks(updatedList);
          setError(null); // Clear any previous errors
        } else {
          // No risks remain - set empty state and close modal after a brief delay
          setFinalizedRisks([]);
          setTimeout(() => {
            onClose();
          }, 1000); // Give user time to see the "no risks" message
        }
      } else {
        setError(result.message || "Failed to delete risk");
      }
    } catch (err) {
      console.error("Error deleting risk:", err);
      setError("An error occurred while deleting risk");
    }
  };

  const filteredRisks = finalizedRisks.filter((risk) => {
    const matchesSearch = risk.description.toLowerCase().includes(searchTerm.toLowerCase()) || risk.category.toLowerCase().includes(searchTerm.toLowerCase()) || (risk.department && risk.department.toLowerCase().includes(searchTerm.toLowerCase())) || (risk.riskOwner && risk.riskOwner.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesCategory = !filterCategory || risk.category === filterCategory;
    const matchesProgress = !filterProgress || risk.riskProgress === filterProgress;

    return matchesSearch && matchesCategory && matchesProgress;
  });

  const getRiskLevelClass = (level: string) => {
    switch (level.toLowerCase()) {
      case "high":
        return "risk-high";
      case "medium":
        return "risk-medium";
      case "low":
        return "risk-low";
      default:
        return "risk-medium";
    }
  };

  const getCategoryClass = (category: string) => {
    const categoryLower = category.toLowerCase();
    if (categoryLower.includes("operational")) return "category-operational";
    if (categoryLower.includes("financial")) return "category-financial";
    if (categoryLower.includes("strategic")) return "category-strategic";
    if (categoryLower.includes("compliance") || categoryLower.includes("legal")) return "category-compliance";
    if (categoryLower.includes("cyber") || categoryLower.includes("technology")) return "category-technology";
    if (categoryLower.includes("reputation")) return "category-reputational";
    if (categoryLower.includes("environmental")) return "category-environmental";
    if (categoryLower.includes("competition")) return "category-competition";
    if (categoryLower.includes("external")) return "category-external";
    if (categoryLower.includes("innovation")) return "category-innovation";
    if (categoryLower.includes("internal")) return "category-internal";
    if (categoryLower.includes("project")) return "category-project";
    if (categoryLower.includes("safety")) return "category-safety";
    return "category-default";
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return "N/A";
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return "N/A";
    }
  };

  if (isLoading) {
    return (
      <div className="risk-register-modal">
        <div className="risk-register-content">
          <div className="risk-register-header">
            <h3>📋 Risk Register</h3>
            <button onClick={onClose} className="close-btn">
              ×
            </button>
          </div>
          <div className="loading-container">
            <div className="loading-spinner"></div>
            <p>Loading finalized risks...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="risk-register-modal">
      <div className="risk-register-content">
        <div className="risk-register-header">
          <h3>📋 Risk Register</h3>
          <button onClick={onClose} className="close-btn">
            ×
          </button>
        </div>

        {error && (
          <div className="error-message">
            <p>❌ {error}</p>
            <button onClick={fetchFinalizedRisks} className="retry-btn">
              Retry
            </button>
          </div>
        )}

        {!error && (
          <>
            <div className="risk-register-controls">
              <div className="search-filters">
                <input type="text" placeholder="Search risks..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} className="search-input" />
                <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)} className="filter-select">
                  <option value="">All Categories</option>
                  {RISK_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
                <select value={filterProgress} onChange={(e) => setFilterProgress(e.target.value)} className="filter-select">
                  <option value="">All Progress</option>
                  {PROGRESS_OPTIONS.map((progress) => (
                    <option key={progress} value={progress}>
                      {progress}
                    </option>
                  ))}
                </select>
              </div>
              <div className="risk-count">
                {filteredRisks.length} of {finalizedRisks.length} finalized risks
              </div>
            </div>

            <div className="risk-register-container">
              {filteredRisks.length === 0 ? (
                <div className="no-risks-message">
                  {finalizedRisks.length === 0 ? (
                    <>
                      <p>📭 No finalized risks found</p>
                      <p>Risks will appear here once you finalize them from the risk assessment.</p>
                    </>
                  ) : (
                    <>
                      <p>🔍 No risks match your current filters</p>
                      <p>Try adjusting your search term or filter criteria.</p>
                    </>
                  )}
                </div>
              ) : (
                <div className="risks-grid">
                  {filteredRisks.map((risk, index) => (
                    <div key={risk.id} className="risk-card">
                      <div className="risk-card-header">
                        <span className={`category-badge ${getCategoryClass(risk.category)}`}>{risk.category}</span>
                        <div className="risk-levels">
                          <span className={`risk-level ${getRiskLevelClass(risk.likelihood)}`}>L: {risk.likelihood}</span>
                          <span className={`risk-level ${getRiskLevelClass(risk.impact)}`}>I: {risk.impact}</span>
                        </div>
                      </div>

                      <div className="risk-card-body">
                        <h4 className="risk-description">{risk.description}</h4>
                        <p className="treatment-strategy">{risk.treatmentStrategy}</p>
                      </div>

                      <div className="risk-card-details">
                        <div className="detail-row">
                          <span className="detail-label">Asset Value:</span>
                          <span className="detail-value">{risk.assetValue || "Not specified"}</span>
                        </div>
                        <div className="detail-row">
                          <span className="detail-label">Department:</span>
                          <span className="detail-value">{risk.department || "Not specified"}</span>
                        </div>
                        <div className="detail-row">
                          <span className="detail-label">Risk Owner:</span>
                          <span className="detail-value">{risk.riskOwner || "Not specified"}</span>
                        </div>
                        <div className="detail-row">
                          <span className="detail-label">Security Impact:</span>
                          <span className="detail-value">{risk.securityImpact || "Not specified"}</span>
                        </div>
                        <div className="detail-row">
                          <span className="detail-label">Target Date:</span>
                          <span className="detail-value">{formatDate(risk.targetDate)}</span>
                        </div>
                        <div className="detail-row">
                          <span className="detail-label">Progress:</span>
                          <span className={`progress-badge progress-${risk.riskProgress?.toLowerCase().replace(" ", "-")}`}>{risk.riskProgress || "Identified"}</span>
                        </div>
                        <div className="detail-row">
                          <span className="detail-label">Residual Exposure:</span>
                          <span className={`exposure-badge exposure-${risk.residualExposure?.toLowerCase().replace(" ", "-")}`}>{risk.residualExposure || "Not specified"}</span>
                        </div>
                      </div>

                      <div className="risk-card-footer">
                        <span className="risk-date">Finalized: {formatDate(risk.createdAt)}</span>
                        <button className="delete-risk-btn" onClick={() => deleteRisk(index)}>
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        <div className="risk-register-footer">
          <button className="close-register-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
