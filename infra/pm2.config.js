// Start from any directory; resolve installation paths relative to this file.
const path = require('path');
const root = path.resolve(__dirname, '..');
const python = process.env.ZAUQ_PYTHON || path.join(root, 'venv', 'bin', 'python');
module.exports = {
  apps: [
    {
      name: 'zauq-backend',
      cwd: root,
      script: python,
      interpreter: 'none',
      args: '-m uvicorn backend.main:app --host 127.0.0.1 --port 8002',
      env: { PYTHONUNBUFFERED: '1' },
      max_restarts: 10,
      restart_delay: 2000,
    },
    {
      name: 'zauq-bot',
      cwd: root,
      script: python,
      interpreter: 'none',
      args: '-m bot.client',
      env: { PYTHONUNBUFFERED: '1' },
      max_restarts: 10,
      restart_delay: 2000,
    },
  ],
};
