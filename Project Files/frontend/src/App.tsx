// Import React (stores changing data, runs code when component loads/updates)
import { useEffect, useState } from "react";

// Import Socket.IO client so frontend can talk to backend
import { io } from "socket.io-client";

// Import CSS file for styling
import "./App.css";

// Import Chart.js tools for graphing
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from "chart.js";

// Import React wrapper for Chart.js
import { Scatter } from "react-chartjs-2";

// Register chart features so Chart.js knows what to use
ChartJS.register(
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend
);

// Backend URL (Uses environment variable if available, otherwise defaults to localhost)
const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:5000";

// Create socket connection to backend
const socket = io(backendUrl);

// Type for coordinates
type Position = {
  x: number;
  y: number;
};

// Type for room grid (Makes a 2D array of numbers)
type Grid = number[][];

// Manual commands
type Command = "start" | "stop" | "reset";

// Expected data from backend map updates
interface MapUpdatePayload {
  grid: Grid;
  finch: Position;
  path: Position[];
}

// Expected status update format
interface StatusUpdatePayload {
  status: string;
}

// Main app component
function App() {
  // Stores room map grid
  const [grid, setGrid] = useState<Grid>([]);

  // Stores finch position
  const [finch, setfinch] = useState<Position>({
    x: 0,
    y: 0,
  });

  // Stores finch path history
  const [path, setPath] = useState<Position[]>([]);

  // Stores connection status
  const [status, setStatus] = useState("Disconnected");

  // Runs once when page loads
  useEffect(() => {
    // Listen for backend connection
    socket.on("connect", () => {
      setStatus("Connected");
    });

    // Listen for backend disconnect
    socket.on("disconnect", () => {
      setStatus("Disconnected");
    });

    // Listen for room map updates
    socket.on("map_update", (data: MapUpdatePayload) => {
      // Update frontend data
      setGrid(data.grid);
      setfinch(data.finch);
      setPath(data.path);
    });

    // Listen for status messages
    socket.on("status_update", (data: StatusUpdatePayload) => {
      setStatus(data.status);
    });

    // Cleanup socket when itloses
    return () => {
      socket.off();
    };
  }, []);

  // Send commands to backend
  const sendCommand = (cmd: Command) => {
    socket.emit("command", cmd);
  };

  // Chart data (Converts path into x,y points)
  const chartData = {
    datasets: [
      {
        label: "Finch Path",

        // Convert path array into chart points
        data: path.map((point) => ({
          x: point.x,
          y: point.y,
        })),
      },
    ],
  };

  // UI rendering
  return (
    <div className="app-container">

      {/* Page title */}
      <header className="header">
        <h1>Finch Room Mapper Dashboard</h1>
      </header>

      {/* Main dashboard */}
      <div className="dashboard">

        {/* Status section */}
        <div className="panel status-panel">
          <h2>Status</h2>
          <p>{status}</p>
        </div>

        {/* Finch telemetry */}
        <div className="panel telemetry-panel">
          <h2>finch Telemetry</h2>

          <p>X: {finch.x}</p>
          <p>Y: {finch.y}</p>

          {/* Total positions traveled */}
          <p>Path Points: {path.length}</p>
        </div>

        {/* Finch controls */}
        <div className="panel controls-panel">
          <h2>Controls</h2>

          {/* Start finch */}
          <button onClick={() => sendCommand("start")}>
            Start
          </button>

          {/* Stop finch */}
          <button onClick={() => sendCommand("stop")}>
            Stop
          </button>

          {/* Reset map */}
          <button onClick={() => sendCommand("reset")}>
            Reset
          </button>
        </div>

        {/* Grid map */}
        <div className="panel map-panel">
          <h2>Room Map</h2>

          <div className="grid-container">

            {/* Loop through rows */}
            {grid.map((row, y) => (

              <div key={y} className="grid-row">

                {/* Loop through cells */}
                {row.map((cell, x) => {
                  // Default cell style
                  let cellClass = "grid-cell";

                  // Wall
                  if (cell === 1) {
                    cellClass += " wall";
                  }

                  // Path
                  if (
                    path.some(
                      (p) => p.x === x && p.y === y
                    )
                  ) {
                    cellClass += " path";
                  }

                  // Finch position
                  if (
                    finch.x === x &&
                    finch.y === y
                  ) {
                    cellClass += " finch";
                  }

                  // Draw cell
                  return (
                    <div
                      key={x}
                      className={cellClass}
                    ></div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Chart panel */}
        <div className="panel chart-panel">
          <h2>Live Path Tracking</h2>

          {/* Draw chart */}
          <Scatter data={chartData} />
        </div>
      </div>
    </div>
  );
}

// Export app so React can use it
export default App;