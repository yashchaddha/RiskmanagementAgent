import { useState, useEffect } from "react";
import { Auth } from "./pages/Auth";
import { Chatbot } from "./pages/Chatbot";
import "./App.css";

function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("token"));

  useEffect(() => {
    // Update document title for the Risk Management Agent
    document.title = "Nexi - AI Powered Risk Assessment Agent";
  }, []);

  const handleAuthSuccess = (jwt: string) => {
    setToken(jwt);
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
  };

  return (
    <div className="App" style={{ width: '100%', height: '100vh' }}>
      {!token ? (
        <Auth onAuthSuccess={handleAuthSuccess} />
      ) : (
        <Chatbot onLogout={handleLogout} />
      )}
    </div>
  );
}

export default App;
