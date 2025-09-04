import React, { useState } from "react";
import "./Auth.css";
import logo from "../assets/logo.svg";

interface AuthProps {
  onAuthSuccess: (token: string) => void;
}

const API_URL = import.meta.env.VITE_API_URL || "https://api.agentic.complynexus.com";

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
            risks_applicable: risksApplicable
          }
        : new URLSearchParams({ username, password });
      const res = await fetch(url, {
        method: "POST",
        headers: isSignup
          ? { "Content-Type": "application/json" }
          : { "Content-Type": "application/x-www-form-urlencoded" },
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
    setIsSignup(s => !s);
    clearForm();
  };

  return (
    <div className="auth-container">
      <div className="brand-row">
        <div className="brand-left">
          <img src={logo} alt="ComplyNexus" className="brand-logo-img" />
        </div>
        <div className="brand-right">
          <div className="agent-dot">◇</div>
          <div className="agent-text">Risk Agent</div>
        </div>
      </div>

      <div className="auth-card">
        <h2>{isSignup ? "Create account" : "Welcome back"}</h2>
        <p className="auth-description">
          {isSignup
            ? "Create your organization workspace to access risk tools."
            : "Access your organization's risk assessment dashboard and compliance tools."}
        </p>

        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />

          {isSignup && (
            <>
              <input
                type="text"
                placeholder="Organization name"
                value={organizationName}
                onChange={e => setOrganizationName(e.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Location (City, Country)"
                value={location}
                onChange={e => setLocation(e.target.value)}
                required
              />
              <input
                type="text"
                placeholder="Industry domain (e.g., Finance, Healthcare)"
                value={domain}
                onChange={e => setDomain(e.target.value)}
                required
              />
            </>
          )}

          {!isSignup && (
            <div className="aux-row">
              <a href="#" onClick={e => e.preventDefault()} className="link subtle">Forgot password?</a>
            </div>
          )}

          <button type="submit" disabled={loading}>
            {loading ? "Please wait..." : isSignup ? "Create account" : "Sign in"}
          </button>
        </form>

        <button onClick={toggleMode} className="toggle-btn">
          {isSignup ? "Already have an account? Sign in" : "Don't have an account? Sign up"}
        </button>

        {error && <div className="error">{error}</div>}
      </div>

      <div className="footer">© {new Date().getFullYear()} <span>ComplyNexus</span> All Rights Reserved.</div>
    </div>
  );
}; 