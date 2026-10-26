import json, os, sys, re
HERE=os.path.dirname(os.path.abspath(__file__)); BR=os.path.join(HERE,"..","backend_reference")
sys.path.insert(0,BR); os.environ.setdefault("SOCCER_BRAIN_DIR",os.path.join(HERE,"..","engine")); sys.path.insert(0,os.environ["SOCCER_BRAIN_DIR"])
os.environ.setdefault("APP_ENCRYPTION_KEY","AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
import admin_shell as SH, accounts as A, site_studio as SS, textguard
mods=[{"id":m[0],"label":m[1],"group":m[2],"icon":m[3],"route":m[4],"perms":list(m[5])} for m in SH.MODULES]
perms={r:("*" if "*" in A.PERMS[r] else sorted(A.PERMS[r])) for r in ("owner","admin","support","analyst")}
d=SS.defaults()
presets={}
for k,p in SS.PRESETS.items():
    th,bt=SS.apply_preset(d["theme"],d["buttons"],k)
    presets[k]={"label":p["label"],"colors":th["colors"],"radius":p["radius"],"btn_radius":bt["radius_px"]}
fonts={k:v["stack"] for k,v in SS.FONTS.items()}
flab={k:v["label"] for k,v in SS.FONTS.items()}
radius={k:list(v) for k,v in SS.RADIUS.items()}
base={"theme":d["theme"],"buttons":d["buttons"],"nav":d["nav"],"radius":radius}
t=open(os.path.join(HERE,"template.html")).read()
for k,v in {"__MODULES__":mods,"__GROUPS__":SH.GROUP_ORDER,"__PERMS__":perms,"__TABS__":SH.DEFAULT_TABS,"__PRESETS__":presets,"__FONTS__":fonts,"__BASE__":base,"__FLAB__":flab}.items():
    t=t.replace(k,json.dumps(v))
t=t.replace("__BANNED__","/"+textguard.BANNED.pattern+"/gi")
open(os.path.join(HERE,"admin_prototype.html"),"w").write(t)
print("built",len(t)//1024,"KB")
