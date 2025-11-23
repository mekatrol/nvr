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

## Set up NAS mount

```bash
sudo nano /etc/wsl.conf
```

## Add to contents

```init
[automount]
enabled=true

[filesystem]
fsTab=true
```

```bash
sudo mkdir -p /mnt/nas
sudo apt install cifs-utils
```

### Replace following values

> //nas.lan/nas with nas path  
> /mnt/nas with actual mount name  
> 'user' in path /home/user with actual user name  

```bash
sudo nano /etc/fstab
```

```ini
//nas.lan/nas /mnt/nas cifs  credentials=/home/user/.smbcredentials,uid=1000,gid=1000,file_mode=0777,dir_mode=0777,vers=3.0,_netdev,nofail  0  0
```

```bash
nano ~/.smbcredentials
```

```ini
username=user
password=!MyPassword111
```

```bash
chmod 600 ~/.smbcredentials
```

#### from a PowerShell pront

```powershell
wsl --shutdown
```

#### then restart Ubuntu prompt

```bash
mount | grep nas.lan
```

## Create Service

```bash
sudo nano /etc/systemd/system/nvr.service
```

### Enter content

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
