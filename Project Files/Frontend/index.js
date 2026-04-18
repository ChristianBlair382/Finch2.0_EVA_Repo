import React, { useEffect, useState } from "react";
import { io } from "socket.io-client";

const socket = io("http://localhost:5000");

function App() {
  const [grid, setGrid] = useState([]);
  const [robot, setRobot] = useState({ x: 0, y: 0 });
  const [path, setPath] = useState([]);
  const [status, setStatus] = useState("Disconnected");

  useEffect(() => {
    socket.on("connect", () => {
      setStatus("Connected");
    });

    socket.on("disconnect", () => {
      setStatus("Disconnected");
    });

    socket.on("map_update", (data) => {
      setGrid(data.grid);
      setRobot(data.robot);
      setPath(data.path);
    });

    return () => socket.off();
  }, []);

  const sendCommand = (cmd) => {
    socket.emit("command", cmd);
  };

  return (
    <div style={{ textAlign: "center" }}>
      <h1>Finch Room Mapper</h1>

      <p>Status: {status}</p>
      <p>
        Robot Position: ({robot.x}, {robot.y})
      </p>

      <div>
        <button onClick={() => sendCommand("start")}>Start</button>
        <button onClick={() => sendCommand("stop")}>Stop</button>
        <button onClick={() => sendCommand("reset")}>Reset</button>
      </div>

      <div style={{ display: "inline-block", marginTop: 20 }}>
        {grid.map((row, y) => (
          <div key={y} style={{ display: "flex" }}>
            {row.map((cell, x) => {
              let color = "white";

              if (cell === 1) color = "black";

              if (path.some((p) => p.x === x && p.y === y)) {
                color = "lightblue";
              }

              if (robot.x === x && robot.y === y) {
                color = "red";
              }

              return (
                <div
                  key={x}
                  style={{
                    width: 20,
                    height: 20,
                    border: "1px solid #ccc",
                    backgroundColor: color,
                  }}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;