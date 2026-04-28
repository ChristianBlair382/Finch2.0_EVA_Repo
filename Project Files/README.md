Room Navigating Finch Project
Written: William Chen, Christian Blair, Armaan Yazdani

The finch navigates along the walls of the room and marks their positions based on an estimated coordinates system.
Accounts for inaccuracies from running on carpet.

Uses multithreading to ensure smooth movement of the finch while scanning.

Minimizes the amount of turns required to optimise accuracy, as every turn on carpet leads to additional inaccuracy.

## Local Web App Setup (Frontend <-> Backend)

### 1) Start backend (Flask + Socket.IO)

From `Project Files/backend`:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Backend runs on `http://127.0.0.1:5000`.

### 2) Start frontend (Vite)

From `Project Files/frontend`:

```powershell
npm install
npm run dev
```

Frontend runs on `http://127.0.0.1:5173` by default.

### 3) Optional backend URL override

If your backend is not on `http://127.0.0.1:5000`, set:

```powershell
$env:VITE_BACKEND_URL="http://<your-host>:5000"
npm run dev
```

### Current Socket Events

- Frontend -> backend: `command` (`start`, `stop`, `reset`)
- Backend -> frontend: `map_update`, `status_update`