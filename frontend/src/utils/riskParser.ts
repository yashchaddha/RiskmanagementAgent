export interface Risk {
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
  securityImpact?: 'Yes' | 'No';
  targetDate?: string;
  riskProgress?: 'Identified' | 'Mitigated' | 'Ongoing Mitigation';
  residualExposure?: 'High' | 'Medium' | 'Low' | 'Ongoing Mitigation';
}

export function parseRisksFromLLMResponse(response: string): Risk[] {
  const risks: Risk[] = [];
  
  try {
    // First, try to parse as JSON
    const jsonMatch = response.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const jsonStr = jsonMatch[0];
      console.log("Attempting to parse JSON:", jsonStr);
      const parsedData = JSON.parse(jsonStr);
      
      if (parsedData.risks && Array.isArray(parsedData.risks)) {
        console.log("Found risks array with", parsedData.risks.length, "risks");
        parsedData.risks.forEach((risk: any, index: number) => {
          if (risk.description && risk.category) {
            risks.push({
              id: `risk-${index + 1}`,
              description: risk.description,
              category: risk.category,
              likelihood: risk.likelihood || "Medium",
              impact: risk.impact || "Medium",
              treatmentStrategy: risk.treatment_strategy || risk.treatmentStrategy || "Implement appropriate risk mitigation strategies.",
              isSelected: true,
              // Initialize new fields with default values
              assetValue: risk.asset_value || "",
              department: risk.department || "",
              riskOwner: risk.risk_owner || "",
              securityImpact: risk.security_impact || undefined,
              targetDate: risk.target_date || "",
              riskProgress: risk.risk_progress || "Identified",
              residualExposure: risk.residual_exposure || undefined
            });
          }
        });
        
        if (risks.length > 0) {
          console.log("Successfully parsed", risks.length, "risks from JSON");
          return risks;
        }
      }
    }
  } catch (error) {
    console.log("JSON parsing failed, falling back to text parsing:", error);
  }
  
  // Fallback to text parsing if JSON parsing fails
  const riskSections = response.split(/\d+\.\s*Risk|Risk\s*\d+:|^Risk\s*\d+/i).filter(section => section.trim());
  
  if (riskSections.length === 0) {
    // If no clear sections found, try to extract from the full text
    return extractRisksFromText(response);
  }
  
  riskSections.forEach((section, index) => {
    const risk = parseRiskSection(section.trim(), index + 1);
    if (risk) {
      risks.push(risk);
    }
  });
  
  // If we couldn't parse structured risks, fall back to text extraction
  if (risks.length === 0) {
    return extractRisksFromText(response);
  }
  
  return risks;
}

function parseRiskSection(section: string, riskNumber: number): Risk | null {
  try {
    // Extract description (usually the first paragraph)
    const descriptionMatch = section.match(/(?:Description|Risk Description|Description:)\s*[:.]?\s*(.+?)(?=\n|$|Category|Likelihood|Impact|Treatment)/i);
    const description = descriptionMatch ? descriptionMatch[1].trim() : extractFirstParagraph(section);
    
    // Extract category
    const categoryMatch = section.match(/(?:Category|Risk Category|Category:)\s*[:.]?\s*(.+?)(?=\n|$|Likelihood|Impact|Treatment|Description)/i);
    const category = categoryMatch ? categoryMatch[1].trim() : "Operational Risks";
    
    // Extract likelihood
    const likelihoodMatch = section.match(/(?:Likelihood|Likelihood:)\s*[:.]?\s*(High|Medium|Low)/i);
    const likelihood = likelihoodMatch ? likelihoodMatch[1] : "Medium";
    
    // Extract impact
    const impactMatch = section.match(/(?:Impact|Impact:)\s*[:.]?\s*(High|Medium|Low)/i);
    const impact = impactMatch ? impactMatch[1] : "Medium";
    
    // Extract treatment strategy
    const treatmentMatch = section.match(/(?:Treatment|Strategy|Treatment Strategy|Risk Treatment|Treatment Strategy:)\s*[:.]?\s*(.+?)(?=\n|$|Risk|$)/i);
    const treatmentStrategy = treatmentMatch ? treatmentMatch[1].trim() : extractLastParagraph(section);
    
    if (!description || description.length < 10) {
      return null;
    }
    
    return {
      id: `risk-${riskNumber}`,
      description: cleanText(description),
      category: cleanText(category),
      likelihood: likelihood,
      impact: impact,
      treatmentStrategy: cleanText(treatmentStrategy),
      isSelected: true, // Default to selected
      // Initialize new fields with default values
      assetValue: "",
      department: "",
      riskOwner: "",
      securityImpact: undefined,
      targetDate: "",
      riskProgress: "Identified",
      residualExposure: undefined
    };
  } catch (error) {
    console.error("Error parsing risk section:", error);
    return null;
  }
}

