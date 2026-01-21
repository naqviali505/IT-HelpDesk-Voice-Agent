import { useState, useEffect } from 'react'
import { RetellWebClient } from 'retell-client-js-sdk'
import './App.css'

const retellWebClient = new RetellWebClient();
function App() {
  const [isCalling, setIsCalling] = useState(false);

  useEffect(() => {
    retellWebClient.on("call_ended", () => {
      console.log("Call ended");
      setIsCalling(false);
    });

    retellWebClient.on("error", (error) => {
      console.error("Retell Error:", error);
      setIsCalling(false);
    });
  }, []);

  const toggleCall = async () => {
    if (isCalling) {
      retellWebClient.stopCall();
      setIsCalling(false);
      return;
    }

    try {
      setIsCalling(true);
      const baseUrl = import.meta.env.VITE_NGROK_URL;
      const response = await fetch(`${baseUrl}/create-web-call`,{
        method: "POST",
      });
      const data = await response.json();
      await retellWebClient.startCall({
        accessToken: data.access_token,
      });

    } catch (error) {
      console.error("Failed to start call:", error);
      setIsCalling(false);
    }
  };

  return (
  <div className="container">
    <div className="card">
      <h1>Helpdesk Voice Assistant</h1>
      <p style={{marginBottom: '2rem', textTransform: 'none', opacity: 0.6}}>
        Instant hardware & system support
      </p>

      <div className="orb-container">
        <button 
          onClick={toggleCall} 
          className={`call-button ${isCalling ? 'active' : ''}`}
        >
          {isCalling ? "⏹️" : "🎙️"}
        </button>
      </div>

      <p className={isCalling ? "active-status" : "status-text"}>
        {isCalling ? "••• AGENT LISTENING •••" : "READY TO ASSIST"}
      </p>
    </div>
  </div>
);
}
export default App;