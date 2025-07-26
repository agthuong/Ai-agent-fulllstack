import React, { useState, useEffect } from 'react';
import './App.css';

// Define the components of our system based on your diagram
const NODES = {
  "DB-MASTER": { top: '50%', left: '50%' },
  "DB-AI báo giá": { top: '30%', left: '20%' },
  "AI Thư ký": { top: '70%', left: '20%' },
  "VISION-AI": { top: '30%', left: '80%' },
  "USER": { top: '10%', left: '50%' },
  "TRẢ LỜI CHO USER": { top: '90%', left: '50%' },
};

const AgentNode = ({ name, status, message }) => {
  return (
    <div className={`node ${status}`} style={NODES[name]}>
      <div className="node-name">{name.replace(/<br>/g, ' ')}</div>
      {status === 'active' && <div className="node-message">{message}</div>}
    </div>
  );
};

function App() {
  const [nodes, setNodes] = useState({});
  const [isStreaming, setIsStreaming] = useState(false);

  const startSimulation = () => {
    // Reset states
    setNodes({});
    setIsStreaming(true);

    const eventSource = new EventSource("http://localhost:8000/stream");

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      setNodes(prevNodes => {
        const newNodes = {...prevNodes};
        
        // Update the current node
        newNodes[data.node] = { status: data.status, message: data.message };

        // Deactivate other nodes if the current one is active
        if (data.status === 'active') {
          Object.keys(newNodes).forEach(key => {
            if (key !== data.node && newNodes[key].status === 'active') {
              newNodes[key] = { ...newNodes[key], status: 'inactive' };
            }
          });
        }
        
        // When master is complete, end the stream
        if(data.node === "DB-MASTER" && data.status === "complete") {
            eventSource.close();
            setIsStreaming(false);
        }

        return newNodes;
      });
    };

    eventSource.onerror = (err) => {
      console.error("EventSource failed:", err);
      eventSource.close();
      setIsStreaming(false);
    };
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Agent Flow Visualization</h1>
        <button onClick={startSimulation} disabled={isStreaming}>
          {isStreaming ? 'Simulation in Progress...' : 'Start Simulation'}
        </button>
      </header>
      <div className="canvas">
        {Object.entries(NODES).map(([name]) => (
          <AgentNode 
            key={name}
            name={name}
            status={nodes[name]?.status || 'idle'}
            message={nodes[name]?.message || ''}
          />
        ))}
      </div>
    </div>
  );
}

export default App; 