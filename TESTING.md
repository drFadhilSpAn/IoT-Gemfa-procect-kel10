# Matriks Pengujian

Catat timestamp, perintah, respons, motion_rms, rotation_rad, latensi, dan hasil.

1. PING: dashboard menerima PONG.
2. ARM: sensor_active/armed menjadi true.
3. DISARM: alarm tidak dibuat walau HP digerakkan.
4. SET_THRESHOLD: nilai baru muncul pada status.
5. TEST_ALARM: HP B bergetar dan ACK sukses.
6. Sensor diam: RMS rendah, keputusan NORMAL.
7. Sensor digerakkan: alert terkirim.
8. Internet HP B dimatikan: status retained/LWT menjadi OFFLINE.
9. Project ID salah: tidak ada komunikasi, membuktikan isolasi topic.
10. Refresh dashboard: status retained terakhir segera tampil.
