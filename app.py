from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
from datetime import date, timedelta
import json, re

app = Flask(__name__, static_folder=None)
ROOT = Path(__file__).resolve().parent
DB = ROOT / "data.json"
USERS = [
    {"id":1,"login":"student1","displayName":"Иван Студентов","role":"student"},
    {"id":2,"login":"student2","displayName":"Мария Студентова","role":"student"},
    {"id":3,"login":"admin","displayName":"Администратор Пупкин","role":"admin"},
]
EQUIPMENT = {"projector","whiteboard","computers","audio","video"}
ROOMS = [
("A-101","A",1,30,["projector","whiteboard"]),("A-102","A",1,20,["whiteboard"]),
("A-203","A",2,15,["computers","projector"]),("B-101","B",1,40,["projector","audio"]),
("B-204","B",2,25,["projector","whiteboard","audio"]),("B-305","B",3,10,["whiteboard"]),
("C-110","C",1,50,["projector","audio","video"]),("C-210","C",2,35,["computers"]),
("C-301","C",3,12,["whiteboard","projector"]),("D-101","D",1,60,["projector","audio","video"]),
("D-202","D",2,18,["whiteboard"]),("D-303","D",3,24,["projector","computers"])]
def seed():
    today=date.today()
    bookings=[
    (1,1,1,1,"10:00","11:30","active","Консультация"),
    (2,1,2,1,"14:00","15:30","active","Подготовка к семинару"),
    (3,4,2,1,"09:00","10:30","active","Собрание группы"),
    (4,7,3,1,"12:00","14:00","active","Встреча с деканом"),
    (5,1,1,0,"15:00","16:00","cancelled","Отменили"),
    (6,10,2,2,"13:00","15:00","active","Лекция"),
    (7,5,1,1,"16:00","17:30","active","Кружок")]
    return {"rooms":[{"id":i+1,"name":n,"building":b,"floor":fl,"capacity":cap,"equipment":eq} for i,(n,b,fl,cap,eq) in enumerate(ROOMS)],
    "bookings":[{"id":i,"roomId":rid,"userId":uid,"date":(today+timedelta(days=off)).isoformat(),"startTime":st,"endTime":en,"status":status,"comment":comment} for i,rid,uid,off,st,en,status,comment in bookings],
    "nextBookingId":8,"nextRoomId":13}
if not DB.exists(): DB.write_text(json.dumps(seed(),ensure_ascii=False,indent=2),encoding="utf-8")
def load(): return json.loads(DB.read_text(encoding="utf-8"))
def save(db): DB.write_text(json.dumps(db,ensure_ascii=False,indent=2),encoding="utf-8")
def error(code,msg,status,details=None): return jsonify({"code":code,"message":msg,"details":details or {}}),status
def current_user():
    token=request.headers.get("Authorization","").replace("Bearer ","")
    uid=request.headers.get("X-User-Id")
    return next((u for u in USERS if token=="mock-token-"+u["login"] or (uid and str(u["id"])==uid)),None)
def require_admin():
    u=current_user()
    if not u: return None,error("UNAUTHORIZED","Требуется авторизация",401)
    if u["role"]!="admin": return None,error("FORBIDDEN","Недостаточно прав",403)
    return u,None
def mins(t):
    h,m=map(int,t.split(":")); return h*60+m
def valid_date(s):
    try: return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}",s)) and date.fromisoformat(s)
    except: return False
def expanded(db,b):
    r=next((x for x in db["rooms"] if x["id"]==b["roomId"]),{})
    u=next((x for x in USERS if x["id"]==b["userId"]),{})
    return {**b,"roomName":r.get("name"),"userDisplayName":u.get("displayName")}
def free_slots(db,rid,d):
    busy=sorted([b for b in db["bookings"] if b["roomId"]==rid and b["date"]==d and b["status"]=="active"],key=lambda x:mins(x["startTime"]))
    out=[]; cursor=540
    def fmt(v): return f"{v//60:02d}:{v%60:02d}"
    for b in busy:
        s,e=mins(b["startTime"]),mins(b["endTime"])
        if s>cursor: out.append({"startTime":fmt(cursor),"endTime":fmt(s)})
        cursor=max(cursor,e)
    if cursor<1080: out.append({"startTime":fmt(cursor),"endTime":fmt(1080)})
    return [x for x in out if mins(x["endTime"])-mins(x["startTime"])>=30]

@app.get("/")
def home(): return send_from_directory(ROOT,"index.html")
@app.get("/<path:name>")
def static_files(name): return send_from_directory(ROOT,name)
@app.post("/api/auth/login")
def login():
    b=request.get_json(silent=True) or {}
    u=next((x for x in USERS if x["login"]==b.get("login") and b.get("password")==x["login"]),None)
    return (jsonify({"token":"mock-token-"+u["login"],"user":u}) if u else error("UNAUTHORIZED","Неверный логин или пароль",401))
@app.get("/api/rooms")
def rooms():
    db=load(); arr=db["rooms"]; building=request.args.get("building"); cap=request.args.get("minCapacity"); eq=request.args.get("equipment")
    if building: arr=[r for r in arr if r["building"]==building]
    if cap:
        if not cap.isdigit() or int(cap)<1: return error("VALIDATION_ERROR","minCapacity должен быть целым числом больше нуля",400)
        arr=[r for r in arr if r["capacity"]>=int(cap)]
    if eq:
        wanted=eq.split(",")
        if any(x not in EQUIPMENT for x in wanted): return error("VALIDATION_ERROR","Неизвестное оборудование",400)
        arr=[r for r in arr if all(x in r["equipment"] for x in wanted)]
    return jsonify(arr)
