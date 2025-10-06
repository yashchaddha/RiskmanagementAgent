import React, { useState, useEffect, useRef } from "react";
import "./Chatbot.css";
import logo from "../assets/logo.svg";
import { RiskTable } from "./RiskTable";
import { RiskRegister } from "./RiskRegister";
import { ControlsTable } from "./ControlsTable";
import { ControlLibrary } from "./ControlLibrary";
import { RiskProfileTable } from "./RiskProfileTable";
import { MatrixPreviewModal } from "./MatrixPreviewModal";
import { parseRisksFromLLMResponse } from "../utils/riskParser";
import loaderAnimation from "../assets/loader-animation.gif";
import badge from "../assets/badge.png";
import nexiGif from "../assets/nexi.gif";
import arrowUp from "../assets/arrow-up.png";

interface AssistantAction {
  type: string;
  item?: AuditNextItem;
}

interface Message {
  id: string;
  text: string;
  sender: "user" | "bot";
  timestamp: Date;
  action?: AssistantAction;
}

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

interface AuditProgressSummary {
  total?: number;
  pending?: number;
  answered?: number;
  skipped?: number;
  all_completed?: boolean;
}

interface AuditEvidenceRecord {
  id: string;
  file_name: string;
  file_size?: number;
  content_type?: string | null;
  bucket?: string | null;
  object_key?: string | null;
  uploaded_at?: string;
  uploaded_by?: string;
  checksum?: string | null;
  version_id?: string | null;
  validation_status?: string | null;
  validation_summary?: string | null;
  validation_confidence?: number | null;
  validation_recommendations?: string[] | null;
  last_validated_at?: string | null;
  validation_model?: string | null;
  validation_error?: string | null;
  validation_truncated?: boolean | null;
}

interface AuditNextItem {
  item_id?: string;
  iso_reference?: string;
  title?: string;
  section_title?: string;
  status?: string;
  description?: string;
  answer?: string;
  type?: string;
  attached_control_ids?: string[];
  evidences?: AuditEvidenceRecord[];
}

interface RiskContext {
  organization?: string;
  industry?: string;
  risk_areas?: string[];
  compliance_requirements?: string[];
  audit?: AuditProgressSummary;
  audit_next_item?: AuditNextItem;
  audit_complete?: boolean;
}

interface ChatTurn {
  role: "user" | "assistant" | "system" | string;
  content: string;
}

interface RiskLevel {
  level: number;
  title: string;
  description: string;
}
interface MatrixProfile {
  riskType: string;
  definition: string;
  likelihoodScale: RiskLevel[];
  impactScale: RiskLevel[];
  matrixSize: string;
}
interface EditableRiskProfile extends MatrixProfile {
  isEditing?: boolean;
}
interface MatrixPreviewData {
  matrix_size: string;
  profiles: MatrixProfile[];
  totalProfiles: number;
}
interface AnnexAMapping {
  id: string;
  title: string;
}
interface ControlItem {
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

// Global animation state to prevent restarts
const animationStates = new Map<
  string,
  {
    isAnimating: boolean;
    currentText: string;
    timer: number | null;
  }
>();

const AnimatedText: React.FC<{ text: string; animate: boolean; onDone?: () => void; onProgress?: () => void; speedMsPerChar?: number; messageId?: string }> = ({ text, animate, onDone, onProgress, speedMsPerChar = 15, messageId }) => {
  const [displayedText, setDisplayedText] = useState(animate ? "" : text);
  const indexRef = useRef(0);
  const onDoneRef = useRef(onDone);
  const onProgressRef = useRef(onProgress);

  // Update refs when callbacks change
  useEffect(() => {
    onDoneRef.current = onDone;
    onProgressRef.current = onProgress;
  }, [onDone, onProgress]);

  useEffect(() => {
    if (!animate) {
      setDisplayedText(text);
      if (messageId) {
        const state = animationStates.get(messageId);
        if (state) {
          if (state.timer) clearTimeout(state.timer);
          animationStates.delete(messageId);
        }
      }
      return;
    }

    if (!messageId) {
      setDisplayedText(text);
      return;
    }

    const state = animationStates.get(messageId);

    // If we're already animating the same text, don't restart
    if (state && state.isAnimating && state.currentText === text) {
      return;
    }

    // If we're animating different text, clear the current animation first
    if (state && state.isAnimating && state.currentText !== text) {
      if (state.timer) {
        clearTimeout(state.timer);
      }
    }

    setDisplayedText("");
    indexRef.current = 0;

    const totalChars = text.length;
    const targetDurationMs = Math.min(4000, Math.max(1200, totalChars * speedMsPerChar));
    const stepMs = Math.max(8, Math.floor(targetDurationMs / Math.max(1, totalChars)));

    const tick = () => {
      const nextIndex = indexRef.current + 1;
      setDisplayedText(text.slice(0, nextIndex));
      indexRef.current = nextIndex;
      if (onProgressRef.current) onProgressRef.current();
      if (nextIndex < text.length) {
        const timer = window.setTimeout(tick, stepMs);
        const currentState = animationStates.get(messageId);
        if (currentState) {
          currentState.timer = timer;
        }
      } else {
        const currentState = animationStates.get(messageId);
        if (currentState) {
          currentState.isAnimating = false;
          currentState.timer = null;
        }
        if (onDoneRef.current) onDoneRef.current();
      }
    };

    const timer = window.setTimeout(tick, stepMs);
    animationStates.set(messageId, {
      isAnimating: true,
      currentText: text,
      timer,
    });

    return () => {
      const currentState = animationStates.get(messageId);
      if (currentState && currentState.timer) {
        clearTimeout(currentState.timer);
        currentState.isAnimating = false;
        currentState.timer = null;
      }
    };
  }, [text, animate, speedMsPerChar, messageId]);

  return <p>{displayedText}</p>;
};

interface ChatbotProps {
  onLogout: () => void;
}

export const Chatbot: React.FC<ChatbotProps> = ({ onLogout }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<ChatTurn[]>([]);
  const [riskContext, setRiskContext] = useState<RiskContext>({});
  const [showRiskSummary, setShowRiskSummary] = useState(false);
  const [riskSummary, setRiskSummary] = useState("");
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [showRiskTable, setShowRiskTable] = useState(false);
  const [showRiskRegister, setShowRiskRegister] = useState(false);
  const [showRiskProfileTable, setShowRiskProfileTable] = useState(false);
  const [showMatrixPreviewModal, setShowMatrixPreviewModal] = useState(false);
  const [matrixPreviewData, setMatrixPreviewData] = useState<MatrixPreviewData | null>(null);
  const [generatedRisks, setGeneratedRisks] = useState<Risk[]>([]);
  const [isFinalizingRisks, setIsFinalizingRisks] = useState(false);
  const [showControlsTable, setShowControlsTable] = useState(false);
  const [showControlLibrary, setShowControlLibrary] = useState(false);
  const [generatedControls, setGeneratedControls] = useState<ControlItem[]>([]);
  const [isSavingControls, setIsSavingControls] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [animateMessageId, setAnimateMessageId] = useState<string | null>(null);

  const [isAuditAnswerModalOpen, setIsAuditAnswerModalOpen] = useState(false);
  const [activeAuditItem, setActiveAuditItem] = useState<AuditNextItem | null>(null);
  const [auditAnswerText, setAuditAnswerText] = useState("");
  const [isSubmittingAuditAnswer, setIsSubmittingAuditAnswer] = useState(false);
  const [isUploadingAuditEvidence, setIsUploadingAuditEvidence] = useState(false);
  const [uploadedAuditEvidence, setUploadedAuditEvidence] = useState<AuditEvidenceRecord[]>([]);
  const [auditModalAlert, setAuditModalAlert] = useState<string>("");
  const [validatingEvidenceId, setValidatingEvidenceId] = useState<string | null>(null);
  const [removingEvidenceId, setRemovingEvidenceId] = useState<string | null>(null);
  const [isRefreshingAuditItem, setIsRefreshingAuditItem] = useState(false);
  const [isAttachControlsModalOpen, setIsAttachControlsModalOpen] = useState(false);
  const [attachControlsList, setAttachControlsList] = useState<ControlItem[]>([]);
  const [selectedControlIds, setSelectedControlIds] = useState<string[]>([]);
  const [isLoadingAttachControls, setIsLoadingAttachControls] = useState(false);
  const [isSavingAttachControls, setIsSavingAttachControls] = useState(false);
  const [attachControlsAlert, setAttachControlsAlert] = useState<string>("");

  const fileUploadInputRef = useRef<HTMLInputElement | null>(null);

  const auditProgress = riskContext?.audit;
  const auditNextItem = riskContext?.audit_next_item;
  const auditComplete = Boolean(riskContext?.audit_complete || auditProgress?.all_completed);
  const answeredCount = auditProgress?.answered ?? 0;
  const pendingCount = auditProgress?.pending ?? 0;
  const skippedCount = auditProgress?.skipped ?? 0;
  const totalCount = auditProgress?.total ?? answeredCount + pendingCount + skippedCount;

  const formatEvidenceStatus = (status?: string | null) => {
    if (!status) return "";
    return status.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
  };

  const formatValidationConfidence = (value?: number | null) => {
    if (typeof value !== "number" || Number.isNaN(value)) {
      return null;
    }
    return `${Math.round(value * 100)}% confidence`;
  };

  const formatValidationTimestamp = (iso?: string | null) => {
    if (!iso) return null;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return null;
    }
    return date.toLocaleString();
  };

