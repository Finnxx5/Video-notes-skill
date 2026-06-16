import sys
from pathlib import Path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path: sys.path.insert(0, str(_root))

def build_anchors(segments, transcript_segments=None, merge_window=3.0, safety_net_mid=True, pause_threshold=2.5):
    for seg in segments:
        raw = []
        for vm in seg.visual_moments:
            raw.append({"time":vm.time,"priority":0})
        raw.append({"time":seg.start+0.5,"priority":1})
        if safety_net_mid and (seg.end-seg.start)>5:
            raw.append({"time":(seg.start+seg.end)/2,"priority":2})
        if transcript_segments:
            prev_end=None
            for ts in transcript_segments:
                if seg.start <= ts.start <= seg.end:
                    if prev_end and (ts.start-prev_end)>pause_threshold:
                        pt=prev_end+(ts.start-prev_end)/2
                        if seg.start<=pt<=seg.end: raw.append({"time":pt,"priority":3})
                if ts.end<seg.end: prev_end=ts.end
        raw.sort(key=lambda x:(float(x["time"]), int(x.get("priority", 9))))
        merged=[]
        i=0
        while i<len(raw):
            best=raw[i]; j=i+1
            while j<len(raw) and (raw[j]["time"]-best["time"])<merge_window:
                if raw[j]["priority"]<best["priority"]: best=raw[j]
                j+=1
            merged.append(best["time"]); i=j
        if len(merged)>6:
            llm_times={vm.time for vm in seg.visual_moments}
            priority=[t for t in merged if t in llm_times]
            other=[t for t in merged if t not in set(priority)]
            if len(priority)<6:
                slots=6-len(priority)
                if len(other)>slots:
                    step=len(other)/slots
                    other=[other[min(int(i*step+step/2),len(other)-1)] for i in range(slots)]
                priority.extend(other)
            merged=sorted(priority)[:6]
        seg.anchors=merged
    return segments

def get_all_anchors(segments):
    result=[]
    for s in segments: result.extend(s.anchors)
    return sorted(set(result))

def anchor_stats(segments):
    total=sum(len(s.anchors) for s in segments)
    return {"total_anchors":total,"segments_count":len(segments),"avg_per_segment":round(total/max(len(segments),1),1)}
