from __future__ import annotations

from typing import Any


def history_entry(state: dict, area_id: str | None) -> Any:
    aid = str(area_id or "").strip() or "pallet-town"
    if aid == "route-1":
        rp = (state.get("route_panels") or {}).get("route-1")
        panel = 1
        if isinstance(rp, dict):
            try:
                panel = max(1, min(int(rp.get("panel", 1)), 3))
            except Exception:
                panel = 1
        return {"area_id": "route-1", "route_panel": int(panel)}
    return aid


def history_push(state: dict, area_id: str | None, *, max_len: int = 15) -> None:
    hist = state.get("area_history")
    if not isinstance(hist, list):
        hist = []
    hist.append(history_entry(state, area_id))
    state["area_history"] = hist[-max(1, int(max_len)) :]


def history_pop(state: dict, default_area: str = "pallet-town") -> str:
    hist = state.get("area_history")
    if not isinstance(hist, list) or not hist:
        return str(default_area or "pallet-town")
    raw = hist.pop()
    state["area_history"] = hist
    if isinstance(raw, dict):
        area = str(raw.get("area_id") or "").strip() or str(default_area or "pallet-town")
        if area == "route-1":
            panel = 3
            try:
                panel = max(1, min(int(raw.get("route_panel", 3)), 3))
            except Exception:
                panel = 3
            rp = state.setdefault("route_panels", {})
            rp["route-1"] = {"panel": int(panel), "pos": ("end" if panel >= 3 else "start")}
            state["route_panels"] = rp
        return area
    prev = str(raw or "").strip()
    return prev or str(default_area or "pallet-town")
