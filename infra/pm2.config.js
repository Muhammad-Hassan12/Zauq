module.exports = {
  apps: [
    {
      name: 'zauq-backend',
      script: 'backend/main.py',
      interpreter: '/root/Zauq/venv/bin/python',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONPATH: '/root/Zauq',
      },
      max_restarts: 10,
      restart_delay: 2000,
    },
    {
      name: 'zauq-bot',
      script: 'bot/client.py',
      interpreter: '/root/Zauq/venv/bin/python',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONPATH: '/root/Zauq',
      },
      max_restarts: 10,
      restart_delay: 2000,
    },
  ],
};
