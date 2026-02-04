#!/root/crypto-bot/venv/bin/python3
"""
Запуск Flask WebApp отдельным процессом
"""
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/root/crypto-bot')
os.chdir('/root/crypto-bot')

from app.webapp.server import app
from app.core.logger import logger

if __name__ == '__main__':
    port = int(os.environ.get('FLASK_PORT', 5000))
    logger.info(f"🌐 Starting Flask WebApp on 0.0.0.0:{port}")
    try:
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        logger.error(f"❌ Flask error: {e}")
        import traceback
        traceback.print_exc()
