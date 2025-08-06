import { useState, useEffect } from "react";
import { Auth } from "./pages/Auth";
import { Chatbot } from "./pages/Chatbot";
import "./App.css";

function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));

  useEffect(() => {
    // Update document title for the Risk Management Agent
    document.title = "Risk Management Agent - AI-Powered Risk Assessment";
  }, []);

  const handleAuthSuccess = (jwt: string) => {
    setToken(jwt);
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
  };

  return (
    <div className="App">
      {!token ? (
        <Auth onAuthSuccess={handleAuthSuccess} />
      ) : (
        <Chatbot onLogout={handleLogout} />
      )}
    </div>
  );
}

export default App;
