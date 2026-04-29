// Import React (stores changing data, runs code when component loads/updates)
import { useEffect, useRef, useState } from "react";

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
const backendUrl =
  import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:5000";

// Create socket connection to backend
const socket = io(backendUrl);

// Type for coordinates
type Position = {
  x: number;
  y: number;
};

// Type for room grid (Makes a 2D array of numbers)
type Grid = number[][];

// Commands sent to backend
type Command =
  | "start"
  | "stop"
  | "reset"
  | "scan_anchor"
  | "up"
  | "down"
  | "left"
  | "right";

// Expected data from backend map updates
interface MapUpdatePayload {
  grid: Grid;
  robot: Position;
  path: Position[];
  // raw_path is the same trajectory as path but in centimeters (the path
  // field is clamped to the 20x20 grid for the grid panel). The chart
  // uses raw_path so it shares a coordinate scale with anchors.
  raw_path: Position[];
  // anchors mirrors anchors.csv on the backend — wall positions in cm.
  anchors: Position[];
  temperature: number;
  light: number;
}

// Expected status update format
interface StatusUpdatePayload {
  status: string;
}

// Main app component
function App() {
  // Stores room map grid
  const [grid, setGrid] = useState<Grid>([]);

  // Stores robot position
  const [robot, setRobot] = useState<Position>({
    x: 0,
    y: 0,
  });

  // Stores robot path history (grid coordinates, used by the grid panel)
  const [path, setPath] = useState<Position[]>([]);

  // Stores robot path history in centimeters (used by the room-map chart
  // so it shares a coordinate scale with the anchors).
  const [rawPath, setRawPath] = useState<Position[]>([]);

  // Stores wall anchors streamed from the backend (mirror of anchors.csv).
  const [anchors, setAnchors] = useState<Position[]>([]);

  // Stores connection status
  const [status, setStatus] = useState("Disconnected");

  // Stores navigation mode
  const [mode, setMode] = useState("automatic");

  // Stores sensor data
  const [temperature, setTemperature] = useState(0);
  const [light, setLight] = useState(0);

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
      setRobot(data.robot);
      setPath(data.path);

      // raw_path / anchors may be missing on older backends — default
      // to [] so the chart renders cleanly during the rollout.
      setRawPath(data.raw_path ?? []);
      setAnchors(data.anchors ?? []);

      // Update sensor values
      setTemperature(data.temperature);
      setLight(data.light);
    });

    // Listen for status messages
    socket.on("status_update", (data: StatusUpdatePayload) => {
      setStatus(data.status);
    });

    // Cleanup socket when it closes
    return () => {
      socket.off();
    };
  }, []);

  // Send commands to backend
  const sendCommand = (cmd: Command) => {
    socket.emit("command", cmd);
  };

  // Hidden file input — triggered by the Load Map button. Kept in a ref
  // so we can call .click() programmatically from the visible button.
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Open the OS file picker. The actual upload happens in onFileSelected.
  const handleLoadMapClick = () => {
    fileInputRef.current?.click();
  };

  // Serialize the live map (path + anchors, both in cm) to JSON and
  // trigger a browser download. The file format matches what the backend
  // writes to room_map.json, so a Save Map → Load Map round-trip is
  // lossless. Filename gets a timestamp so saving multiple maps in one
  // session doesn't clobber. Lands in the user's default Downloads
  // folder; no backend involvement.
  const handleSaveMapClick = () => {
    const payload = {
      path: rawPath,
      anchors: anchors,
    };
    const json = JSON.stringify(payload, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);

    // Timestamp like 2026-04-28T17-32-09 — colons stripped because they
    // are illegal in Windows filenames.
    const stamp = new Date()
      .toISOString()
      .replace(/[:.]/g, "-")
      .replace(/T/, "_")
      .slice(0, 19);
    const filename = `room_map_${stamp}.json`;

    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setStatus(`Saved ${filename}`);
  };

  // Read the selected JSON, parse it, and ship the {path, anchors} to the
  // backend via the new 'load_map' socket event. Backend will replace its
  // state and emit a map_update so the chart re-renders.
  const onFileSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result as string;
        const parsed = JSON.parse(text);
        socket.emit("load_map", {
          path: parsed.path ?? [],
          anchors: parsed.anchors ?? [],
        });
      } catch (e) {
        setStatus(`Failed to parse map file: ${(e as Error).message}`);
      }
    };
    reader.onerror = () => setStatus("Failed to read map file");
    reader.readAsText(file);
    // Reset so re-selecting the same filename still triggers onChange.
    event.target.value = "";
  };

  // Chart data — two datasets in the same cm-scale coordinate space:
  //   1. Finch Path: connected line of poses from raw_path
  //   2. Wall Anchors: standalone points from the backend's anchors stream
  // Together they form a live room map.
  const chartData = {
    datasets: [
      {
        label: "Finch Path",
        data: rawPath.map((point) => ({ x: point.x, y: point.y })),
        showLine: true,
        borderColor: "rgba(54, 162, 235, 0.8)",
        backgroundColor: "rgba(54, 162, 235, 0.5)",
        pointRadius: 2,
      },
      {
        label: "Wall Anchors",
        data: anchors.map((point) => ({ x: point.x, y: point.y })),
        // Connect anchors in the order they're recorded — navigateRoom
        // and searchForCorner deliberately keep them in traversal order
        // (see comment in RoomNav.searchForCorner) so the polyline traces
        // the room outline rather than zig-zagging.
        showLine: true,
        borderColor: "rgba(255, 99, 132, 1)",
        backgroundColor: "rgba(255, 99, 132, 1)",
        pointRadius: 5,
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

        {/* Robot telemetry */}
        <div className="panel telemetry-panel">
          <h2>Telemetry</h2>

          <p>X: {robot.x}</p>
          <p>Y: {robot.y}</p>

          {/* Total positions traveled */}
          <p>Path Points: {path.length}</p>

          {/* Temperature sensor */}
          <p>Temperature: {temperature}°C</p>

          {/* Light sensor */}
          <p>Light Level: {light}</p>
        </div>

        {/* Finch controls */}
        <div className="panel controls-panel">
          <h2>Controls</h2>

          {/* Select automatic mode */}
          <button onClick={() => setMode("automatic")}>
            Automatic Navigation
          </button>

          {/* Select manual mode */}
          <button onClick={() => setMode("manual")}>
            Manual Navigation
          </button>

          {/* Save the live map (path + anchors) as a JSON file to
              the browser's default download location. */}
          <button onClick={handleSaveMapClick}>
            Save Map
          </button>

          {/* Load a previously saved room_map.json (path + anchors). */}
          <button onClick={handleLoadMapClick}>
            Load Map
          </button>
          {/* No `accept` filter on purpose — Windows' file picker hides
              non-matching files entirely (showing only folders) when the
              filter is restrictive, which surprises users. We validate
              the contents in onFileSelected instead, so any file can be
              picked and the parser will report a clean error on bad JSON. */}
          <input
            ref={fileInputRef}
            type="file"
            style={{ display: "none" }}
            onChange={onFileSelected}
          />

          {/* Automatic navigation controls */}
          {mode === "automatic" && (
            <>
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
            </>
          )}

          {/* Manual navigation controls */}
          {mode === "manual" && (
            <div className="manual-controls">

              {/* Scan anchor button */}
              <button
                onClick={() => sendCommand("scan_anchor")}
              >
                Scan Anchor
              </button>

              {/* Arrow Buttons */}
              <div className="arrow-row">
                <button
                  className="arrow-key"
                  onClick={() =>
                    sendCommand("up")
                  }
                >
                  ↑
                </button>
              </div>

              <div className="arrow-row">
                <button
                  className="arrow-key"
                  onClick={() =>
                    sendCommand("left")
                  }
                >
                  ←
                </button>

                <button
                  className="arrow-key"
                  onClick={() =>
                    sendCommand("down")
                  }
                >
                  ↓
                </button>

                <button
                  className="arrow-key"
                  onClick={() =>
                    sendCommand("right")
                  }
                >
                  →
                </button>
              </div>
              <p>
                Use buttons to move Finch
                and scan anchors
              </p>
            </div>
          )}
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
                    robot.x === x &&
                    robot.y === y
                  ) {
                    cellClass += " robot";
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

        {/* Chart panel — live room map: trajectory + wall anchors */}
        <div className="panel chart-panel">
          <h2>Live Room Map</h2>

          {/* Draw chart */}
          <Scatter data={chartData} />
        </div>
      </div>
    </div>
  );
}

// Export app so React can use it
export default App;