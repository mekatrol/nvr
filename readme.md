# Set up instructions

## Install ffmpeg

```bash
sudo apt install ffmpeg
ffmpeg -version
```

## Clone repo

```bash
cd ~/
mkdir repos
cd repos
git clone https://github.com/mekatrol/nvr.git
```

## Init python

```bash
cd ~/repos/nvr
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Create Service

```bash
sudo nano /etc/systemd/system/nvr.service
```

**Enter contents:**

```ini
[Unit]
Description=NVR service
After=network-online.target

[Service]
User=user
WorkingDirectory=/home/user/repos/nvr

# Export RTSP credentials into the service environment
Environment="RTSP_USER=your_rtsp_username"
Environment="RTSP_PASSWORD=your_rtsp_password"

# Use venv python
ExecStart=/home/user/repos/nvr/venv/bin/python /home/user/app/nvr.py

Restart=always
RestartSec=5
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable nvr.service
sudo systemctl start nvr.service
sudo systemctl status nvr.service
```
