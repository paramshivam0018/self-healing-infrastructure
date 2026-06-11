from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import psutil
import time
import threading

app = FastAPI(title="Self-Healing Demo App")
Instrumentator().instrument(app).expose(app)

app_state = {
    "healthy": True,
    "crash_mode": False,
    "memory_stress": False,
    "cpu_stress": False,
    "start_time": time.time()
}

memory_hog = []

@app.get("/health")
def health():
    if app_state["crash_mode"]:
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "reason": "crash_mode_active"}
        )
    return {"status": "ok", "uptime_seconds": int(time.time() - app_state["start_time"])}

@app.get("/ready")
def ready():
    if not app_state["healthy"]:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}

@app.get("/status")
def status():
    return {
        "healthy": app_state["healthy"],
        "crash_mode": app_state["crash_mode"],
        "memory_stress": app_state["memory_stress"],
        "cpu_stress": app_state["cpu_stress"],
        "uptime_seconds": int(time.time() - app_state["start_time"]),
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_used_mb": round(psutil.virtual_memory().used / 1024 / 1024, 2),
    }

@app.post("/simulate/crash")
def simulate_crash():
    app_state["crash_mode"] = True
    app_state["healthy"] = False
    return {"message": "Crash mode activated! Kubernetes will restart this pod."}

@app.post("/simulate/memory-stress")
def simulate_memory_stress():
    app_state["memory_stress"] = True
    memory_hog.append("x" * (100 * 1024 * 1024))
    return {"message": "Memory stress activated!", "memory_used_mb": round(psutil.virtual_memory().used / 1024 / 1024, 2)}

@app.post("/simulate/cpu-stress")
def simulate_cpu_stress():
    app_state["cpu_stress"] = True
    def burn_cpu():
        end_time = time.time() + 30
        while time.time() < end_time:
            _ = sum(i * i for i in range(10000))
        app_state["cpu_stress"] = False
    thread = threading.Thread(target=burn_cpu)
    thread.daemon = True
    thread.start()
    return {"message": "CPU stress activated for 30 seconds!"}

@app.post("/simulate/recover")
def recover():
    app_state["healthy"] = True
    app_state["crash_mode"] = False
    app_state["memory_stress"] = False
    app_state["cpu_stress"] = False
    memory_hog.clear()
    return {"message": "App recovered successfully!"}
