import React, { useState } from "react";
import "./Auth.css";

interface AuthProps {
  onAuthSuccess: (token: string) => void;
}

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const Auth: React.FC<AuthProps> = ({ onAuthSuccess }) => {
  const [isSignup, setIsSignup] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [location, setLocation] = useState("");
  const [domain, setDomain] = useState("");
  const [risksApplicable, setRisksApplicable] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const url = isSignup ? `${API_URL}/auth/signup` : `${API_URL}/auth/login`;
      const body = isSignup
        ? {
            username,
            password,
            organization_name: organizationName,
            location,
            domain,
            risks_applicable: risksApplicable,
          }
        : new URLSearchParams({ username, password });
      const res = await fetch(url, {
        method: "POST",
        headers: isSignup ? { "Content-Type": "application/json" } : { "Content-Type": "application/x-www-form-urlencoded" },
        body: isSignup ? JSON.stringify(body) : body.toString(),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Auth failed");
      }
      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      onAuthSuccess(data.access_token);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const clearForm = () => {
    setUsername("");
    setPassword("");
    setOrganizationName("");
    setLocation("");
    setDomain("");
    setRisksApplicable([]);
    setError("");
  };

  const toggleMode = () => {
    setIsSignup((s) => !s);
    clearForm();
  };

  return (
    <div className="auth-container">
      <div className="auth-header">
        <h1>🛡️ NexiAgent</h1>
        <p className="auth-subtitle">AI-powered risk & compliance assistant</p>
      </div>

      <div className="auth-card">
        <h2>{isSignup ? "Create Account" : "Welcome Back"}</h2>
        <p className="auth-description">{isSignup ? "Join our platform to streamline your organization's risk management and compliance processes." : "Access your organization's risk assessment dashboard and compliance tools."}</p>

        <form onSubmit={handleSubmit}>
          <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {isSignup && (
            <>
              <input type="text" placeholder="Organization Name" value={organizationName} onChange={(e) => setOrganizationName(e.target.value)} required />
              <input type="text" placeholder="Location (City, Country)" value={location} onChange={(e) => setLocation(e.target.value)} required />
              <input type="text" placeholder="Industry Domain (e.g., Finance, Healthcare, Technology)" value={domain} onChange={(e) => setDomain(e.target.value)} required />
            </>
          )}
          <button type="submit" disabled={loading}>
            {loading ? "Please wait..." : isSignup ? "Create Account" : "Sign In"}
          </button>
        </form>

        <button onClick={toggleMode} className="toggle-btn">
          {isSignup ? "Already have an account? Sign In" : "Don't have an account? Create Account"}
        </button>

        {error && <div className="error">{error}</div>}
      </div>
    </div>
  );
};