function extractRisksFromText(text: string): Risk[] {
  const risks: Risk[] = [];
  
  // Split by common risk indicators
  const riskIndicators = [
    /(?:risk|threat|vulnerability|exposure|hazard)/gi,
    /(?:operational|financial|strategic|compliance|cybersecurity|environmental|reputational)/gi
  ];
  
  // Find sentences that contain risk-related keywords
  const sentences = text.split(/[.!?]+/).filter(sentence => sentence.trim().length > 20);
  
  let riskCount = 0;
  sentences.forEach((sentence) => {
    const cleanSentence = sentence.trim();
    if (cleanSentence.length < 20) return;
    
    // Check if sentence contains risk-related content
    const hasRiskKeywords = riskIndicators.some(indicator => indicator.test(cleanSentence));
    
    if (hasRiskKeywords && riskCount < 10) {
      riskCount++;
      
      // Determine category based on content
      const category = determineCategory(cleanSentence);
      
      // Determine likelihood and impact (default to medium)
      const likelihood = determineLikelihood(cleanSentence);
      const impact = determineImpact(cleanSentence);
      
      risks.push({
        id: `risk-${riskCount}`,
        description: cleanText(cleanSentence),
        category: category,
        likelihood: likelihood,
        impact: impact,
        treatmentStrategy: "Implement appropriate controls and monitoring based on risk assessment.",
        isSelected: true,
        // Initialize new fields with default values
        assetValue: "",
        department: "",
        riskOwner: "",
        securityImpact: undefined,
        targetDate: "",
        riskProgress: "Identified",
        residualExposure: undefined
      });
    }
  });
  
  return risks;
}

function extractFirstParagraph(text: string): string {
  const paragraphs = text.split(/\n\s*\n/);
  return paragraphs[0] || text.substring(0, 200);
}

function extractLastParagraph(text: string): string {
  const paragraphs = text.split(/\n\s*\n/);
  return paragraphs[paragraphs.length - 1] || "Implement appropriate risk mitigation strategies.";
}

function determineCategory(text: string): string {
  const textLower = text.toLowerCase();
  
  if (textLower.includes('competition') || textLower.includes('competitor') || textLower.includes('market share')) {
    return "Competition";
  } else if (textLower.includes('external') || textLower.includes('economic') || textLower.includes('political')) {
    return "External";
  } else if (textLower.includes('financial') || textLower.includes('money') || textLower.includes('cost') || textLower.includes('revenue')) {
    return "Financial";
  } else if (textLower.includes('innovation') || textLower.includes('research') || textLower.includes('development') || textLower.includes('rd')) {
    return "Innovation";
  } else if (textLower.includes('internal') || textLower.includes('employee') || textLower.includes('management')) {
    return "Internal";
  } else if (textLower.includes('legal') || textLower.includes('compliance') || textLower.includes('regulation') || textLower.includes('law')) {
    return "Legal and Compliance";
  } else if (textLower.includes('operational') || textLower.includes('process') || textLower.includes('system')) {
    return "Operational";
  } else if (textLower.includes('project') || textLower.includes('timeline') || textLower.includes('scope')) {
    return "Project Management";
  } else if (textLower.includes('reputation') || textLower.includes('brand') || textLower.includes('public')) {
    return "Reputational";
  } else if (textLower.includes('safety') || textLower.includes('health') || textLower.includes('accident')) {
    return "Safety";
  } else if (textLower.includes('strategic') || textLower.includes('business') || textLower.includes('market')) {
    return "Strategic";
  } else if (textLower.includes('technology') || textLower.includes('cyber') || textLower.includes('security') || textLower.includes('data breach')) {
    return "Technology";
  }
  
  return "Operational";
}

function determineLikelihood(text: string): string {
  const textLower = text.toLowerCase();
  
  if (textLower.includes('critical') || textLower.includes('extremely likely') || textLower.includes('certain')) {
    return "Critical";
  } else if (textLower.includes('severe') || textLower.includes('very likely') || textLower.includes('frequent')) {
    return "Severe";
  } else if (textLower.includes('high') || textLower.includes('likely') || textLower.includes('probable')) {
    return "High";
  } else if (textLower.includes('low') || textLower.includes('unlikely') || textLower.includes('rare')) {
    return "Low";
  }
  
  return "Medium";
}

function determineImpact(text: string): string {
  const textLower = text.toLowerCase();
  
  if (textLower.includes('critical') || textLower.includes('catastrophic') || textLower.includes('devastating')) {
    return "Critical";
  } else if (textLower.includes('severe') || textLower.includes('major') || textLower.includes('significant')) {
    return "Severe";
  } else if (textLower.includes('high') || textLower.includes('substantial') || textLower.includes('considerable')) {
    return "High";
  } else if (textLower.includes('low') || textLower.includes('minor') || textLower.includes('minimal')) {
    return "Low";
  }
  
  return "Medium";
}

function cleanText(text: string): string {
  return text
    .replace(/^\s*[-•*]\s*/, '') // Remove leading bullets
    .replace(/^\s*\d+\.\s*/, '') // Remove leading numbers
    .replace(/^\s*[:.]\s*/, '') // Remove leading colons/periods
    .trim();
} 