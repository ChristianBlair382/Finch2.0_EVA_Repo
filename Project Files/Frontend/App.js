import { useEffect, useState } from "react";
import socket from "./socket";

function App() {
  const [robot, setRobot] = useState(null);

  useEffect(() => {
    socket.on("robot_data", (data) => {
      setRobot(data);
    });

    return () => socket.off("robot_data");
  }, []);

  return (
    <div>
      <h1>Finch Robot</h1>

      <button onClick={() => socket.emit("start")}>
        Start
      </button>

      <button onClick={() => socket.emit("stop")}>
        Stop
      </button>

      <pre>{JSON.stringify(robot, null, 2)}</pre>
    </div>
  );
}

export default App;