@app.get("/api/rooms/<int:rid>")
def room(rid):
    db=load(); r=next((x for x in db["rooms"] if x["id"]==rid),None)
    return jsonify(r) if r else error("ROOM_NOT_FOUND","Аудитория не найдена",404)
@app.get("/api/rooms/<int:rid>/free-slots")
def slots(rid):
    db=load(); r=next((x for x in db["rooms"] if x["id"]==rid),None)
    if not r: return error("ROOM_NOT_FOUND","Аудитория не найдена",404)
    d=request.args.get("date","")
    if not valid_date(d) or d<date.today().isoformat(): return error("VALIDATION_ERROR","Укажите корректную дату не в прошлом",400)
    return jsonify({"roomId":rid,"date":d,"freeSlots":free_slots(db,rid,d)})
@app.post("/api/bookings")
def create_booking():
    u=current_user()
    if not u: return error("UNAUTHORIZED","Требуется авторизация",401)
    b=request.get_json(silent=True) or {}; db=load()
    r=next((x for x in db["rooms"] if x["id"]==b.get("roomId")),None)
    if not r: return error("ROOM_NOT_FOUND","Аудитория не найдена",404)
    d,st,en=b.get("date",""),b.get("startTime",""),b.get("endTime","")
    if not valid_date(d) or d<date.today().isoformat() or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",st) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",en):
        return error("VALIDATION_ERROR","Проверьте дату и время",400)
    s,e=mins(st),mins(en)
    if s>=e or s<540 or e>1080 or s%30 or e%30: return error("VALIDATION_ERROR","Время должно быть кратно 30 минутам в диапазоне 09:00–18:00",400)
    if any(x["roomId"]==r["id"] and x["date"]==d and x["status"]=="active" and s<mins(x["endTime"]) and e>mins(x["startTime"]) for x in db["bookings"]):
        return error("BOOKING_CONFLICT","Аудитория уже забронирована на это время",409,{"roomId":r["id"],"date":d,"startTime":st,"endTime":en})
    obj={"id":db["nextBookingId"],"roomId":r["id"],"userId":u["id"],"date":d,"startTime":st,"endTime":en,"status":"active","comment":b.get("comment","")}
    db["nextBookingId"]+=1; db["bookings"].append(obj); save(db)
    return jsonify(expanded(db,obj)),201
@app.get("/api/bookings/my")
def my_bookings():
    u=current_user()
    if not u: return error("UNAUTHORIZED","Требуется авторизация",401)
    db=load(); status=request.args.get("status")
    return jsonify([expanded(db,b) for b in db["bookings"] if b["userId"]==u["id"] and (not status or b["status"]==status)])
@app.delete("/api/bookings/<int:bid>")
def cancel_booking(bid):
    u=current_user()
    if not u: return error("UNAUTHORIZED","Требуется авторизация",401)
    db=load(); b=next((x for x in db["bookings"] if x["id"]==bid),None)
    if not b: return error("BOOKING_NOT_FOUND","Бронь не найдена",404)
    if b["userId"]!=u["id"]: return error("FORBIDDEN","Нельзя отменить чужую бронь",403)
    if b["status"]=="cancelled": return error("ALREADY_CANCELLED","Бронь уже отменена",409)
    b["status"]="cancelled"; save(db); return jsonify({"id":bid,"status":"cancelled"})
@app.get("/api/admin/bookings")
def admin_bookings():
    u,err= require_admin()
    if err: return err
    db=load(); a=db["bookings"]
    for key in ("date","roomId","userId","status"):
        val=request.args.get(key)
        if val: a=[x for x in a if str(x.get(key))==val]
    return jsonify([expanded(db,b) for b in a])
@app.delete("/api/admin/bookings/<int:bid>")
def admin_cancel(bid):
    u,err=require_admin()
    if err: return err
    db=load(); b=next((x for x in db["bookings"] if x["id"]==bid),None)
    if not b: return error("BOOKING_NOT_FOUND","Бронь не найдена",404)
    if b["status"]=="cancelled": return error("ALREADY_CANCELLED","Бронь уже отменена",409)
    b["status"]="cancelled"; save(db); return jsonify({"id":bid,"status":"cancelled"})
@app.route("/api/admin/rooms",methods=["POST"])
@app.route("/api/admin/rooms/<int:rid>",methods=["PUT"])
def admin_room(rid=None):
    u,err=require_admin()
    if err: return err
    db=load(); b=request.get_json(silent=True) or {}; old=next((x for x in db["rooms"] if x["id"]==rid),None)
    if rid and not old: return error("ROOM_NOT_FOUND","Аудитория не найдена",404)
    name=str(b.get("name","")).strip(); building=b.get("building"); floor=b.get("floor"); cap=b.get("capacity"); eq=b.get("equipment")
    if not name or building not in ["A","B","C","D"] or not isinstance(floor,int) or floor<1 or not isinstance(cap,int) or cap<1 or not isinstance(eq,list) or any(x not in EQUIPMENT for x in eq) or any(x["name"].lower()==name.lower() and x["id"]!=(rid or -1) for x in db["rooms"]):
        return error("VALIDATION_ERROR","Проверьте поля аудитории и уникальность названия",400)
    obj={"id":rid or db["nextRoomId"],"name":name,"building":building,"floor":floor,"capacity":cap,"equipment":eq}
    if rid: db["rooms"]=[obj if x["id"]==rid else x for x in db["rooms"]]
    else: db["rooms"].append(obj); db["nextRoomId"]+=1
    save(db); return jsonify(obj), (200 if rid else 201)

if __name__=="__main__":
    print("CampusFlow запущен: http://127.0.0.1:5000")
    app.run(host="127.0.0.1",port=5000,debug=False)
