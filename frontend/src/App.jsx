import { useState, useEffect } from 'react'
import { RetellWebClient } from 'retell-client-js-sdk'
import './App.css'

// Initialize the client outside the component to prevent re-renders
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
      const response = await fetch("https://d454a0b2c16a.ngrok-free.app/create-web-call", {
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
      <h1>IT Helpdesk Voice AI</h1>
      
      <div className="card">
        <button 
          onClick={toggleCall} 
          className={`call-button ${isCalling ? 'active' : ''}`}
        >
          {isCalling ? (
            <span>Stop Call ⏹️</span>
          ) : (
            <span>Start IT Support Call 🎙️</span>
          )}
        </button>
        <p className={isCalling ? "active-status" : "status-text"}>
          {isCalling ? "Agent is listening..." : "Click to speak with an IT Technician"}
        </p>
      </div>
    </div>
  );
}
export default App;
