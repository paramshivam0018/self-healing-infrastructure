#!/usr/bin/env python3
"""
Auto-Remediation Script
Continuously monitors pods and takes healing actions automatically.
"""

import subprocess
import time
import json
import requests
import logging
from datetime import datetime

# ─── Logging Setup ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("healing_events.log")
    ]
)
log = logging.getLogger("healer")

# ─── Config ─────────────────────────────────────────────────────
APP_URL = "http://192.168.49.2:30080"
CHECK_INTERVAL = 10       # seconds between checks
MAX_RESTARTS = 5          # alert if pod restarts exceed this
CPU_THRESHOLD = 80.0      # percent
MEMORY_THRESHOLD = 85.0   # percent

# ─── Kubectl Helpers ────────────────────────────────────────────

def get_pods():
    """Get all pods in default namespace"""
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", "default", "-o", "json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)["items"]

def restart_pod(pod_name):
    """Delete pod — Kubernetes will recreate it automatically"""
    log.warning(f"🔄 Restarting pod: {pod_name}")
    subprocess.run(
        ["kubectl", "delete", "pod", pod_name, "-n", "default"],
        capture_output=True
    )
    log.info(f"✅ Pod {pod_name} deleted — Kubernetes will recreate it")

def scale_deployment(replicas):
    """Scale the deployment up or down"""
    log.info(f"📈 Scaling deployment to {replicas} replicas")
    subprocess.run([
        "kubectl", "scale", "deployment", "self-healing-app",
        f"--replicas={replicas}", "-n", "default"
    ], capture_output=True)

def get_pod_restarts(pod):
    """Get restart count for a pod"""
    try:
        containers = pod["status"].get("containerStatuses", [])
        if containers:
            return containers[0]["restartCount"]
    except:
        pass
    return 0

def get_pod_status(pod):
    """Get pod phase and ready status"""
    phase = pod["status"].get("phase", "Unknown")
    conditions = pod["status"].get("conditions", [])
    ready = any(c["type"] == "Ready" and c["status"] == "True" for c in conditions)
    return phase, ready

# ─── Health Checks ──────────────────────────────────────────────

def check_app_health():
    """Check application health endpoint"""
    try:
        response = requests.get(f"{APP_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def check_app_metrics():
    """Check CPU and memory usage"""
    try:
        response = requests.get(f"{APP_URL}/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                "cpu_percent": data.get("cpu_percent", 0),
                "memory_percent": data.get("memory_percent", 0),
                "memory_used_mb": data.get("memory_used_mb", 0),
            }
    except:
        pass
    return None

# ─── Remediation Actions ────────────────────────────────────────

def handle_unhealthy_pod(pod_name, reason):
    """Handle an unhealthy pod"""
    log.warning(f"⚠️  Unhealthy pod detected: {pod_name} — Reason: {reason}")
    restart_pod(pod_name)
    log.info(f"🏥 Remediation complete for {pod_name}")

def handle_high_restarts(pod_name, restart_count):
    """Handle pod with too many restarts"""
    log.error(f"🚨 Pod {pod_name} has {restart_count} restarts — possible crash loop!")
    log.info("📋 Fetching pod logs for diagnosis...")
    result = subprocess.run(
        ["kubectl", "logs", pod_name, "--previous", "-n", "default", "--tail=20"],
        capture_output=True, text=True
    )
    if result.stdout:
        log.info(f"📄 Last logs:\n{result.stdout}")
    log.warning("⚡ High restart count — monitoring closely")

def handle_high_cpu(cpu_percent):
    """Handle high CPU usage"""
    log.warning(f"🔥 High CPU detected: {cpu_percent}% — scaling up!")
    scale_deployment(3)
    log.info("✅ Scaled to 3 replicas to handle CPU load")

def handle_high_memory(memory_percent):
    """Handle high memory usage"""
    log.warning(f"💾 High memory detected: {memory_percent}% — restarting pods")
    pods = get_pods()
    for pod in pods:
        pod_name = pod["metadata"]["name"]
        if "self-healing-app" in pod_name:
            restart_pod(pod_name)
            time.sleep(5)
    log.info("✅ Pods restarted to free memory")

# ─── Main Loop ──────────────────────────────────────────────────

def main():
    log.info("🚀 Auto-Healer started — monitoring every %ds", CHECK_INTERVAL)
    log.info(f"📍 Watching: {APP_URL}")
    log.info(f"⚙️  Thresholds — CPU: {CPU_THRESHOLD}% | Memory: {MEMORY_THRESHOLD}%")
    log.info("─" * 60)

    cycle = 0
    while True:
        cycle += 1
        log.info(f"🔍 Check cycle #{cycle}")

        # ── Check 1: Pod health via kubectl ──
        pods = get_pods()
        for pod in pods:
            pod_name = pod["metadata"]["name"]
            if "self-healing-app" not in pod_name:
                continue

            phase, ready = get_pod_status(pod)
            restart_count = get_pod_restarts(pod)

            if not ready and phase == "Running":
                handle_unhealthy_pod(pod_name, "pod not ready")

            if restart_count > MAX_RESTARTS:
                handle_high_restarts(pod_name, restart_count)

        # ── Check 2: App health endpoint ──
        healthy = check_app_health()
        if not healthy:
            log.warning("❌ App health check failed!")
        else:
            log.info("✅ App health: OK")

        # ── Check 3: Resource usage ──
        metrics = check_app_metrics()
        if metrics:
            cpu = metrics["cpu_percent"]
            mem = metrics["memory_percent"]
            log.info(f"📊 CPU: {cpu}% | Memory: {mem}% ({metrics['memory_used_mb']}MB)")

            if cpu > CPU_THRESHOLD:
                handle_high_cpu(cpu)

            if mem > MEMORY_THRESHOLD:
                handle_high_memory(mem)

        log.info("─" * 60)
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
