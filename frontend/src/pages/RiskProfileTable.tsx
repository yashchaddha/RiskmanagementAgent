import React, { useState, useEffect } from "react";
import "./RiskProfileTable.css";

interface RiskLevel {
  level: number;
  title: string;
  description: string;
}

interface RiskProfile {
  riskType: string;
  definition: string;
  likelihoodScale: RiskLevel[];
  impactScale: RiskLevel[];
  matrixSize: string;
}

interface EditableRiskProfile extends RiskProfile {
  isEditing?: boolean;
}

interface RiskProfileTableProps {
  onClose: () => void;
}

export const RiskProfileTable: React.FC<RiskProfileTableProps> = ({ onClose }) => {
  const [profiles, setProfiles] = useState<EditableRiskProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedProfile, setExpandedProfile] = useState<string | null>(null);
  const [editingProfile, setEditingProfile] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchRiskProfiles();
  }, []);

  const fetchRiskProfiles = async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        setError("No authentication token found");
        setLoading(false);
        return;
      }

      const response = await fetch("http://localhost:8000/user/risk-profiles/table", {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setProfiles(data.tableData);
        } else {
          setError(data.message || "Failed to load risk profiles");
        }
      } else {
        setError("Failed to fetch risk profiles");
      }
    } catch (error) {
      setError("Error connecting to server");
      console.error("Error fetching risk profiles:", error);
    } finally {
      setLoading(false);
    }
  };

  const toggleProfileExpansion = (riskType: string) => {
    setExpandedProfile(expandedProfile === riskType ? null : riskType);
  };

  const toggleEditMode = (riskType: string) => {
    setEditingProfile(editingProfile === riskType ? null : riskType);
  };

  const handleProfileUpdate = (riskType: string, field: string, value: string | RiskLevel[], index?: number) => {
    setProfiles((prev) =>
      prev.map((profile) => {
        if (field === "definition" && profile.riskType === riskType) {
          return { ...profile, definition: value as string };
        } else if (field === "likelihoodScale" && Array.isArray(value) && profile.riskType === riskType) {
          return { ...profile, likelihoodScale: value as RiskLevel[] };
        } else if (field === "impactScale" && Array.isArray(value) && profile.riskType === riskType) {
          return { ...profile, impactScale: value as RiskLevel[] };
        } else if (field === "likelihoodTitle" && typeof index === "number") {
          // Propagate likelihood title change to all profiles
          const newScale = [...profile.likelihoodScale];
          newScale[index] = { ...newScale[index], title: value as string };
          return { ...profile, likelihoodScale: newScale };
        } else if (field === "likelihoodDescription" && typeof index === "number" && profile.riskType === riskType) {
          const newScale = [...profile.likelihoodScale];
          newScale[index] = { ...newScale[index], description: value as string };
          return { ...profile, likelihoodScale: newScale };
        } else if (field === "impactTitle" && typeof index === "number") {
          // Propagate impact title change to all profiles
          const newScale = [...profile.impactScale];
          newScale[index] = { ...newScale[index], title: value as string };
          return { ...profile, impactScale: newScale };
        } else if (field === "impactDescription" && typeof index === "number" && profile.riskType === riskType) {
          const newScale = [...profile.impactScale];
          newScale[index] = { ...newScale[index], description: value as string };
          return { ...profile, impactScale: newScale };
        }
        return profile;
      })
    );
  };

  const saveProfileChanges = async (riskType: string) => {
    setSaving(true);
    try {
      const profile = profiles.find((p) => p.riskType === riskType);
      if (!profile) return;

      const token = localStorage.getItem("token");

      // Save all profiles to ensure synchronized changes are persisted
      const savePromises = profiles.map(async (profileToSave) => {
        const response = await fetch("http://localhost:8000/user/risk-profiles/update", {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            riskType: profileToSave.riskType,
            definition: profileToSave.definition,
            likelihoodScale: profileToSave.likelihoodScale,
            impactScale: profileToSave.impactScale,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to save ${profileToSave.riskType} profile`);
        }

        return response.json();
      });

      await Promise.all(savePromises);
      setEditingProfile(null);
      // Show success message
      console.log("All risk profiles updated successfully");
    } catch (error) {
      console.error("Error saving profiles:", error);
      // Show error message to user
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="risk-profile-overlay">
        <div className="risk-profile-modal">
          <div className="loading-spinner">
            <div className="spinner"></div>
            <p>Loading your risk profiles...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="risk-profile-overlay">
        <div className="risk-profile-modal">
          <div className="error-message">
            <h3>⚠️ Error Loading Risk Profiles</h3>
            <p>{error}</p>
            <button onClick={onClose} className="close-button">
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="risk-profile-overlay">
      <div className="risk-profile-modal">
        <div className="risk-profile-header">
          <h2>📊 Your Risk Profile Dashboard</h2>
          <p>Comprehensive risk assessment framework with category-specific scales</p>
          <button onClick={onClose} className="close-button">
            ✕
          </button>
        </div>

        {editingProfile && (
          <div className="sync-notice">
            <span className="sync-icon">🔄</span>
            <span>Likelihood and Impact titles are synchronized across all risk categories. Changes to titles will apply to all categories.</span>
          </div>
        )}

        <div className="risk-profile-content">
          {profiles.length === 0 ? (
            <div className="no-profiles">
              <h3>No Risk Profiles Found</h3>
              <p>Your risk profiles haven't been set up yet. Please contact your administrator.</p>
            </div>
          ) : (
            <div className="profiles-container">
              {profiles.map((profile) => (
                <div key={profile.riskType} className="profile-card">
                  <div className="profile-header">
                    <div className="profile-title" onClick={() => toggleProfileExpansion(profile.riskType)}>
                      <h3>{profile.riskType}</h3>
                      <span className="matrix-size">{profile.matrixSize}</span>
                    </div>
                    <div className="profile-actions">
                      <button
                        className="edit-button"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleEditMode(profile.riskType);
                        }}
                      >
                        {editingProfile === profile.riskType ? "Cancel" : "Edit"}
                      </button>
                      {editingProfile === profile.riskType && (
                        <button
                          className="save-button"
                          onClick={(e) => {
                            e.stopPropagation();
                            saveProfileChanges(profile.riskType);
                          }}
                          disabled={saving}
                        >
                          {saving ? "Saving..." : "Save"}
                        </button>
                      )}
                      <div className="expand-icon" onClick={() => toggleProfileExpansion(profile.riskType)}>
                        {expandedProfile === profile.riskType ? "▼" : "▶"}
                      </div>
                    </div>
                  </div>

                  <div className="profile-definition">{editingProfile === profile.riskType ? <textarea value={profile.definition} onChange={(e) => handleProfileUpdate(profile.riskType, "definition", e.target.value)} className="editable-definition" rows={3} /> : <p>{profile.definition}</p>}</div>

                  {expandedProfile === profile.riskType && (
                    <div className="profile-details">
                      <div className="scales-container">
                        <div className="scale-section">
                          <h4>Likelihood Scale (1-5)</h4>
                          <div className="scale-table">
                            <table>
                              <thead>
                                <tr>
                                  <th>Level</th>
                                  <th>Title</th>
                                  <th>Description</th>
                                </tr>
                              </thead>
                              <tbody>
                                {profile.likelihoodScale.map((level, index) => (
                                  <tr key={level.level}>
                                    <td className="level-cell">{level.level}</td>
                                    <td className="title-cell">
                                      {editingProfile === profile.riskType ? (
                                        <div className="synchronized-input-container">
                                          <input type="text" value={level.title} onChange={(e) => handleProfileUpdate(profile.riskType, "likelihoodTitle", e.target.value, index)} className="editable-input synchronized-input" title="This change will apply to all risk categories" />
                                          <span className="sync-indicator" title="Synchronized across all categories">
                                            🔄
                                          </span>
                                        </div>
                                      ) : (
                                        level.title
                                      )}
                                    </td>
                                    <td className="description-cell">{editingProfile === profile.riskType ? <textarea value={level.description} onChange={(e) => handleProfileUpdate(profile.riskType, "likelihoodDescription", e.target.value, index)} className="editable-textarea" rows={2} /> : level.description}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>

                        <div className="scale-section">
                          <h4>Impact Scale (1-5)</h4>
                          <div className="scale-table">
                            <table>
                              <thead>
                                <tr>
                                  <th>Level</th>
                                  <th>Title</th>
                                  <th>Description</th>
                                </tr>
                              </thead>
                              <tbody>
                                {profile.impactScale.map((level, index) => (
                                  <tr key={level.level}>
                                    <td className="level-cell">{level.level}</td>
                                    <td className="title-cell">
                                      {editingProfile === profile.riskType ? (
                                        <div className="synchronized-input-container">
                                          <input type="text" value={level.title} onChange={(e) => handleProfileUpdate(profile.riskType, "impactTitle", e.target.value, index)} className="editable-input synchronized-input" title="This change will apply to all risk categories" />
                                          <span className="sync-indicator" title="Synchronized across all categories">
                                            🔄
                                          </span>
                                        </div>
                                      ) : (
                                        level.title
                                      )}
                                    </td>
                                    <td className="description-cell">{editingProfile === profile.riskType ? <textarea value={level.description} onChange={(e) => handleProfileUpdate(profile.riskType, "impactDescription", e.target.value, index)} className="editable-textarea" rows={2} /> : level.description}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
