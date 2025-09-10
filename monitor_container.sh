#!/bin/bash

# Container monitoring script to detect and restart stalled containers
# This script should be run as a cron job on the host Mac

CONTAINER_NAME="calendar-busy-light"
HEARTBEAT_FILE="./data/heartbeat.txt"
LOG_FILE="./logs/container_monitor.log"
MAX_HEARTBEAT_AGE=300  # 5 minutes in seconds

# Ensure log directory exists
mkdir -p logs

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Check if container is running
is_container_running() {
    docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" --quiet | grep -q .
}

# Check heartbeat age
check_heartbeat() {
    if [[ ! -f "$HEARTBEAT_FILE" ]]; then
        log "❌ Heartbeat file not found: $HEARTBEAT_FILE"
        return 1
    fi
    
    local heartbeat_timestamp
    heartbeat_timestamp=$(cat "$HEARTBEAT_FILE" 2>/dev/null | head -n1)
    
    if [[ -z "$heartbeat_timestamp" ]]; then
        log "❌ Empty heartbeat file"
        return 1
    fi
    
    local current_time
    current_time=$(date +%s)
    
    local heartbeat_age
    heartbeat_age=$((current_time - ${heartbeat_timestamp%.*}))  # Remove decimal part
    
    log "🔍 Heartbeat age: ${heartbeat_age}s (max: ${MAX_HEARTBEAT_AGE}s)"
    
    if [[ $heartbeat_age -gt $MAX_HEARTBEAT_AGE ]]; then
        log "⚠️ Heartbeat is stale (${heartbeat_age}s > ${MAX_HEARTBEAT_AGE}s)"
        return 1
    fi
    
    log "✅ Heartbeat is fresh"
    return 0
}

# Restart container
restart_container() {
    log "🔄 Restarting container: $CONTAINER_NAME"
    
    # Try graceful restart first
    if docker restart "$CONTAINER_NAME" 2>/dev/null; then
        log "✅ Container restarted successfully"
        return 0
    fi
    
    # If restart fails, try stop and start
    log "⚠️ Graceful restart failed, trying stop/start..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    sleep 5
    
    if docker-compose up -d; then
        log "✅ Container recreated successfully"
        return 0
    else
        log "❌ Failed to restart container"
        return 1
    fi
}

# Send notification (optional - requires terminal-notifier)
send_notification() {
    local message="$1"
    if command -v terminal-notifier >/dev/null 2>&1; then
        terminal-notifier -title "Calendar Busy Light" -message "$message" 2>/dev/null || true
    fi
}

# Main monitoring logic
main() {
    log "🔍 Checking container health..."
    
    if ! is_container_running; then
        log "❌ Container is not running"
        send_notification "Container is not running, attempting restart..."
        restart_container
        return
    fi
    
    if ! check_heartbeat; then
        log "💀 Container appears to be stalled (heartbeat stale)"
        send_notification "Container stalled, restarting..."
        restart_container
        return
    fi
    
    log "✅ Container is healthy"
}

# Check if we're in the right directory
if [[ ! -f "docker-compose.yml" ]]; then
    echo "Error: docker-compose.yml not found. Run this script from the project directory."
    exit 1
fi

# Run the main function
main

# Clean up old log entries (keep last 100 lines)
if [[ -f "$LOG_FILE" ]] && [[ $(wc -l < "$LOG_FILE") -gt 100 ]]; then
    tail -n 100 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

