import React, { useState } from 'react';
import './MatrixPreviewModal.css';

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

interface MatrixPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  matrixData: {
    matrix_size: string;
    profiles: RiskProfile[];
  } | null;
  onApplyMatrix: (matrixSize: string, updatedProfiles?: EditableRiskProfile[]) => Promise<void>;
}

export const MatrixPreviewModal: React.FC<MatrixPreviewModalProps> = ({
  isOpen,
  onClose,
  matrixData,
  onApplyMatrix
}) => {
  const [expandedProfile, setExpandedProfile] = useState<string | null>(null);
  const [isApplying, setIsApplying] = useState(false);
  const [editingProfile, setEditingProfile] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<EditableRiskProfile[]>([]);

  // Initialize profiles when matrixData changes
  React.useEffect(() => {
    if (matrixData) {
      console.log("MatrixPreviewModal received data:", matrixData);
      setProfiles(matrixData.profiles.map(profile => ({ ...profile, isEditing: false })));
    }
  }, [matrixData]);

  if (!isOpen || !matrixData) {
    return null;
  }

  const handleApplyMatrix = async () => {
    setIsApplying(true);
    try {
      console.log("MatrixPreviewModal calling onApplyMatrix with:", { matrix_size: matrixData.matrix_size, profiles });
      await onApplyMatrix(matrixData.matrix_size, profiles);
      onClose();
    } catch (error) {
      console.error('Error applying matrix:', error);
    } finally {
      setIsApplying(false);
    }
  };

  const toggleProfileExpansion = (riskType: string) => {
    setExpandedProfile(expandedProfile === riskType ? null : riskType);
  };

  const toggleEditMode = (riskType: string) => {
    setEditingProfile(editingProfile === riskType ? null : riskType);
  };

  const handleProfileUpdate = (riskType: string, field: string, value: string | RiskLevel[], index?: number) => {
    setProfiles(prev => prev.map(profile => {
      if (field === 'definition' && profile.riskType === riskType) {
        return { ...profile, definition: value as string };
      } else if (field === 'likelihoodTitle' && typeof index === 'number') {
        // Propagate likelihood title change to all profiles
        const newScale = [...profile.likelihoodScale];
        newScale[index] = { ...newScale[index], title: value as string };
        return { ...profile, likelihoodScale: newScale };
      } else if (field === 'likelihoodDescription' && typeof index === 'number' && profile.riskType === riskType) {
        const newScale = [...profile.likelihoodScale];
        newScale[index] = { ...newScale[index], description: value as string };
        return { ...profile, likelihoodScale: newScale };
      } else if (field === 'impactTitle' && typeof index === 'number') {
        // Propagate impact title change to all profiles
        const newScale = [...profile.impactScale];
        newScale[index] = { ...newScale[index], title: value as string };
        return { ...profile, impactScale: newScale };
      } else if (field === 'impactDescription' && typeof index === 'number' && profile.riskType === riskType) {
        const newScale = [...profile.impactScale];
        newScale[index] = { ...newScale[index], description: value as string };
        return { ...profile, impactScale: newScale };
      }
      return profile;
    }));
  };



  return (
    <div className="matrix-preview-overlay">
      <div className="matrix-preview-modal">
        <div className="matrix-preview-header">
          <h2>🎯 {matrixData.matrix_size} Matrix Preview</h2>
          <p>Review the recommended {matrixData.matrix_size} risk assessment framework</p>
          <button onClick={onClose} className="close-button">
            ✕
          </button>
        </div>

        <div className="matrix-preview-content">
          <div className="preview-notice">
            <span className="preview-icon">👁️</span>
            <span>This is a preview. Your existing risk profiles will remain unchanged until you click "Set this as my Risk Profile".</span>
          </div>
          
          {editingProfile && (
            <div className="sync-notice">
              <span className="sync-icon">🔄</span>
              <span>Likelihood and Impact titles are synchronized across all risk categories. Changes to titles will apply to all categories.</span>
            </div>
          )}

          <div className="profiles-container">
            {profiles.map((profile) => (
                              <div key={profile.riskType} className="profile-card">
                  <div className="profile-header">
                    <div 
                      className="profile-title"
                      onClick={() => toggleProfileExpansion(profile.riskType)}
                    >
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
                        {editingProfile === profile.riskType ? 'Cancel' : 'Edit'}
                      </button>
                      <div 
                        className="expand-icon"
                        onClick={() => toggleProfileExpansion(profile.riskType)}
                      >
                        {expandedProfile === profile.riskType ? '▼' : '▶'}
                      </div>
                    </div>
                  </div>

                  <div className="profile-definition">
                    {editingProfile === profile.riskType ? (
                      <textarea
                        value={profile.definition}
                        onChange={(e) => handleProfileUpdate(profile.riskType, 'definition', e.target.value)}
                        className="editable-definition"
                        rows={3}
                      />
                    ) : (
                      <p>{profile.definition}</p>
                    )}
                  </div>

                {expandedProfile === profile.riskType && (
                  <div className="scales-container">
                    <div className="scale-section">
                      <h4>Likelihood Scale (1-{profile.likelihoodScale.length})</h4>
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
                                      <input
                                        type="text"
                                        value={level.title}
                                        onChange={(e) => handleProfileUpdate(profile.riskType, 'likelihoodTitle', e.target.value, index)}
                                        className="editable-input synchronized-input"
                                        title="This change will apply to all risk categories"
                                      />
                                      <span className="sync-indicator" title="Synchronized across all categories">🔄</span>
                                    </div>
                                  ) : (
                                    level.title
                                  )}
                                </td>
                                <td className="description-cell">
                                  {editingProfile === profile.riskType ? (
                                    <textarea
                                      value={level.description}
                                      onChange={(e) => handleProfileUpdate(profile.riskType, 'likelihoodDescription', e.target.value, index)}
                                      className="editable-textarea"
                                      rows={2}
                                    />
                                  ) : (
                                    level.description
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <div className="scale-section">
                      <h4>Impact Scale (1-{profile.impactScale.length})</h4>
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
                                      <input
                                        type="text"
                                        value={level.title}
                                        onChange={(e) => handleProfileUpdate(profile.riskType, 'impactTitle', e.target.value, index)}
                                        className="editable-input synchronized-input"
                                        title="This change will apply to all risk categories"
                                      />
                                      <span className="sync-indicator" title="Synchronized across all categories">🔄</span>
                                    </div>
                                  ) : (
                                    level.title
                                  )}
                                </td>
                                <td className="description-cell">
                                  {editingProfile === profile.riskType ? (
                                    <textarea
                                      value={level.description}
                                      onChange={(e) => handleProfileUpdate(profile.riskType, 'impactDescription', e.target.value, index)}
                                      className="editable-textarea"
                                      rows={2}
                                    />
                                  ) : (
                                    level.description
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="matrix-preview-footer">
          <div className="action-buttons">
            <button 
              className="cancel-button"
              onClick={onClose}
            >
              Cancel
            </button>
            <button 
              className="apply-button"
              onClick={handleApplyMatrix}
              disabled={isApplying}
            >
              {isApplying ? 'Applying...' : 'Set this as my Risk Profile'}
            </button>
          </div>
          <div className="warning-text">
            ⚠️ This action will replace your existing risk profiles with this {matrixData.matrix_size} configuration.
          </div>
        </div>
      </div>
    </div>
  );
}; 