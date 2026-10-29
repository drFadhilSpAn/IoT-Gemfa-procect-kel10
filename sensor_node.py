#!/usr/bin/env python3
import json, math, os, queue, signal, subprocess, threading, time, uuid
from collections import deque
import paho.mqtt.client as mqtt

CONFIG_FILE=os.environ.get("SHAKEWATCH_CONFIG","config.json")
with open(CONFIG_FILE,encoding="utf-8") as f: CFG=json.load(f)
PROJECT=CFG["project_id"]; DEVICE=CFG["device_id"]
BASE=f"{PROJECT}"
TOP={k:f"{BASE}/{v}" for k,v in {
 "telemetry":f"edge/{DEVICE}/telemetry", "status":f"edge/{DEVICE}/status",
 "command":f"command/{DEVICE}", "response":f"response/{DEVICE}", "alert":"alerts"}.items()}
state={"armed":True,"motion_threshold":float(CFG.get("motion_threshold",0.7)),
       "rotation_threshold":float(CFG.get("rotation_threshold",0.25)),"connected":False}
stop=threading.Event(); samples=deque(maxlen=int(CFG.get("window_size",10))); seq=0

def now_ms(): return int(time.time()*1000)
def publish_json(topic,obj,qos=0,retain=False):
    if state["connected"]: client.publish(topic,json.dumps(obj,separators=(",",":")),qos=qos,retain=retain)
def status(reason="periodic"):
    publish_json(TOP["status"],{"device_id":DEVICE,"online":True,"armed":state["armed"],
      "motion_threshold":state["motion_threshold"],"rotation_threshold":state["rotation_threshold"],
      "reason":reason,"timestamp":now_ms()},1,True)
def response(cid,ok,message,extra=None):
    d={"command_id":cid,"device_id":DEVICE,"success":ok,"message":message,"timestamp":now_ms()}
    if extra:d.update(extra)
    publish_json(TOP["response"],d,1)

def on_connect(c,u,flags,reason_code,properties=None):
    state["connected"]=True; c.subscribe(TOP["command"],qos=1); status("connected")
def on_disconnect(c,u,disconnect_flags,reason_code,properties=None): state["connected"]=False
def on_message(c,u,msg):
    try:
        p=json.loads(msg.payload.decode()); cid=str(p.get("command_id",uuid.uuid4()))
        cmd=str(p.get("command","")).upper()
        if cmd=="ARM": state["armed"]=True; response(cid,True,"Monitoring activated")
        elif cmd=="DISARM": state["armed"]=False; response(cid,True,"Monitoring stopped")
        elif cmd=="SET_THRESHOLD":
            mt=float(p.get("motion_threshold",state["motion_threshold"])); rt=float(p.get("rotation_threshold",state["rotation_threshold"]))
            if not (0.05<=mt<=20 and 0.01<=rt<=20): raise ValueError("threshold di luar batas")
            state["motion_threshold"],state["rotation_threshold"]=mt,rt
            response(cid,True,"Threshold updated",{"motion_threshold":mt,"rotation_threshold":rt})
        elif cmd=="TEST_ALARM":
            subprocess.run(["termux-vibrate","-d","1200"],check=False); response(cid,True,"Alarm test executed")
        elif cmd=="PING": response(cid,True,"PONG")
        else: response(cid,False,"Unknown command")
        status("command")
    except Exception as e: response(str(locals().get("cid","unknown")),False,f"Command rejected: {e}")

def find_values(data,needle):
    for name,body in data.items():
        if needle.lower() in name.lower() and isinstance(body,dict):
            v=body.get("values")
            if isinstance(v,list) and len(v)>=3:return [float(x) for x in v[:3]]
    return None

def read_sensors():
    names=CFG.get("sensor_query","accelerometer,gyroscope")
    cp=subprocess.run(["termux-sensor","-s",names,"-n","1"],capture_output=True,text=True,timeout=8)
    if cp.returncode!=0: raise RuntimeError(cp.stderr.strip() or "termux-sensor gagal")
    data=json.loads(cp.stdout); return find_values(data,"accelerometer"),find_values(data,"gyroscope")

def loop():
    global seq
    interval=float(CFG.get("sample_interval_sec",0.5)); last_status=0; rot=0.0; prev=time.monotonic(); cooldown=0
    while not stop.is_set():
        started=time.monotonic()
        try:
            acc,gyr=read_sensors(); current=time.monotonic(); dt=max(0,min(current-prev,2)); prev=current
            if not acc: raise RuntimeError("Accelerometer tidak ditemukan")
            mag=math.sqrt(sum(x*x for x in acc)); linear=abs(mag-9.80665); samples.append(linear)
            rms=math.sqrt(sum(x*x for x in samples)/len(samples))
            gyro_speed=math.sqrt(sum(x*x for x in gyr)) if gyr else 0.0; rot=gyro_speed*dt
            seq+=1; active=state["armed"] and (rms>=state["motion_threshold"] or rot>=state["rotation_threshold"])
            payload={"device_id":DEVICE,"sequence":seq,"motion_rms":round(rms,4),"rotation_rad":round(rot,4),
              "acceleration_magnitude":round(mag,4),"gyro_available":bool(gyr),"armed":state["armed"],
              "alert":active,"timestamp":now_ms()}
            publish_json(TOP["telemetry"],payload,0)
            if active and time.time()>cooldown:
                publish_json(TOP["alert"],payload,1); cooldown=time.time()+float(CFG.get("alert_cooldown_sec",5))
            if time.time()-last_status>15: status(); last_status=time.time()
        except Exception as e:
            publish_json(TOP["status"],{"device_id":DEVICE,"online":True,"error":str(e),"timestamp":now_ms()},1,True)
            print("ERROR:",e,flush=True)
        stop.wait(max(0.05,interval-(time.monotonic()-started)))

def shutdown(*_):
    stop.set(); publish_json(TOP["status"],{"device_id":DEVICE,"online":False,"timestamp":now_ms()},1,True)
    time.sleep(.2); client.disconnect()
signal.signal(signal.SIGINT,shutdown); signal.signal(signal.SIGTERM,shutdown)
client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=f"{DEVICE}-{uuid.uuid4().hex[:8]}")
client.on_connect=on_connect; client.on_disconnect=on_disconnect; client.on_message=on_message
if CFG.get("username"): client.username_pw_set(CFG["username"],CFG.get("password",""))
if CFG.get("tls",True): client.tls_set()
client.will_set(TOP["status"],json.dumps({"device_id":DEVICE,"online":False,"timestamp":now_ms()}),qos=1,retain=True)
client.connect(CFG["mqtt_host"],int(CFG.get("mqtt_port",8883)),60); client.loop_start()
print(f"ShakeWatch sensor aktif: {DEVICE} -> {CFG['mqtt_host']}",flush=True)
try: loop()
finally: shutdown()
