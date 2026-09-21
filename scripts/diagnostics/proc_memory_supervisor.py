#!/usr/bin/env python3
from __future__ import annotations
import csv,json,os,sys,time
from pathlib import Path

def kv(path):
    out={}
    try:
        for line in Path(path).read_text().splitlines():
            if ":" in line:
                k,v=line.split(":",1); out[k]=v.strip()
    except (FileNotFoundError,PermissionError,ProcessLookupError):
        pass
    return out

def kb(v):
    try: return int(v.split()[0])
    except Exception: return None

def children(pid):
    seen={pid}; changed=True
    while changed:
        changed=False
        for p in Path("/proc").iterdir():
            if not p.name.isdigit(): continue
            try:
                stat=(p/"stat").read_text().split()
                if int(stat[3]) in seen and int(p.name) not in seen:
                    seen.add(int(p.name)); changed=True
            except (FileNotFoundError,PermissionError,ProcessLookupError,ValueError):
                pass
    return sorted(seen)

root=int(sys.argv[1]); out=Path(sys.argv[2]); interval=float(sys.argv[3] if len(sys.argv)>3 else "0.25")
fields=["timestamp_utc","monotonic_ns","pid","ppid","comm","vmrss_kb","vmhwm_kb","vmsize_kb","rssanon_kb","rssfile_kb","rssshmem_kb","smaps_rss_kb","smaps_pss_kb","private_clean_kb","private_dirty_kb","swap_kb","mem_available_kb","swap_free_kb","cpu_user_ticks","cpu_system_ticks"]
out.parent.mkdir(parents=True,exist_ok=True)
with out.open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    while Path(f"/proc/{root}").exists():
        mem=kv("/proc/meminfo")
        for pid in children(root):
            st=kv(f"/proc/{pid}/status"); sm=kv(f"/proc/{pid}/smaps_rollup")
            try:
                raw=Path(f"/proc/{pid}/stat").read_text().split()
                row={"timestamp_utc":time.strftime("%Y-%m-%dT%H:%M:%S",time.gmtime())+f".{time.time_ns()%1_000_000_000:09d}Z","monotonic_ns":time.monotonic_ns(),"pid":pid,"ppid":raw[3],"comm":raw[1].strip("()"),"vmrss_kb":kb(st.get("VmRSS","")),"vmhwm_kb":kb(st.get("VmHWM","")),"vmsize_kb":kb(st.get("VmSize","")),"rssanon_kb":kb(st.get("RssAnon","")),"rssfile_kb":kb(st.get("RssFile","")),"rssshmem_kb":kb(st.get("RssShmem","")),"smaps_rss_kb":kb(sm.get("Rss","")),"smaps_pss_kb":kb(sm.get("Pss","")),"private_clean_kb":kb(sm.get("Private_Clean","")),"private_dirty_kb":kb(sm.get("Private_Dirty","")),"swap_kb":kb(sm.get("Swap","")),"mem_available_kb":kb(mem.get("MemAvailable","")),"swap_free_kb":kb(mem.get("SwapFree","")),"cpu_user_ticks":raw[13],"cpu_system_ticks":raw[14]}
                w.writerow(row)
            except (FileNotFoundError,PermissionError,ProcessLookupError,IndexError):
                pass
        f.flush(); time.sleep(interval)
