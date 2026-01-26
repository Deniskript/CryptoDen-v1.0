#!/bin/bash
# Healthcheck для CryptoDen Bot

LOG_FILE="/var/log/crypto-bot-healthcheck.log"
MAX_LOG_SIZE=1000000  # 1MB

# Ротация логов
if [ -f "$LOG_FILE" ] && [ $(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null) -gt $MAX_LOG_SIZE ]; then
    mv "$LOG_FILE" "${LOG_FILE}.old"
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Проверяем запущен ли бот
STATUS=$(supervisorctl status crypto:crypto-bot 2>/dev/null | awk '{print $2}')

if [ "$STATUS" != "RUNNING" ]; then
    log "⚠️ Bot not running (status: $STATUS). Restarting..."
    supervisorctl start crypto:crypto-bot >> "$LOG_FILE" 2>&1
    sleep 5
    
    NEW_STATUS=$(supervisorctl status crypto:crypto-bot | awk '{print $2}')
    if [ "$NEW_STATUS" == "RUNNING" ]; then
        log "✅ Bot restarted successfully"
    else
        log "❌ Failed to restart bot (status: $NEW_STATUS)"
    fi
else
    # Проверяем был ли последний лог недавно (в последние 5 минут)
    LAST_LOG=$(tail -1 /var/log/crypto-bot.out.log 2>/dev/null)
    if [ -z "$LAST_LOG" ]; then
        log "⚠️ No logs found, bot might be stuck"
    fi
fi