  // const currentAnnexReference = activeAuditItem?.iso_reference || "";

  const attachedControlOptions = selectedControlIds.map((controlId) => {
    const detail = attachControlsList.find((control) => control.control_id === controlId);
    return { controlId, detail };
  });

  const availableControls = attachControlsList.filter((control) => !selectedControlIds.includes(control.control_id));

  const hasAnyAttachableControls = availableControls.length > 0 || attachedControlOptions.length > 0;

  // Note: latestBotMessageId no longer used; animation is controlled by animateMessageId

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleChatSuccess = async (data: any) => {
    const formattedResponse = await checkForRiskGeneration(data.response, data.risk_context);
    const assistantActions = Array.isArray(data?.assistant_actions) ? data.assistant_actions : [];
    const requestAction = assistantActions.find((action: any) => action?.type === "request_audit_answer");

    const botMessage: Message = {
      id: (Date.now() + 1).toString(),
      text: formattedResponse,
      sender: "bot",
      timestamp: new Date(),
      action: requestAction && requestAction.item ? { type: requestAction.type, item: requestAction.item } : undefined,
    };

    setMessages((prev) => [...prev, botMessage]);
    setAnimateMessageId(botMessage.id);
    setConversationHistory(data.conversation_history);
    setRiskContext(data.risk_context);

    const genControls = data?.risk_context?.generated_controls;
    if (Array.isArray(genControls) && genControls.length > 0) {
      setGeneratedControls(genControls);
      setShowControlsTable(true);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (!isAttachControlsModalOpen) {
      if (activeAuditItem?.attached_control_ids) {
        setSelectedControlIds(activeAuditItem.attached_control_ids);
      } else {
        setSelectedControlIds([]);
      }
    }
  }, [activeAuditItem?.item_id, isAttachControlsModalOpen]);

  useEffect(() => {
    // Get greeting when component mounts
    getGreeting();
  }, []);

