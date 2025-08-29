import React, { useState, useEffect, useRef } from "react";
import "./Chatbot.css";
import { RiskTable } from "./RiskTable";
import { RiskRegister } from "./RiskRegister";
import { RiskProfileTable } from "./RiskProfileTable";
import { MatrixPreviewModal } from "./MatrixPreviewModal";
import { parseRisksFromLLMResponse } from "../utils/riskParser";

interface Message {
  id: string;
  text: string;
  sender: "user" | "bot";
  timestamp: Date;
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

interface RiskContext {
  organization?: string;
  industry?: string;
  risk_areas?: string[];
  compliance_requirements?: string[];
}

interface ChatbotProps {
  onLogout: () => void;
}

export const Chatbot: React.FC<ChatbotProps> = ({ onLogout }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<any[]>([]);
  const [riskContext, setRiskContext] = useState<RiskContext>({});
  const [showRiskSummary, setShowRiskSummary] = useState(false);
  const [riskSummary, setRiskSummary] = useState("");
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false);
  const [showRiskTable, setShowRiskTable] = useState(false);
  const [showRiskRegister, setShowRiskRegister] = useState(false);
  const [showRiskProfileTable, setShowRiskProfileTable] = useState(false);
  const [showMatrixPreviewModal, setShowMatrixPreviewModal] = useState(false);
  const [matrixPreviewData, setMatrixPreviewData] = useState<any>(null);
  const [generatedRisks, setGeneratedRisks] = useState<Risk[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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

        // Check if this response contains generated risks and format it
        const formattedResponse = await checkForRiskGeneration(data.response);

        // Create bot message with formatted response
        const botMessage: Message = {
          id: (Date.now() + 1).toString(),
          text: formattedResponse,
          sender: "bot",
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, botMessage]);
        setConversationHistory(data.conversation_history);
        setRiskContext(data.risk_context);
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
    } finally {
      setIsLoading(false);
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
    return ["Generate risks for our organization", "Open risk register", "Generate finalized risks summary", "Update my risk preferences", "What are the key operational risks for our organization?", "How can we improve our compliance with GDPR?", "What cybersecurity risks should we be aware of?", "Help me create a risk assessment framework"];
  };

  const handleQuickAction = (action: string) => {
    if (action === "Generate finalized risks summary") {
      generateRiskSummary();
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
          const formattedMatrixData = {
            matrix_size: matrixSize,
            profiles:
              matrixData.risk_categories?.map((category: any) => ({
                riskType: category.riskType,
                definition: category.definition,
                likelihoodScale: matrixData.matrix_scales?.likelihood || [],
                impactScale: matrixData.matrix_scales?.impact || [],
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

  const handleApplyMatrix = async (matrixSize: string, updatedProfiles?: any[]) => {
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

  const checkForRiskGeneration = async (response: string) => {
    // Check if the response contains generated risks (JSON format or text format)
    const hasJsonRisks = response.includes('"risks"') && response.includes('"description"');

    // More specific risk generation indicators
    const riskGenerationIndicators = ["generated risks for your organization", "risk assessment for", "applicable risks", "risk recommendations", "risk analysis results"];

    // Check for preference update indicators to avoid false positives
    const preferenceUpdateIndicators = ["current risk preference settings", "risk preference options", "updating to", "matrix configuration", "preference settings"];

    const isPreferenceUpdate = preferenceUpdateIndicators.some((indicator) => response.toLowerCase().includes(indicator.toLowerCase()));

    // Only proceed if it's not a preference update and contains risk generation indicators
    if (!isPreferenceUpdate && (hasJsonRisks || riskGenerationIndicators.some((indicator) => response.toLowerCase().includes(indicator.toLowerCase())))) {
      const parsedRisks = parseRisksFromLLMResponse(response);
      if (parsedRisks.length > 0) {
        setGeneratedRisks(parsedRisks);
        setShowRiskTable(true);

        // Save risks to database
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
          <h2>🛡️ Risk Management Agent</h2>
          <p className="header-subtitle">AI-powered risk assessment & compliance management</p>
        </div>
        <div className="header-actions">
          <button onClick={generateRiskSummary} disabled={isGeneratingSummary} className="summary-btn" title="Generate comprehensive risk assessment summary based on your finalized risks">
            {isGeneratingSummary ? "Generating..." : "📊 Finalized Risks Summary"}
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

      {showRiskTable && <RiskTable risks={generatedRisks} onRiskSelectionChange={handleRiskSelectionChange} onFinalize={handleFinalizeRisks} onClose={() => setShowRiskTable(false)} />}

      {showRiskRegister && <RiskRegister onClose={() => setShowRiskRegister(false)} />}

      {showRiskProfileTable && <RiskProfileTable onClose={() => setShowRiskProfileTable(false)} />}

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

      <div className="quick-actions">
        <h4>💡 Quick Actions</h4>
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
              <p>{message.text}</p>
              <span className="message-time">{formatTime(message.timestamp)}</span>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message bot-message">
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <div className="input-wrapper">
          <textarea value={inputMessage} onChange={(e) => setInputMessage(e.target.value)} onKeyPress={handleKeyPress} placeholder="Ask about risk assessment, compliance, or risk management strategies..." disabled={isLoading} rows={1} className="chat-input" />
          <button onClick={sendMessage} disabled={!inputMessage.trim() || isLoading} className="send-btn">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M22 2L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};
