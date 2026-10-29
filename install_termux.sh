#!/data/data/com.termux/files/usr/bin/bash
set -e
pkg update -y
pkg install -y python termux-api git
python -m pip install -r requirements.txt
[ -f config.json ] || cp config.example.json config.json
echo "Selesai. Edit config.json lalu jalankan: termux-wake-lock && python sensor_node.py"