  const getGreeting = async () => {
    // Use static greeting message
    const greetingMessage: Message = {
      id: Date.now().toString(),
      text: "Welcome to the Risk Management Agent! I'm here to help your organization with comprehensive risk assessment, compliance management, and risk mitigation strategies.\n\nI can assist you with identifying operational, financial, strategic, and compliance risks, as well as provide guidance on industry regulations and best practices.\n\nWhat specific risk management challenges or compliance requirements would you like to discuss today?",
      sender: "bot",
      timestamp: new Date(),
    };
    setMessages([greetingMessage]);
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputMessage,
      sender: "user",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage("");
    setIsLoading(true);

    // Check for apply matrix intent first
    if (checkForApplyMatrixIntent(inputMessage)) {
      const matrixSize = extractMatrixSize(inputMessage);
      const response = await applyMatrixRecommendation(matrixSize);

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: response,
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
      setAnimateMessageId(botMessage.id);
      setIsLoading(false);
      return;
    }

    // Check for matrix recommendation intent
    if (checkForMatrixRecommendationIntent(inputMessage)) {
      const matrixSize = extractMatrixSize(inputMessage);
      const response = await createMatrixRecommendation(matrixSize);

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: response,
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
      setAnimateMessageId(botMessage.id);
      setIsLoading(false);
      return;
    }

    // Check for risk profile intent
    if (checkForRiskProfileIntent(inputMessage)) {
      setShowRiskProfileTable(true);
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "📊 Opening your Risk Profile Dashboard...\n\nI'll display your comprehensive risk assessment framework with all risk categories and their specialized assessment scales.",
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
      setAnimateMessageId(botMessage.id);
      setIsLoading(false);
      return;
    }

    // Check for risk register intent
    if (checkForRiskRegisterIntent(inputMessage)) {
      setShowRiskRegister(true);
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "📋 Opening your Risk Register...\n\nI'll display all your finalized risks in a comprehensive view where you can search, filter, and review your risk assessment data.",
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
      setAnimateMessageId(botMessage.id);
      setIsLoading(false);
      return;
    }

    // Check for control library intent
    if (checkForControlLibraryIntent(inputMessage)) {
      setShowControlLibrary(true);
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "📚 Opening your Control Library...\n\nI'll display all your existing controls from the database. You can search, filter, and review all controls in your organization's control library.",
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
      setAnimateMessageId(botMessage.id);
      setIsLoading(false);
      return;
    }

    try {
      const token = localStorage.getItem("token");
      console.log("Token from localStorage:", token ? "Token exists" : "No token found");

      if (!token) {
        throw new Error("No authentication token found");
      }

      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: inputMessage,
          conversation_history: conversationHistory,
          risk_context: riskContext,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        await handleChatSuccess(data);
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error("API Error:", response.status, errorData);

        let errorText = "Sorry, I encountered an error while processing your risk management query. Please try again.";

        if (response.status === 401) {
          errorText = "Authentication error. Please log in again.";
        } else if (errorData.detail) {
          errorText = `Error: ${errorData.detail}`;
        }

        const errorMessage: Message = {
          id: (Date.now() + 1).toString(),
          text: errorText,
          sender: "bot",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMessage]);
        setAnimateMessageId(errorMessage.id);
      }
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "Sorry, I encountered an error while processing your risk management query. Please try again.",
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setAnimateMessageId(errorMessage.id);
    } finally {
      setIsLoading(false);
    }
  };

  const saveSelectedControls = async (controls: ControlItem[]) => {
    try {
      setIsSavingControls(true);
      const token = localStorage.getItem("token");
      if (!token) throw new Error("No authentication token found");

      // Bulk-save in a single API call for reliability
      const payload = {
        controls: controls.map((c) => ({
          control_id: c.control_id,
          control_title: c.control_title,
          control_description: c.control_description,
          objective: c.objective,
          annexA_map: Array.isArray(c.annexA_map) ? c.annexA_map : [],
          owner_role: c.owner_role || "",
          process_steps: c.process_steps || [],
          evidence_samples: c.evidence_samples || [],
          linked_risk_ids: c.linked_risk_ids || [],
          metrics: c.metrics || [],
          frequency: c.frequency || "",
          policy_ref: c.policy_ref || "",
          status: c.status || "Planned",
          rationale: c.rationale || "",
          assumptions: c.assumptions || "",
        })),
      };

      const resp = await fetch("http://localhost:8000/controls/bulk-save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      const result = await resp.json().catch(() => ({} as any));
      const savedCount = (result?.data?.length as number) || 0;
      const failedCount = (result?.failed?.length as number) || 0;

      // Close modal, clear context and notify user in chat
      setShowControlsTable(false);
      setGeneratedControls([]);
      setRiskContext((prev) => {
        const rc: any = { ...(prev || {}) };
        if ((rc as any).generated_controls !== undefined) delete (rc as any).generated_controls;
        return rc;
      });
      const botMessage: Message = {
        id: (Date.now() + 2).toString(),
        text: failedCount ? `Saved ${savedCount} control(s). ${failedCount} failed to save.` : `Saved ${savedCount} control(s) to your control library.`,
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
      setAnimateMessageId(botMessage.id);
    } catch (e) {
      console.error("Error saving controls:", e);
      const botMessage: Message = {
        id: (Date.now() + 2).toString(),
        text: `There was an error saving your controls. Please try again.`,
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, botMessage]);
      setAnimateMessageId(botMessage.id);
    } finally {
      setIsSavingControls(false);
    }
  };

  const generateRiskSummary = async () => {
    setIsGeneratingSummary(true);
    try {
      const token = localStorage.getItem("token");
      const response = await fetch("http://localhost:8000/risk-summary/finalized", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setRiskSummary(data.summary);
        setShowRiskSummary(true);
      } else {
        setRiskSummary("Unable to generate risk assessment summary. Please try again.");
        setShowRiskSummary(true);
      }
    } catch (error) {
      console.error("Error generating summary:", error);
      setRiskSummary("Unable to generate risk assessment summary due to an error.");
      setShowRiskSummary(true);
    } finally {
      setIsGeneratingSummary(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const getQuickActions = () => {
    return ["Generate risks for our organization", "Open risk register", "Control Library", "Generate finalized risks summary", "Update my risk preferences", "Help me create a risk assessment framework"];
  };

  const handleQuickAction = (action: string) => {
    if (action === "Generate finalized risks summary") {
      generateRiskSummary();
    } else if (action === "Control Library") {
      setShowControlLibrary(true);
    } else {
      setInputMessage(action);
    }
  };

  const handleRiskSelectionChange = async (riskId: string, isSelected: boolean) => {
    setGeneratedRisks((prevRisks) => prevRisks.map((risk) => (risk.id === riskId ? { ...risk, isSelected } : risk)));

    // Update risk selection in database
    await updateRiskSelectionInDatabase(riskId, isSelected);
  };

  const updateRiskSelectionInDatabase = async (riskId: string, isSelected: boolean) => {
    try {
      const token = localStorage.getItem("token");
      const riskIndex = generatedRisks.findIndex((risk) => risk.id === riskId);

      if (riskIndex !== -1) {
        const response = await fetch(`http://localhost:8000/risks/${riskIndex}/selection`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            is_selected: isSelected,
          }),
        });

        if (response.ok) {
          console.log("Risk selection updated successfully");
        } else {
          console.error("Failed to update risk selection");
        }
      }
    } catch (error) {
      console.error("Error updating risk selection:", error);
    }
  };

  const handleFinalizeRisks = async (selectedRisks: Risk[]) => {
    try {
      setIsFinalizingRisks(true);
      const token = localStorage.getItem("token");

      // Use the selectedRisks directly since they already contain the edited data
      const risksToFinalize = selectedRisks;

      console.log("Finalizing risks:", risksToFinalize); // Debug log

      const response = await fetch("http://localhost:8000/risks/finalize", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          risks: risksToFinalize.map((risk) => ({
            description: risk.description,
            category: risk.category,
            likelihood: risk.likelihood,
            impact: risk.impact,
            treatment_strategy: risk.treatmentStrategy,
            is_selected: risk.isSelected,
            asset_value: risk.assetValue,
            department: risk.department,
            risk_owner: risk.riskOwner,
            security_impact: risk.securityImpact,
            target_date: risk.targetDate,
            risk_progress: risk.riskProgress,
            residual_exposure: risk.residualExposure,
          })),
        }),
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Risks finalized successfully:", data.message);

        // Add a success message to the chat
        const successMessage: Message = {
          id: (Date.now() + 1).toString(),
          text: `✅ **Risks Finalized Successfully!**\n\n${data.message}\n\nYour selected risks have been saved to the finalized risks collection and are now part of your organization's risk assessment.`,
          sender: "bot",
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, successMessage]);
        setShowRiskTable(false);
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error("Failed to finalize risks:", errorData);

        // Add an error message to the chat
        const errorMessage: Message = {
          id: (Date.now() + 1).toString(),
          text: `❌ **Error Finalizing Risks**\n\nFailed to finalize the selected risks. Please try again.`,
          sender: "bot",
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, errorMessage]);
      }
    } catch (error) {
      console.error("Error finalizing risks:", error);

      // Add an error message to the chat
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: `❌ **Error Finalizing Risks**\n\nAn error occurred while finalizing the risks. Please try again.`,
        sender: "bot",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsFinalizingRisks(false);
    }
  };

  const checkForRiskProfileIntent = (message: string): boolean => {
    const riskProfileIndicators = ["show risk profile", "view risk profile", "display risk profile", "open risk profile", "risk profile", "my risk profile", "risk categories", "risk scales", "likelihood scale", "impact scale", "risk matrix", "risk assessment matrix", "show risk matrix", "view risk matrix", "risk preferences", "risk settings", "risk configuration", "risk framework"];

    return riskProfileIndicators.some((indicator) => message.toLowerCase().includes(indicator.toLowerCase()));
  };

  const checkForMatrixRecommendationIntent = (message: string): boolean => {
    const matrixKeywords = ["recommend", "suggest", "create", "generate", "set up", "configure", "3x3", "3*3", "4x4", "4*4", "5x5", "5*5", "matrix size", "risk matrix"];

    const hasMatrixKeyword = matrixKeywords.some((keyword) => message.toLowerCase().includes(keyword.toLowerCase()));

    const hasMatrixSize = /(3x3|3\*3|4x4|4\*4|5x5|5\*5)/i.test(message);

    return hasMatrixKeyword && hasMatrixSize;
  };

  const checkForApplyMatrixIntent = (message: string): boolean => {
    const applyKeywords = ["apply", "confirm", "accept", "use", "implement", "activate", "make permanent", "finalize", "commit", "save"];

    const hasApplyKeyword = applyKeywords.some((keyword) => message.toLowerCase().includes(keyword.toLowerCase()));

    const hasMatrixSize = /(3x3|3\*3|4x4|4\*4|5x5|5\*5)/i.test(message);

    return hasApplyKeyword && hasMatrixSize;
  };

  const openAuditAnswerModal = async (item?: AuditNextItem) => {
    if (!item?.item_id) return;

    setActiveAuditItem(item);
    setAuditAnswerText(item.answer ?? "");
    setUploadedAuditEvidence(item.evidences ?? []);
    setValidatingEvidenceId(null);
    setRemovingEvidenceId(null);
    setAuditModalAlert("");
    setIsAuditAnswerModalOpen(true);

    const token = localStorage.getItem("token");
    if (!token) {
      setAuditModalAlert("Authentication error. Please log in again.");
      return;
    }

    setIsRefreshingAuditItem(true);

    try {
      const response = await fetch(`http://localhost:8000/audit/items/${item.item_id}`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.data) {
        const latestItem = data.data as AuditNextItem;
        setActiveAuditItem(latestItem);
        setAuditAnswerText(latestItem.answer ?? "");
        setUploadedAuditEvidence(latestItem.evidences ?? []);
      } else {
        const message = data?.detail || data?.message || "Failed to fetch the latest clause details.";
        setAuditModalAlert(message);
      }
    } catch (error) {
      setAuditModalAlert("Failed to fetch the latest clause details. Please try again.");
    } finally {
      setIsRefreshingAuditItem(false);
    }
  };

  const closeAuditAnswerModal = () => {
    closeAttachControlsModal();
    setIsAuditAnswerModalOpen(false);
    setActiveAuditItem(null);
    setAuditAnswerText("");
    setUploadedAuditEvidence([]);
    setSelectedControlIds([]);
    setValidatingEvidenceId(null);
    setRemovingEvidenceId(null);
    setIsRefreshingAuditItem(false);
    setAuditModalAlert("");
    if (fileUploadInputRef.current) {
      fileUploadInputRef.current.value = "";
    }
  };

  const handleAuditEvidenceUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!activeAuditItem?.item_id || !event.target.files?.length) {
      return;
    }

    const token = localStorage.getItem("token");
    if (!token) {
      setAuditModalAlert("Authentication error. Please log in again.");
      return;
    }

    const file = event.target.files[0];
    setIsUploadingAuditEvidence(true);
    setAuditModalAlert("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`http://localhost:8000/audit/items/${activeAuditItem.item_id}/evidence`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.data) {
        const updatedItem = data.data as AuditNextItem;
        setActiveAuditItem(updatedItem);
        setAuditAnswerText(updatedItem.answer ?? "");
        setUploadedAuditEvidence(updatedItem.evidences ?? []);
        setValidatingEvidenceId(null);
        setRemovingEvidenceId(null);
        setAuditModalAlert(data?.message || `Evidence "${file.name}" uploaded successfully.`);
      } else {
        const message = data?.detail || data?.message || "Failed to upload evidence. Please try again.";
        setAuditModalAlert(message);
      }
    } catch (error) {
      setAuditModalAlert("Failed to upload evidence. Please try again.");
    } finally {
      setIsUploadingAuditEvidence(false);
      if (fileUploadInputRef.current) {
        fileUploadInputRef.current.value = "";
      }
    }
  };

  const handleValidateEvidence = async (evidenceId: string) => {
    if (!activeAuditItem?.item_id) {
      setAuditModalAlert("Unable to determine the clause or control. Please close and reopen the dialog.");
      return;
    }

    const token = localStorage.getItem("token");
    if (!token) {
      setAuditModalAlert("Authentication error. Please log in again.");
      return;
    }

    setValidatingEvidenceId(evidenceId);
    setAuditModalAlert("");

    try {
      const response = await fetch(`http://localhost:8000/audit/items/${activeAuditItem.item_id}/evidence/${evidenceId}/validate`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.data) {
        const updatedItem = data.data as AuditNextItem;
        setActiveAuditItem(updatedItem);
        setAuditAnswerText(updatedItem.answer ?? "");
        setUploadedAuditEvidence(updatedItem.evidences ?? []);
        setRemovingEvidenceId((current) => (current === evidenceId ? null : current));
        setAuditModalAlert(data?.message || "Evidence validation completed.");
      } else {
        const message = data?.detail || data?.message || "Failed to validate evidence. Please try again.";
        setAuditModalAlert(message);
      }
    } catch (error) {
      setAuditModalAlert("Failed to validate evidence. Please try again.");
    } finally {
      setValidatingEvidenceId(null);
    }
  };

  const handleRemoveEvidence = async (evidenceId: string) => {
    if (!activeAuditItem?.item_id) {
      setAuditModalAlert("Unable to determine the clause or control. Please close and reopen the dialog.");
      return;
    }

    const token = localStorage.getItem("token");
    if (!token) {
      setAuditModalAlert("Authentication error. Please log in again.");
      return;
    }

    setRemovingEvidenceId(evidenceId);
    setAuditModalAlert("");

    try {
      const response = await fetch(`http://localhost:8000/audit/items/${activeAuditItem.item_id}/evidence/${evidenceId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.data) {
        const updatedItem = data.data as AuditNextItem;
        setActiveAuditItem(updatedItem);
        setAuditAnswerText(updatedItem.answer ?? "");
        setUploadedAuditEvidence(updatedItem.evidences ?? []);
        setValidatingEvidenceId((current) => (current === evidenceId ? null : current));
        setAuditModalAlert(data?.message || "Evidence removed.");
      } else {
        const message = data?.detail || data?.message || "Failed to remove evidence. Please try again.";
        setAuditModalAlert(message);
      }
    } catch (error) {
      setAuditModalAlert("Failed to remove evidence. Please try again.");
    } finally {
      setRemovingEvidenceId(null);
    }
  };

  const loadControlsForAttachment = async () => {
    const token = localStorage.getItem("token");
    if (!token) {
      setAttachControlsAlert("Authentication error. Please log in again.");
      setAttachControlsList([]);
      return;
    }

    setIsLoadingAttachControls(true);
    setAttachControlsAlert("");

    try {
      const response = await fetch("http://localhost:8000/controls", {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && Array.isArray(data?.data)) {
        const controls = data.data as ControlItem[];
        const isoReference = (activeAuditItem?.iso_reference || "").trim();
        const normalizedIso = isoReference.replace(/[^a-z0-9]/gi, "").toLowerCase();
        const filteredControls = controls.filter((control) => {
          if (!isoReference) return true;
          return (control.annexA_map || []).some((mapping) => {
            const mappingId = (mapping?.id || "").trim();
            if (!mappingId) return false;
            const normalizedMapping = mappingId.replace(/[^a-z0-9]/gi, "").toLowerCase();
            return normalizedMapping === normalizedIso;
          });
        });

        setAttachControlsList(filteredControls);
        if (filteredControls.length === 0) {
          setAttachControlsAlert("No controls found that are mapped to this annex.");
        }
      } else {
        const message = data?.detail || data?.message || "Failed to load controls. Please try again.";
        setAttachControlsAlert(message);
        setAttachControlsList([]);
      }
    } catch (error) {
      setAttachControlsAlert("Failed to load controls. Please try again.");
      setAttachControlsList([]);
    } finally {
      setIsLoadingAttachControls(false);
    }
  };

  const openAttachControlsModal = async (item?: AuditNextItem | null) => {
    const targetItem = item ?? activeAuditItem;
    if (!targetItem?.item_id) {
      return;
    }

    setSelectedControlIds(targetItem.attached_control_ids ?? []);
    setAttachControlsAlert("");
    setAttachControlsList([]);
    setIsAttachControlsModalOpen(true);
    await loadControlsForAttachment();
  };

  const closeAttachControlsModal = () => {
    setIsAttachControlsModalOpen(false);
    setAttachControlsList([]);
    setAttachControlsAlert("");
    setIsLoadingAttachControls(false);
    setIsSavingAttachControls(false);
  };

  const toggleControlSelection = (controlId: string) => {
    setSelectedControlIds((prev) => {
      if (prev.includes(controlId)) {
        return prev.filter((id) => id !== controlId);
      }
      return [...prev, controlId];
    });
  };

  const handleAttachControlsSubmit = async () => {
    if (!activeAuditItem?.item_id) {
      setAttachControlsAlert("Unable to determine the annex control. Please close and reopen the dialog.");
      return;
    }

    const token = localStorage.getItem("token");
    if (!token) {
      setAttachControlsAlert("Authentication error. Please log in again.");
      return;
    }

    setIsSavingAttachControls(true);
    setAttachControlsAlert("");

    try {
      const response = await fetch(`http://localhost:8000/audit/items/${activeAuditItem.item_id}/controls`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ control_ids: selectedControlIds }),
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok && data?.data) {
        const updatedItem = data.data as AuditNextItem;
        setActiveAuditItem(updatedItem);
        setSelectedControlIds(updatedItem.attached_control_ids ?? []);
        setUploadedAuditEvidence(updatedItem.evidences ?? []);

        setRiskContext((prev) => {
          if (!prev) return prev;
          const next = { ...prev };
          if (next.audit_next_item?.item_id === updatedItem.item_id) {
            next.audit_next_item = { ...next.audit_next_item, attached_control_ids: updatedItem.attached_control_ids };
          }
          return next;
        });

        setAuditModalAlert("Controls attached to this annex have been updated.");
        closeAttachControlsModal();
      } else {
        const message = data?.detail || data?.message || "Failed to update controls. Please try again.";
        setAttachControlsAlert(message);
      }
    } catch (error) {
      setAttachControlsAlert("Failed to update controls. Please try again.");
    } finally {
      setIsSavingAttachControls(false);
    }
  };

  const sendAuditConfirmationMessage = async (messageText: string): Promise<boolean> => {
    const userMessage: Message = {
      id: Date.now().toString(),
      text: messageText,
      sender: "user",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    let wasSuccessful = false;

    try {
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("No authentication token found");
      }

      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: messageText,
          conversation_history: conversationHistory,
          risk_context: riskContext,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        await handleChatSuccess(data);
        wasSuccessful = true;
      } else {
        const errorData = await response.json().catch(() => ({}));
        let errorText = "Sorry, I encountered an error while processing your audit update. Please try again.";
        if (response.status === 401) {
          errorText = "Authentication error. Please log in again.";
        } else if (errorData.detail) {
          errorText = `Error: ${errorData.detail}`;
        }

        const errorMessage: Message = {
          id: (Date.now() + 1).toString(),
          text: errorText,
          sender: "bot",
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, errorMessage]);
        setAnimateMessageId(errorMessage.id);
      }
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "Sorry, I encountered an error while processing your audit update. Please try again.",
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setAnimateMessageId(errorMessage.id);
    } finally {
      setIsLoading(false);
    }

    return wasSuccessful;
  };

  const handleAuditAnswerSubmit = async () => {
    if (!activeAuditItem?.item_id) {
      setAuditModalAlert("Unable to determine the clause. Please close the dialog and try again.");
      return;
    }

    if (!auditAnswerText.trim()) {
      setAuditModalAlert("Please enter your clause response before submitting.");
      return;
    }

    const token = localStorage.getItem("token");
    if (!token) {
      setAuditModalAlert("Authentication error. Please log in again.");
      return;
    }

    setIsSubmittingAuditAnswer(true);
    setAuditModalAlert("");

    try {
      const response = await fetch(`http://localhost:8000/audit/items/${activeAuditItem.item_id}/answer`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ answer: auditAnswerText.trim() }),
      });

      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        const updatedItem = data?.data as AuditNextItem | undefined;
        if (updatedItem) {
          setActiveAuditItem(updatedItem);
          setAuditAnswerText(updatedItem.answer ?? "");
          setUploadedAuditEvidence(updatedItem.evidences ?? []);
        }

        const clauseLabel = updatedItem?.iso_reference || activeAuditItem.iso_reference || activeAuditItem.title || "the clause";
        const delivered = await sendAuditConfirmationMessage(`Answer recorded for ${clauseLabel}.`);
        if (delivered) {
          closeAuditAnswerModal();
        } else {
          setAuditModalAlert("Answer saved, but I couldn't notify Nexi. Please try again to continue the conversation.");
        }
      } else {
        const message = data?.detail || data?.message || "Failed to submit the answer. Please try again.";
        setAuditModalAlert(message);
      }
    } catch (error) {
      setAuditModalAlert("Failed to submit the answer. Please try again.");
    } finally {
      setIsSubmittingAuditAnswer(false);
    }
  };

  const extractMatrixSize = (message: string): string => {
    if (/(3x3|3\*3)/i.test(message)) return "3x3";
    if (/(4x4|4\*4)/i.test(message)) return "4x4";
    if (/(5x5|5\*5)/i.test(message)) return "5x5";
    return "5x5"; // default
  };

  const createMatrixRecommendation = async (matrixSize: string) => {
    try {
      const token = localStorage.getItem("token");

      // Create a message for the agent to process
      const matrixMessage = `Recommend a ${matrixSize} matrix for my organization`;

      console.log("Sending matrix recommendation request to agent:", matrixMessage);

      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: matrixMessage,
          conversation_history: conversationHistory,
          risk_context: riskContext,
        }),
      });

      if (response.ok) {
        const data = await response.json();

        // Update conversation history and risk context
        setConversationHistory(data.conversation_history);
        setRiskContext(data.risk_context);

        // Check if the agent generated matrix data
        if (data.risk_context && data.risk_context.generated_matrix) {
          console.log("Matrix data generated by agent:", data.risk_context.generated_matrix);

          // Transform agent's matrix data to match the expected format for the modal
          const matrixData = data.risk_context.generated_matrix;
          const toRiskLevels = (scale: unknown[]): RiskLevel[] => {
            return (scale || []).map((item: unknown, idx: number) => {
              if (typeof item === "object" && item !== null && "level" in (item as Record<string, unknown>) && "title" in (item as Record<string, unknown>)) {
                const obj = item as { level?: unknown; title?: unknown; description?: unknown };
                return { level: Number(obj.level) || idx + 1, title: String(obj.title || ""), description: String(obj.description || "") };
              }
              const title = String(item as unknown as string);
              return { level: idx + 1, title, description: "" };
            });
          };

          const formattedMatrixData: MatrixPreviewData = {
            matrix_size: matrixSize,
            profiles:
              (matrixData.risk_categories as Array<{ riskType: string; definition: string; likelihoodScale?: unknown[]; impactScale?: unknown[] }>)?.map((category) => ({
                riskType: category.riskType,
                definition: category.definition,
                likelihoodScale: toRiskLevels(category.likelihoodScale || []),
                impactScale: toRiskLevels(category.impactScale || []),
                matrixSize: matrixSize,
              })) || [],
            totalProfiles: matrixData.risk_categories?.length || 0,
          };

          setMatrixPreviewData(formattedMatrixData);
          setShowMatrixPreviewModal(true);
        } else {
          // Fallback: Fetch matrix data from API if agent didn't generate it
          console.log("No matrix data from agent, fetching from API");
          try {
            const matrixDataResponse = await fetch("http://localhost:8000/user/risk-profiles/matrix-recommendation", {
              method: "POST",
              headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                matrix_size: matrixSize,
              }),
            });

            if (matrixDataResponse.ok) {
              const matrixResult = await matrixDataResponse.json();
              if (matrixResult.success) {
                console.log("Fallback matrix data received:", matrixResult.data);
                setMatrixPreviewData(matrixResult.data);
                setShowMatrixPreviewModal(true);
              }
            }
          } catch (matrixError) {
            console.error("Error fetching fallback matrix data:", matrixError);
          }
        }

        // Return the agent's response
        return data.response;
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error("Agent API Error:", response.status, errorData);

        if (response.status === 401) {
          return "Authentication error. Please log in again.";
        } else if (errorData.detail) {
          return `Error: ${errorData.detail}`;
        }

        return "Failed to create matrix recommendation. Please try again.";
      }
    } catch (error) {
      console.error("Error creating matrix recommendation:", error);
      return "An error occurred while creating the matrix recommendation.";
    }
  };

  const applyMatrixRecommendation = async (matrixSize: string) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch("http://localhost:8000/user/risk-profiles/apply-matrix-recommendation", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          matrix_size: matrixSize,
        }),
      });

      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          return `✅ **${matrixSize} Matrix Configuration Applied Successfully!**

Your risk profiles have been permanently updated with the ${matrixSize} matrix configuration. All risk categories now use the new assessment scales.

**What's Changed:**
• All risk categories updated to ${matrixSize} matrix
• Likelihood and impact scales synchronized across categories
• Configuration is now permanent and will be used for future risk assessments

You can continue using the risk profile dashboard to further customize the scales if needed.`;
        } else {
          return `Error applying matrix configuration: ${result.message}`;
        }
      } else {
        return "Failed to apply matrix configuration. Please try again.";
      }
    } catch (error) {
      console.error("Error applying matrix configuration:", error);
      return "An error occurred while applying the matrix configuration.";
    }
  };

  const handleApplyMatrix = async (matrixSize: string, updatedProfiles?: EditableRiskProfile[]) => {
    try {
      const token = localStorage.getItem("token");

      console.log("Applying matrix configuration:", { matrixSize, updatedProfiles });

      // Use the new endpoint that accepts custom profiles
      const response = await fetch("http://localhost:8000/user/risk-profiles/apply-matrix-configuration", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          matrix_size: matrixSize,
          profiles: updatedProfiles || [],
        }),
      });

      if (response.ok) {
        const result = await response.json();
        if (result.success) {
          // Close the modal and show success message
          setShowMatrixPreviewModal(false);
          setMatrixPreviewData(null);

          const botMessage: Message = {
            id: (Date.now() + 1).toString(),
            text: `✅ **${matrixSize} Matrix Configuration Applied Successfully!**

Your risk profiles have been permanently updated with the ${matrixSize} matrix configuration. All risk categories now use the new assessment scales.

**What's Changed:**
• All risk categories updated to ${matrixSize} matrix
• Likelihood and impact scales synchronized across categories
• Configuration is now permanent and will be used for future risk assessments

You can now use the risk profile dashboard to further customize the scales if needed.`,
            sender: "bot",
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, botMessage]);
        } else {
          throw new Error(result.message);
        }
      } else {
        throw new Error("Failed to apply matrix configuration");
      }
    } catch (error) {
      console.error("Error applying matrix configuration:", error);
      // Show error message
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: `❌ **Error Applying Matrix Configuration**

Failed to apply the ${matrixSize} matrix configuration: ${error instanceof Error ? error.message : "Unknown error"}

Please try again or contact support if the issue persists.`,
        sender: "bot",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    }
  };

  const checkForRiskRegisterIntent = (message: string): boolean => {
    const riskRegisterIndicators = ["open risk register", "show risk register", "view risk register", "display risk register", "show finalized risks", "view finalized risks", "display finalized risks", "open finalized risks", "risk register", "finalized risks", "show my risks", "view my risks", "display my risks"];

    return riskRegisterIndicators.some((indicator) => message.toLowerCase().includes(indicator.toLowerCase()));
  };

  const checkForControlLibraryIntent = (message: string): boolean => {
    const controlLibraryIndicators = ["open control library", "show control library", "view control library", "display control library", "control library", "show controls", "view controls", "display controls", "my controls", "existing controls", "control database"];

    return controlLibraryIndicators.some((indicator) => message.toLowerCase().includes(indicator.toLowerCase()));
  };

  const checkForRiskGeneration = async (response: string, riskContext: any) => {
    if (riskContext.generated_risks) {
      const parsedRisks = parseRisksFromLLMResponse(response);
      if (parsedRisks.length > 0) {
        setGeneratedRisks(parsedRisks);
        setShowRiskTable(true);
        await saveRisksToDatabase(parsedRisks);

        return formatRisksForChat(parsedRisks);
      }
    }
    return response;
  };

  const saveRisksToDatabase = async (risks: Risk[]) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch("http://localhost:8000/risks/save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          risks: risks.map((risk) => ({
            description: risk.description,
            category: risk.category,
            likelihood: risk.likelihood,
            impact: risk.impact,
            treatment_strategy: risk.treatmentStrategy,
            is_selected: risk.isSelected,
            asset_value: risk.assetValue,
            department: risk.department,
            risk_owner: risk.riskOwner,
            security_impact: risk.securityImpact,
            target_date: risk.targetDate,
            risk_progress: risk.riskProgress,
            residual_exposure: risk.residualExposure,
          })),
        }),
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Risks saved successfully:", data.message);
      } else {
        console.error("Failed to save risks to database");
      }
    } catch (error) {
      console.error("Error saving risks to database:", error);
    }
  };

  const formatRisksForChat = (risks: Risk[]): string => {
    let formattedResponse = "🔍 Generated Risks for Your Organization\n\n";

    risks.forEach((risk, index) => {
      formattedResponse += `${index + 1}. ${risk.description}\n`;
      formattedResponse += `📋 Category: ${risk.category}\n`;
      formattedResponse += `📊 Likelihood: ${risk.likelihood}\n`;
      formattedResponse += `⚡ Impact: ${risk.impact}\n`;
      formattedResponse += `🛡️ Treatment Strategy: ${risk.treatmentStrategy}\n`;
      formattedResponse += `\n---\n\n`;
    });

    formattedResponse += "💡 You can view these risks in a detailed table format and select which ones to include in your risk assessment.";

    return formattedResponse;
  };

  return (
    <div className="chatbot-container">
      <div className="chatbot-header">
        <div className="header-content">
          <div className="brand">
            <img src={logo} alt="ComplyNexus" className="brand-logo-img" />
          </div>
        </div>
        <div className="header-actions">
          <button onClick={generateRiskSummary} disabled={isGeneratingSummary} className="summary-btn" title="Generate comprehensive risk assessment summary based on your finalized risks">
            {isGeneratingSummary ? "Generating..." : "Finalised Risk Summary"}
          </button>
          <button onClick={onLogout} className="logout-btn">
            Logout
          </button>
        </div>
      </div>

      {showRiskSummary && (
        <div className="risk-summary-modal">
          <div className="summary-content">
            <div className="summary-header">
              <h3>📊 Finalized Risks Assessment Summary</h3>
              <button onClick={() => setShowRiskSummary(false)} className="close-btn">
                ×
              </button>
            </div>
            <div className="summary-body">
              <pre>{riskSummary}</pre>
            </div>
          </div>
        </div>
      )}

      {showRiskTable && (
        <RiskTable
          risks={generatedRisks}
          onRiskSelectionChange={handleRiskSelectionChange}
          onFinalize={handleFinalizeRisks}
          onClose={() => {
            setShowRiskTable(false);
            setGeneratedRisks([]);
            setRiskContext((prev) => {
              const rc: any = { ...(prev || {}) };
              if (rc.generated_risks !== undefined) delete rc.generated_risks;
              return rc;
            });
          }}
          isFinalizing={isFinalizingRisks}
        />
      )}

      {showRiskRegister && <RiskRegister onClose={() => setShowRiskRegister(false)} />}

      {showControlsTable && (
        <ControlsTable
          controls={generatedControls}
          onClose={() => {
            setShowControlsTable(false);
            setGeneratedControls([]);
            setRiskContext((prev) => {
              const rc: any = { ...(prev || {}) };
              if (rc.generated_controls !== undefined) delete rc.generated_controls;
              return rc;
            });
          }}
          onSaveSelected={saveSelectedControls}
          isSaving={isSavingControls}
        />
      )}

      {showRiskProfileTable && <RiskProfileTable onClose={() => setShowRiskProfileTable(false)} />}

      {showControlLibrary && <ControlLibrary onClose={() => setShowControlLibrary(false)} />}

      {showMatrixPreviewModal && (
        <MatrixPreviewModal
          isOpen={showMatrixPreviewModal}
          onClose={() => {
            setShowMatrixPreviewModal(false);
            setMatrixPreviewData(null);
          }}
          matrixData={matrixPreviewData}
          onApplyMatrix={handleApplyMatrix}
        />
      )}

      {isAuditAnswerModalOpen && activeAuditItem && (
        <div className="audit-modal-backdrop">
          <div className="audit-modal">
            <div className="audit-modal-header">
              <h3>Submit Clause Response</h3>
              <button className="audit-modal-close" onClick={closeAuditAnswerModal} disabled={isSubmittingAuditAnswer || isUploadingAuditEvidence}>
                X
              </button>
            </div>
            <div className="audit-modal-body">
              {isRefreshingAuditItem && <div className="audit-modal-refresh">Fetching the latest clause details...</div>}
              <p className="audit-modal-clause">
                {activeAuditItem.iso_reference && <span className="audit-modal-clause-ref">{activeAuditItem.iso_reference}</span>}
                {activeAuditItem.title && <span className="audit-modal-clause-title">{activeAuditItem.title}</span>}
              </p>
              {activeAuditItem.description && <p className="audit-modal-description">{activeAuditItem.description}</p>}
              <label className="audit-modal-label" htmlFor="audit-answer-input">
                Your response
              </label>
              <textarea id="audit-answer-input" value={auditAnswerText} onChange={(event) => setAuditAnswerText(event.target.value)} placeholder="Capture your clause response..." rows={6} disabled={isSubmittingAuditAnswer} />
              <div className="audit-modal-buttons">
                <button className="audit-submit-btn" onClick={handleAuditAnswerSubmit} disabled={isSubmittingAuditAnswer || isUploadingAuditEvidence}>
                  {isSubmittingAuditAnswer ? "Saving..." : "Submit answer"}
                </button>
                <label className={`audit-upload-btn${isUploadingAuditEvidence || isSubmittingAuditAnswer ? " disabled" : ""}`}>
                  <input type="file" ref={fileUploadInputRef} onChange={handleAuditEvidenceUpload} disabled={isUploadingAuditEvidence || isSubmittingAuditAnswer} accept="*/*" hidden />
                  {isUploadingAuditEvidence ? "Uploading..." : "Upload evidence"}
                </label>
                {activeAuditItem?.type === "annex" && (
                  <button className="audit-attach-btn" onClick={() => void openAttachControlsModal(activeAuditItem)} disabled={isSubmittingAuditAnswer || isUploadingAuditEvidence || isRefreshingAuditItem}>
                    Attach controls
                  </button>
                )}
                <button className="audit-cancel-btn" onClick={closeAuditAnswerModal} disabled={isSubmittingAuditAnswer || isUploadingAuditEvidence}>
                  Cancel
                </button>
              </div>
              {uploadedAuditEvidence.length > 0 && (
                <div className="audit-uploaded-list">
                  <span>Uploaded evidence:</span>
                  <ul>
                    {uploadedAuditEvidence.map((evidence) => {
                      const statusLabel = formatEvidenceStatus(evidence.validation_status);
                      const confidenceLabel = formatValidationConfidence(evidence.validation_confidence);
                      const validatedAt = formatValidationTimestamp(evidence.last_validated_at);
                      const recommendations = Array.isArray(evidence.validation_recommendations) ? evidence.validation_recommendations : [];

                      return (
                        <li key={evidence.id}>
                          <div className="audit-evidence-row">
                            <div className="audit-evidence-header">
                              <div className="audit-evidence-meta">
                                <span className="audit-evidence-name">{evidence.file_name}</span>
                                {statusLabel && <span className={`audit-evidence-status audit-evidence-status-${evidence.validation_status}`}>{statusLabel}</span>}
                                {confidenceLabel && <span className="audit-evidence-confidence">{confidenceLabel}</span>}
                                {validatedAt && <span className="audit-evidence-timestamp">Last checked {validatedAt}</span>}
                              </div>
                              <div className="audit-evidence-actions">
                                <button className="audit-evidence-remove-btn" onClick={() => handleRemoveEvidence(evidence.id)} disabled={isRefreshingAuditItem || isUploadingAuditEvidence || isSubmittingAuditAnswer || removingEvidenceId === evidence.id || validatingEvidenceId === evidence.id} aria-label={`Remove ${evidence.file_name}`}>
                                  &times;
                                </button>
                                <button className="audit-evidence-validate-btn" onClick={() => handleValidateEvidence(evidence.id)} disabled={isRefreshingAuditItem || isUploadingAuditEvidence || isSubmittingAuditAnswer || validatingEvidenceId === evidence.id || removingEvidenceId === evidence.id}>
                                  {validatingEvidenceId === evidence.id ? "Validating..." : "Validate evidence"}
                                </button>
                              </div>
                            </div>
                            {evidence.validation_summary && <p className="audit-evidence-summary">{evidence.validation_summary}</p>}
                            {!evidence.validation_summary && evidence.validation_error && <p className="audit-evidence-error">{evidence.validation_error}</p>}
                            {recommendations.length > 0 && (
                              <ul className="audit-evidence-recommendations">
                                {recommendations.map((rec, index) => (
                                  <li key={index}>{rec}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              {auditModalAlert && <p className="audit-modal-alert">{auditModalAlert}</p>}
            </div>
          </div>
        </div>
      )}

      {isAttachControlsModalOpen && activeAuditItem && (
        <div className="audit-modal-backdrop">
          <div className="attach-controls-modal">
            <div className="attach-controls-header">
              <h3>Attach Controls</h3>
              <button className="attach-controls-close" onClick={closeAttachControlsModal} disabled={isSavingAttachControls} aria-label="Close attach controls modal">
                &times;
              </button>
            </div>
            <div className="attach-controls-body">
              <p className="attach-controls-context">
                Annex {activeAuditItem.iso_reference || ""}
                {activeAuditItem.title ? ` - ${activeAuditItem.title}` : ""}
              </p>
              {attachControlsAlert && <p className="attach-controls-alert">{attachControlsAlert}</p>}
              {isLoadingAttachControls ? (
                <p className="attach-controls-loading">Loading controls...</p>
              ) : !hasAnyAttachableControls ? (
                <p className="attach-controls-empty">No controls mapped to this annex.</p>
              ) : (
                <div className="attach-controls-sections">
                  <div className="attach-controls-section">
                    <h4>Currently attached</h4>
                    {attachedControlOptions.length === 0 ? (
                      <p className="attach-controls-empty">No controls attached yet.</p>
                    ) : (
                      <div className="attach-controls-list">
                        {attachedControlOptions.map(({ controlId, detail }) => (
                          <label key={controlId} className="attach-control-item">
                            <input type="checkbox" checked={selectedControlIds.includes(controlId)} onChange={() => toggleControlSelection(controlId)} disabled={isSavingAttachControls} />
                            <span>
                              <span className="attach-control-title">{detail?.control_title || controlId}</span>
                              <span className="attach-control-id">{controlId}</span>
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="attach-controls-section">
                    <h4>Available controls</h4>
                    {availableControls.length === 0 ? (
                      <p className="attach-controls-empty">All eligible controls are already attached.</p>
                    ) : (
                      <div className="attach-controls-list">
                        {availableControls.map((control) => (
                          <label key={control.control_id} className="attach-control-item">
                            <input type="checkbox" checked={selectedControlIds.includes(control.control_id)} onChange={() => toggleControlSelection(control.control_id)} disabled={isSavingAttachControls} />
                            <span>
                              <span className="attach-control-title">
                                {control.control_title}
                                <span className="attach-control-label">Recommended</span>
                              </span>
                              {control.control_id ? <span className="attach-control-id">{control.control_id}</span> : null}
                            </span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div className="attach-controls-footer">
              <button className="attach-controls-save" onClick={handleAttachControlsSubmit} disabled={isSavingAttachControls}>
                {isSavingAttachControls ? "Saving..." : "Save attachments"}
              </button>
              <button className="attach-controls-cancel" onClick={closeAttachControlsModal} disabled={isSavingAttachControls}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {auditProgress && (
        <div className="audit-status-card">
          <div className="audit-status-top">
            <span className="audit-status-title">Audit Facilitator</span>
            <span className={`audit-status-badge ${auditComplete ? "complete" : "in-progress"}`}>{auditComplete ? "Complete" : "In Progress"}</span>
          </div>
          <div className="audit-status-metrics">
            <span>
              <strong>{answeredCount}</strong> answered
            </span>
            <span>
              <strong>{pendingCount}</strong> pending
            </span>
            <span>
              <strong>{skippedCount}</strong> skipped
            </span>
            <span>
              <strong>{totalCount}</strong> total
            </span>
          </div>
          {!auditComplete && auditNextItem?.iso_reference && (
            <div className="audit-next-clause">
              <span className="audit-next-label">Next clause</span>
              <span className="audit-next-value">
                {auditNextItem.iso_reference}
                {auditNextItem.title ? ` — ${auditNextItem.title}` : ""}
              </span>
            </div>
          )}
          {!auditComplete && skippedCount > 0 && <p className="audit-skip-note">{skippedCount === 1 ? "1 clause is skipped" : `${skippedCount} clauses are skipped`} — complete them before finishing the assessment.</p>}
          {auditComplete && <p className="audit-complete-note">Great work—the audit checklist is complete. Ask Nexi to generate risks whenever you're ready.</p>}
        </div>
      )}

      <div className="quick-actions">
        <h4>Quick Actions</h4>
        <div className="action-buttons">
          {getQuickActions().map((action, index) => (
            <button key={index} onClick={() => handleQuickAction(action)} className="quick-action-btn" disabled={isLoading}>
              {action}
            </button>
          ))}
        </div>
      </div>

      <div className="chat-messages">
        {messages.map((message) => (
          <div key={message.id} className={`message ${message.sender === "user" ? "user-message" : "bot-message"}`}>
            <div className="message-content">
              {message.sender === "bot" ? (
                <>
                  <div className="bot-header">
                    <img src={badge} alt="Risk Agent" className="bot-badge-img" style={{ width: "500px", height: "22px", display: "block" }} />
                  </div>
                  <AnimatedText
                    text={message.text}
                    animate={animateMessageId === message.id}
                    onProgress={scrollToBottom}
                    onDone={() => {
                      if (animateMessageId === message.id) setAnimateMessageId(null);
                    }}
                    messageId={message.id}
                  />
                  {message.action?.type === "request_audit_answer" && (
                    <button className="audit-answer-button" onClick={() => void openAuditAnswerModal(message.action?.item)} disabled={isLoading}>
                      Submit answer
                    </button>
                  )}
                </>
              ) : (
                <p>{message.text}</p>
              )}
              <span className="message-time">{formatTime(message.timestamp)}</span>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message bot-message">
            <div className="message-content">
              <div className="loader-row">
                <img src={loaderAnimation} alt="Loading" className="loader-animation" />
                <span className="loader-text">Nexi is thinking...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <div className="input-wrapper">
          <img src={nexiGif} alt="Nexi" className="input-gif" />
          <textarea value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} onKeyPress={handleKeyPress} placeholder="Ask about risk assessment, compliance, or risk management strategies..." disabled={isLoading} rows={1} className="chat-input" />
          <button onClick={sendMessage} disabled={!inputMessage.trim() || isLoading} className="send-btn">
            <img src={arrowUp} alt="Send" className="send-icon" />
          </button>
        </div>
      </div>
    </div>
  );
};
