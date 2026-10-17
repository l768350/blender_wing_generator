bl_info = {
    "name": "Blender Wing Generator",
    "author": "AIGeneratedCode",
    "version": (0, 54, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Blender Wing Generator",
    "description": "Parametric bird-wing generator with flat-pose search, six-bone wing chain, feather bones, skinning, constraints and fold control",
    "category": "Object",
}

import bpy
import contextlib
import math
import json
import re
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
    IntProperty, PointerProperty, StringProperty,
)
from mathutils import Vector
from bpy_extras.io_utils import ImportHelper
from bpy.app.handlers import persistent

# -----------------------------------------------------------------------------
# Configuration and pure geometry helpers
# -----------------------------------------------------------------------------

ROOT_COLLECTION = "WING_MODEL"
FEATHER_COLLECTION = "WINGGEN_Feathers"
LEGACY_GUIDE_COLLECTION = "WINGGEN_Skeleton_Guides"   # drawn by older versions; removed when found
MM_TO_M = 0.001
TP = math.tau
D2R = math.pi / 180.0
SIDES = ("L", "R")
FLIGHT_GROUPS = {"primaries", "secondaries", "tertials"}

GROUP_DEFS = [
    ("primaries", "初级飞羽", "", "flight"),
    ("secondaries", "次级飞羽", "", "flight"),
    ("tertials", "三级飞羽", "", "flight"),
    ("primaryCoverts", "初级覆羽", "", "covert"),
    ("greaterCoverts", "大覆羽", "", "covert"),
    ("medianCoverts", "中覆羽", "", "covert"),
    ("lesserCoverts", "小覆羽", "", "covert"),
    ("axillaries", "腋羽", "", "aux"),
    ("alula", "小翼羽", "", "aux"),
]
GROUP_LABELS = {g[0]: g[1] for g in GROUP_DEFS}
GROUP_ENUM_ITEMS = [(g[0], g[1], "") for g in GROUP_DEFS]
# Keep HTML and Blender count keys identical for the JSON parameter bridge.
DEFAULT_FEATHER_COUNTS = {
    "secondaries": 10, "primaries": 10, "tertials": 3,
    "medianCoverts": 10, "palmMedianCoverts": 6, "lesserCoverts": 9,
    "axillaries": 3, "alula": 3,
}
FEATHER_COUNT_LIMITS = {
    "secondaries": (2, 20), "primaries": (2, 20), "tertials": (1, 12),
    "medianCoverts": (2, 24), "palmMedianCoverts": (1, 16), "lesserCoverts": (2, 24),
    "axillaries": (0, 12), "alula": (0, 12),
}
COMBO_PARAM_ITEMS = [
    ('lengthScale', '长度比例', ''),
    ('widthScale', '宽度比例', ''),
    ('chordScale', '翼面纵深比例', ''),
    ('sweepOffset', '羽轴后掠偏移', ''),
    ('chordDistOffset', '弦长分布偏移', ''),
    ('rootDistOffset', '羽根分布偏移', ''),
    ('fanOffset', '飞羽扇开偏移', ''),
    ('roundnessOffset', '翼尖圆钝度偏移', ''),
    ('gapOffset', '分指强度偏移', ''),
    ('tipLiftOffset', '翼尖离面偏移', ''),
]
JOINTS = [
    ("Shoulder yaw", 0.0, 25.0, 0.0),
    ("Shoulder roll", 0.0, 60.0, 0.0),
    ("Shoulder axial", 0.0, 0.0, 0.0),
    ("Elbow flexion", 70.0, 15.0, 0.0),
    ("Wrist yaw", 30.0, 15.0, 0.0),
    ("Wrist roll", -35.0, 27.0, 0.3),
    ("Wrist axial", 0.0, 0.0, 0.0),
]

FL_BASE_DEFAULT = [118, 115, 112, 110, 108, 105, 100, 95, 88, 80,
                   112, 118, 125, 135, 150, 165, 180, 193, 200, 193,
                   72, 66, 60]
FW_BASE_DEFAULT = [26, 27, 27, 27, 27, 26, 25, 24, 22, 20,
                   24, 24, 23, 22, 21, 20, 19, 18, 18, 18,
                   22, 22, 22]
CO = [
    [.78, -.10, -22], [.68, -.08, -12], [.42, -.15, 18], [.20, -.20, 41], [.18, -.32, 43],
    [.17, -.43, 44], [.14, -.44, 40], [.12, -.45, 34.6], [.13, -.45, 32.7], [.15, -.40, 31],
    [.87, -.15, -31], [.95, -.10, -34], [1.0, -.05, -36], [1.05, -.18, -36], [1.09, -.30, -33.8],
    [1.13, -.35, -32], [1.16, -.40, -29.8], [1.13, -.55, -22], [1.07, -.70, -12.6], [1.05, -.80, -3],
]

FORM_PRESETS = {
    "pigeon": {"label": "原始鸽翼", "values": {"span": 100, "chord": 100, "width": 100, "sweep": 0, "fan": 0, "roundness": 50, "gap": 0, "tip_lift": 0, "chord_dist": 50, "bone_h": 100, "bone_f": 100, "bone_hand": 100, "hand_digits": 28, "primary_attach": 50}},
    "elliptical": {"label": "椭圆翼", "values": {"span": 92, "chord": 114, "width": 124, "sweep": -1, "fan": 1, "roundness": 90, "gap": 0, "tip_lift": 0, "chord_dist": 82, "bone_h": 104, "bone_f": 100, "bone_hand": 86, "hand_digits": 23, "primary_attach": 20}},
    "highspeed": {"label": "尖窄高速翼", "values": {"span": 112, "chord": 84, "width": 70, "sweep": 18, "fan": 1, "roundness": 8, "gap": 0, "tip_lift": 0, "chord_dist": 24, "bone_h": 100, "bone_f": 89, "bone_hand": 165, "hand_digits": 44, "primary_attach": 92}},
    "dynamic": {"label": "长窄滑翔翼", "values": {"span": 130, "chord": 84, "width": 72, "sweep": 0, "fan": 2, "roundness": 18, "gap": 0, "tip_lift": 3, "chord_dist": 15, "bone_h": 92, "bone_f": 122, "bone_hand": 132, "hand_digits": 38, "primary_attach": 90}},
    "slot": {"label": "升腾滑翔翼", "values": {"span": 116, "chord": 102, "width": 102, "sweep": 0, "fan": 9, "roundness": 18, "gap": 72, "tip_lift": 8, "chord_dist": 58, "bone_h": 98, "bone_f": 112, "bone_hand": 110, "hand_digits": 31, "primary_attach": 82}},
}

GROUP_DEFAULTS = {
    "length_scale": 1.0, "width_scale": 1.0, "chord_scale": 1.0,
    "sweep_offset": 0.0, "root_dist_offset": 0.0, "chord_dist_offset": 0.0,
    "fan_offset": 0.0, "roundness_offset": 0.0, "gap_offset": 0.0, "tip_lift_offset": 0.0,
    "start_pct": 100.0, "end_pct": 100.0, "curve": "LINEAR", "mesh_segments": 0,
    "vane_fold_angle_deg": 0.0,
}

# Defaults keep individual controls for primary/secondary/tertiary flight feathers, while
# adjacent covert feathers share representative chains to avoid an unnecessarily huge rig.
# Internal flags: callbacks call Blender data APIs, so suppress them while bulk-setting values.
_BUILDING = False
_SUPPRESS_UPDATES = False
_UPDATING_MOTION = False


@contextlib.contextmanager
def _suppressed_updates():
    """Silence property-update callbacks while bulk-setting values (restores the previous state)."""
    global _SUPPRESS_UPDATES
    previous = _SUPPRESS_UPDATES
    _SUPPRESS_UPDATES = True
    try:
        yield
    finally:
        _SUPPRESS_UPDATES = previous


def _console(*parts):
    """Print console diagnostics using ASCII-only, English-authored messages."""
    text = " ".join(str(p) for p in parts)
    # Never let localized UI/report strings leak mojibake into the system console.
    print(text.encode("ascii", "backslashreplace").decode("ascii"))


_WARNED = set()


def _warn(where, exc):
    """Console note for a best-effort step that failed; each distinct failure is printed once per session."""
    key = (where, type(exc).__name__)
    if key not in _WARNED:
        _WARNED.add(key)
        _console(f"[Wing Model] {where} failed ({type(exc).__name__}: {exc})")


def _find_view3d_override():
    """Return an available View3D context override for Blender operator calls."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region:
                    return {"window": window, "screen": screen, "area": area, "region": region}
    return None


def clamp(x, low, high):
    return max(low, min(high, x))


COUNT_PROPS = {
    "secondaries": "count_secondaries", "primaries": "count_primaries", "tertials": "count_tertials",
    "medianCoverts": "count_median_coverts", "palmMedianCoverts": "count_palm_median_coverts",
    "lesserCoverts": "count_lesser_coverts", "axillaries": "count_axillaries", "alula": "count_alula",
}


def settings_counts(settings):
    return {key: int(getattr(settings, prop)) for key, prop in COUNT_PROPS.items()}


def ensure_feather_count_settings(settings, reset=False):
    """Resize per-flight-feather controls while preserving all feather IDs that still exist."""
    counts = settings_counts(settings)
    specs = flight_specs(counts)
    expected_ids = [spec[0] for spec in specs]
    current_ids = [item.feather_id for item in settings.feathers]
    if current_ids == expected_ids and not reset:
        return
    old = {}
    for item in settings.feathers:
        old[item.feather_id] = {
            "base_length_mm": item.base_length_mm, "base_width_mm": item.base_width_mm,
            "root_offset_mm": item.root_offset_mm, "angle_offset_deg": item.angle_offset_deg,
            "skinward_offset_mm": item.skinward_offset_mm, "tip_skinward_offset_mm": item.tip_skinward_offset_mm,
        }
    with _suppressed_updates():
        while len(settings.feathers):
            settings.feathers.remove(len(settings.feathers)-1)
        for fid, group_id, local in specs:
            item = settings.feathers.add()
            item.feather_id = fid
            item.group_id = group_id
            vals = old.get(fid) if (not reset) else None
            if vals:
                item.base_length_mm = vals["base_length_mm"]
                item.base_width_mm = vals["base_width_mm"]
                item.root_offset_mm = vals["root_offset_mm"]
                item.angle_offset_deg = vals["angle_offset_deg"]
                item.skinward_offset_mm = vals.get("skinward_offset_mm", 0.0)
                item.tip_skinward_offset_mm = vals.get("tip_skinward_offset_mm", 0.0)
            else:
                length, width = default_feather_profile(group_id, local)
                item.base_length_mm = length
                item.base_width_mm = width
                item.root_offset_mm = 0.0
                item.angle_offset_deg = 0.0
                item.skinward_offset_mm = 0.0
                item.tip_skinward_offset_mm = 0.0


def v_add(a, b): return [a[i] + b[i] for i in range(3)]
def v_sub(a, b): return [a[i] - b[i] for i in range(3)]
def v_mul(a, s): return [x * s for x in a]
def v_dot(a, b): return sum(a[i] * b[i] for i in range(3))
def v_cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def v_len(a): return math.sqrt(sum(x*x for x in a))
def v_norm(a):
    length = v_len(a)
    return [x / length for x in a] if length > 1.0e-12 else [0.0, 0.0, 1.0]
def lerp(a, b, t): return a + (b-a)*t


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def rz(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def ry(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def v_rotate(v, axis, angle):
    axis = v_norm(axis)
    c, s = math.cos(angle), math.sin(angle)
    kv = v_cross(axis, v)
    kd = v_dot(axis, v)
    return [v[i]*c + kv[i]*s + axis[i]*kd*(1-c) for i in range(3)]


def flight_specs(counts=None):
    counts = counts or DEFAULT_FEATHER_COUNTS
    specs = []
    for group_id, prefix in (("secondaries", "S"), ("primaries", "P"), ("tertials", "T")):
        for local in range(max(0, int(counts.get(group_id, DEFAULT_FEATHER_COUNTS[group_id])))):
            specs.append((f"{prefix}{local+1}", group_id, local))
    return specs


def flight_group_and_local(i, counts=None):
    counts = counts or DEFAULT_FEATHER_COUNTS
    ns = int(counts.get("secondaries", 10))
    np = int(counts.get("primaries", 10))
    nt = int(counts.get("tertials", 3))
    if i < ns:
        return "secondaries", i, ns
    if i < ns + np:
        return "primaries", i-ns, np
    return "tertials", i-ns-np, nt


def feather_id(i, counts=None):
    group, local, _n = flight_group_and_local(i, counts)
    prefix = {"secondaries": "S", "primaries": "P", "tertials": "T"}[group]
    return f"{prefix}{local+1}"


def flight_index_for(counts, group_id, local):
    if group_id == "secondaries":
        return int(local)
    if group_id == "primaries":
        return int(counts["secondaries"]) + int(local)
    return int(counts["secondaries"]) + int(counts["primaries"]) + int(local)


def extrapolate_profile(values, local, low=0.0, high=400.0):
    if local < len(values):
        return float(values[local])
    if not values:
        return float(low)
    last = float(values[-1])
    prev = float(values[-2]) if len(values) > 1 else last
    return clamp(last + (last-prev)*(local-len(values)+1), low, high)


def default_feather_profile(group_id, local):
    lengths = {
        "secondaries": FL_BASE_DEFAULT[:10],
        "primaries": FL_BASE_DEFAULT[10:20],
        "tertials": FL_BASE_DEFAULT[20:23],
    }
    widths = {
        "secondaries": FW_BASE_DEFAULT[:10],
        "primaries": FW_BASE_DEFAULT[10:20],
        "tertials": FW_BASE_DEFAULT[20:23],
    }
    return (extrapolate_profile(lengths[group_id], local, 12, 400),
            extrapolate_profile(widths[group_id], local, 5, 100))



def root_distribution_value(state, group_id):
    base = state["form"]["primary_attach"] if group_id == "primaries" else 50.0
    return clamp(base + state["groups"][group_id]["root_dist_offset"], 0.0, 100.0)


def distort_root_u(state, u, group_id):
    value = root_distribution_value(state, group_id)
    factor = .65 + (value / 100.0) * .7
    return clamp(.5 + (u-.5)*factor, 0.0, 1.0)


def effective_bone_lengths(state):
    f = state["form"]
    raw = [state["bone_base"][0]*f["bone_h"], state["bone_base"][1]*f["bone_f"], state["bone_base"][2]*f["bone_hand"]]
    base_sum = sum(state["bone_base"][:3])
    total = sum(raw) or 1.0
    scale = (base_sum / total) * f["span"]
    return [v*scale for v in raw]


def joints_at_t0():
    # Preserve the confirmed HTML's default phase (t=0), including the existing per-joint amplitudes.
    return [mean + amp * math.cos(TP * (0.0-phase)) for _, mean, amp, phase in JOINTS]


def fk(state, angles):
    y, r, p, f, o, b, wr = [x*D2R for x in angles]
    u = [0, -1, 0]
    shoulder_width = state["bone_base"][3]
    sh = [0, -shoulder_width, 0]
    bl = effective_bone_lengths(state)
    Rs = mat_mul(mat_mul(rz(y), rx(-r)), ry(p))
    e = [sh[i] + mat_vec(Rs, u)[i]*bl[0] for i in range(3)]
    Re = mat_mul(Rs, rz(f))
    w = [e[i] + mat_vec(Re, u)[i]*bl[1] for i in range(3)]
    Rw = mat_mul(mat_mul(mat_mul(Re, rz(-o)), rx(-b)), ry(-wr))
    t = [w[i] + mat_vec(Rw, u)[i]*bl[2] for i in range(3)]
    return {"points": [sh, e, w, t], "Re": Re, "Rw": Rw}


def wrist_angles(k, finger_offset_deg=0.0):
    a = v_norm(v_sub(k["points"][2], k["points"][1]))
    c = v_norm(v_sub(k["points"][3], k["points"][2]))
    tw = 180.0 - math.acos(clamp(v_dot(a, c), -1.0, 1.0))/D2R
    tf = clamp(16.0 - 20.0*(tw-85.0)/70.0, -10.0, 32.0) + finger_offset_deg
    return tw, tf


def scale_for_groups(state, groups, param, include_global=True):
    groups = list(dict.fromkeys(groups))
    key = f"{param}_scale"
    result = 1.0
    if param == "length" and include_global:
        result *= state["global_length"]
    for group_id in groups:
        result *= state["groups"][group_id][key]
    combo_param = f"{param}Scale"
    for combo in state["combos"]:
        if set(combo["targets"]).intersection(groups):
            if combo.get("param") == combo_param:
                result *= float(combo.get("value", 100.0))/100.0
            elif "param" not in combo:  # backward-compatible old three-scale combo payload
                legacy_key = {"length": "length_pct", "width": "width_pct", "chord": "chord_pct"}[param]
                result *= float(combo.get(legacy_key, 100.0))/100.0
    return result


_OFFSET_COMBO_KEYS = {
    "sweep_offset": "sweepOffset", "root_dist_offset": "rootDistOffset",
    "chord_dist_offset": "chordDistOffset", "fan_offset": "fanOffset",
    "roundness_offset": "roundnessOffset", "gap_offset": "gapOffset",
    "tip_lift_offset": "tipLiftOffset",
}


def offset_for_groups(state, groups, param):
    groups = list(dict.fromkeys(groups))
    result = sum(state["groups"][g][param] for g in groups)
    combo_param = _OFFSET_COMBO_KEYS[param]
    for combo in state["combos"]:
        if combo.get("param") == combo_param and set(combo["targets"]).intersection(groups):
            result += float(combo.get("value", 0.0))
    return result


def length_distribution_value_pct(setting, u):
    """Evaluate the group's piecewise length-multiplier profile at normalized row position u."""
    pos = clamp(float(u), 0.0, 1.0) * 100.0
    knots = [(0.0, float(setting.get("start_pct", 100.0)))]
    for point in setting.get("length_reference_points", []) or []:
        if not isinstance(point, dict):
            continue
        knots.append((clamp(float(point.get("position_pct", 50.0)), 1.0, 99.0),
                      clamp(float(point.get("value_pct", 100.0)), 25.0, 200.0)))
    knots.append((100.0, float(setting.get("end_pct", 100.0))))
    knots.sort(key=lambda item: item[0])
    # If malformed/imported points duplicate a position, keep the last point at that position.
    compact = []
    for position, value in knots:
        if compact and abs(position - compact[-1][0]) < 1.0e-6:
            compact[-1] = (position, value)
        else:
            compact.append((position, value))
    left, right = compact[0], compact[-1]
    for i in range(len(compact)-1):
        if pos <= compact[i+1][0]:
            left, right = compact[i], compact[i+1]
            break
    span = max(1.0e-6, right[0] - left[0])
    t = clamp((pos - left[0]) / span, 0.0, 1.0)
    if str(setting.get("curve", "LINEAR")).upper() == "SMOOTH":
        t = t*t*(3.0-2.0*t)
    return left[1] + (right[1] - left[1]) * t


def length_distribution_factor(state, group_id, u):
    setting = state["groups"][group_id]
    return length_distribution_value_pct(setting, u) / 100.0


def flight_distribution_u(i, counts=None):
    group, local, n = flight_group_and_local(i, counts)
    return 0.0 if n <= 1 else local / float(n-1)


def chord_dist_for(state, groups):
    return clamp(state["form"]["chord_dist"] + offset_for_groups(state, groups, "chord_dist_offset"), 0.0, 100.0)


def form_length_factor(state, i, linked_groups=None):
    counts = state.get("counts", DEFAULT_FEATHER_COUNTS)
    group, local, n = flight_group_and_local(i, counts)
    groups = linked_groups or [group]
    fdata = state["form"]
    kind = state["preset"]
    u = 0.0 if n <= 1 else local / float(n-1)
    cd = chord_dist_for(state, groups)
    factor = 1.0
    if group == "secondaries":
        if kind == "elliptical": factor = .98 + .08*math.sin(math.pi*u)
        elif kind == "highspeed": factor = 1.02 - .07*u
        elif kind == "dynamic": factor = .97 + .06*u
        elif kind == "slot": factor = .98 + .03*u
        factor *= 1.0 + ((cd-50.0)/50.0)*.12*math.sin(math.pi*u)
    elif group == "primaries":
        if kind == "elliptical": factor = .94 + .12*math.sin(math.pi*u)
        elif kind == "highspeed": factor = .88 + .25*u
        elif kind == "dynamic": factor = .94 + .15*u
        elif kind == "slot": factor = .92 + .25*u
        rnd = clamp(fdata["roundness"] + offset_for_groups(state, groups, "roundness_offset"), 0.0, 100.0)
        edge = clamp((u-.55)/.45, 0.0, 1.0)
        factor *= 1.0 + ((50.0-rnd)/50.0)*.14*math.pow(edge, 1.6)
        factor *= 1.0 - ((cd-50.0)/50.0)*.10*u
    return factor


def form_flight_length(state, i):
    counts = state.get("counts", DEFAULT_FEATHER_COUNTS)
    group, _local, _n = flight_group_and_local(i, counts)
    return (state["feathers"][i]["length_mm"]
            * scale_for_groups(state, [group], "length", True)
            * state["form"]["chord"]
            * scale_for_groups(state, [group], "chord", False)
            * form_length_factor(state, i, [group])
            * length_distribution_factor(state, group, flight_distribution_u(i, counts)))


def linked_flight_length(state, i, linked_group):
    counts = state.get("counts", DEFAULT_FEATHER_COUNTS)
    parent, _local, _n = flight_group_and_local(i, counts)
    groups = [parent, linked_group] if linked_group else [parent]
    return (state["feathers"][i]["length_mm"]
            * scale_for_groups(state, groups, "length", True)
            * state["form"]["chord"]
            * scale_for_groups(state, groups, "chord", False)
            * form_length_factor(state, i, groups)
            * length_distribution_factor(state, parent, flight_distribution_u(i, counts)))


def form_flight_width(state, i):
    counts = state.get("counts", DEFAULT_FEATHER_COUNTS)
    group, local, n = flight_group_and_local(i, counts)
    u = 0.0 if n <= 1 else local / float(n-1)
    factor = 1.0
    preset = state["preset"]
    if group == "secondaries" and preset == "highspeed":
        factor = 1.0-.06*u
    if group == "primaries":
        if preset == "elliptical": factor = 1.0+.04*math.sin(math.pi*u)
        elif preset == "highspeed": factor = .98-.16*u
        elif preset == "dynamic": factor = .98-.09*u
        elif preset == "slot": factor = 1.0-.04*u
        factor *= 1.0 + ((chord_dist_for(state, [group])-50.0)/50.0)*.04*math.sin(math.pi*u)
    return state["feathers"][i]["width_mm"]*state["form"]["width"]*scale_for_groups(state, [group], "width", False)*factor


def primary_root_u(state, local_index):
    counts = state.get("counts", DEFAULT_FEATHER_COUNTS)
    n = int(counts["primaries"])
    u = 0.0 if n <= 1 else local_index/float(n-1)
    dist = root_distribution_value(state, "primaries") / 100.0
    start = lerp(.15, .08, dist)
    end = lerp(.82, .98, dist)
    power = lerp(.78, 1.18, dist)
    return distort_root_u(state, start+(end-start)*math.pow(u, power), "primaries")


def secondary_slot_index(local_index, count):
    gap_slot = max(1, min(count-1, int(math.floor((count+1)*.4 + .5))))
    return local_index if local_index < gap_slot else local_index + 1


def make_thumb_geo(state, k):
    pts = k["points"]
    c = v_sub(pts[3], pts[2]); ch = v_norm(c); a = v_norm(v_sub(pts[2], pts[1]))
    tm0 = mat_vec(k["Rw"], [-1, 0, 0])
    trm = v_norm(v_sub(tm0, v_mul(a, v_dot(tm0, a))))
    leadm = v_mul(trm, -1)
    nm = mat_vec(k["Rw"], [0, 0, 1])
    motion = state.get("motion", {})
    fold = clamp(motion.get("fold_pct", 0.0)/100.0, 0.0, 1.0)
    al = motion.get("alula_open_deg", 15.0)*D2R*(1.0-fold)
    b0 = v_add(v_add(pts[2], v_mul(c, .05)), v_mul(leadm, 2.0))
    g = al*.8
    dir_t = v_norm(v_add(v_mul(ch, math.cos(g)), v_mul(nm, math.sin(g))))
    return {"B0": b0, "tip": v_add(b0, v_mul(dir_t, 12.0)), "ch": ch, "trM": trm, "nM": nm, "al": al}


def generate_feathers(state, k, phase=0.0):
    counts = dict(DEFAULT_FEATHER_COUNTS)
    counts.update(state.get("counts", {}))
    points = k["points"] if isinstance(k, (list, tuple)) else k["points"]
    # fk() in this add-on returns a dictionary; tolerate the legacy list-like shape too.
    motion = state.get("motion", {})
    tw, tf = wrist_angles(k, motion.get("finger_offset_deg", 0.0))
    axis = v_norm(v_sub(points[2], points[1]))
    c = v_sub(points[3], points[2])
    g = max(0.0, -math.sin(TP*phase))
    out, flight, th = [], [], []
    tr_u = mat_vec(k["Re"], [-1, 0, 0]); n_u = mat_vec(k["Re"], [0, 0, 1])
    tm0 = mat_vec(k["Rw"], [-1, 0, 0])
    tr_m = v_norm(v_sub(tm0, v_mul(axis, v_dot(tm0, axis))))
    n_m = mat_vec(k["Rw"], [0, 0, 1])
    bl = effective_bone_lengths(state)
    specs = flight_specs(counts)

    def coefficient_for(group_id, local):
        if group_id == "secondaries":
            profile = CO[:10]
        elif group_id == "primaries":
            profile = CO[10:20]
        else:
            return None
        target_count = int(counts[group_id])
        if target_count == len(profile):
            return profile[min(local, len(profile)-1)]
        if target_count <= 1:
            return profile[0]
        u = local / float(target_count-1)
        x = clamp(u, 0.0, 1.0) * (len(profile)-1)
        lo = int(math.floor(x)); hi = min(len(profile)-1, lo+1); f = x-lo
        return [lerp(profile[lo][j], profile[hi][j], f) for j in range(3)]

    def angle_at_group_u(group_id, u):
        """Continuously sample already-computed feather angles along one flight-feather row."""
        if group_id == "secondaries":
            offset = 0; count = int(counts["secondaries"])
        elif group_id == "primaries":
            offset = int(counts["secondaries"]); count = int(counts["primaries"])
        else:
            offset = int(counts["secondaries"]) + int(counts["primaries"]); count = int(counts["tertials"])
        if count <= 1:
            return th[offset] if offset < len(th) else 90.0
        x = clamp(float(u), 0.0, 1.0) * (count-1)
        lo = int(math.floor(x)); hi = min(count-1, lo+1); f = x-lo
        return lerp(th[offset+lo], th[offset+hi], f)

    for i, (fid, group, local) in enumerate(specs):
        n = int(counts[group])
        u = 0.0 if n <= 1 else local/float(n-1)
        is_secondary = group == "secondaries"
        is_primary = group == "primaries"
        is_tertial = group == "tertials"
        feather_data = state["feathers"][i]
        co = coefficient_for(group, local)
        if is_tertial:
            last_secondary_theta = th[max(0, int(counts["secondaries"])-1)] if th else 90.0
            tertial_pos = 0.0 if n <= 1 else (local / float(n-1))*2.0
            base_th = clamp(last_secondary_theta - 5.0*(1.0+tertial_pos), 0.0, 170.0)
        else:
            base_th = clamp(co[0]*tw + co[1]*tf + co[2], 0.0, 170.0)
        sweep_factor = .45 if is_secondary else (1.0 if is_primary else 0.0)
        sweep = state["form"]["sweep"]*sweep_factor + offset_for_groups(state, [group], "sweep_offset") + feather_data["angle_offset_deg"]
        fan = ((state["form"]["fan"] + offset_for_groups(state, [group], "fan_offset"))*(u-.5)*2.0) if is_primary else 0.0
        thf = base_th+sweep+fan
        phi = (180.0-thf)*D2R
        pr = not is_secondary
        tr = tr_m if pr else tr_u
        nw = n_m if pr else n_u
        direction = v_norm(v_add(v_mul(axis, math.cos(phi)), v_mul(tr, math.sin(phi))))
        root_offset = feather_data["root_offset_mm"]
        if is_tertial:
            root_base = .95-.30*u
            root = v_add(points[0], v_mul(v_sub(points[1], points[0]), clamp(distort_root_u(state, root_base, "tertials") + root_offset/max(1.0, bl[0]), 0.0, 1.0)))
        elif is_primary:
            root = v_add(points[2], v_mul(c, clamp(primary_root_u(state, local) + root_offset/max(1.0, bl[2]), 0.0, 1.0)))
        else:
            slot = secondary_slot_index(local, n)
            pos = .95-.9*slot/max(1.0, float(n))
            root = v_add(points[1], v_mul(v_sub(points[2], points[1]), clamp(distort_root_u(state, pos, "secondaries") + root_offset/max(1.0, bl[1]), 0.0, 1.0)))

        if is_primary:
            beta_coefficient = .5+.5*u
        elif is_tertial:
            # Preserve the original plugin's default tertiary feather coefficient.
            beta_coefficient = .3
        else:
            beta_coefficient = .5*u*.6
        if is_secondary and motion.get("secondary_follow_yellow_reference", False):
            # Smoothly interpolate the yellow-feather reference coefficient over the dynamic secondary group.
            smooth_u = u*u*(3.0-2.0*u)
            wrist_reference_coefficient = .5
            primary_count = max(2, int(counts["primaries"]))
            elbow_reference_coefficient = .5 + .5*primary_count/max(1.0, float(primary_count-1))
            beta_coefficient = lerp(wrist_reference_coefficient, elbow_reference_coefficient, smooth_u)
        beta = motion.get("valve_angle_deg", 25.0)*D2R*g*beta_coefficient
        n2 = v_norm(v_rotate(nw, direction, motion.get("shingle_tilt_deg", 6.0)*D2R+beta))
        wv = v_norm(v_cross(n2, direction))
        if v_dot(wv, axis) < 0: wv = v_mul(wv, -1)
        length = form_flight_length(state, i)
        width = form_flight_width(state, i)
        if is_tertial:
            lf = .47
        elif is_secondary:
            lf = .40 + .06*min(local, 7)/7.0 + (.01*(local-7) if local > 7 else 0.0)
        else:
            lf = .385-.19*u
        vertices = []
        def profile(s): return min(1.0, s/.25)*(math.sqrt(max(0.0, 1.0-((s-.8)/.2)**2)) if s>.8 else 1.0)
        u_outer = u if is_primary else 0.0
        slot_u = max(0.0, (u_outer-.38)/.62)
        gap = clamp(state["form"]["gap"]+offset_for_groups(state,[group],"gap_offset"), 0.0, 100.0)
        tip_lift = max(0.0, state["form"]["tip_lift"]+offset_for_groups(state,[group],"tip_lift_offset"))
        split = gap/100.0*30.0*math.pow(slot_u,1.25) if is_primary else 0.0
        lift = tip_lift*math.pow(u_outer,1.5) if is_primary else 0.0
        sep_raw = tr_m if pr else tr_u
        sep_dir = v_norm(v_sub(sep_raw, v_mul(direction, v_dot(sep_raw,direction))))
        def center_at(s):
            return v_add(v_add(v_add(root, v_mul(direction,length*s)), v_mul(sep_dir,split*s*s)), v_mul(n2,lift*s*s*s))
        for j in range(17):
            s = j/16.0; p0 = center_at(s); vertices.append(v_add(p0, v_mul(wv,width*lf*profile(s))))
        for j in range(16,-1,-1):
            s=j/16.0; p0=center_at(s)
            em=1.0-.35*math.exp(-(((s-.6)/.07)**2)) if is_primary and local == n-1 else 1.0
            vertices.append(v_sub(p0,v_mul(wv,width*(1.0-lf)*profile(s)*em)))
        tip = center_at(1.0)
        centerline = [center_at(j / 16.0) for j in range(17)]
        feather = {"pts": vertices, "centerline": centerline, "base": root, "tip": tip, "pr": pr, "cov": False, "nm": n2, "idx": i, "group": group, "id": fid, "vt": False}
        out.append(feather); flight.append(feather); th.append(thf)

        covert_group = "primaryCoverts" if is_primary else "greaterCoverts"
        covert_u = u
        linked_len = linked_flight_length(state, i, covert_group) * (.5 if pr else .58) * length_distribution_factor(state, covert_group, covert_u)
        covert_width_scale = scale_for_groups(state, [covert_group], "width", False)
        for sd in [1, -1]:
            nc = v_norm(v_rotate(v_mul(nw,sd), direction, sd*((6.0+4.0)*D2R+beta)))
            wc = v_norm(v_cross(nc,direction))
            if v_dot(wc,axis)<0: wc=v_mul(wc,-1)
            b2=v_add(root,v_mul(nc,1.5)); cp=[]; pf=lambda s:min(1.0,s/.2)*(math.sqrt(max(0.0,1.0-((s-.7)/.3)**2)) if s>.7 else 1.0)
            for j in range(17):
                s=j/16.0;cp.append(v_add(v_add(b2,v_mul(direction,linked_len*s)),v_mul(wc,linked_len*.22*state["form"]["width"]*covert_width_scale*.5*pf(s))))
            for j in range(16,-1,-1):
                s=j/16.0;cp.append(v_sub(v_add(b2,v_mul(direction,linked_len*s)),v_mul(wc,linked_len*.22*state["form"]["width"]*covert_width_scale*.5*pf(s))))
            covert_centerline = [v_add(b2, v_mul(direction, linked_len * (j / 16.0))) for j in range(17)]
            out.append({"pts":cp,"centerline":covert_centerline,"base":b2,"tip":v_add(b2,v_mul(direction,linked_len)),"pr":pr,"cov":True,"ly":1,"vt":sd<0,"nm":nc,"group":covert_group,"id":f"{covert_group}:{fid}:{'under' if sd<0 else 'upper'}"})

    # Covert row helpers; row positions are evenly re-spaced when counts change.
    lw = v_len(v_sub(points[2],points[1])); lh=v_len(v_sub(points[1],points[0])); p0=v_add(points[0],v_mul(v_sub(points[1],points[0]),.65)); lo=lh*.35; lt=lw+lo
    def upt(dd):
        return v_add(points[2],v_mul(v_sub(points[1],points[2]),dd/lw)) if dd<=lw else v_add(points[1],v_mul(v_sub(p0,points[1]),min(1.0,(dd-lw)/lo)))
    refs=[]
    ns=int(counts["secondaries"]); nt=int(counts["tertials"])
    for local in range(ns):
        slot=secondary_slot_index(local,ns); idx=flight_index_for(counts,"secondaries",local)
        refs.append([(.05+.9*slot/max(1.0,float(ns)))*lw,th[idx],idx])
    for local in range(nt):
        u=0.0 if nt<=1 else local/float(nt-1); idx=flight_index_for(counts,"tertials",local)
        refs.append([lw+(.05+.30*u)*lh,th[idx],idx])
    def rf(dd, col):
        if dd<=refs[0][0]: return refs[0][col]
        for q in range(1,len(refs)):
            if dd<=refs[q][0]:
                ratio=(dd-refs[q-1][0])/(refs[q][0]-refs[q-1][0] or 1e-9)
                return lerp(refs[q-1][col],refs[q][col],ratio)
        return refs[-1][col]
    def rf_len(dd,group_id):
        if dd<=refs[0][0]: return linked_flight_length(state,refs[0][2],group_id)
        for q in range(1,len(refs)):
            if dd<=refs[q][0]:
                ratio=(dd-refs[q-1][0])/(refs[q][0]-refs[q-1][0] or 1e-9)
                return lerp(linked_flight_length(state,refs[q-1][2],group_id),linked_flight_length(state,refs[q][2],group_id),ratio)
        return linked_flight_length(state,refs[-1][2],group_id)

    def mkc(base,thr,nw0,length,ly,pr,bt,tilt,wr,sd,group_id,ident):
        nw=v_mul(nw0,sd)
        phi=(180.0-thr)*D2R
        direction=v_norm(v_add(v_mul(axis,math.cos(phi)),v_mul(tr_m if pr else tr_u,math.sin(phi))))
        group_angle=offset_for_groups(state,[group_id],"sweep_offset")
        nc=v_norm(v_rotate(nw,direction,sd*((tilt+group_angle)*D2R+bt)))
        wc=v_norm(v_cross(nc,direction))
        if v_dot(wc,axis)<0: wc=v_mul(wc,-1)
        b2=v_add(base,v_mul(nc,1.5+ly)); width=length*(wr if wr is not None else .26)*state["form"]["width"]*scale_for_groups(state,[group_id],"width",False)
        cp=[]
        def pf(s): return min(1.0,s/.2)*(math.sqrt(max(0.0,1.0-((s-.7)/.3)**2)) if s>.7 else 1.0)
        for j in range(13):
            u=j/12.0;cp.append(v_add(v_add(b2,v_mul(direction,length*u)),v_mul(wc,width*.5*pf(u))))
        for j in range(12,-1,-1):
            u=j/12.0;cp.append(v_sub(v_add(b2,v_mul(direction,length*u)),v_mul(wc,width*.5*pf(u))))
        centerline = [v_add(b2, v_mul(direction, length * (j / 12.0))) for j in range(13)]
        out.append({"pts":cp,"centerline":centerline,"base":b2,"tip":v_add(b2,v_mul(direction,length)),"pr":pr,"cov":True,"ly":ly,"vt":sd<0,"nm":nc,"group":group_id,"id":ident})

    def bs(u): return motion.get("valve_angle_deg",25.0)*D2R*g*.3*clamp(u,0,1)*.8
    for ly,n,lam,kap,lr,wr,tilt,group_id,subtype in [
        (2,int(counts["medianCoverts"]),.8,.25,.36,.26,12.0,"medianCoverts","median"),
        (3,int(counts["lesserCoverts"]),.45,.45,.23,.3,14.0,"lesserCoverts","lesser"),
        (4,int(counts["lesserCoverts"]),0,.55,.2,.4,16.0,"lesserCoverts","marginal"),
    ]:
        for m in range(n):
            row_u=0.0 if n<=1 else m/float(n-1); s_base=.06+.89*row_u; ss=distort_root_u(state,s_base,group_id); dd=ss*lt
            lp=v_add(points[2],v_mul(v_sub(p0,points[2]),ss)); pt=v_add(v_mul(lp,1-lam),v_mul(upt(dd),lam))
            angle0=rf(dd,1)*(1-kap)+90.0*kap
            dist_scale=length_distribution_factor(state,group_id,row_u)
            for sd in [1,-1]: mkc(pt,angle0,n_u,rf_len(dd,group_id)*lr*dist_scale,ly,False,bs(min(1.0,max(0.0,dd/max(lw,1e-9)))),tilt,wr,sd,group_id,f"{subtype}{m+1}:{'under' if sd<0 else 'upper'}")

    # Axillaries are a model-extension group, distinct from scapular feathers.
    ax_count=int(counts["axillaries"])
    for j in range(ax_count):
        u0=0.0 if ax_count<=1 else j/float(ax_count-1)
        base_len=extrapolate_profile([64.0,60.0,56.0],j,12.0,100.0)
        u=distort_root_u(state,lerp(.9,.5,u0),"axillaries")
        base=v_add(points[0],v_mul(v_sub(points[1],points[0]),u))
        length=base_len*state["global_length"]*scale_for_groups(state,["axillaries"],"length",False)*length_distribution_factor(state,"axillaries",u0)
        tertial_local=max(0,min(nt-1,int(math.floor(u0*max(1,nt-1)+.5))))
        if (ax_count == DEFAULT_FEATHER_COUNTS["axillaries"] and nt == DEFAULT_FEATHER_COUNTS["tertials"]):
            angle=th[flight_index_for(counts,"tertials",tertial_local)]
        else:
            angle=angle_at_group_u("tertials",u0)
        mkc(base,angle,n_u,length,1,False,bs(u0),10.0,.34,-1,"axillaries",f"axillary{j+1}")

    # Palm-region median coverts.
    q=v_add(points[1],v_mul(v_sub(points[2],points[1]),.75))
    palm_n=int(counts["palmMedianCoverts"]); primary_n=int(counts["primaries"])
    for i in range(palm_n):
        row_u=0.0 if palm_n<=1 else i/float(palm_n-1)
        ss=distort_root_u(state,.12+.78*row_u,"medianCoverts")
        primary_u=clamp((ss-.1)/.88,0.0,1.0)
        j=max(0,min(primary_n-1,int(math.floor(primary_u*(primary_n-1)+.5))))
        p_idx=flight_index_for(counts,"primaries",j)
        if (palm_n == DEFAULT_FEATHER_COUNTS["palmMedianCoverts"] and primary_n == DEFAULT_FEATHER_COUNTS["primaries"]):
            palm_reference_angle=th[p_idx]
        else:
            palm_reference_angle=angle_at_group_u("primaries",primary_u)
        up=v_add(points[2],v_mul(c,ss)); lp=v_add(q,v_mul(v_sub(points[3],q),ss)); pt=v_add(v_mul(lp,.25),v_mul(up,.75))
        for sd in [1,-1]: mkc(pt,palm_reference_angle*.6+90.0*.4,n_m,linked_flight_length(state,p_idx,"medianCoverts")*.3*length_distribution_factor(state,"medianCoverts",row_u),2,True,motion.get("valve_angle_deg",25.0)*D2R*(.5+.5*primary_u)*.8,12.0,None,sd,"medianCoverts",f"palmMedian{i+1}:{'under' if sd<0 else 'upper'}")

    # Alula feathers + the simplified thumb geometry.
    thumb=make_thumb_geo(state,k); alula_n=int(counts["alula"])
    for j in range(alula_n):
        u_al=0.0 if alula_n<=1 else j/float(alula_n-1)
        base_len=extrapolate_profile([38.0,34.0,28.0],j,8.0,80.0)
        base_width=extrapolate_profile([12.0,10.0,8.0],j,3.0,30.0)
        root_u=.6+.4*u_al
        base=v_add(thumb["B0"],v_mul(v_sub(thumb["tip"],thumb["B0"]),root_u))
        psi=(3.0+8.0*u_al+offset_for_groups(state,["alula"],"sweep_offset"))*D2R
        direction=v_norm(v_add(v_add(v_mul(thumb["ch"],math.cos(psi)),v_mul(thumb["trM"],math.sin(psi))),v_mul(thumb["nM"],math.tan(thumb["al"]*.35))))
        tl=thumb["al"]
        sg=1 if v_dot(v_rotate(thumb["nM"],direction,.1),thumb["trM"])>v_dot(thumb["nM"],thumb["trM"]) else -1
        nc=v_norm(v_rotate(thumb["nM"],direction,sg*tl)); wc=v_norm(v_cross(nc,direction))
        if v_dot(wc,thumb["trM"])>0: wc=v_mul(wc,-1)
        length=base_len*state["global_length"]*scale_for_groups(state,["alula"],"length",False)*length_distribution_factor(state,"alula",u_al)
        width=base_width*state["form"]["width"]*scale_for_groups(state,["alula"],"width",False)
        b2=v_add(base,v_mul(nc,4.5));cp=[]
        def pf_al(s): return min(1.0,s/.2)*(math.sqrt(max(0.0,1.0-((s-.75)/.25)**2)) if s>.75 else 1.0)
        for q0 in range(13):
            u=q0/12.0;cp.append(v_add(v_add(b2,v_mul(direction,length*u)),v_mul(wc,width*.35*pf_al(u))))
        for q0 in range(12,-1,-1):
            u=q0/12.0;cp.append(v_sub(v_add(b2,v_mul(direction,length*u)),v_mul(wc,width*.65*pf_al(u))))
        centerline = [v_add(b2, v_mul(direction, length * (q0 / 12.0))) for q0 in range(13)]
        out.append({"pts":cp,"centerline":centerline,"base":b2,"tip":v_add(b2,v_mul(direction,length)),"pr":True,"cov":True,"ly":5,"vt":False,"nm":nc,"group":"alula","id":f"alula{j+1}"})
    return out


def apply_skinward_offsets(feathers, state):
    """Nudge feather geometry toward its local supporting side, never world Z.

    This add-on does not yet include a deformable wing-skin surface. The stable proxy is
    the negative local feather-plane normal stored by the original growth formula. Global,
    group and individual offsets add together; tip-only offset eases in along the feather.
    A positive value moves inward toward the backing/support side.
    """
    form = state.get("form", {})
    groups = state.get("groups", {})
    individual = {str(item.get("id", "")): item for item in state.get("feathers", [])}
    global_root = float(form.get("skinward_offset_mm", 0.0))
    global_tip = float(form.get("tip_skinward_offset_mm", 0.0))
    for feather in feathers:
        normal = feather.get("nm")
        if not normal:
            continue
        inward = v_mul(v_norm(normal), -1.0)
        group = groups.get(feather.get("group", ""), {})
        own = individual.get(str(feather.get("id", "")), {})
        root_offset = combine_scope_values("sum", (global_root, float(group.get("skinward_offset_mm", 0.0)),
                                                    float(own.get("skinward_offset_mm", 0.0))))
        tip_offset = combine_scope_values("sum", (global_tip, float(group.get("tip_skinward_offset_mm", 0.0)),
                                                   float(own.get("tip_skinward_offset_mm", 0.0))))
        if abs(root_offset) < 1e-12 and abs(tip_offset) < 1e-12:
            continue
        def delta_at(t):
            eased = t * t * (3.0 - 2.0 * t)
            return v_mul(inward, root_offset + tip_offset * eased)
        pts = feather.get("pts", [])
        half = len(pts) // 2
        if half >= 2 and len(pts) == half * 2:
            last = float(half - 1)
            for idx, point in enumerate(pts):
                t = idx / last if idx < half else (len(pts) - 1 - idx) / last
                pts[idx] = v_add(point, delta_at(t))
        centerline = feather.get("centerline", [])
        if len(centerline) >= 2:
            last = float(len(centerline) - 1)
            feather["centerline"] = [v_add(point, delta_at(idx / last)) for idx, point in enumerate(centerline)]
        if "base" in feather:
            feather["base"] = v_add(feather["base"], delta_at(0.0))
        if "tip" in feather:
            feather["tip"] = v_add(feather["tip"], delta_at(1.0))
    return feathers


def _rotate_vector_axis(vector, axis, angle_radians):
    """Rotate vector around a normalized axis using Rodrigues' formula."""
    c = math.cos(angle_radians)
    sn = math.sin(angle_radians)
    return v_add(
        v_add(v_mul(vector, c), v_mul(v_cross(axis, vector), sn)),
        v_mul(axis, v_dot(axis, vector) * (1.0 - c)),
    )


def apply_feather_vane_fold(feathers, settings):
    """Fold each feather's two vane halves around the connected rachis/centerline.

    This is a cross-sectional fold, not a C/S bow along the feather length.
    The centerline remains fixed. At each station the upper rail rotates by +angle
    and the lower rail by -angle around the local centerline tangent, producing a
    shallow convex/concave vane. Positive values fold toward the stored feather-plane
    normal; negative values fold the opposite way. Per-feather values live in the
    Advanced-page modifier collection and default to zero.
    """
    global_angle_deg = float(getattr(settings, "global_vane_fold_angle_deg", 0.0))
    group_angles_deg = {
        str(item.group_id): float(getattr(item, "vane_fold_angle_deg", 0.0))
        for item in getattr(settings, "groups", [])
    }
    individual_angles_deg = {
        str(item.feather_id): float(getattr(item, "fold_angle_deg", 0.0))
        for item in getattr(settings, "mesh_overrides", [])
    }
    invert_front_back = bool(getattr(settings, "invert_front_back_fold_direction", False))
    for feather in feathers:
        feather_id = str(feather.get("id", ""))
        group_id = str(feather.get("group", ""))
        angle_deg = combine_scope_values(
            "sum", (global_angle_deg, group_angles_deg.get(group_id, 0.0), individual_angles_deg.get(feather_id, 0.0)),
            limit=90.0)
        # 'vt' marks the underside/back member of paired coverts in the current generator.
        # When enabled, reverse its fold relative to the upper/front member.
        if invert_front_back and bool(feather.get("vt", False)):
            angle_deg = -angle_deg
        angle = math.radians(angle_deg)
        if abs(angle) < 1.0e-9:
            continue
        pts = feather.get("pts", [])
        centerline = feather.get("centerline", [])
        if len(pts) < 4 or len(pts) % 2:
            continue
        station_count = len(pts) // 2
        if len(centerline) != station_count or station_count < 2:
            continue

        normal = v_norm(feather.get("nm", [0.0, 0.0, 1.0]))
        # Determine angle sign so positive always folds toward the stored local normal,
        # including on mirrored wings where the local orientation can reverse.
        orientation = 0.0
        for i in range(1, station_count - 1):
            prev_c = centerline[i - 1]
            next_c = centerline[i + 1]
            tangent = v_norm(v_sub(next_c, prev_c))
            upper_vec = v_sub(pts[i], centerline[i])
            upper_vec = v_sub(upper_vec, v_mul(tangent, v_dot(upper_vec, tangent)))
            if v_len(upper_vec) > 1.0e-8 and v_len(tangent) > 1.0e-8:
                orientation = v_dot(v_cross(tangent, upper_vec), normal)
                if abs(orientation) > 1.0e-8:
                    break
        angle_sign = -1.0 if orientation < 0.0 else 1.0

        # pts = upper rail root-to-tip + lower rail tip-to-root.
        # Rotate each side around the corresponding centerline point and local tangent.
        for i in range(station_count):
            if i == 0:
                tangent_raw = v_sub(centerline[1], centerline[0])
            elif i == station_count - 1:
                tangent_raw = v_sub(centerline[-1], centerline[-2])
            else:
                tangent_raw = v_sub(centerline[i + 1], centerline[i - 1])
            if v_len(tangent_raw) < 1.0e-8:
                continue
            tangent = v_norm(tangent_raw)
            center = centerline[i]
            upper_index = i
            lower_index = len(pts) - 1 - i

            upper_vec = v_sub(pts[upper_index], center)
            upper_vec = v_sub(upper_vec, v_mul(tangent, v_dot(upper_vec, tangent)))
            lower_vec = v_sub(pts[lower_index], center)
            lower_vec = v_sub(lower_vec, v_mul(tangent, v_dot(lower_vec, tangent)))

            upper_rot = _rotate_vector_axis(upper_vec, tangent, angle * angle_sign)
            lower_rot = _rotate_vector_axis(lower_vec, tangent, -angle * angle_sign)
            pts[upper_index] = v_add(center, upper_rot)
            pts[lower_index] = v_add(center, lower_rot)
    return feathers


# -----------------------------------------------------------------------------
# Blender collection / mesh helpers
# -----------------------------------------------------------------------------

GROUP_COLORS = {
    "primaries": (0.65, .34, .075, 1), "secondaries": (.08, .36, .30, 1), "tertials": (.12, .43, .34, 1),
    "primaryCoverts": (.88, .62, .23, 1), "greaterCoverts": (.20, .55, .47, 1), "medianCoverts": (.38, .68, .59, 1),
    "lesserCoverts": (.54, .76, .68, 1), "axillaries": (.32, .49, .36, 1), "alula": (.75, .48, .12, 1),
}


def ensure_material(name, rgba):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = .48
    return mat


def ensure_collection(name, parent):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in [c.name for c in parent.children]:
        parent.children.link(coll)
    return coll


def _remove_object_and_data(obj):
    data = getattr(obj, "data", None)
    data_type = getattr(obj, "type", None)
    bpy.data.objects.remove(obj, do_unlink=True)
    # Slider callbacks rebuild generated geometry frequently. Remove now-orphaned data blocks
    # instead of leaving hundreds of unused meshes/curves/armatures in the .blend file.
    try:
        if data is not None and data.users == 0:
            if data_type == 'MESH' and data.name in bpy.data.meshes:
                bpy.data.meshes.remove(data)
            elif data_type == 'CURVE' and data.name in bpy.data.curves:
                bpy.data.curves.remove(data)
            elif data_type == 'ARMATURE' and data.name in bpy.data.armatures:
                bpy.data.armatures.remove(data)
    except Exception:
        pass


def clear_collection_objects(coll):
    for obj in list(coll.objects):
        _remove_object_and_data(obj)


def delete_object_if_exists(name):
    obj = bpy.data.objects.get(name)
    if obj:
        _remove_object_and_data(obj)


def _remove_legacy_guides():
    """Older versions drew reference curves in a guide collection; delete it when a scene still has one."""
    collection = bpy.data.collections.get(LEGACY_GUIDE_COLLECTION)
    if collection is not None:
        clear_collection_objects(collection)
        bpy.data.collections.remove(collection)


SCOPES = ("GLOBAL", "GROUP", "FEATHER")
SCOPE_LABELS = {"GLOBAL": "整体", "GROUP": "羽毛组", "FEATHER": "单根"}
# Per-feather parameters that exist at a single level only (flight feathers; collection "feathers").
FEATHER_ONLY_PROPS = ("base_length_mm", "base_width_mm", "root_offset_mm", "angle_offset_deg")


class ScopeParam:
    """A parameter settable at several levels.

    where maps level -> (collection, attribute); collection None means the scene settings themselves.
    rule "sum": levels add up (optionally limited to +-limit); rule "inherit": innermost value > 0 wins.
    """
    def __init__(self, key, label, rule, where, limit=None):
        self.key, self.label, self.rule, self.where, self.limit = key, label, rule, where, limit


SCOPE_PARAMS = (
    ScopeParam("skin_root", "根部向翼面微移（mm）", "sum",
               {"GLOBAL": (None, "skinward_offset_mm"), "GROUP": ("groups", "skinward_offset_mm"),
                "FEATHER": ("feathers", "skinward_offset_mm")}),
    ScopeParam("skin_tip", "羽尖向翼面微移（mm）", "sum",
               {"GLOBAL": (None, "tip_skinward_offset_mm"), "GROUP": ("groups", "tip_skinward_offset_mm"),
                "FEATHER": ("feathers", "tip_skinward_offset_mm")}),
    ScopeParam("fold", "中轴翻折（°）", "sum",
               {"GLOBAL": (None, "global_vane_fold_angle_deg"), "GROUP": ("groups", "vane_fold_angle_deg"),
                "FEATHER": ("mesh_overrides", "fold_angle_deg")}, limit=90.0),
    ScopeParam("segments", "纵向分段数", "inherit",
               {"GLOBAL": (None, "global_mesh_segments"), "GROUP": ("groups", "mesh_segments"),
                "FEATHER": ("mesh_overrides", "mesh_segments")}),
)


def combine_scope_values(rule, values, limit=None):
    """Merge (whole wing, group, single feather) values into the one the generator uses."""
    if rule == "sum":
        total = values[0]
        for value in values[1:]:
            total += value  # plain left-to-right addition (sum() uses compensated rounding)
        return clamp(total, -limit, limit) if limit else total
    for value in reversed(values[1:]):
        if value > 0:
            return max(1, min(64, int(value)))
    return max(1, min(64, int(values[0])))


def scope_owner(settings, collection, group_id="", feather_id=""):
    """The settings object, group item or feather item that stores a value (None when it does not exist)."""
    if collection is None:
        return settings
    if collection == "groups":
        return next((item for item in settings.groups if item.group_id == group_id), None)
    return next((item for item in getattr(settings, collection) if item.feather_id == feather_id), None)


def scope_values(settings, param, group_id, feather_id):
    """Stored value of a parameter at each level, None where that level has no storage."""
    values = []
    for scope in SCOPES:
        collection, attr = param.where[scope]
        owner = scope_owner(settings, collection, group_id, feather_id)
        values.append(None if owner is None else getattr(owner, attr))
    return values


def _mesh_override_key(feather_id):
    """Turn generated feather IDs into stable Blender enum identifiers."""
    safe = "".join(ch if (ch.isascii() and (ch.isalnum() or ch == "_")) else "_" for ch in str(feather_id))
    if not safe or not safe[0].isalpha():
        safe = "F_" + safe
    return ("M_" + safe)[:63]


_DYNAMIC_MESH_OVERRIDE_ENUM_CACHE = [("M_NONE", "尚未生成羽毛列表", "")]


def dynamic_mesh_override_items(self, context):
    global _DYNAMIC_MESH_OVERRIDE_ENUM_CACHE
    settings = getattr(getattr(context, "scene", None), "wing_model_settings", None) if context else None
    if settings is None or not hasattr(settings, "mesh_overrides") or len(settings.mesh_overrides) == 0:
        _DYNAMIC_MESH_OVERRIDE_ENUM_CACHE = [("M_NONE", "尚未生成羽毛列表", "")]
    else:
        _DYNAMIC_MESH_OVERRIDE_ENUM_CACHE = [(item.key, item.label, item.feather_id) for item in settings.mesh_overrides]
    return _DYNAMIC_MESH_OVERRIDE_ENUM_CACHE


def ensure_mesh_override_settings(settings, by_group, reset=False):
    """Create a persistent mesh-density override entry for every generated feather ID."""
    expected = []
    seen = set()
    for group_id, _label, _short, _kind in GROUP_DEFS:
        for feather in by_group.get(group_id, []):
            fid = str(feather.get("id", ""))
            if fid and fid not in seen:
                expected.append((fid, group_id))
                seen.add(fid)
    current_ids = [item.feather_id for item in settings.mesh_overrides]
    expected_ids = [fid for fid, _gid in expected]
    if current_ids == expected_ids and not reset:
        return
    old = {item.feather_id: {
        "mesh_segments": int(item.mesh_segments),
        "fold_angle_deg": float(getattr(item, "fold_angle_deg", 0.0)),
    } for item in settings.mesh_overrides}
    active_id = next((item.feather_id for item in settings.mesh_overrides
                      if item.key == getattr(settings, "active_mesh_override", "")), "")
    with _suppressed_updates():
        while len(settings.mesh_overrides):
            settings.mesh_overrides.remove(len(settings.mesh_overrides) - 1)
        for fid, group_id in expected:
            item = settings.mesh_overrides.add()
            item.key = _mesh_override_key(fid)
            item.feather_id = fid
            item.group_id = group_id
            item.label = f"{GROUP_LABELS.get(group_id, group_id)} · {fid}"
            previous = old.get(fid, {}) if not reset else {}
            item.mesh_segments = 0 if reset else int(previous.get("mesh_segments", 0))
            item.fold_angle_deg = 0.0 if reset else float(previous.get("fold_angle_deg", 0.0))
        valid = {item.key for item in settings.mesh_overrides}
        desired_key = _mesh_override_key(active_id) if active_id else ""
        if desired_key not in valid and settings.mesh_overrides:
            desired_key = settings.mesh_overrides[0].key
        if desired_key in valid:
            settings.active_mesh_override = desired_key


def apply_mesh_station_settings(by_group, settings):
    """Resolve segments: single feather override > group override > global setting.

    The public settings are longitudinal segment counts. The mesh builder receives
    station counts (segments + 1). A value of 1 creates a connected root-to-tip centerline
    with no internal axial cuts; the original outer contour samples are always retained.
    """
    group_segments = {item.group_id: int(getattr(item, "mesh_segments", 0)) for item in settings.groups}
    feather_segments = {item.feather_id: int(getattr(item, "mesh_segments", 0)) for item in settings.mesh_overrides}
    global_segments = max(1, min(64, int(getattr(settings, "global_mesh_segments", 1))))
    for group_id, feathers in by_group.items():
        group_value = group_segments.get(group_id, 0)
        for feather in feathers:
            own_value = feather_segments.get(str(feather.get("id", "")), 0)
            resolved_segments = combine_scope_values("inherit", (global_segments, group_value, own_value))
            feather["mesh_stations"] = resolved_segments + 1


def _mesh_topology_signature(feathers):
    """Signature includes ngon topology version, contour reduction masks and axial cuts."""
    signature = []
    for feather in feathers:
        rows = feather_surface_rows(feather)
        if rows is None:
            continue
        upper, center, lower = rows
        points = feather.get("pts", [])
        native_stations = len(points) // 2
        target_stations = int(feather.get("mesh_stations", 0) or 0)
        cut_count = target_stations if target_stations >= 2 else native_stations
        upper_keep = tuple(_collinear_keep_indices(upper))
        lower_keep = tuple(_collinear_keep_indices(lower))
        signature.append((str(feather.get("id", "")), native_stations, cut_count, upper_keep, lower_keep))
    # Version prefix forces existing v1.4.1 fan-triangulated meshes to rebuild once.
    return "centerline_ngon_v1_4_2:" + json.dumps(signature, ensure_ascii=False, separators=(",", ":"))


def _sample_polyline_parameter(points, t):
    """Sample a rail at normalized index parameter t without simplifying its source polyline."""
    if not points:
        return [0.0, 0.0, 0.0]
    if len(points) == 1 or t <= 0.0:
        return list(points[0])
    if t >= 1.0:
        return list(points[-1])
    x = max(0.0, min(1.0, float(t))) * (len(points) - 1)
    lo = int(math.floor(x))
    hi = min(len(points) - 1, lo + 1)
    f = x - lo
    if abs(f) < 1e-10:
        return list(points[lo])
    return [lerp(points[lo][axis], points[hi][axis], f) for axis in range(3)]


def _collinear_keep_indices(points, tolerance=1.0e-6):
    """Return a stable-in-order subset of contour station indices, removing redundant collinear points.

    The tolerance is expressed in the generator's millimetre-space coordinates. The endpoints
    are always retained. Only a point on the straight segment between its neighbors is removed,
    so curved/tapered silhouette sections keep their samples. The same helper runs in mesh build,
    vertex updates and topology-signature calculation to keep vertex order deterministic.
    """
    count = len(points)
    if count <= 2:
        return list(range(count))
    eps2 = float(tolerance) * float(tolerance)
    kept = [0]
    for index in range(1, count):
        kept.append(index)
        while len(kept) >= 3:
            ia, ib, ic = kept[-3], kept[-2], kept[-1]
            a, b, c = points[ia], points[ib], points[ic]
            ac = [c[k] - a[k] for k in range(3)]
            ab = [b[k] - a[k] for k in range(3)]
            denom = sum(value * value for value in ac)
            if denom <= eps2:
                # Degenerate repeated segments: keep the later endpoint, drop the middle point.
                kept.pop(-2)
                continue
            t = sum(ab[k] * ac[k] for k in range(3)) / denom
            if t < -1.0e-9 or t > 1.0 + 1.0e-9:
                break
            distance_sq = sum(value * value for value in ab) - (sum(ab[k] * ac[k] for k in range(3)) ** 2) / denom
            if distance_sq <= eps2:
                kept.pop(-2)
            else:
                break
    return kept


def feather_surface_rows(feather):
    """Return the original upper/lower contour rails plus centerline, without resampling them.

    The v1.3.0 implementation resampled the contour rails to the low axial-segment count.
    That changed the outer silhouette. In this implementation contour stations are always
    retained; axial cross-section cuts are handled separately by build_feather_side_data().
    """
    points = [list(p) for p in feather.get("pts", [])]
    if len(points) < 4 or len(points) % 2:
        return None
    stations = len(points) // 2
    if stations < 2:
        return None
    upper = [list(p) for p in points[:stations]]
    lower = [list(p) for p in reversed(points[stations:])]
    if len(upper) != len(lower):
        return None
    explicit_centerline = feather.get("centerline")
    if isinstance(explicit_centerline, (list, tuple)) and len(explicit_centerline) == stations:
        center = [list(p) for p in explicit_centerline]
    else:
        center = [[(a[axis] + b[axis]) * 0.5 for axis in range(3)] for a, b in zip(upper, lower)]
    # Preserve the original root/tip convention and exact bind-axis endpoints.
    root = list(center[0])
    tip = list(center[-1])
    upper[0] = lower[0] = center[0] = root
    upper[-1] = lower[-1] = center[-1] = tip
    return upper, center, lower


def build_feather_side_data(feather, mirrored=False, include_faces=True):
    """Create two contour rails split by a connected centerline.

    Every axial band is represented by one upper and one lower n-gon. The centerline edge is
    shared by those two faces. This deliberately avoids fan-triangulating each band's perimeter
    from its root vertex, which previously created many spoke-like edges. Exact/near-exactly
    collinear contour samples are removed, while silhouette-changing samples remain.
    """
    rows = feather_surface_rows(feather)
    if rows is None:
        return [], [], [], [], []
    upper, center, lower = rows
    native_count = len(center)
    target_stations = int(feather.get("mesh_stations", 0) or 0)
    cut_count = target_stations if target_stations >= 2 else native_count
    cut_count = max(2, cut_count)
    cut_ts = [round(i / float(cut_count - 1), 12) for i in range(cut_count)]
    cut_keys = set(cut_ts)
    upper_native_ts = {round(i / float(native_count - 1), 12) for i in _collinear_keep_indices(upper)}
    lower_native_ts = {round(i / float(native_count - 1), 12) for i in _collinear_keep_indices(lower)}
    upper_ts = sorted(upper_native_ts | cut_keys)
    lower_ts = sorted(lower_native_ts | cut_keys)
    all_ts = sorted(set(upper_ts) | set(lower_ts) | cut_keys)

    verts = []
    grid_rows = []
    station_values = []
    mirror_values = []

    def add_vertex(point, row_id, t):
        y = -point[1] if mirrored else point[1]
        verts.append((point[0] * MM_TO_M, y * MM_TO_M, point[2] * MM_TO_M))
        grid_rows.append(int(row_id))
        station_values.append(float(t))
        mirror_values.append(1 if mirrored else 0)
        return len(verts) - 1

    upper_ids = {}
    lower_ids = {}
    center_ids = {}
    root_key, tip_key = cut_ts[0], cut_ts[-1]
    root_id = add_vertex(list(center[0]), 1, 0.0)
    upper_ids[root_key] = lower_ids[root_key] = center_ids[root_key] = root_id

    for t in all_ts[1:-1]:
        key = round(t, 12)
        if key in upper_ts:
            upper_ids[key] = add_vertex(_sample_polyline_parameter(upper, t), 0, t)
        if key in lower_ts:
            lower_ids[key] = add_vertex(_sample_polyline_parameter(lower, t), 2, t)
        if key in cut_keys:
            center_ids[key] = add_vertex(_sample_polyline_parameter(center, t), 1, t)

    tip_id = add_vertex(list(center[-1]), 1, 1.0)
    upper_ids[tip_key] = lower_ids[tip_key] = center_ids[tip_key] = tip_id

    faces = []
    if include_faces:
        for band_index in range(cut_count - 1):
            t0, t1 = cut_ts[band_index], cut_ts[band_index + 1]
            c0, c1 = center_ids[t0], center_ids[t1]
            upper_rail_ts = [t for t in upper_ts if t0 - 1e-12 <= t <= t1 + 1e-12]
            lower_rail_ts = [t for t in lower_ts if t0 - 1e-12 <= t <= t1 + 1e-12]
            upper_polygon = [c0] + [upper_ids[round(t, 12)] for t in upper_rail_ts] + [c1]
            lower_polygon = [c0, c1] + [lower_ids[round(t, 12)] for t in reversed(lower_rail_ts)]
            for polygon in (upper_polygon, lower_polygon):
                compact = []
                for index in polygon:
                    if not compact or compact[-1] != index:
                        compact.append(index)
                if len(compact) > 1 and compact[0] == compact[-1]:
                    compact.pop()
                # N-gons keep the contour chain and connected centerline as the actual mesh edges;
                # Blender handles render-time tessellation without storing root-fan diagonals.
                if len(set(compact)) >= 3:
                    face = tuple(compact)
                    faces.append(tuple(reversed(face)) if mirrored else face)
    return verts, faces, grid_rows, station_values, mirror_values


def build_feather_vertex_positions(feathers):
    """Build only coordinates, matching build_feather_grid_mesh_data's exact vertex order."""
    verts = []
    for feather in feathers:
        for mirrored in (False, True):
            side_verts, _faces, _rows, _stations, _mirrors = build_feather_side_data(
                feather, mirrored=mirrored, include_faces=False)
            verts.extend(side_verts)
    return verts

def _write_wing_mesh_attributes(mesh, point_attributes):
    """Replace topology metadata after a geometry refresh (Blender 5.2 API)."""
    for name, (data_type, values) in point_attributes.items():
        old = mesh.attributes.get(name)
        if old is not None:
            mesh.attributes.remove(old)
        attr = mesh.attributes.new(name=name, type=data_type, domain='POINT')
        for index, value in enumerate(values):
            attr.data[index].value = value


def build_feather_grid_mesh_data(feathers):
    """Build feather surfaces with preserved contour rails and sparse centerline cuts."""
    verts, faces, mat_indices = [], [], []
    feather_index_values, grid_row_values = [], []
    station_values, mirror_values = [], []
    id_map = []

    for feather_index, feather in enumerate(feathers):
        rows = feather_surface_rows(feather)
        if rows is None:
            continue
        feather_id = str(feather.get("id", f"feather_{feather_index + 1}"))
        id_map.append(feather_id)
        mesh_feather_index = len(id_map) - 1
        material_index = 1 if feather.get("vt", False) else 0

        for mirrored in (False, True):
            side_verts, side_faces, side_rows, side_stations, side_mirrors = build_feather_side_data(
                feather, mirrored=mirrored, include_faces=True)
            offset = len(verts)
            verts.extend(side_verts)
            faces.extend(tuple(index + offset for index in face) for face in side_faces)
            mat_indices.extend([material_index] * len(side_faces))
            feather_index_values.extend([mesh_feather_index] * len(side_verts))
            grid_row_values.extend(side_rows)
            station_values.extend(side_stations)
            mirror_values.extend(side_mirrors)

    attributes = {
        "wing_feather_index": ("INT", feather_index_values),
        "wing_grid_row": ("INT", grid_row_values),
        "wing_station": ("FLOAT", station_values),
        "wing_mirror_side": ("INT", mirror_values),
    }
    return verts, faces, mat_indices, attributes, id_map

def _apply_feather_mesh_data(mesh, feathers):
    verts, faces, mat_indices, attributes, id_map = build_feather_grid_mesh_data(feathers)
    mesh.clear_geometry()
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    _write_wing_mesh_attributes(mesh, attributes)
    for poly, index in zip(mesh.polygons, mat_indices):
        poly.material_index = index
        # Triangulated axial bands preserve the native outer contour; smooth shading
        # keeps the deliberately sparse centerline sections visually continuous.
        poly.use_smooth = True
    return id_map


def make_group_mesh(group_id, feathers, collection):
    name = f"WINGGEN_Feathers_{group_id}"
    delete_object_if_exists(name)
    mesh = bpy.data.meshes.new(name + "Mesh")
    id_map = _apply_feather_mesh_data(mesh, feathers)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj["wing_model_generated"] = True
    obj["feather_group_id"] = group_id
    obj["wing_feather_topology"] = "centerline_shared_ngon_bands_v1_5_0_uv_processing"
    obj["wing_feather_ids_json"] = json.dumps(id_map, ensure_ascii=False)
    obj["wing_mesh_topology_signature"] = _mesh_topology_signature(feathers)
    top = ensure_material("WING_MAT_"+group_id+"_Upper", GROUP_COLORS[group_id])
    c = GROUP_COLORS[group_id]
    under = ensure_material("WING_MAT_"+group_id+"_Under", (min(1,c[0]*1.14+.04), min(1,c[1]*1.14+.04), min(1,c[2]*1.14+.04), 1))
    mesh.materials.append(top); mesh.materials.append(under)
    solid = obj.modifiers.new("WING_FeatherThickness", 'SOLIDIFY')
    solid.thickness = 0.00025
    solid.offset = 0.0
    return obj


def update_group_mesh(obj, group_id, feathers):
    """Update vertex positions in-place when topology is unchanged; rebuild only on mismatch."""
    if obj is None or obj.type != 'MESH':
        return False
    mesh = obj.data
    signature = _mesh_topology_signature(feathers)
    if obj.get("wing_mesh_topology_signature", "") == signature:
        positions = build_feather_vertex_positions(feathers)
        if len(mesh.vertices) == len(positions):
            flat = [component for point in positions for component in point]
            mesh.vertices.foreach_set("co", flat)
            mesh.update()
            return False
    id_map = _apply_feather_mesh_data(mesh, feathers)
    obj["wing_feather_topology"] = "centerline_shared_ngon_bands_v1_5_0_uv_processing"
    obj["wing_feather_ids_json"] = json.dumps(id_map, ensure_ascii=False)
    obj["wing_mesh_topology_signature"] = signature
    return True


def _mesh_attr_values(mesh, name, default=0):
    """Read a point-domain mesh attribute into a plain list."""
    attr = mesh.attributes.get(name)
    if attr is None:
        return [default] * len(mesh.vertices)
    try:
        return [item.value for item in attr.data]
    except Exception:
        return [default] * len(mesh.vertices)


def _uv_lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def _uv_vec_length(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _uv_sample_center(samples, station):
    """Interpolate centerline samples in normalized station space."""
    if not samples:
        return (0.0, 0.0, 0.0)
    if station <= samples[0][0]:
        return samples[0][1]
    if station >= samples[-1][0]:
        return samples[-1][1]
    for i in range(len(samples) - 1):
        t0, p0 = samples[i]
        t1, p1 = samples[i + 1]
        if t0 <= station <= t1:
            f = 0.0 if abs(t1 - t0) < 1e-12 else (station - t0) / (t1 - t0)
            return _uv_lerp3(p0, p1, f)
    return samples[-1][1]


def _collect_uv_islands(scene):
    """Collect each feather on each mirrored wing as a separate possible UV island."""
    keys = []
    objects = []
    for group_id, *_ in GROUP_DEFS:
        obj = bpy.data.objects.get(f"WINGGEN_Feathers_{group_id}")
        if not obj or obj.type != 'MESH':
            continue
        mesh = obj.data
        feather_values = _mesh_attr_values(mesh, "wing_feather_index", -1)
        mirror_values = _mesh_attr_values(mesh, "wing_mirror_side", 0)
        local = sorted({(int(fi), int(mir)) for fi, mir in zip(feather_values, mirror_values) if int(fi) >= 0})
        for feather_index, mirror_side in local:
            keys.append((obj.name, feather_index, mirror_side))
        objects.append(obj)
    # The order remains stable across updates as long as generated feather IDs/order do not change.
    return objects, {key: i for i, key in enumerate(keys)}, len(keys)


def apply_uv_to_mesh(mesh, object_name, shape_mode='PROPORTION', layout_mode='PACKED',
                     island_indices=None, total_islands=0):
    """Create one UV island per feather-side or overlap all islands, using mesh point attributes.

    PROPORTION maps lateral distance against feather length to preserve width/length ratio.
    RECTANGLE stretches each feather to its tile's full rectangular UV region.
    OVERLAP shares a single UV region for reusable textures; PACKED assigns every feather-side
    a non-overlapping tile in one shared atlas across all feather-group objects.
    """
    if mesh is None or len(mesh.vertices) == 0 or len(mesh.polygons) == 0:
        if mesh is not None and mesh.uv_layers.get("WingUV") is None:
            try:
                mesh.uv_layers.new(name="WingUV")
            except Exception:
                pass
        return

    feather_values = _mesh_attr_values(mesh, "wing_feather_index", -1)
    row_values = _mesh_attr_values(mesh, "wing_grid_row", 1)
    station_values = _mesh_attr_values(mesh, "wing_station", 0.0)
    mirror_values = _mesh_attr_values(mesh, "wing_mirror_side", 0)
    coords = [(v.co.x, v.co.y, v.co.z) for v in mesh.vertices]

    island_vertices = {}
    center_samples = {}
    for i, (fi, row_id, station, mir) in enumerate(zip(feather_values, row_values, station_values, mirror_values)):
        if int(fi) < 0:
            continue
        key = (object_name, int(fi), int(mir))
        island_vertices.setdefault(key, []).append(i)
        if int(row_id) == 1:
            center_samples.setdefault(key, []).append((float(station), coords[i]))

    # Determine each feather's length and cross-axis extent. The current mesh stores centerline
    # vertices at axial cuts; with one segment this is exactly the root-tip line.
    island_metrics = {}
    lateral_values = [0.0] * len(mesh.vertices)
    side_signs = [0.0] * len(mesh.vertices)
    for key, vertex_indices in island_vertices.items():
        samples = sorted(center_samples.get(key, []), key=lambda item: item[0])
        # Drop duplicate center stations while preserving deterministic order.
        unique_samples = []
        for sample in samples:
            if not unique_samples or abs(sample[0] - unique_samples[-1][0]) > 1e-8:
                unique_samples.append(sample)
            else:
                unique_samples[-1] = sample
        samples = unique_samples
        if len(samples) >= 2:
            length = sum(_uv_vec_length(samples[i-1][1], samples[i][1]) for i in range(1, len(samples)))
        else:
            length = 1.0
        length = max(length, 1e-9)
        max_lateral = 0.0
        for vi in vertex_indices:
            row_id = int(row_values[vi])
            if row_id == 1:
                continue
            center = _uv_sample_center(samples, float(station_values[vi]))
            lateral = _uv_vec_length(coords[vi], center)
            lateral_values[vi] = lateral
            side_signs[vi] = 1.0 if row_id == 0 else (-1.0 if row_id == 2 else 0.0)
            max_lateral = max(max_lateral, lateral)
        island_metrics[key] = (length, max(max_lateral, 1e-9))

    island_count = max(1, int(total_islands or len(island_vertices) or 1))
    columns = max(1, int(math.ceil(math.sqrt(island_count))))
    rows = max(1, int(math.ceil(island_count / columns)))
    uv_by_vertex = [(0.5, 0.5)] * len(mesh.vertices)

    for key, vertex_indices in island_vertices.items():
        length, max_lateral = island_metrics.get(key, (1.0, 1.0))
        if layout_mode == 'PACKED':
            slot = int(island_indices.get(key, 0)) if island_indices else 0
            col = slot % columns
            row = slot // columns
            cell_w, cell_h = 1.0 / columns, 1.0 / rows
            x0, y0 = col * cell_w, row * cell_h
            margin = 0.08
            available_w, available_h = cell_w * (1.0 - 2.0 * margin), cell_h * (1.0 - 2.0 * margin)
        else:
            x0 = y0 = 0.0
            cell_w = cell_h = 1.0
            margin = 0.04
            available_w, available_h = 1.0 - 2.0 * margin, 1.0 - 2.0 * margin

        if shape_mode == 'RECTANGLE':
            scale_u = available_w
            scale_v = available_h
            u_start = x0 + (cell_w - scale_u) * 0.5
            v_center = y0 + cell_h * 0.5
        else:
            aspect = (2.0 * max_lateral) / length
            # Keep the feather's length/width ratio while fitting inside the available tile.
            scale_u = min(available_w, available_h / max(aspect, 1e-8))
            u_start = x0 + (cell_w - scale_u) * 0.5
            v_center = y0 + cell_h * 0.5
            scale_v = scale_u

        for vi in vertex_indices:
            u_local = max(0.0, min(1.0, float(station_values[vi])))
            sign = side_signs[vi]
            lateral = lateral_values[vi]
            u = u_start + u_local * scale_u
            if shape_mode == 'RECTANGLE':
                v = v_center + sign * (lateral / max_lateral) * (scale_v * 0.5)
            else:
                # Same UV scale in U and V, so the approximate physical aspect ratio is preserved.
                v = v_center + sign * (lateral / length) * scale_u
            uv_by_vertex[vi] = (u, v)

    uv_layer = mesh.uv_layers.get("WingUV") or mesh.uv_layers.new(name="WingUV")
    try:
        uv_layer.active_render = True
    except Exception:
        pass
    # Mesh polygons share centerline vertices, but their UV follows the same continuous axis.
    # Distinct upper/lower surfaces occupy opposite sides of the centerline in UV space.
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uv_by_vertex[loop.vertex_index]
    try:
        mesh.update()
    except Exception:
        pass


def apply_uv_settings_to_scene(scene):
    """Apply the selected UV modes to all generated feather objects as one atlas."""
    settings = getattr(scene, "wing_model_settings", None) if scene else None
    if settings is None:
        return 0
    objects, island_indices, total_islands = _collect_uv_islands(scene)
    for obj in objects:
        apply_uv_to_mesh(
            obj.data, obj.name,
            getattr(settings, "uv_shape_mode", 'PROPORTION'),
            getattr(settings, "uv_layout_mode", 'PACKED'),
            island_indices, total_islands,
        )
    return len(objects)


def uv_settings_update(self, context):
    """Refresh UV coordinates without rebuilding wing geometry or animation topology."""
    if _BUILDING:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene:
        try:
            apply_uv_settings_to_scene(scene)
        except Exception as exc:
            _console("[Wing Model] UV update failed:", repr(exc))


def build_state(settings):
    groups = {}
    for item in settings.groups:
        groups[item.group_id] = {
            "length_scale": item.length_scale, "width_scale": item.width_scale, "chord_scale": item.chord_scale,
            "sweep_offset": item.sweep_offset, "root_dist_offset": item.root_dist_offset,
            "chord_dist_offset": item.chord_dist_offset, "fan_offset": item.fan_offset,
            "roundness_offset": item.roundness_offset, "gap_offset": item.gap_offset,
            "tip_lift_offset": item.tip_lift_offset,
            "skinward_offset_mm": item.skinward_offset_mm, "tip_skinward_offset_mm": item.tip_skinward_offset_mm,
            "start_pct": item.start_pct, "end_pct": item.end_pct, "curve": item.curve,
            "length_reference_points": [
                {"position_pct": point.position_pct, "value_pct": point.value_pct}
                for point in item.length_reference_points
            ],
        }
    feathers = [{"id": f.feather_id, "length_mm": f.base_length_mm, "width_mm": f.base_width_mm,
                 "root_offset_mm": f.root_offset_mm, "angle_offset_deg": f.angle_offset_deg,
                 "skinward_offset_mm": f.skinward_offset_mm, "tip_skinward_offset_mm": f.tip_skinward_offset_mm} for f in settings.feathers]
    combos = []
    for c in settings.combos:
        targets = set(c.targets)
        if not targets:
            continue
        value = c.value_pct if c.param in {"lengthScale", "widthScale", "chordScale"} else c.offset_value
        combos.append({"name": c.name, "targets": targets, "param": c.param, "value": value})
    counts = {
        "secondaries": int(settings.count_secondaries), "primaries": int(settings.count_primaries),
        "tertials": int(settings.count_tertials), "medianCoverts": int(settings.count_median_coverts),
        "palmMedianCoverts": int(settings.count_palm_median_coverts), "lesserCoverts": int(settings.count_lesser_coverts),
        "axillaries": int(settings.count_axillaries), "alula": int(settings.count_alula),
    }
    form = {
        "span": settings.span_pct/100.0, "chord": settings.wing_depth_pct/100.0,
        "width": settings.global_width_pct/100.0, "sweep": settings.sweep_deg,
        "fan": settings.primary_fan_deg, "roundness": settings.roundness,
        "gap": settings.primary_gap_pct, "tip_lift": settings.tip_lift_mm,
        "chord_dist": settings.chord_dist_pct,
        "skinward_offset_mm": settings.skinward_offset_mm,
        "tip_skinward_offset_mm": settings.tip_skinward_offset_mm,
        "bone_h": settings.bone_h_pct/100.0,
        "bone_f": settings.bone_f_pct/100.0, "bone_hand": settings.bone_hand_pct/100.0,
        "hand_digits": settings.hand_digits_pct/100.0, "primary_attach": settings.primary_attach_pct,
    }
    motion = {
        "fold_pct": settings.fold_pct,
        "finger_offset_deg": settings.finger_offset_deg,
        "valve_angle_deg": settings.valve_angle_deg,
        "shingle_tilt_deg": settings.shingle_tilt_deg,
        "alula_open_deg": settings.alula_open_deg,
        "secondary_follow_yellow_reference": settings.secondary_follow_yellow_reference,
    }
    return {"form": form, "preset": settings.wing_preset, "global_length": settings.global_length_pct/100.0,
            "groups": groups, "feathers": feathers, "combos": combos, "counts": counts,
            "bone_base": [settings.humerus_base_mm, settings.forearm_base_mm, settings.handwing_base_mm, settings.shoulder_span_mm],
            "motion": motion}


def bone_points_for_state(state, angles=None):
    if angles is None:
        angles = joints_at_t0()
    k = fk(state, angles)
    pts = k["points"]
    hj = v_add(pts[2], v_mul(v_sub(pts[3], pts[2]), 1.0-state["form"]["hand_digits"]))
    return k, hj


def joint_values(settings):
    if settings and len(settings.joints) == len(JOINTS):
        return [(j.label, j.mean_deg, j.amplitude_deg, j.phase) for j in settings.joints]
    return JOINTS


def _motion_cycles_at_frame(scene, settings, frame):
    """Evaluate the existing generator's loop phase at an arbitrary timeline frame."""
    fps = max(1e-6, float(scene.render.fps) / max(1e-6, float(scene.render.fps_base)))
    rate = max(0.0, float(settings.flap_rate_hz))
    start = float(scene.frame_start)
    end = float(scene.frame_end)
    frame_count = max(1, int(round(end - start)) + 1)
    if rate <= 1.0e-8 or frame_count <= 1:
        return 0.0
    desired_cycles = rate * frame_count / fps
    loop_cycles = max(1, int(math.floor(desired_cycles + 0.5)))
    frame_position = (float(frame) - start) % frame_count
    progress = frame_position / frame_count
    return progress * loop_cycles


def motion_cycles(scene, settings):
    """Return the original generator's loop-aligned cycle coordinate at the current frame."""
    return _motion_cycles_at_frame(scene, settings, scene.frame_current)

def motion_angles(settings, cycle_time):
    """Port of the confirmed HTML motion logic; cycle_time is cycles elapsed on the timeline."""
    joints = joint_values(settings)
    phase = cycle_time % 1.0
    fold = clamp(float(settings.fold_pct) / 100.0, 0.0, 1.0)
    envelope = 0.0 if settings.flight_gait == 'glide' else 1.0
    motion_scale = float(settings.motion_scale_pct) / 100.0
    amplitude_scale = 1.0 - 0.85 * fold
    angles = [mean + amp * amplitude_scale * motion_scale * envelope * math.cos(TP * (cycle_time - ph))
              for _label, mean, amp, ph in joints]

    if settings.flight_state == 'takeoff':
        angles[1] += 8.0 * envelope; angles[3] -= 5.0 * envelope
    elif settings.flight_state == 'climb':
        angles[1] += 5.0 * envelope; angles[0] -= 4.0 * envelope
    elif settings.flight_state == 'accelerate':
        angles[0] -= 5.0 * envelope; angles[4] -= 3.0 * envelope
    elif settings.flight_state == 'decelerate':
        angles[1] -= 4.0 * envelope; angles[3] += 5.0 * envelope
    elif settings.flight_state == 'turn':
        angles[0] += float(settings.turn_strength_deg) * envelope * 0.25
    elif settings.flight_state == 'descent':
        angles[1] -= 5.0 * envelope
    elif settings.flight_state == 'landing':
        angles[1] += 8.0 * envelope; angles[3] += 12.0 * envelope
        fold = max(fold, 0.25)

    if settings.flight_gait == 'hover':
        down_fraction = clamp(float(settings.hover_down_pct) / 100.0, 0.42, 0.56)
        wave = (math.cos(math.pi * phase / max(down_fraction, 1.0e-4)) if phase < down_fraction
                else -math.cos(math.pi * (phase-down_fraction) / max(1.0-down_fraction, 1.0e-4)))
        angles[1] = joints[1][1] + (float(settings.hover_amp_deg) / 2.0) * motion_scale * wave
        # Confirmed hover fix: shoulder axial rotation flips the entire forearm/handwing frames;
        # wrist axial remains its local mean to avoid double-applying the same large flip.
        angles[2] = joints[2][1] + (float(settings.hover_amp_deg) * 0.22) * motion_scale * math.sin(TP * phase)
        angles[6] = joints[6][1]

    angles[3] = lerp(angles[3], 145.0, fold)
    angles[4] = lerp(angles[4], 90.0, fold)
    return angles


def update_motion_geometry(scene, force=False):
    """Re-evaluate kinematics and feather meshes at the current timeline frame."""
    global _UPDATING_MOTION
    if _UPDATING_MOTION or _BUILDING:
        return
    settings = getattr(scene, "wing_model_settings", None)
    if settings is None:
        return
    # Safety switch: when Python animation is off (e.g. after rigging) nothing is rebuilt per frame,
    # so it cannot fight with armature/IK-driven deformation.
    if (not force and not bool(getattr(settings, "python_animation_enabled", False))) or _rig_meshes_bound():
        return
    ensure_settings(scene)
    feather_collection = bpy.data.collections.get(FEATHER_COLLECTION)
    if feather_collection is None:
        build_model(scene)
        return
    expected = [bpy.data.objects.get(f"WINGGEN_Feathers_{gid}") for gid, *_ in GROUP_DEFS]
    if any(obj is None for obj in expected):
        build_model(scene)
        return

    _UPDATING_MOTION = True
    try:
        state = build_state(settings)
        cycles = motion_cycles(scene, settings)
        angles = motion_angles(settings, cycles)
        k = fk(state, angles)
        joint_phase = joint_values(settings)[1][3]
        feather_phase = (cycles - joint_phase) % 1.0
        feather_data = generate_feathers(state, k, feather_phase)
        apply_skinward_offsets(feather_data, state)
        by_group = {g[0]: [] for g in GROUP_DEFS}
        for feather in feather_data:
            if feather["group"] in by_group:
                by_group[feather["group"]].append(feather)
        ensure_mesh_override_settings(settings, by_group)
        apply_feather_vane_fold(feather_data, settings)
        apply_mesh_station_settings(by_group, settings)
        uv_needs_refresh = False
        for (group_id, *_), obj in zip(GROUP_DEFS, expected):
            # update_group_mesh returns True only if topology had to be rebuilt.
            uv_needs_refresh = update_group_mesh(obj, group_id, by_group[group_id]) or uv_needs_refresh
        if uv_needs_refresh:
            apply_uv_settings_to_scene(scene)
    except Exception as exc:
        _console("[Wing Model] Motion update failed:", repr(exc))
    finally:
        _UPDATING_MOTION = False


@persistent
def wing_model_frame_change_handler(scene, depsgraph=None):
    update_motion_geometry(scene)


def _cancel_blocked_playback():
    for window in bpy.context.window_manager.windows:
        if window.screen.is_animation_playing:
            try:
                with bpy.context.temp_override(window=window, screen=window.screen):
                    bpy.ops.screen.animation_cancel(restore_frame=False)
            except Exception as exc:
                _warn("cancelling blocked playback", exc)
    return None


@persistent
def wing_model_playback_guard(scene, depsgraph=None):
    """Python animation off and no rig: block timeline playback (including the space bar)."""
    settings = getattr(scene, "wing_model_settings", None)
    if settings is None or bool(settings.python_animation_enabled):
        return
    if bpy.data.objects.get(RIG_OBJECT) is not None:
        return
    bpy.app.timers.register(_cancel_blocked_playback, first_interval=0.0)


_HANDLER_LISTS = (("frame_change_post", "wing_model_frame_change_handler", wing_model_frame_change_handler),
                  ("animation_playback_pre", "wing_model_playback_guard", wing_model_playback_guard))


def remove_frame_handler():
    for list_name, name, _func in _HANDLER_LISTS:
        handlers = getattr(bpy.app.handlers, list_name)
        for handler in list(handlers):
            if getattr(handler, "__name__", "") == name:
                try: handlers.remove(handler)
                except ValueError: pass


def install_frame_handler():
    remove_frame_handler()
    for list_name, _name, func in _HANDLER_LISTS:
        getattr(bpy.app.handlers, list_name).append(func)


def motion_update(self, context):
    if _SUPPRESS_UPDATES or _BUILDING or _UPDATING_MOTION:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene:
        update_motion_geometry(scene)


def python_animation_update(self, context):
    """Turning Python animation back on re-evaluates the generator meshes at the current frame."""
    if _SUPPRESS_UPDATES or _BUILDING or not bool(self.python_animation_enabled):
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene:
        update_motion_geometry(scene)


def build_model(scene):
    global _BUILDING
    if _BUILDING:
        return
    settings = getattr(scene, "wing_model_settings", None)
    if settings is None:
        return
    if _rig_meshes_bound():
        _console("[Wing Model] Rebuild skipped: feather meshes are bound to the rig. Clear the rig binding first.")
        return
    ensure_settings(scene)
    _BUILDING = True
    try:
        root = bpy.data.collections.get(ROOT_COLLECTION)
        if root is None:
            root = bpy.data.collections.new(ROOT_COLLECTION)
            scene.collection.children.link(root)
        elif root.name not in [c.name for c in scene.collection.children]:
            scene.collection.children.link(root)
        feathers_coll = ensure_collection(FEATHER_COLLECTION, root)
        clear_collection_objects(feathers_coll)
        _remove_legacy_guides()
        state = build_state(settings)
        cycles = motion_cycles(scene, settings)
        angles = motion_angles(settings, cycles)
        k = fk(state, angles)
        joint_phase = joint_values(settings)[1][3]
        feather_data = generate_feathers(state, k, (cycles - joint_phase) % 1.0)
        apply_skinward_offsets(feather_data, state)
        by_group = {g[0]: [] for g in GROUP_DEFS}
        for feather in feather_data:
            if feather["group"] in by_group:
                by_group[feather["group"]].append(feather)
        ensure_mesh_override_settings(settings, by_group)
        apply_feather_vane_fold(feather_data, settings)
        apply_mesh_station_settings(by_group, settings)
        for group_id, _label, _short, _kind in GROUP_DEFS:
            make_group_mesh(group_id, by_group[group_id], feathers_coll)
        # Apply UVs after every group object exists so packed mode can create one shared atlas.
        apply_uv_settings_to_scene(scene)
        # Set a helpful default active object and scene units.
        scene.unit_settings.system = 'METRIC'
        scene.unit_settings.scale_length = 1.0
        scene.unit_settings.length_unit = 'MILLIMETERS'
    except Exception as exc:
        _console("[Wing Model] Rebuild failed:", repr(exc))
        raise
    finally:
        _BUILDING = False


# -----------------------------------------------------------------------------
# Properties and interactive Blender panel
# -----------------------------------------------------------------------------

def geometry_update(self, context):
    if _SUPPRESS_UPDATES or _BUILDING:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene:
        build_model(scene)


def feather_count_update(self, context):
    if _SUPPRESS_UPDATES or _BUILDING:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if not scene or not hasattr(scene, "wing_model_settings"):
        return
    ensure_feather_count_settings(scene.wing_model_settings)
    build_model(scene)


def rig_update(self, context):
    if _SUPPRESS_UPDATES or _BUILDING:
        return
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene:
        build_model(scene)


def preset_update(self, context):
    if _SUPPRESS_UPDATES or _BUILDING:
        return
    config = FORM_PRESETS.get(self.wing_preset, FORM_PRESETS["pigeon"])["values"]
    with _suppressed_updates():
        self.span_pct = config["span"]
        self.wing_depth_pct = config["chord"]
        self.global_width_pct = config["width"]
        self.sweep_deg = config["sweep"]
        self.primary_fan_deg = config["fan"]
        self.roundness = config["roundness"]
        self.primary_gap_pct = config["gap"]
        self.tip_lift_mm = config["tip_lift"]
        self.chord_dist_pct = config["chord_dist"]
        self.bone_h_pct = config["bone_h"]
        self.bone_f_pct = config["bone_f"]
        self.bone_hand_pct = config["bone_hand"]
        self.hand_digits_pct = config["hand_digits"]
        self.primary_attach_pct = config["primary_attach"]
    scene = context.scene if context and context.scene else bpy.context.scene
    if scene:
        build_model(scene)


def clear_length_reference_points(group):
    while len(group.length_reference_points):
        group.length_reference_points.remove(len(group.length_reference_points)-1)


def combo_update(self, context): geometry_update(self, context)


class WING_PG_LengthReferencePoint(bpy.types.PropertyGroup):
    position_pct: FloatProperty(name="组内位置 %", default=50.0, min=1.0, max=99.0, precision=1, update=geometry_update)
    value_pct: FloatProperty(name="长度倍率 %", default=100.0, min=25.0, max=200.0, precision=1, update=geometry_update)


class WING_PG_Group(bpy.types.PropertyGroup):
    group_id: StringProperty()
    label: StringProperty()
    length_scale: FloatProperty(name="长度比例", default=1.0, min=.25, max=2.5, subtype='FACTOR', update=geometry_update)
    width_scale: FloatProperty(name="宽度比例", default=1.0, min=.25, max=2.5, subtype='FACTOR', update=geometry_update)
    chord_scale: FloatProperty(name="纵深比例", default=1.0, min=.25, max=2.5, subtype='FACTOR', update=geometry_update)
    sweep_offset: FloatProperty(name="羽轴后掠偏移", default=0.0, min=-20, max=20, update=geometry_update)
    root_dist_offset: FloatProperty(name="根部分布偏移", default=0.0, min=-50, max=50, update=geometry_update)
    chord_dist_offset: FloatProperty(name="弦长分布偏移", default=0.0, min=-50, max=50, update=geometry_update)
    fan_offset: FloatProperty(name="扇开偏移", default=0.0, min=-12, max=12, update=geometry_update)
    roundness_offset: FloatProperty(name="圆钝度偏移", default=0.0, min=-50, max=50, update=geometry_update)
    gap_offset: FloatProperty(name="分指偏移", default=0.0, min=-100, max=100, update=geometry_update)
    tip_lift_offset: FloatProperty(name="翼尖离面偏移", default=0.0, min=-16, max=16, update=geometry_update)
    skinward_offset_mm: FloatProperty(name="向翼面／骨骼基底微移（mm）", default=0.0, min=-2.0, max=2.0, precision=2, update=geometry_update)
    tip_skinward_offset_mm: FloatProperty(name="羽尖向支撑面微移（mm）", default=0.0, min=-2.0, max=2.0, precision=2, update=geometry_update)
    start_pct: FloatProperty(name="首端倍率 %", default=100, min=25, max=200, update=geometry_update)
    end_pct: FloatProperty(name="末端倍率 %", default=100, min=25, max=200, update=geometry_update)
    curve: EnumProperty(name="分段过渡方式", items=[('LINEAR', '线性', ''),('SMOOTH', '平滑', '')], default='LINEAR', update=geometry_update)
    mesh_segments: IntProperty(name="纵向分段数", default=0, min=0, max=64, update=geometry_update)
    vane_fold_angle_deg: FloatProperty(name="羽组翻折（°）", default=0.0, min=-45.0, max=45.0, precision=1, update=geometry_update)
    length_reference_points: CollectionProperty(type=WING_PG_LengthReferencePoint)


class WING_PG_MeshOverride(bpy.types.PropertyGroup):
    key: StringProperty()
    feather_id: StringProperty()
    group_id: StringProperty()
    label: StringProperty()
    mesh_segments: IntProperty(name="纵向分段数", default=0, min=0, max=64, update=geometry_update)
    fold_angle_deg: FloatProperty(name="中轴两侧折角（°）", default=0.0, min=-45.0, max=45.0, precision=1, update=geometry_update)


class WING_PG_Feather(bpy.types.PropertyGroup):
    feather_id: StringProperty()
    group_id: StringProperty()
    base_length_mm: FloatProperty(name="基础长度（mm）", default=100, min=1, max=400, update=geometry_update)
    base_width_mm: FloatProperty(name="基础宽度（mm）", default=20, min=1, max=100, update=geometry_update)
    root_offset_mm: FloatProperty(name="根部偏移（mm）", default=0, min=-30, max=30, update=geometry_update)
    angle_offset_deg: FloatProperty(name="羽轴角度偏移（°）", default=0, min=-45, max=45, update=geometry_update)
    skinward_offset_mm: FloatProperty(name="向翼面／骨骼基底微移（mm）", default=0.0, min=-2.0, max=2.0, precision=2, update=geometry_update)
    tip_skinward_offset_mm: FloatProperty(name="羽尖向支撑面微移（mm）", default=0.0, min=-2.0, max=2.0, precision=2, update=geometry_update)


class WING_PG_Combo(bpy.types.PropertyGroup):
    name: StringProperty(name="名称", default="自定义组合")
    targets: EnumProperty(name="目标羽组", items=GROUP_ENUM_ITEMS, options={'ENUM_FLAG'}, default={'primaries','secondaries','tertials'}, update=combo_update)
    param: EnumProperty(name="修改内容", items=COMBO_PARAM_ITEMS, default='lengthScale', update=combo_update)
    value_pct: FloatProperty(name="倍率 %", default=110.0, min=25.0, max=250.0, update=combo_update)
    offset_value: FloatProperty(name="偏移量", default=0.0, min=-100.0, max=200.0, update=combo_update)


class WING_PG_Joint(bpy.types.PropertyGroup):
    joint_id: StringProperty()
    label: StringProperty()
    mean_deg: FloatProperty(name="均值 °", default=0.0, min=-120, max=150, update=motion_update)
    amplitude_deg: FloatProperty(name="幅值 °", default=0.0, min=0, max=90, update=motion_update)
    phase: FloatProperty(name="相位", default=0.0, min=0.0, max=1.0, update=motion_update, subtype='FACTOR')


class WING_PG_Settings(bpy.types.PropertyGroup):
    active_page: EnumProperty(name="页面", items=[
        ('SHAPE', '翅膀形状', ''),
        ('ANIMATION', '动画', ''),
        ('RIG_CONTROLS', '骨骼动画', ''),
        ('MODEL_PROCESSING', 'UV', ''),
        ('ADVANCED', '高级设置', ''),
    ], default='SHAPE')
    uv_shape_mode: EnumProperty(name="UV 形状", items=[
        ('PROPORTION', '保持比例', ''),
        ('RECTANGLE', '统一矩形', ''),
    ], default='PROPORTION', update=uv_settings_update)
    uv_layout_mode: EnumProperty(name="UV 布局", items=[
        ('PACKED', '独立打包', ''),
        ('OVERLAP', '重叠共享', ''),
    ], default='PACKED', update=uv_settings_update)
    global_mesh_segments: IntProperty(
        name="全局纵向分段数",
        default=1, min=1, max=64, update=geometry_update)
    mesh_settings_migrated: BoolProperty(name="网格细分默认值已初始化", default=False, options={'HIDDEN'})
    mesh_defaults_migrated_v131: BoolProperty(name="轮廓保留与细分默认值已迁移", default=False, options={'HIDDEN'})
    mesh_defaults_migrated_v141: BoolProperty(name="低细分默认值已迁移", default=False, options={'HIDDEN'})
    global_vane_fold_angle_deg: FloatProperty(name="整体羽毛翻折（°）", default=0.0, min=-45.0, max=45.0, precision=1, update=geometry_update)
    invert_front_back_fold_direction: BoolProperty(name="翻转正面/背面羽毛的翻折方向", default=False, update=geometry_update)
    skinward_offset_mm: FloatProperty(name="整体向翼面／骨骼基底微移（mm）", default=0.0, min=-2.0, max=2.0, precision=2, update=geometry_update)
    tip_skinward_offset_mm: FloatProperty(name="整体羽尖向支撑面微移（mm）", default=0.0, min=-2.0, max=2.0, precision=2, update=geometry_update)
    wing_preset: EnumProperty(name="翼型预设", items=[(k,v["label"],"") for k,v in FORM_PRESETS.items()], default='pigeon', update=preset_update)
    global_length_pct: FloatProperty(name="整体羽长比例 %", default=100, min=25, max=250, update=geometry_update)
    global_width_pct: FloatProperty(name="整体羽宽比例 %", default=100, min=25, max=250, update=geometry_update)
    span_pct: FloatProperty(name="骨骼链总长比例 %", default=100, min=65, max=140, update=rig_update)
    wing_depth_pct: FloatProperty(name="翼面纵深比例 %", default=100, min=60, max=150, update=geometry_update)
    bone_h_pct: FloatProperty(name="肱骨相对比例 %", default=100, min=70, max=135, update=rig_update)
    bone_f_pct: FloatProperty(name="前臂相对比例 %", default=100, min=70, max=140, update=rig_update)
    bone_hand_pct: FloatProperty(name="手翼相对比例 %", default=100, min=70, max=180, update=rig_update)
    hand_digits_pct: FloatProperty(name="指骨占手翼末端比例 %", default=28, min=15, max=45, update=rig_update)
    humerus_base_mm: FloatProperty(name="肱骨基础长度 mm", default=48.3, min=10, max=120, update=rig_update)
    forearm_base_mm: FloatProperty(name="前臂基础长度 mm", default=60, min=10, max=150, update=rig_update)
    handwing_base_mm: FloatProperty(name="手翼基础长度 mm", default=38, min=10, max=120, update=rig_update)
    shoulder_span_mm: FloatProperty(name="肩部参考半宽 mm", default=15, min=1, max=50, update=rig_update)
    sweep_deg: FloatProperty(name="羽轴后掠偏移 °", default=0, min=-12, max=20, update=geometry_update)
    primary_fan_deg: FloatProperty(name="初级飞羽扇开 °", default=0, min=0, max=12, update=geometry_update)
    roundness: FloatProperty(name="翼尖圆钝度", default=50, min=0, max=100, update=geometry_update)
    primary_gap_pct: FloatProperty(name="初级飞羽分指强度 %", default=0, min=0, max=100, update=geometry_update)
    tip_lift_mm: FloatProperty(name="翼尖离面高度 mm", default=0, min=0, max=16, update=geometry_update)
    chord_dist_pct: FloatProperty(name="飞羽弦长分布 %", default=50, min=0, max=100, update=geometry_update)
    primary_attach_pct: FloatProperty(name="初级飞羽附着分布 %", default=50, min=0, max=100, update=geometry_update)

    # Feather counts synchronized with the HTML model; linked coverts are derived from flight-feather counts.
    count_secondaries: IntProperty(name="次级飞羽数量", default=10, min=2, max=20, update=feather_count_update)
    count_primaries: IntProperty(name="初级飞羽数量", default=10, min=2, max=20, update=feather_count_update)
    count_tertials: IntProperty(name="三级飞羽数量", default=3, min=1, max=12, update=feather_count_update)
    count_median_coverts: IntProperty(name="中覆羽数量", default=10, min=2, max=24, update=geometry_update)
    count_palm_median_coverts: IntProperty(name="手翼中覆羽数量", default=6, min=1, max=16, update=geometry_update)
    count_lesser_coverts: IntProperty(name="小覆羽 / 缘覆羽每排数量", default=9, min=2, max=24, update=geometry_update)
    count_axillaries: IntProperty(name="腋羽数量", default=3, min=0, max=12, update=geometry_update)
    count_alula: IntProperty(name="小翼羽数量", default=3, min=0, max=12, update=geometry_update)
    active_group: EnumProperty(name="当前羽毛组", items=GROUP_ENUM_ITEMS, default='primaries', )
    adv_section: EnumProperty(name="高级设置分类", items=[
        ('DATA', '基础数据设置', ''),
        ('RIG', '骨骼设置', ''),
    ], default='DATA')
    adv_scope: EnumProperty(name="编辑级别", items=[
        ('GLOBAL', '整体', ''),
        ('GROUP', '羽毛组', ''),
        ('FEATHER', '单根', ''),
    ], default='GLOBAL')
    active_mesh_override: EnumProperty(
        name="单根羽毛", items=dynamic_mesh_override_items, default=0,
    )
    groups: CollectionProperty(type=WING_PG_Group)
    feathers: CollectionProperty(type=WING_PG_Feather)
    mesh_overrides: CollectionProperty(type=WING_PG_MeshOverride)
    combos: CollectionProperty(type=WING_PG_Combo)
    show_advanced: BoolProperty(name="显示高级参数", default=False)
    show_combos: BoolProperty(name="显示多组组合修改器", default=True)

    # Timeline-driven motion controls. The rate uses HTML semantics: cycles per second.
    motion_scale_pct: FloatProperty(name="拍翼幅度 %", default=100.0, min=0.0, max=150.0, update=motion_update)
    flap_rate_hz: FloatProperty(
        name="拍翼速率",
        default=0.4, min=0.0, max=2.0, precision=2, update=motion_update)
    flight_state: EnumProperty(name="飞行状态", items=[
        ('takeoff', '起飞', ''),('climb', '爬升', ''),('cruise', '平飞巡航', ''),('accelerate', '加速', ''),
        ('decelerate', '减速', ''),('turn', '转弯', ''),('descent', '下降', ''),('landing', '着陆制动', '')], default='cruise', update=motion_update)
    flight_gait: EnumProperty(name="飞行步态", items=[
        ('continuous', '持续拍翼', ''),('glide', '无拍翼滑翔', ''),('hover', '蜂鸟式悬停拍翼', '')], default='continuous', update=motion_update)
    turn_strength_deg: FloatProperty(name="转弯强度 °", default=18.0, min=0, max=40, update=motion_update)
    hover_amp_deg: FloatProperty(name="悬停拍动幅度 °", default=107.0, min=80, max=130, update=motion_update)
    hover_down_pct: FloatProperty(name="下拍周期占比 %", default=48.0, min=42, max=56, update=motion_update)
    fold_pct: FloatProperty(name="折叠度 %", default=0.0, min=0, max=100, update=motion_update)
    finger_offset_deg: FloatProperty(name="指角偏移 °", default=0.0, min=-30, max=30, update=motion_update)
    valve_angle_deg: FloatProperty(name="瓣膜开度 °", default=25.0, min=0, max=50, update=motion_update)
    shingle_tilt_deg: FloatProperty(name="覆瓦倾角 °", default=6.0, min=-20, max=30, update=motion_update)
    alula_open_deg: FloatProperty(name="小翼羽张开 °", default=15.0, min=0, max=40, update=motion_update)
    secondary_follow_yellow_reference: BoolProperty(
        name="绿色次级飞羽跟随黄色羽毛参考",
        default=False,
        update=motion_update,
    )
    python_animation_enabled: BoolProperty(
        name="Python 动画播放",
        default=False, update=python_animation_update)
    rig_auto_flat_pose: BoolProperty(
        name="一键绑骨时自动寻找平摊姿势",
        default=True)
    rig_fan_follow_pct: FloatProperty(
        name="羽毛跟随强度 %",
        default=70.0, min=0.0, max=100.0)
    rig_blend_radius_mm: FloatProperty(
        name="混合半径 mm",
        default=12.0, min=0.0, max=200.0)
    rig_blend_falloff: FloatProperty(
        name="权重衰减指数",
        default=1.5, min=0.1, max=6.0)
    rig_blend_neighbor_pct: FloatProperty(
        name="邻骨权重上限 %",
        default=100.0, min=0.0, max=100.0)
    rig_blend_max_targets: IntProperty(
        name="最多参考骨骼数",
        default=2, min=1, max=4)
    rig_spread_max_angle_deg: FloatProperty(
        name="扇形最大角度 °",
        default=20.0, min=0.0, max=90.0)
    rig_pose_sweep_deg: FloatProperty(name="前后摆最大角 °", default=30.0, min=0.0, max=90.0)
    rig_pose_flap_deg: FloatProperty(name="上下扇最大角 °", default=40.0, min=0.0, max=90.0)
    rig_pose_pitch_deg: FloatProperty(name="俯仰最大角 °", default=20.0, min=0.0, max=60.0)
    rig_pose_twist_deg: FloatProperty(name="扭转最大角 °", default=30.0, min=0.0, max=90.0)
    rig_wrist_flex_deg: FloatProperty(name="手腕上下最大角 °", default=35.0, min=0.0, max=90.0)
    rig_wrist_sweep_deg: FloatProperty(name="手腕前后最大角 °", default=25.0, min=0.0, max=90.0)
    rig_finger_curl_deg: FloatProperty(name="指节弯曲最大角 °", default=30.0, min=0.0, max=90.0)
    rig_finger_sweep_deg: FloatProperty(name="指节前后最大角 °", default=15.0, min=0.0, max=60.0)
    rig_thumb_open_deg: FloatProperty(name="拇指张开最大角 °", default=35.0, min=0.0, max=90.0)
    rig_thumb_flex_deg: FloatProperty(name="拇指上下最大角 °", default=30.0, min=0.0, max=90.0)
    rig_digit2_ratio: FloatProperty(name="指节 2 跟随比例", default=0.7, min=0.0, max=1.5)
    rig_fold_spread_end: FloatProperty(name="展开淡出终点", default=0.5, min=0.05, max=1.0)
    rig_fold_hand_keep_pct: FloatProperty(name="折叠时手部保留 %", default=0.0, min=0.0, max=100.0)
    rig_bend_max_deg: FloatProperty(name="弯折单区最大角 °", default=25.0, min=1.0, max=90.0)
    rig_bend_ramp_pct: FloatProperty(name="区域渐变比例 %", default=100.0, min=5.0, max=100.0)
    show_motion_advanced: BoolProperty(name="显示局部运动参数", default=False)
    show_joint_params: BoolProperty(name="显示关节驱动参数", default=False)
    show_cycle_params: BoolProperty(name="显示循环细节参数", default=False)
    joints: CollectionProperty(type=WING_PG_Joint)


class WING_OT_CreateModel(bpy.types.Operator):
    bl_idname = "wing_model.create_model"
    bl_label = "创建 / 重建翅膀模型"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        ensure_settings(context.scene)
        if _rig_meshes_bound():
            self.report({'WARNING'}, "Feather meshes are bound to the rig. Clear the rig binding before rebuilding.")
            return {'CANCELLED'}
        build_model(context.scene)
        focus_view_on_wing()
        self.report({'INFO'}, "Wing model generated or updated.")
        return {'FINISHED'}


class WING_OT_AddCombo(bpy.types.Operator):
    bl_idname = "wing_model.add_combo"
    bl_label = "添加多组组合修改器"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.wing_model_settings
        item = s.combos.add()
        item.name = f"组合修改器 {len(s.combos)}"
        item.targets = {'primaries','secondaries','tertials'}
        item.param = 'lengthScale'; item.value_pct = 110.0; item.offset_value = 0.0
        return {'FINISHED'}


class WING_OT_AddLengthReferencePoint(bpy.types.Operator):
    bl_idname = "wing_model.add_length_reference_point"
    bl_label = "添加长度参考点"
    bl_options = {'REGISTER', 'UNDO'}

    group_id: StringProperty()

    def execute(self, context):
        s = context.scene.wing_model_settings
        g = next((x for x in s.groups if x.group_id == self.group_id), None)
        if not g:
            return {'CANCELLED'}
        if len(g.length_reference_points) >= 12:
            self.report({'WARNING'}, "Each feather group supports up to 12 intermediate reference points.")
            return {'CANCELLED'}
        knots = [(0.0, g.start_pct)] + [(p.position_pct, p.value_pct) for p in g.length_reference_points] + [(100.0, g.end_pct)]
        knots.sort(key=lambda item: item[0])
        best = None
        for left, right in zip(knots, knots[1:]):
            gap = right[0] - left[0]
            if gap > 1.0 and (best is None or gap > best[0]):
                best = (gap, left, right)
        if best is None:
            self.report({'WARNING'}, "Reference points are too close to add another point.")
            return {'CANCELLED'}
        _gap, left, right = best
        pos = round((left[0] + right[0]) * .5, 1)
        setting = {
            "start_pct": g.start_pct, "end_pct": g.end_pct, "curve": g.curve,
            "length_reference_points": [{"position_pct": p.position_pct, "value_pct": p.value_pct} for p in g.length_reference_points],
        }
        val = round(length_distribution_value_pct(setting, pos/100.0), 1)
        point = g.length_reference_points.add()
        point.position_pct = pos
        point.value_pct = clamp(val, 25.0, 200.0)
        build_model(context.scene)
        return {'FINISHED'}


class WING_OT_RemoveLengthReferencePoint(bpy.types.Operator):
    bl_idname = "wing_model.remove_length_reference_point"
    bl_label = "删除长度参考点"
    bl_options = {'REGISTER', 'UNDO'}

    group_id: StringProperty()
    index: IntProperty(default=-1, min=-1)

    def execute(self, context):
        s = context.scene.wing_model_settings
        g = next((x for x in s.groups if x.group_id == self.group_id), None)
        if not g or not (0 <= self.index < len(g.length_reference_points)):
            return {'CANCELLED'}
        g.length_reference_points.remove(self.index)
        build_model(context.scene)
        return {'FINISHED'}


class WING_OT_ClearLengthReferencePoints(bpy.types.Operator):
    bl_idname = "wing_model.clear_length_reference_points"
    bl_label = "清除中间参考点"
    bl_options = {'REGISTER', 'UNDO'}

    group_id: StringProperty()

    def execute(self, context):
        s = context.scene.wing_model_settings
        g = next((x for x in s.groups if x.group_id == self.group_id), None)
        if not g:
            return {'CANCELLED'}
        clear_length_reference_points(g)
        build_model(context.scene)
        return {'FINISHED'}


class WING_OT_RemoveCombo(bpy.types.Operator):
    bl_idname = "wing_model.remove_combo"
    bl_label = "删除组合修改器"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()
    def execute(self, context):
        s = context.scene.wing_model_settings
        if 0 <= self.index < len(s.combos):
            s.combos.remove(self.index)
            build_model(context.scene)
        return {'FINISHED'}


class WING_OT_ResetGroup(bpy.types.Operator):
    bl_idname = "wing_model.reset_group"
    bl_label = "重置当前羽组"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.wing_model_settings
        g = next((x for x in s.groups if x.group_id == s.active_group), None)
        if not g: return {'CANCELLED'}
        with _suppressed_updates():
            for key, value in GROUP_DEFAULTS.items(): setattr(g,key,value)
            g.mesh_segments = 0
            g.skinward_offset_mm = 0.0; g.tip_skinward_offset_mm = 0.0
            for override in context.scene.wing_model_settings.mesh_overrides:
                if override.group_id == g.group_id:
                    override.mesh_segments = 0
            clear_length_reference_points(g)
        build_model(context.scene)
        return {'FINISHED'}


SETTINGS_DEFAULTS = {
    "wing_preset": 'pigeon', "global_length_pct": 100, "global_width_pct": 100, "span_pct": 100, "wing_depth_pct": 100,
    "global_mesh_segments": 1, "mesh_settings_migrated": True,
    "mesh_defaults_migrated_v131": True, "mesh_defaults_migrated_v141": True,
    "motion_scale_pct": 100, "flap_rate_hz": 0.4, "flight_state": 'cruise', "flight_gait": 'continuous',
    "turn_strength_deg": 18, "hover_amp_deg": 107, "hover_down_pct": 48, "fold_pct": 0,
    "finger_offset_deg": 0, "valve_angle_deg": 25, "shingle_tilt_deg": 6, "alula_open_deg": 15,
    "secondary_follow_yellow_reference": False, "python_animation_enabled": False,
    "humerus_base_mm": 48.3, "forearm_base_mm": 60, "handwing_base_mm": 38, "shoulder_span_mm": 15,
    "sweep_deg": 0, "primary_fan_deg": 0, "roundness": 50, "primary_gap_pct": 0, "tip_lift_mm": 0,
    "chord_dist_pct": 50, "primary_attach_pct": 50,
    "skinward_offset_mm": 0.0, "tip_skinward_offset_mm": 0.0,
    "global_vane_fold_angle_deg": 0.0, "invert_front_back_fold_direction": False,
}


class WING_OT_ResetAll(bpy.types.Operator):
    bl_idname = "wing_model.reset_all"
    bl_label = "恢复默认参数"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        s = context.scene.wing_model_settings
        with _suppressed_updates():
            for key, value in SETTINGS_DEFAULTS.items():
                setattr(s, key, value)
            for i, joint in enumerate(s.joints):
                if i < len(JOINTS):
                    _label, mean, amp, phase = JOINTS[i]
                    joint.mean_deg=mean; joint.amplitude_deg=amp; joint.phase=phase
            for g in s.groups:
                for key, value in GROUP_DEFAULTS.items(): setattr(g,key,value)
                g.mesh_segments = 0
                g.skinward_offset_mm = 0.0; g.tip_skinward_offset_mm = 0.0
                clear_length_reference_points(g)
            for override in s.mesh_overrides:
                override.mesh_segments = 0
                override.fold_angle_deg = 0.0
            for key, prop in COUNT_PROPS.items():
                setattr(s, prop, DEFAULT_FEATHER_COUNTS[key])
            ensure_feather_count_settings(s, reset=True)
            s.combos.clear()
        build_model(context.scene)
        return {'FINISHED'}


# (property, HTML form key, HTML->Blender scale, min, max)
IMPORT_FORM_FIELDS = (
    ("span_pct", "span", 100.0, 65.0, 140.0), ("wing_depth_pct", "chord", 100.0, 60.0, 150.0),
    ("global_width_pct", "width", 100.0, 60.0, 145.0), ("sweep_deg", "sweep", 1.0, -12.0, 20.0),
    ("primary_fan_deg", "fan", 1.0, 0.0, 12.0), ("roundness", "roundness", 1.0, 0.0, 100.0),
    ("primary_gap_pct", "gap", 1.0, 0.0, 100.0), ("tip_lift_mm", "tip_lift", 1.0, 0.0, 16.0),
    ("chord_dist_pct", "chord_dist", 1.0, 0.0, 100.0), ("bone_h_pct", "bone_h", 100.0, 70.0, 135.0),
    ("bone_f_pct", "bone_f", 100.0, 70.0, 140.0), ("bone_hand_pct", "bone_hand", 100.0, 70.0, 180.0),
    ("hand_digits_pct", "hand_digits", 100.0, 15.0, 45.0), ("primary_attach_pct", "primary_attach", 1.0, 0.0, 100.0),
)
# (property, key in "bone_base_mm", min, max)
IMPORT_BONE_FIELDS = (
    ("humerus_base_mm", "humerus", 10.0, 120.0), ("forearm_base_mm", "forearm", 10.0, 150.0),
    ("handwing_base_mm", "handwing", 10.0, 120.0), ("shoulder_span_mm", "shoulder_span", 1.0, 50.0),
)
# (property, key in "motion", min, max)
IMPORT_MOTION_FIELDS = (
    ("motion_scale_pct", "motion_scale_pct", 0.0, 150.0), ("flap_rate_hz", "playback_rate", 0.0, 2.0),
    ("turn_strength_deg", "turn_strength_deg", 0.0, 40.0), ("hover_amp_deg", "hover_amp_deg", 80.0, 130.0),
    ("hover_down_pct", "hover_down_pct", 42.0, 56.0), ("fold_pct", "fold_pct", 0.0, 100.0),
    ("finger_offset_deg", "finger_offset_deg", -30.0, 30.0), ("valve_angle_deg", "valve_angle_deg", 0.0, 50.0),
    ("shingle_tilt_deg", "shingle_tilt_deg", -20.0, 30.0), ("alula_open_deg", "alula_open_deg", 0.0, 40.0),
)
GROUP_IMPORT_KEYS = (
    "length_scale", "width_scale", "chord_scale", "sweep_offset", "root_dist_offset", "chord_dist_offset",
    "fan_offset", "roundness_offset", "gap_offset", "tip_lift_offset", "start_pct", "end_pct", "curve",
)


class WING_OT_ImportHTMLParameters(bpy.types.Operator, ImportHelper):
    bl_idname = "wing_model.import_html_parameters"
    bl_label = "从 HTML 导入参数 JSON"
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or payload.get("schema") != "bird-wing-model-parameters":
                self.report({'ERROR'}, "JSON format mismatch. Export the complete Blender parameter JSON from the HTML tool.")
                return {'CANCELLED'}
            if int(payload.get("version", 0)) != 1:
                self.report({'ERROR'}, f"Unsupported parameter file version: {payload.get('version')}")
                return {'CANCELLED'}

            scene = context.scene
            ensure_settings(scene)
            settings = scene.wing_model_settings
            form = payload.get("form", {})
            counts = payload.get("counts", {})
            groups = payload.get("groups", {})
            motion = payload.get("motion", {})
            bone = payload.get("bone_base_mm", {})
            feather_payload = payload.get("feathers", [])
            joint_payload = payload.get("joints", [])
            combo_payload = payload.get("combos", [])

            with _suppressed_updates():
                preset = payload.get("preset", "pigeon")
                if preset in FORM_PRESETS:
                    settings.wing_preset = preset
                settings.global_length_pct = clamp(float(payload.get("global_length_scale", 1.0))*100.0, 25.0, 250.0)

                # Morphology parameters. The imported form overrides preset defaults so custom edits survive.
                for prop, key, scale, lo, hi in IMPORT_FORM_FIELDS:
                    setattr(settings, prop, clamp(float(form.get(key, getattr(settings, prop) / scale)) * scale, lo, hi))
                for prop, key, lo, hi in IMPORT_BONE_FIELDS:
                    setattr(settings, prop, clamp(float(bone.get(key, getattr(settings, prop))), lo, hi))

                # Counts are applied first so per-feather controls can be resized and matched by persistent feather IDs.
                for key, prop_name in COUNT_PROPS.items():
                    if key in counts:
                        lo, hi = FEATHER_COUNT_LIMITS[key]
                        setattr(settings, prop_name, int(clamp(int(counts[key]), lo, hi)))
                ensure_feather_count_settings(settings)

                group_by_id = {g.group_id: g for g in settings.groups}
                for gid, values in groups.items():
                    item = group_by_id.get(gid)
                    if not item or not isinstance(values, dict):
                        continue
                    for src_key in GROUP_IMPORT_KEYS:
                        if src_key not in values:
                            continue
                        value = values[src_key]
                        if src_key == "curve":
                            value = str(value).upper()
                            if value not in {"LINEAR", "SMOOTH"}: value = "LINEAR"
                        else:
                            value = float(value)
                        setattr(item, src_key, value)
                    if "length_reference_points" in values and isinstance(values.get("length_reference_points"), list):
                        clear_length_reference_points(item)
                        sorted_points = sorted(
                            [p for p in values.get("length_reference_points", []) if isinstance(p, dict)],
                            key=lambda p: float(p.get("position_pct", 50.0))
                        )[:12]
                        used_positions = set()
                        for raw_point in sorted_points:
                            pos = round(clamp(float(raw_point.get("position_pct", 50.0)), 1.0, 99.0), 1)
                            if pos in used_positions:
                                continue
                            used_positions.add(pos)
                            point = item.length_reference_points.add()
                            point.position_pct = pos
                            point.value_pct = clamp(float(raw_point.get("value_pct", 100.0)), 25.0, 200.0)

                feather_by_id = {f.feather_id: f for f in settings.feathers}
                for item_data in feather_payload:
                    if not isinstance(item_data, dict):
                        continue
                    item = feather_by_id.get(item_data.get("id"))
                    if not item:
                        continue
                    for key, prop_name, lo, hi in (
                        ("base_length_mm", "base_length_mm", 1.0, 400.0),
                        ("base_width_mm", "base_width_mm", 1.0, 100.0),
                        ("root_offset_mm", "root_offset_mm", -30.0, 30.0),
                        ("angle_offset_deg", "angle_offset_deg", -45.0, 45.0),
                    ):
                        if key in item_data:
                            setattr(item, prop_name, clamp(float(item_data[key]), lo, hi))

                settings.combos.clear()
                valid_groups = set(GROUP_LABELS)
                valid_combo_params = {item[0] for item in COMBO_PARAM_ITEMS}
                for raw in combo_payload:
                    if not isinstance(raw, dict):
                        continue
                    targets = set(raw.get("targets", [])) & valid_groups
                    param = raw.get("param", "lengthScale")
                    if not targets or param not in valid_combo_params:
                        continue
                    combo = settings.combos.add()
                    combo.name = str(raw.get("name", f"组合修改器 {len(settings.combos)}"))
                    combo.targets = targets
                    combo.param = param
                    value = float(raw.get("value", 100.0 if param in {"lengthScale", "widthScale", "chordScale"} else 0.0))
                    if param in {"lengthScale", "widthScale", "chordScale"}:
                        combo.value_pct = clamp(value, 25.0, 250.0)
                    else:
                        combo.offset_value = clamp(value, -100.0, 200.0)

                # Motion and seven joint drivers.
                for prop, key, lo, hi in IMPORT_MOTION_FIELDS:
                    setattr(settings, prop, clamp(float(motion.get(key, getattr(settings, prop))), lo, hi))
                state_value = motion.get("flight_state", settings.flight_state)
                gait_value = motion.get("flight_gait", settings.flight_gait)
                valid_states = {"takeoff", "climb", "cruise", "accelerate", "decelerate", "turn", "descent", "landing"}
                valid_gaits = {"continuous", "glide", "hover"}
                if state_value in valid_states:
                    settings.flight_state = state_value
                if gait_value in valid_gaits:
                    settings.flight_gait = gait_value
                settings.secondary_follow_yellow_reference = bool(motion.get("secondary_follow_yellow_reference", settings.secondary_follow_yellow_reference))
                for i, data in enumerate(joint_payload):
                    if i >= len(settings.joints) or not isinstance(data, dict):
                        continue
                    joint = settings.joints[i]
                    joint.mean_deg = clamp(float(data.get("mean_deg", joint.mean_deg)), -120.0, 150.0)
                    joint.amplitude_deg = clamp(float(data.get("amplitude_deg", joint.amplitude_deg)), 0.0, 90.0)
                    joint.phase = clamp(float(data.get("phase", joint.phase)), 0.0, 1.0)

                active_group = payload.get("active_group")
                if active_group in GROUP_LABELS:
                    settings.active_group = active_group
                override_key = _mesh_override_key(payload.get("active_feather") or "")
                if any(item.key == override_key for item in settings.mesh_overrides):
                    settings.active_mesh_override = override_key

                if "fps" in motion:
                    scene.render.fps = int(clamp(int(motion["fps"]), 1, 120))
                    scene.render.fps_base = 1.0

            build_model(scene)
            self.report({'INFO'}, f"Imported HTML parameters: {len(settings.feathers)} primary feathers and {len(settings.combos)} combination modifiers.")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"Import failed: {exc}")
            _console("[Wing Model] HTML parameter import failed:", repr(exc))
            return {'CANCELLED'}


class WING_OT_ApplyUV(bpy.types.Operator):
    bl_idname = "wing_model.apply_uv"
    bl_label = "重新生成 / 应用 UV"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            count = apply_uv_settings_to_scene(context.scene)
        except Exception as exc:
            self.report({'ERROR'}, f"UV generation failed: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Updated UVs for {count} feather-group objects.")
        return {'FINISHED'}


class WING_OT_ResetModelPose(bpy.types.Operator):
    bl_idname = "wing_model.reset_model_pose"
    bl_label = "恢复模型默认位置"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        root = bpy.data.collections.get(ROOT_COLLECTION)
        if root is not None:
            stack = [root]
            visited = set()
            while stack:
                coll = stack.pop()
                if coll.name in visited:
                    continue
                visited.add(coll.name)
                stack.extend(list(coll.children))
                for obj in coll.objects:
                    if not obj.get("wing_model_generated", False):
                        continue
                    obj.location = (0.0, 0.0, 0.0)
                    obj.rotation_euler = (0.0, 0.0, 0.0)
                    obj.scale = (1.0, 1.0, 1.0)
        scene.frame_set(scene.frame_start)
        update_motion_geometry(scene, force=True)
        self.report({'INFO'}, "Generated model objects reset to identity transforms.")
        return {'FINISHED'}


def _selected_scope_ids(s):
    """(group id, feather id) addressed by the scope editor's current selection."""
    if s.adv_scope == 'FEATHER':
        item = next((x for x in s.mesh_overrides if x.key == s.active_mesh_override), None)
        return (item.group_id, item.feather_id) if item else ("", "")
    return (s.active_group if s.adv_scope == 'GROUP' else ""), ""


class WING_OT_ScopeCopyToGroup(bpy.types.Operator):
    bl_idname = "wing_model.scope_copy_to_group"
    bl_label = "应用到本组全部羽毛"
    bl_options = {'REGISTER', 'UNDO'}
    param: StringProperty()

    def execute(self, context):
        s = context.scene.wing_model_settings
        param = next((p for p in SCOPE_PARAMS if p.key == self.param), None)
        group_id, feather_id = _selected_scope_ids(s)
        collection, attr = param.where["FEATHER"] if param else (None, "")
        source = scope_owner(s, collection, group_id, feather_id) if collection else None
        if source is None:
            self.report({'WARNING'}, "当前羽毛没有这个单根参数")
            return {'CANCELLED'}
        value = getattr(source, attr)
        with _suppressed_updates():
            for item in getattr(s, collection):
                if item.group_id == source.group_id:
                    setattr(item, attr, value)
        geometry_update(s, context)
        return {'FINISHED'}


def _draw_scope_editor(layout, s):
    """One editor for whole-wing / feather-group / single-feather values of the same parameters."""
    box = layout.box()
    box.label(text="羽毛参数 · 整体 / 羽毛组 / 单根", icon='MODIFIER')
    box.row(align=True).prop(s, "adv_scope", expand=True)
    scope = s.adv_scope
    if scope == 'GROUP':
        box.prop(s, "active_group", text="羽毛组")
    elif scope == 'FEATHER':
        box.prop(s, "active_mesh_override", text="羽毛")
    group_id, feather_id = _selected_scope_ids(s)
    if scope == 'FEATHER' and not feather_id:
        box.label(text="请先创建或重建翅膀模型。", icon='INFO')
        return
    if scope == 'FEATHER':
        flight = scope_owner(s, "feathers", group_id, feather_id)
        if flight is not None:
            col = box.column(align=True)
            for attr in FEATHER_ONLY_PROPS:
                col.prop(flight, attr, slider=True)
    for param in SCOPE_PARAMS:
        collection, attr = param.where[scope]
        owner = scope_owner(s, collection, group_id, feather_id)
        if owner is None:
            continue
        column = box.column(align=True)
        column.prop(owner, attr, text=param.label, slider=(param.rule == "sum"))
        if scope == 'FEATHER':
            copy = column.operator("wing_model.scope_copy_to_group", text="应用到本组全部羽毛", icon='DUPLICATE')
            copy.param = param.key


def _draw_lr_rows(box, rig, holder_name, props, labels):
    """One slider row per property, left and right wing side by side."""
    for prop in props:
        sliders = [(side, rig.pose.bones.get(holder_name(side))) for side in SIDES]
        sliders = [(side, holder) for side, holder in sliders if holder is not None and prop in holder.keys()]
        if not sliders:
            continue
        linked = len(sliders) == 2 and bool(rig.get("wingrig_lr_linked", False))
        if linked:
            sliders = sliders[:1]
        column = box.column(align=True)
        column.label(text=labels[prop])
        row = column.row(align=True)
        for side, holder in sliders:
            row.prop(holder, f'["{prop}"]', text="左右联动" if linked else ("左" if side == "L" else "右"), slider=True)


class WING_PT_ControlPanel(bpy.types.Panel):
    bl_label = "Blender Wing Generator"
    bl_idname = "WING_PT_control_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Blender Wing Generator"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        if not hasattr(scene, "wing_model_settings"):
            layout.operator("wing_model.create_model", icon='MESH_DATA')
            return
        s = scene.wing_model_settings
        header = layout.row(align=True)
        header.operator("wing_model.create_model", text="创建 / 重建", icon='FILE_REFRESH')
        header.operator("wing_model.import_html_parameters", text="导入 HTML JSON", icon='IMPORT')
        layout.operator("wing_model.reset_model_pose", text="恢复模型默认位置", icon='LOOP_BACK')
        for page_ids in (('SHAPE', 'ANIMATION', 'RIG_CONTROLS'), ('MODEL_PROCESSING', 'ADVANCED')):
            tabs = layout.row(align=True)
            for page_id in page_ids:
                tabs.prop_enum(s, "active_page", page_id)

        if s.active_page == 'SHAPE':
            self.draw_shape_page(layout, s)
        elif s.active_page == 'ANIMATION':
            self.draw_animation_page(layout, scene, s)
        elif s.active_page == 'RIG_CONTROLS':
            self.draw_rig_controls_page(layout, scene, s)
        elif s.active_page == 'ADVANCED':
            self.draw_advanced_page(layout, scene, s)
        else:
            self.draw_uv_page(layout, scene, s)

    def draw_rig_settings(self, layout, scene, s):
        rig = bpy.data.objects.get(RIG_OBJECT)
        has_rig = bool(rig and rig.type == "ARMATURE")
        bound = bool(has_rig and rig.get("wingrig_mesh_bound", False))
        layout.label(text="骨骼设置", icon='ARMATURE_DATA')
        if bound:
            warn = layout.box()
            warn.alert = True
            warn.label(text="羽毛网格已绑定骨架，参数已锁定。", icon='LOCKED')
        full = layout.box()
        full.label(text="一键绑骨选项", icon='PLAY')
        full.prop(s, "rig_auto_flat_pose")

        pose_box = layout.box()
        pose_box.label(text="手动寻找平摊姿态", icon='TIME')
        pose_box.operator("wing_model.find_flat_wing_pose", text="寻找平摊姿态并切换到对应帧", icon='VIEW_CAMERA')
        selected_frame = scene.get("wing_model_flat_pose_frame")
        if selected_frame is not None:
            pose_box.label(text=f"上次搜索帧：{int(selected_frame)}；当前帧：{scene.frame_current}")
            score = float(scene.get("wing_model_flat_pose_score", 0.0))
            spread = float(scene.get("wing_model_flat_pose_lateral_span", 0.0))
            flatness = float(scene.get("wing_model_flat_pose_flatness", 0.0))
            pose_box.label(text=f"启发式评分 {score:.3f} · 横向伸展 {spread:.3f} · 平面度 {flatness:.3f}")

        chain_box = layout.box()
        chain_box.label(text="主翼骨骼", icon='BONE_DATA')
        chain_box.operator("wing_model.build_architecture_stage1", text="生成主翼骨骼", icon='ARMATURE_DATA')
        if has_rig:
            chain_box.label(text=f"当前骨架：{len(rig.data.bones)} 根；生成帧：{rig.get('wingrig_pose_source_frame', '未知')}")

        feather_box = layout.box()
        feather_box.label(text="羽毛骨骼与层级", icon='GROUP_BONE')
        feather_box.operator("wing_model.build_feather_bones", text="生成羽毛骨骼", icon='GROUP_BONE')

        skin_box = layout.box()
        skin_box.label(text="蒙皮与权重", icon='MOD_VERTEX_WEIGHT')
        skin_box.operator("wing_model.skin_feathers", text="绑定羽毛并写入权重", icon='MOD_ARMATURE')

        con_box = layout.box()
        con_box.label(text="约束", icon='CONSTRAINT_BONE')
        col = con_box.column(align=True)
        col.prop(s, "rig_blend_radius_mm")
        col.prop(s, "rig_blend_falloff")
        col.prop(s, "rig_blend_neighbor_pct", slider=True)
        col.prop(s, "rig_blend_max_targets")
        con_box.operator("wing_model.add_feather_armature_constraints", text="添加约束", icon='CONSTRAINT_BONE')
        con_box.prop(s, "rig_fan_follow_pct", slider=True)
        con_box.operator("wing_model.add_feather_constraints", text="羽毛扇形联动", icon='CON_ROTLIKE')

        spread_box = layout.box()
        spread_box.label(text="排级扇形展开控制", icon='FULLSCREEN_ENTER')
        spread_box.prop(s, "rig_spread_max_angle_deg", slider=True)
        spread_box.operator("wing_model.build_spread_controls", text="生成扇形展开控制器", icon='FULLSCREEN_ENTER')

        pose_ctrl_box = layout.box()
        pose_ctrl_box.label(text="整体姿态控制", icon='ORIENTATION_GIMBAL')
        col = pose_ctrl_box.column(align=True)
        col.prop(s, "rig_pose_sweep_deg")
        col.prop(s, "rig_pose_flap_deg")
        col.prop(s, "rig_pose_pitch_deg")
        col.prop(s, "rig_pose_twist_deg")
        pose_ctrl_box.operator("wing_model.build_pose_controls", text="生成整体姿态控制器", icon='ORIENTATION_GIMBAL')

        hand_box = layout.box()
        hand_box.label(text="手腕与手指控制", icon='HAND')
        col = hand_box.column(align=True)
        col.prop(s, "rig_wrist_flex_deg")
        col.prop(s, "rig_wrist_sweep_deg")
        col.prop(s, "rig_finger_curl_deg")
        col.prop(s, "rig_finger_sweep_deg")
        col.prop(s, "rig_thumb_open_deg")
        col.prop(s, "rig_thumb_flex_deg")
        col.prop(s, "rig_digit2_ratio", slider=True)
        hand_box.operator("wing_model.build_hand_controls", text="生成手腕与手指控制器", icon='HAND')

        bend_box = layout.box()
        bend_box.label(text="翼面弯折控制", icon='MOD_SIMPLEDEFORM')
        bend_box.prop(s, "rig_bend_max_deg", slider=True)
        bend_box.prop(s, "rig_bend_ramp_pct", slider=True)
        bend_box.operator("wing_model.build_bend_controls", text="生成翼面弯折控制器", icon='MOD_SIMPLEDEFORM')

        fold_box = layout.box()
        fold_box.label(text="折叠动作", icon='ACTION')
        fold_box.operator("wing_model.build_fold_action", text="创建折叠动作与约束", icon='ACTION')

        link_box = layout.box()
        link_box.label(text="折叠与展开联动", icon='LINKED')
        link_box.prop(s, "rig_fold_spread_end", slider=True)
        link_box.prop(s, "rig_fold_hand_keep_pct", slider=True)
        link_box.operator("wing_model.link_fold_spread", text="联动折叠与展开", icon='LINKED')

        cycle_box = layout.box()
        cycle_box.label(text="拍翅循环辅助", icon='FILE_REFRESH')
        row = cycle_box.row(align=True)
        row.operator("wing_model.build_cycle_controls", text="生成拍翅循环控制", icon='FILE_REFRESH')
        row.operator("wing_model.cycle_set_range", text="时间轴设为一周期", icon='TIME')

        panel_box = layout.box()
        panel_box.label(text="显示开关、控制骨形状与颜色", icon='PREFERENCES')
        row = panel_box.row(align=True)
        row.operator("wing_model.build_rig_panel", text="创建显示开关", icon='HIDE_OFF')
        row.operator("wing_model.refresh_rig_style", text="刷新形状与颜色", icon='SHADING_WIRE')

        tools = layout.box()
        row = tools.row(align=True)
        row.operator("wing_model.diagnose_architecture_stage1", text="检查骨骼与绑定", icon='CHECKMARK')
        row.operator("wing_model.remove_architecture_stage1", text="清除全部骨骼与绑定", icon='TRASH')
        if has_rig:
            tools.label(text=f"阶段 {rig.get('wingrig_stage', '?')} / 6 · 蒙皮：{rig.get('wingrig_skinning_status', '未知')}")

    def draw_rig_controls_page(self, layout, scene, s):
        """Animator-facing page: one-click rig, flapping animation, common actions, then controllers by level."""
        rig = bpy.data.objects.get(RIG_OBJECT)
        full = layout.box()
        full.label(text="一键绑骨", icon='PLAY')
        full.operator("wing_model.build_full_rig", text="一键完成全部绑定", icon='ARMATURE_DATA')
        if not (rig and rig.type == "ARMATURE"):
            layout.label(text="尚未生成骨架。", icon='INFO')
            return
        bones = rig.pose.bones

        def has(name, prop):
            bone = bones.get(name)
            return bone is not None and prop in bone.keys()

        fold_on = has(_fold_ctrl_name("L"), "wingrig_ctl") or has(_fold_ctrl_name("R"), "wingrig_ctl")
        pose_on = has(_pose_ctrl_name("L"), POSE_PROPS[0]) or has(_pose_ctrl_name("R"), POSE_PROPS[0])
        hand_on = has(_hand_ctrl_name("L"), HAND_PROPS[0]) or has(_hand_ctrl_name("R"), HAND_PROPS[0])
        bend_on = any(bones.get(_bend_ctrl_name("arm", side)) is not None for side in SIDES)
        found = {pb.name[len("CTRL_spread_"):].rsplit(".", 1)[0] for pb in bones if pb.name.startswith("CTRL_spread_")}
        order = list(SPREAD_ROW_LABELS)
        spread_rows = sorted(found, key=lambda row: order.index(row) if row in order else len(order))
        cycle_on = has(CYCLE_CTRL, "cycle_on")
        if not (fold_on or pose_on or hand_on or bend_on or spread_rows or cycle_on):
            layout.label(text="尚无控制器。", icon='INFO')

        if cycle_on:
            holder = bones[CYCLE_CTRL]
            flap = layout.box()
            flap.label(text="拍翅动画", icon='FILE_REFRESH')
            flap.prop(holder, '["cycle_on"]', text="拍翅幅度", slider=True)
            playing = bool(getattr(getattr(bpy.context, "screen", None), "is_animation_playing", False))
            row = flap.row(align=True)
            row.operator("wing_model.toggle_playback", text="暂停" if playing else "播放",
                         icon='PAUSE' if playing else 'PLAY')
            row.operator("wing_model.cycle_set_range", text="时间轴设为一周期", icon='TIME')
            flap.prop(s, "show_cycle_params", toggle=True)
            if s.show_cycle_params:
                cycle_labels = {"cycle_frames": "周期帧数", "cycle_phase": "整体相位",
                                "downstroke": "下拍占比", "flap_amp": "上下扇幅度", "flap_bias": "翅膀高度偏移",
                                "sweep_amp": "前后摆幅度", "pitch_amp": "俯仰幅度", "twist_amp": "翼尖扭转幅度",
                                "wrist_amp": "手腕幅度", "curl_amp": "指节幅度", "lag_wrist": "手腕滞后",
                                "lag_tip": "翼尖滞后", "lr_offset": "右翼相位差"}
                col = flap.column(align=True)
                for prop, *_rest in CYCLE_SETTINGS:
                    if prop != "cycle_on":
                        col.prop(holder, f'["{prop}"]', text=cycle_labels[prop], slider=True)

        tools = layout.box()
        tools.label(text="常用操作", icon='TOOL_SETTINGS')
        tools.operator("wing_model.reset_rig_pose", text="回归平摊姿态", icon='LOOP_BACK')
        if _rig_link_pairs(rig):
            linked = bool(rig.get("wingrig_lr_linked", False))
            link = tools.operator("wing_model.set_lr_link",
                                  text="左右联动：已开启" if linked else "左右联动：已关闭",
                                  icon='LINKED' if linked else 'UNLINKED')
            link.enable = not linked
        if fold_on or spread_rows or bend_on:
            tools.operator("wing_model.key_base_controls", text="给基础控制器打关键帧", icon='KEY_HLT')

        if fold_on or pose_on:
            wing = layout.box()
            wing.label(text="整翼 · 折叠与姿态", icon='ARMATURE_DATA')
            _draw_ctl_rows(wing, rig, _fold_ctrl_name, "折叠", "wing_slider_pos")
            _draw_lr_rows(wing, rig, _pose_ctrl_name, POSE_PROPS,
                          {"sweep": "前后摆", "flap": "上下扇", "pitch": "俯仰", "twist": "扭转"})
        if fold_on and has(_fold_ctrl_name("L"), "fade_end"):
            fade = layout.box()
            fade.label(text="折叠淡出", icon='LINKED')
            _draw_lr_rows(fade, rig, _fold_ctrl_name, ("fade_end", "hand_keep"),
                          {"fade_end": "淡出终点", "hand_keep": "手部保留比例"})

        if hand_on or bend_on:
            arm = layout.box()
            arm.label(text="手臂分段 · 手部与翼面弯折", icon='HAND')
            _draw_lr_rows(arm, rig, _hand_ctrl_name, HAND_PROPS,
                          {"wrist_flex": "手腕上下", "wrist_sweep": "手腕前后", "finger_curl": "指节弯曲",
                           "finger_sweep": "指节前后", "thumb_open": "拇指张开", "thumb_flex": "拇指上下"})
            zone_labels = {"arm": "弯折 · 上臂区", "fore": "弯折 · 前臂区", "hand": "弯折 · 手掌区", "tip": "弯折 · 指尖区"}
            for zone in BEND_ZONES:
                _draw_ctl_rows(arm, rig, lambda side, zone=zone: _bend_ctrl_name(zone, side), zone_labels[zone], "wing_slider")

        if spread_rows:
            rows_box = layout.box()
            rows_box.label(text="排级 · 扇形展开", icon='FULLSCREEN_ENTER')
            for name in spread_rows:
                _draw_ctl_rows(rows_box, rig, lambda side, name=name: _spread_ctrl_name(name, side),
                               SPREAD_ROW_LABELS.get(name, name), "wing_slider")

        panel_bone = bones.get(CTRL_PANEL_BONE)
        if panel_bone is not None and SHOW_FEATHER_PROP in panel_bone.keys():
            show = layout.box()
            show.label(text="显示开关", icon='HIDE_OFF')
            presets = show.row(align=True)
            for mode, text in (("ANIMATE", "动画模式"), ("RIG", "绑定检查"), ("MAIN", "仅主翼骨骼")):
                presets.operator("wing_model.set_rig_display", text=text).mode = mode
            switch_labels = {"show_main_bones": "主翼骨骼", SHOW_FEATHER_PROP: "羽毛设置骨骼",
                             "show_ctrl_fold": "折叠控制骨", "show_ctrl_spread": "排级扇形控制骨",
                             "show_ctrl_bend": "翼面弯折控制骨",
                             "show_ctrl_holders": "数值持有骨"}
            col = show.column(align=True)
            for prop, _default, _collections in SHOW_SWITCHES:
                if prop in panel_bone.keys():
                    col.prop(panel_bone, f'["{prop}"]', text=switch_labels[prop], slider=True)

    def draw_uv_page(self, layout, scene, s):
        uv_box = layout.box()
        uv_box.label(text="羽毛 UV 展开", icon='IMAGE_DATA')
        uv_box.prop(s, "uv_shape_mode", expand=True)
        uv_box.prop(s, "uv_layout_mode", expand=True)
        uv_box.operator("wing_model.apply_uv", text="重新生成 / 应用 UV", icon='FILE_REFRESH')
        uv_box.separator()
    def draw_shape_page(self, layout, s):
        preset_box = layout.box(); preset_box.label(text="翼型预设", icon='MOD_BUILD')
        preset_box.prop(s, "wing_preset")
        form_box = preset_box.box(); form_box.label(text="翼型轮廓微调", icon='MODIFIER')
        form_box.prop(s, "wing_depth_pct", text="翼面纵深比例", slider=True)
        row = form_box.row(align=True); row.prop(s, "sweep_deg", text="羽轴后掠偏移", slider=True); row.prop(s, "primary_fan_deg", text="初级飞羽扇开", slider=True)
        row = form_box.row(align=True); row.prop(s, "roundness", text="翼尖圆钝度", slider=True); row.prop(s, "primary_gap_pct", text="初级飞羽分指", slider=True)
        row = form_box.row(align=True); row.prop(s, "tip_lift_mm", text="翼尖离面高度", slider=True); row.prop(s, "chord_dist_pct", text="飞羽弦长分布", slider=True)
        form_box.prop(s, "primary_attach_pct", text="初级飞羽附着分布", slider=True)
        bone_box = preset_box.box(); bone_box.label(text="翼骨段比例", icon='BONE_DATA')
        bone_box.prop(s, "span_pct", text="翼展比例", slider=True)
        row = bone_box.row(align=True); row.prop(s, "bone_h_pct", text="上臂比例", slider=True); row.prop(s, "bone_f_pct", text="前臂比例", slider=True)
        row = bone_box.row(align=True); row.prop(s, "bone_hand_pct", text="手翼比例", slider=True); row.prop(s, "hand_digits_pct", text="指骨占比", slider=True)

        overall = layout.box(); overall.label(text="整体羽毛形状", icon='PARTICLES')
        overall.prop(s, "global_length_pct", slider=True)
        overall.prop(s, "global_width_pct", slider=True)
        overall.separator(); overall.label(text="中轴两侧翻折", icon='MODIFIER')
        overall.prop(s, "global_vane_fold_angle_deg", slider=True)
        overall.prop(s, "invert_front_back_fold_direction", toggle=True)

        count_box = layout.box(); count_box.label(text="自定义羽毛数量", icon='OUTLINER_DATA_CURVES')
        row = count_box.row(align=True); row.prop(s, "count_secondaries", text="次级飞羽"); row.prop(s, "count_primaries", text="初级飞羽")
        row = count_box.row(align=True); row.prop(s, "count_tertials", text="三级飞羽")
        row = count_box.row(align=True); row.prop(s, "count_median_coverts", text="中覆羽"); row.prop(s, "count_palm_median_coverts", text="手翼中覆羽")
        row = count_box.row(align=True); row.prop(s, "count_lesser_coverts", text="小覆羽 / 缘覆羽每排")
        row = count_box.row(align=True); row.prop(s, "count_axillaries", text="腋羽"); row.prop(s, "count_alula", text="小翼羽")
        count_box.label(text=f"初级覆羽：{s.count_primaries}；大覆羽：{s.count_secondaries + s.count_tertials}")

        group_box = layout.box(); group_box.label(text="羽毛组参数", icon='GROUP')
        group_box.prop(s, "active_group", text="选择羽毛组")
        g = next((x for x in s.groups if x.group_id == s.active_group), None)
        if g:
            group_box.prop(g, "length_scale", slider=True)
            group_box.prop(g, "width_scale", slider=True)
            group_box.prop(g, "vane_fold_angle_deg", slider=True)
            if g.group_id not in {'axillaries', 'alula'}:
                group_box.prop(g, "chord_scale", slider=True)
            group_box.separator(); group_box.label(text="组内长度分布")
            row = group_box.row(align=True); row.prop(g, "start_pct", slider=True); row.prop(g, "end_pct", slider=True)
            group_box.prop(g, "curve", text="分段过渡方式")
            points_box = group_box.box(); points_box.label(text=f"中间长度参考点", icon='EMPTY_AXIS')
            op = points_box.operator("wing_model.add_length_reference_point", text="添加参考点", icon='ADD'); op.group_id = g.group_id
            if len(g.length_reference_points):
                row = points_box.row(align=True); op = row.operator("wing_model.clear_length_reference_points", text="清除全部参考点", icon='TRASH'); op.group_id = g.group_id
                for original_index, point in sorted(enumerate(g.length_reference_points), key=lambda pair: pair[1].position_pct):
                    pr = points_box.row(align=True); pr.label(text=f"点 {original_index + 1}")
                    pr.prop(point, "position_pct", text="位置 %", slider=True); pr.prop(point, "value_pct", text="倍率 %", slider=True)
                    rm = pr.operator("wing_model.remove_length_reference_point", text="", icon='X'); rm.group_id = g.group_id; rm.index = original_index
            if g.group_id in {'primaries', 'secondaries'}:
                group_box.prop(g, "sweep_offset", slider=True)
                if g.group_id == 'primaries': group_box.prop(g, "fan_offset", slider=True)
            group_box.prop(g, "root_dist_offset", slider=True)
            if g.group_id not in {'axillaries', 'alula'}: group_box.prop(g, "chord_dist_offset", slider=True)
            group_box.operator("wing_model.reset_group", icon='LOOP_BACK')

        combo_box = layout.box(); combo_box.label(text="多组组合修改器", icon='MODIFIER')
        combo_box.operator("wing_model.add_combo", icon='ADD')
        for i, c in enumerate(s.combos):
            cb = combo_box.box(); row = cb.row(align=True); row.prop(c, "name", text="")
            op = row.operator("wing_model.remove_combo", text="", icon='X'); op.index = i
            cb.prop(c, "targets"); cb.prop(c, "param", text="修改内容")
            if c.param in {"lengthScale", "widthScale", "chordScale"}:
                cb.prop(c, "value_pct", text="倍率 %", slider=True)
            else:
                cb.prop(c, "offset_value", text="偏移量", slider=True)


    def draw_animation_page(self, layout, scene, s):
        timeline = layout.box(); timeline.label(text="时间轴", icon='TIME')
        row = timeline.row(align=True); row.prop(scene, "frame_start", text="起始帧"); row.prop(scene, "frame_end", text="结束帧")
        row = timeline.row(align=True); row.prop(scene.render, "fps", text="帧率 FPS"); row.prop(scene.render, "fps_base", text="帧率基数")

        motion = layout.box(); motion.label(text="动作控制", icon='ANIM')
        playing = bool(getattr(getattr(bpy.context, "screen", None), "is_animation_playing", False))
        motion.operator("wing_model.toggle_python_playback", text="停止播放" if playing else "开始播放",
                        icon='PAUSE' if playing else 'PLAY')
        row = motion.row(align=True); row.prop(s, "motion_scale_pct", slider=True); row.prop(s, "flap_rate_hz")
        row = motion.row(align=True); row.prop(s, "flight_state"); row.prop(s, "flight_gait")
        if s.flight_state == 'turn': motion.prop(s, "turn_strength_deg", slider=True)
        if s.flight_gait == 'hover':
            motion.prop(s, "hover_amp_deg", slider=True); motion.prop(s, "hover_down_pct", slider=True)
        motion.prop(s, "show_motion_advanced", toggle=True)
        if s.show_motion_advanced:
            motion.prop(s, "finger_offset_deg", slider=True)
            motion.prop(s, "valve_angle_deg", slider=True)
            motion.prop(s, "shingle_tilt_deg", slider=True)
            motion.prop(s, "alula_open_deg", slider=True)
            motion.separator(); motion.prop(s, "secondary_follow_yellow_reference", toggle=True)
        motion.prop(s, "show_joint_params", toggle=True)
        if s.show_joint_params:
            for joint in s.joints:
                joint_box = motion.box(); joint_box.label(text=joint.label)
                row = joint_box.row(align=True); row.prop(joint, "mean_deg"); row.prop(joint, "amplitude_deg")
                joint_box.prop(joint, "phase", slider=True)

    def draw_advanced_page(self, layout, scene, s):
        layout.row(align=True).prop(s, "adv_section", expand=True)
        if s.adv_section == 'RIG':
            self.draw_rig_settings(layout, scene, s)
            return
        _draw_scope_editor(layout, s)

        bone_box = layout.box(); bone_box.label(text="翼骨段参考尺寸", icon='BONE_DATA')
        bone_box.prop(s, "show_advanced", text="展开骨骼尺寸", toggle=True)
        if s.show_advanced:
            bone_box.prop(s, "humerus_base_mm"); bone_box.prop(s, "forearm_base_mm")
            bone_box.prop(s, "handwing_base_mm"); bone_box.prop(s, "shoulder_span_mm")
        reset_box = layout.box(); reset_box.operator("wing_model.reset_all", text="恢复默认参数", icon='LOOP_BACK')


# -----------------------------------------------------------------------------
# Rig: constants, naming and main-chain specs
# -----------------------------------------------------------------------------
# Rig pipeline: main chain -> feather bones -> skinning -> constraints -> controllers -> fold -> panel.
# The model builder supplies geometry and metadata; every step below is rebuilt from scratch on demand.

RIG_ROOT_COLLECTION = "WING_ARCH_STAGE1"
RIG_OBJECT = "WING_ARCH_STAGE1_Armature"
RIG_SCHEMA = "0.4"

# Main wing chain, grown from the shoulder by extrusion:
#   humerus -> forearm -> palm -> digit1 -> digit2
# and one thumb bone extruded from the forearm/palm junction (the wrist).
MAIN_CHAIN_ROLES = ("humerus", "forearm", "palm", "digit1", "digit2")
THUMB_ROLE = "thumb"
MAIN_ROLE_ORDER = MAIN_CHAIN_ROLES + (THUMB_ROLE,)
MAIN_BONE_PARENT_ROLE = {
    "humerus": None, "forearm": "humerus", "palm": "forearm",
    "digit1": "palm", "digit2": "digit1", "thumb": "forearm",
}
DIGIT1_FRACTION = 0.58          # share of the finger section taken by the first phalanx

# Rig naming and constants (ASCII only: Blender data names never contain Chinese).
MAIN_BONE_PREFIX = "WING_"
FEATHER_BONE_PREFIX = "FEA_"
CTRL_PANEL_BONE = "CTRL_panel"
SHOW_FEATHER_PROP = "show_feather_bones"
FOLD_CTRL_RANGE_M = 0.05        # control bone slides 0..50 mm along its local Y axis
FOLD_ACTION_NAME = "wing_collapse"
FOLD_END_FRAME = 20
FAN_CONSTRAINT_NAME = "WING_FanFollow"
FOLD_CONSTRAINT_NAME = "WING_FoldAction"
LIMIT_CONSTRAINT_NAME = "WING_FoldLimit"
ARMATURE_CONSTRAINT_NAME = "WING_FeatherArmature"
SPREAD_CONSTRAINT_NAME = "WING_FanSpread"
SPREAD_LIMIT_NAME = "WING_SpreadLimit"
TWIST_SHARE = {"forearm": 0.25, "palm": 0.25, "digit1": 0.25, "digit2": 0.25}
SPREAD_CTRL_RANGE_M = 0.03     # row slider travels -30..+30 mm along its local Y axis
ARMATURE_MODIFIER_NAME = "WING_Armature"
THICKNESS_MODIFIER_NAME = "WING_FeatherThickness"
COVERT_FOLLOW = 0.9
MIN_FEATHER_BONE_LENGTH_M = 0.001
COLL_MAIN = "WING_Main"
COLL_SETUP = "FEA_Setup"
COLL_FLIGHT = "FEA_Flight"
COLL_COVERT = "FEA_Covert"
COLL_AUX = "FEA_Aux"
COLL_CTRL = "WING_Ctrl"
COLL_CTRL_FOLD = "CTRL_Fold"      # draggable controllers: fold, row spread, bend
COLL_CTRL_SPREAD = "CTRL_Spread"
COLL_CTRL_BEND = "CTRL_Bend"
COLL_CTRL_HOLDERS = "CTRL_Holders"  # pose / hand / cycle / switch bones only hold values: hidden by default
RIG_COLLECTION_NAMES = (COLL_MAIN, COLL_SETUP, COLL_FLIGHT, COLL_COVERT, COLL_AUX, COLL_CTRL,
                        COLL_CTRL_FOLD, COLL_CTRL_SPREAD, COLL_CTRL_BEND, COLL_CTRL_HOLDERS)
# (custom property on CTRL_panel, default, collections it shows/hides)
SHOW_SWITCHES = (
    ("show_main_bones", 1, (COLL_MAIN,)),
    (SHOW_FEATHER_PROP, 0, (COLL_SETUP,)),
    ("show_ctrl_fold", 1, (COLL_CTRL_FOLD,)),
    ("show_ctrl_spread", 1, (COLL_CTRL_SPREAD,)),
    ("show_ctrl_bend", 1, (COLL_CTRL_BEND,)),
    ("show_ctrl_holders", 0, (COLL_CTRL_HOLDERS,)),
)
SHAPE_COLLECTION = "WING_ARCH_SHAPES"
SHAPE_PREFIX = "WGT_WING_"

# Folded-wing target directions in the XY plane: (backward component, outward component).
# Humerus swings back, forearm folds forward, hand folds back again (Z-shaped folded wing).
FOLD_MAIN_TARGETS = {
    "humerus": (-0.96, 0.28), "forearm": (0.96, 0.28), "palm": (-0.96, 0.28),
    "digit1": (-0.97, 0.24), "digit2": (-0.97, 0.24),
}
FOLD_FEATHER_SPREAD_DEG = {"flight": 5.0, "covert": 9.0, "aux": 14.0}

# Feather-bone keys follow the feather ids written by generate_feathers():
#   flight feathers      S1..S10, P1..P10, T1..T3
#   primary coverts      PC_P<n>       (id "primaryCoverts:P<n>:upper")
#   greater coverts      GC_S<n>/GC_T<n>
#   median / lesser / marginal / palm median / axillary / alula rows
_COVERT_KEY_PREFIX = {
    "median": "MC", "lesser": "LC", "marginal": "LCM",
    "palmMedian": "PMC", "axillary": "AX", "alula": "AL",
}


def _main_bone_name(role, side):
    return f"{MAIN_BONE_PREFIX}{role}.{side}"


def _feather_bone_name(key, side):
    return f"{FEATHER_BONE_PREFIX}{key}.{side}"


def _fold_ctrl_name(side):
    return f"CTRL_fold.{side}"


def feather_bone_key(feather_id):
    """Map a generator feather id to its bone key; upper/under coverts share one bone."""
    fid = str(feather_id)
    if re.match(r"^[SPT]\d+$", fid):
        return fid
    parts = fid.split(":")
    if parts[0] == "primaryCoverts" and len(parts) >= 2:
        return "PC_" + parts[1]
    if parts[0] == "greaterCoverts" and len(parts) >= 2:
        return "GC_" + parts[1]
    match = re.match(r"^([A-Za-z]+)(\d+)$", parts[0])
    if match and match.group(1) in _COVERT_KEY_PREFIX:
        return _COVERT_KEY_PREFIX[match.group(1)] + match.group(2)
    return None


def feather_bone_category(key):
    if re.match(r"^[SPT]\d+$", key):
        return "flight"
    if key.startswith(("AX", "AL")):
        return "aux"
    return "covert"


def _wrap_angle(value):
    return (value + math.pi) % math.tau - math.pi


def _mm_point(point, mirrored):
    return Vector((point[0] * MM_TO_M, (-point[1] if mirrored else point[1]) * MM_TO_M, point[2] * MM_TO_M))


def _bone_spec(name, role, layer, head, tail, parent_role=None,
                           connected=False, deform=False, side="L", module="main_wing"):
    return {
        "name": name,
        "role": role,
        "layer": layer,
        "head": list(head),
        "tail": list(tail),
        "parent_role": parent_role,
        "connected": bool(connected),
        "deform": bool(deform),
        "side": side,
        "module": module,
        "stable_id": f"{layer.lower()}:{module}:{role}:{side}",
    }


def _main_chain_specs(state, angles=None):
    """Return the six-bone main chain per wing at the supplied generator pose.

    Growth order from the shoulder: humerus -> forearm -> palm -> digit1 -> digit2, plus
    a thumb bone extruded from the wrist (forearm tail = palm head). Coordinates are in
    the generator's millimetre coordinate system.
    """
    if angles is None:
        angles = joints_at_t0()
    k, hand_joint = bone_points_for_state(state, angles)
    shoulder, elbow, wrist, tip = [list(p) for p in k["points"]]
    hand_joint = list(hand_joint)
    digit_mid = v_add(hand_joint, v_mul(v_sub(tip, hand_joint), DIGIT1_FRACTION))
    thumb_tip = list(make_thumb_geo(state, k)["tip"])
    segments = {
        "humerus": (shoulder, elbow),
        "forearm": (elbow, wrist),
        "palm": (wrist, hand_joint),
        "digit1": (hand_joint, digit_mid),
        "digit2": (digit_mid, tip),
        "thumb": (wrist, thumb_tip),
    }
    specs = []
    for side, mirrored in (("L", False), ("R", True)):
        def tr(point, mirrored=mirrored):
            point = list(point)
            return [point[0], -point[1], point[2]] if mirrored else point
        for role in MAIN_ROLE_ORDER:
            head, tail = segments[role]
            parent_role = MAIN_BONE_PARENT_ROLE[role]
            spec = _bone_spec(
                _main_bone_name(role, side), role, "MAIN", tr(head), tr(tail), parent_role,
                connected=parent_role is not None, deform=True, side=side, module="main_chain")
            spec["parent_name"] = _main_bone_name(parent_role, side) if parent_role else None
            spec["stable_id"] = f"main_chain:{role}:{side}"
            specs.append(spec)
    return specs


# -----------------------------------------------------------------------------
# Rig utilities
# -----------------------------------------------------------------------------

@contextlib.contextmanager
def _armature_edit_session(rig):
    """Enter Edit Mode on the armature and yield its edit bones; always return to Object Mode."""
    view_override = _find_view3d_override()
    if view_override is None:
        raise RuntimeError("Run the rig generator from a workspace that contains a 3D View.")
    for obj in list(bpy.context.selected_objects):
        try:
            obj.select_set(False)
        except Exception:
            pass
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    with bpy.context.temp_override(**view_override):
        if rig.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            yield rig.data.edit_bones
        finally:
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception as exc:
                _warn("leaving armature edit mode", exc)


def _align_edit_bone_roll(bone):
    """Point every bone's local Z at world +Z so local Z rotation = in-plane fan/fold."""
    try:
        bone.align_roll(Vector((0.0, 0.0, 1.0)))
    except Exception as exc:
        _warn("bone roll alignment", exc)


def _rig_meshes_bound():
    rig = bpy.data.objects.get(RIG_OBJECT)
    return bool(rig is not None and rig.get("wingrig_mesh_bound", False))


def _rig_require_main_chain():
    rig = bpy.data.objects.get(RIG_OBJECT)
    if rig is None or rig.type != "ARMATURE":
        raise RuntimeError("Generate the main wing bones first.")
    if str(rig.get("wingrig_schema_version", "")) != RIG_SCHEMA:
        raise RuntimeError("This rig was made by an older version; regenerate the main wing bones.")
    for side in SIDES:
        for role in MAIN_ROLE_ORDER:
            if rig.data.bones.get(_main_bone_name(role, side)) is None:
                raise RuntimeError(f"Missing main bone: {_main_bone_name(role, side)}")
    return rig


def _rig_feather_bones(rig, side=None):
    return [b for b in rig.data.bones
            if b.name.startswith(FEATHER_BONE_PREFIX) and (side is None or b.name.endswith("." + side))]


def _rig_require_feather_bones():
    rig = _rig_require_main_chain()
    if not _rig_feather_bones(rig) or rig.data.bones.get(CTRL_PANEL_BONE) is None:
        raise RuntimeError("Generate the feather bones first.")
    return rig


def _rig_main_segments(rig, side):
    """Return [(role, head, tail)] for the five chain bones (thumb excluded), armature space."""
    segments = []
    for role in MAIN_CHAIN_ROLES:
        bone = rig.data.bones[_main_bone_name(role, side)]
        segments.append((role, bone.head_local.copy(), bone.tail_local.copy()))
    return segments


def _point_segment_distance(point, a, b):
    ab = b - a
    denom = ab.length_squared
    t = 0.0 if denom < 1.0e-18 else max(0.0, min(1.0, (point - a).dot(ab) / denom))
    return (point - (a + ab * t)).length, t


def _nearest_chain_role(point, segments):
    best_role, best_dist = segments[0][0], None
    for role, a, b in segments:
        dist, _t = _point_segment_distance(point, a, b)
        if best_dist is None or dist < best_dist:
            best_role, best_dist = role, dist
    return best_role


def _chain_param(point, segments):
    """Distance along the shoulder-to-fingertip polyline of the point's nearest projection."""
    best_dist, best_param, cumulative = None, 0.0, 0.0
    for _role, a, b in segments:
        length = (b - a).length
        dist, t = _point_segment_distance(point, a, b)
        if best_dist is None or dist < best_dist:
            best_dist, best_param = dist, cumulative + t * length
        cumulative += length
    return best_param


def _rig_remove_drivers_matching(id_block, fragment):
    anim = getattr(id_block, "animation_data", None)
    if anim is None:
        return
    for fcurve in list(anim.drivers):
        if fragment in fcurve.data_path:
            try:
                anim.drivers.remove(fcurve)
            except Exception as exc:
                _warn("removing an old driver", exc)


def _rig_unbind_meshes(rig=None):
    """Remove Armature modifiers, feather vertex groups and parenting from the feather meshes."""
    if rig is None:
        rig = bpy.data.objects.get(RIG_OBJECT)
    for group_id, *_ in GROUP_DEFS:
        obj = bpy.data.objects.get(f"WINGGEN_Feathers_{group_id}")
        if obj is None or obj.type != 'MESH':
            continue
        for mod in list(obj.modifiers):
            if mod.type == 'ARMATURE' and (mod.name == ARMATURE_MODIFIER_NAME or (rig is not None and mod.object == rig)):
                obj.modifiers.remove(mod)
        for group in list(obj.vertex_groups):
            if group.name.startswith(FEATHER_BONE_PREFIX):
                obj.vertex_groups.remove(group)
        if rig is not None and obj.parent == rig:
            world = obj.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = world
    if rig is not None:
        rig["wingrig_mesh_bound"] = False


def _rig_remove_all(scene):
    """Remove the whole rig, unbind the meshes and restore generator animation."""
    rig = bpy.data.objects.get(RIG_OBJECT)
    _rig_unbind_meshes(rig)
    if rig is not None:
        delete_object_if_exists(RIG_OBJECT)
    _rig_remove_shapes()
    action = bpy.data.actions.get(FOLD_ACTION_NAME)
    if action is not None:
        try:
            action.use_fake_user = False
            bpy.data.actions.remove(action)
        except Exception as exc:
            _warn("removing the fold action", exc)
    settings = getattr(scene, "wing_model_settings", None)
    if "wingrig_prev_python_anim" in scene:
        previous = bool(scene["wingrig_prev_python_anim"])
        del scene["wingrig_prev_python_anim"]
        if settings is not None:
            settings.python_animation_enabled = previous


def _rig_assign_collections(rig):
    """Create bone collections (replacement for the tutorial's Bone Groups) and assign bones."""
    arm = rig.data
    all_collections = getattr(arm, "collections_all", arm.collections)
    for coll in reversed(list(all_collections)):
        if coll.name in RIG_COLLECTION_NAMES:
            arm.collections.remove(coll)

    def new_collection(name, parent=None):
        if parent is not None:
            try:
                return arm.collections.new(name, parent=parent)
            except TypeError:
                pass
        return arm.collections.new(name)

    main = new_collection(COLL_MAIN)
    setup = new_collection(COLL_SETUP)
    flight = new_collection(COLL_FLIGHT, setup)
    covert = new_collection(COLL_COVERT, setup)
    aux = new_collection(COLL_AUX, setup)
    ctrl_root = new_collection(COLL_CTRL)
    fold = new_collection(COLL_CTRL_FOLD, ctrl_root)
    spread = new_collection(COLL_CTRL_SPREAD, ctrl_root)
    bend = new_collection(COLL_CTRL_BEND, ctrl_root)
    holders = new_collection(COLL_CTRL_HOLDERS, ctrl_root)
    try:
        holders.is_visible = False      # the display switch takes over once the panel exists
    except Exception as exc:
        _warn("hiding the value-holder bones", exc)
    by_category = {"flight": flight, "covert": covert, "aux": aux}
    for bone in arm.bones:
        name = bone.name
        if name.startswith(MAIN_BONE_PREFIX):
            main.assign(bone)
        elif name == CTRL_PANEL_BONE or name == CYCLE_CTRL or name.startswith(("CTRL_pose.", "CTRL_hand.")):
            holders.assign(bone)
        elif name.startswith("CTRL_spread_"):
            spread.assign(bone)
        elif name.startswith("CTRL_bend_"):
            bend.assign(bone)
        elif name.startswith("CTRL_"):
            fold.assign(bone)
        elif name.startswith(FEATHER_BONE_PREFIX):
            key = bone.get("wingrig_key", None) or name[len(FEATHER_BONE_PREFIX):].rsplit(".", 1)[0]
            by_category[feather_bone_category(key)].assign(bone)
    parented = getattr(flight, "parent", None) is not None
    return bool(parented)


# ---- custom shapes and colours --------------------------------------------------

def _ring_points(plane, count=24, radius=0.5, center=(0.0, 0.5, 0.0)):
    points = []
    for i in range(count):
        angle = math.tau * i / count
        c, s_ = math.cos(angle) * radius, math.sin(angle) * radius
        if plane == "XZ":
            points.append((center[0] + c, center[1], center[2] + s_))
        elif plane == "YZ":
            points.append((center[0], center[1] + c, center[2] + s_))
        else:
            points.append((center[0] + c, center[1] + s_, center[2]))
    return points


def _shape_geometry(kind):
    """Wire geometry (vertices, edges) in bone-local space; Y runs along the bone, 0 = head, 1 = tail."""
    verts, edges = [], []

    def add_loop(points):
        base = len(verts)
        verts.extend(points)
        edges.extend((base + i, base + (i + 1) % len(points)) for i in range(len(points)))

    if kind == "circle":
        add_loop(_ring_points("XZ"))
    elif kind == "ring_x":
        add_loop(_ring_points("YZ"))
    elif kind == "gem":
        for plane in ("XZ", "YZ", "XY"):
            add_loop(_ring_points(plane, 20))
    elif kind == "bar":
        h = 0.15
        verts.extend([(x, y, z) for y in (0.0, 1.0) for x in (-h, h) for z in (-h, h)])
        edges.extend([(0, 1), (1, 3), (3, 2), (2, 0), (4, 5), (5, 7), (7, 6), (6, 4), (0, 4), (1, 5), (2, 6), (3, 7)])
    elif kind == "diamond":
        verts.extend([(0.5, 0.5, 0.0), (0.0, 0.5, 0.5), (-0.5, 0.5, 0.0), (0.0, 0.5, -0.5), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
        edges.extend([(0, 1), (1, 2), (2, 3), (3, 0)] + [(i, 4) for i in range(4)] + [(i, 5) for i in range(4)])
    elif kind == "cross":
        verts.extend([(-0.5, 0.5, 0.0), (0.5, 0.5, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.5, -0.5), (0.0, 0.5, 0.5)])
        edges.extend([(0, 1), (2, 3), (4, 5)])
    else:
        raise ValueError(kind)
    return verts, edges


def _rig_shapes_collection(scene):
    collection = ensure_collection(SHAPE_COLLECTION, scene.collection)
    try:
        layer = bpy.context.view_layer.layer_collection.children.get(collection.name)
        if layer is not None:
            layer.hide_viewport = True
    except Exception:
        pass
    return collection


def _rig_get_shape(kind, scene):
    name = SHAPE_PREFIX + kind
    obj = bpy.data.objects.get(name)
    if obj is not None:
        return obj
    verts, edges = _shape_geometry(kind)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, edges, [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _rig_shapes_collection(scene).objects.link(obj)
    obj.hide_render = True
    return obj


def _rig_remove_shapes():
    for obj in [o for o in bpy.data.objects if o.name.startswith(SHAPE_PREFIX)]:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        try:
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        except Exception:
            pass
    collection = bpy.data.collections.get(SHAPE_COLLECTION)
    if collection is not None and not collection.objects:
        bpy.data.collections.remove(collection)


BONE_STYLE = (
    # name prefix, colour, custom shape kind (None = default bone), shape scale
    ("CTRL_fold.", (0.95, 0.20, 0.20), "bar", 1.0),
    ("CTRL_spread_", (1.00, 0.55, 0.15), "bar", 1.0),
    ("CTRL_pose.", (0.20, 0.85, 0.95), "gem", 1.4),
    ("CTRL_hand.", (0.95, 0.40, 0.70), "diamond", 1.4),
    ("CTRL_bend_", (0.60, 0.90, 0.20), "ring_x", 1.0),
    ("CTRL_cycle", (1.00, 1.00, 1.00), "circle", 1.8),
    (CTRL_PANEL_BONE, (0.85, 0.85, 0.85), "cross", 1.5),
    (MAIN_BONE_PREFIX, (0.15, 0.45, 0.95), None, 1.0),
)
FEATHER_COLORS = {"flight": (0.20, 0.80, 0.35), "covert": (0.95, 0.80, 0.20), "aux": (0.80, 0.45, 0.90)}


def _bone_style(name):
    for prefix, color, kind, scale in BONE_STYLE:
        if name.startswith(prefix):
            return color, kind, scale
    if name.startswith(FEATHER_BONE_PREFIX):
        key = name[len(FEATHER_BONE_PREFIX):].rsplit(".", 1)[0]
        return FEATHER_COLORS[feather_bone_category(key)], None, 1.0
    return None, None, 1.0


def _rig_style_pose_bones(rig):
    """Rotation mode, colour and custom shape for every bone, by its role."""
    scene = bpy.context.scene
    for pose_bone in rig.pose.bones:
        pose_bone.rotation_mode = 'XYZ'
        color, kind, scale = _bone_style(pose_bone.name)
        if color is None:
            continue
        try:
            pose_bone.color.palette = 'CUSTOM'
            pose_bone.color.custom.normal = color
            pose_bone.color.custom.select = tuple(min(1.0, c + 0.25) for c in color)
            pose_bone.color.custom.active = tuple(min(1.0, c + 0.45) for c in color)
        except Exception as exc:
            _warn("coloring control bones", exc)
        try:
            if kind is None:
                pose_bone.custom_shape = None
            else:
                pose_bone.custom_shape = _rig_get_shape(kind, scene)
                pose_bone.use_custom_shape_bone_size = True
                pose_bone.custom_shape_scale_xyz = (scale, scale, scale)
        except Exception as exc:
            _warn("assigning control bone shapes", exc)


# -----------------------------------------------------------------------------
# Step 2: main wing chain (6 bones per wing)
# -----------------------------------------------------------------------------

def _build_main_chain(scene, settings):
    """Build the six-bone chain per wing (growth order, connected) from the current model pose."""
    if _find_view3d_override() is None:
        raise RuntimeError("Run the main-chain generator from a workspace that contains a 3D View.")
    # Any previous rig and its bound meshes are cleared first so the generator can rebuild.
    _rig_remove_all(scene)
    # Make the visible procedural mesh agree with the active timeline frame.
    build_model(scene)

    state = build_state(settings)
    cycles = motion_cycles(scene, settings)
    angles = motion_angles(settings, cycles)
    specs = _main_chain_specs(state, angles)
    names = {spec["name"] for spec in specs}
    if len(names) != len(specs):
        raise RuntimeError("Main-chain bone naming conflict: duplicate names detected.")
    for spec in specs:
        parent_name = spec.get("parent_name")
        if parent_name and parent_name not in names:
            raise RuntimeError(f"Main-chain parent does not exist: {spec['name']} -> {parent_name}")
        if v_len(v_sub(spec["tail"], spec["head"])) < 1.0e-4:
            raise RuntimeError(f"Main-chain bone is too short: {spec['name']}")

    rig_collection = ensure_collection(RIG_ROOT_COLLECTION, scene.collection)
    arm_data = bpy.data.armatures.new("WING_ARCH_STAGE1_ArmatureData")
    rig = bpy.data.objects.new(RIG_OBJECT, arm_data)
    rig_collection.objects.link(rig)
    rig.show_in_front = True
    arm_data.display_type = "WIRE"
    arm_data.show_axes = False
    rig["wingrig_schema_version"] = RIG_SCHEMA
    rig["wingrig_stage"] = 1
    rig["wingrig_architecture"] = "MAIN CHAIN 6 BONES PER WING"
    rig["wingrig_pose_source_frame"] = int(scene.frame_current)
    rig["wingrig_pose_source_cycles"] = float(cycles)
    rig["wingrig_pose_source_angles_deg_json"] = json.dumps([float(a) for a in angles], separators=(",", ":"))
    rig["wingrig_stage1_main_signature"] = _main_chain_signature(specs)
    rig["wingrig_mesh_bound"] = False
    rig["wingrig_skinning_status"] = "NOT BUILT"
    try:
        with _armature_edit_session(rig) as edit_bones:
            made = {}
            # Simulate an Edit-Bone E extrusion chain: each connected child's head is the exact
            # tail of its parent; the thumb is a second connected child of the forearm.
            for spec in specs:
                bone = edit_bones.new(spec["name"])
                tail = Vector([float(v) * MM_TO_M for v in spec["tail"]])
                parent_name = spec.get("parent_name")
                if parent_name:
                    parent = made[parent_name]
                    bone.head = parent.tail.copy()
                    bone.parent = parent
                    bone.use_connect = True
                else:
                    bone.head = Vector([float(v) * MM_TO_M for v in spec["head"]])
                bone.tail = tail
                if (bone.tail - bone.head).length < 1.0e-7:
                    raise RuntimeError(f"Generated zero-length bone: {spec['name']}")
                bone.use_deform = True
                made[bone.name] = bone
            for bone in made.values():
                _align_edit_bone_roll(bone)
        for spec in specs:
            bone = arm_data.bones.get(spec["name"])
            if bone is None:
                raise RuntimeError(f"Expected main-chain bone was not created: {spec['name']}")
            bone["wingrig_role"] = spec["role"]
            bone["wingrig_layer"] = "MAIN"
            bone["wingrig_side"] = spec["side"]
            bone["wingrig_id"] = spec["stable_id"]
            bone["wingrig_schema_version"] = RIG_SCHEMA
        rig["wingrig_bone_role_manifest_json"] = json.dumps(
            [{"name": spec["name"], "role": spec["role"], "side": spec["side"],
              "parent": spec.get("parent_name") or "", "connected": bool(spec.get("connected")),
              "deform": True, "head_mm": spec["head"], "tail_mm": spec["tail"]}
             for spec in specs], ensure_ascii=False, separators=(",", ":"))
        _rig_assign_collections(rig)
        _rig_style_pose_bones(rig)
        rig["wingrig_validation"] = "MAIN CHAIN CREATED; REST-POSE AND VISUAL CHECK REQUIRED"
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        return rig, {"bones": len(specs), "chains": 2, "bones_per_wing": len(MAIN_ROLE_ORDER),
                     "frame": int(scene.frame_current), "cycles": float(cycles),
                     "angles_deg": [round(float(a), 3) for a in angles]}
    except Exception:
        delete_object_if_exists(RIG_OBJECT)
        raise


def _rig_step_main(scene, settings):
    return _build_main_chain(scene, settings)[1]


# -----------------------------------------------------------------------------
# Step 3: feather bones, parenting, bone collections, control bones
# -----------------------------------------------------------------------------

def _rig_collect_feather_specs(scene, settings):
    """Regenerate feather geometry at the current frame; one entry per feather-bone key."""
    state = build_state(settings)
    cycles = motion_cycles(scene, settings)
    angles = motion_angles(settings, cycles)
    k = fk(state, angles)
    joint_phase = joint_values(settings)[1][3]
    feather_data = generate_feathers(state, k, (cycles - joint_phase) % 1.0)
    apply_skinward_offsets(feather_data, state)
    specs = {}
    for feather in feather_data:
        key = feather_bone_key(feather.get("id", ""))
        if key is None or key in specs:
            continue
        specs[key] = {"key": key, "group": feather.get("group", ""),
                      "base": list(feather["base"]), "tip": list(feather["tip"])}
    return specs


def _feather_specs_signature(specs):
    import zlib
    rows = [(key, tuple(round(float(v), 5) for v in spec["base"]), tuple(round(float(v), 5) for v in spec["tip"]))
            for key, spec in specs.items()]
    payload = json.dumps(sorted(rows), separators=(",", ":"), ensure_ascii=True)
    return f"{zlib.crc32(payload.encode('ascii')) & 0xFFFFFFFF:08X}"


def _rig_require_source_frame(scene, rig):
    source_frame = int(rig.get("wingrig_pose_source_frame", scene.frame_current))
    if int(scene.frame_current) != source_frame:
        raise RuntimeError(f"Go back to frame {source_frame} (the frame the main bones were generated at) and retry.")


def _rig_build_feather_bones(scene, settings):
    rig = _rig_require_main_chain()
    _rig_require_source_frame(scene, rig)
    _rig_unbind_meshes(rig)
    feather_specs = _rig_collect_feather_specs(scene, settings)
    if not feather_specs:
        raise RuntimeError("No feather geometry was generated.")
    segments = {side: _rig_main_segments(rig, side) for side in SIDES}
    parent_info = {}
    with _armature_edit_session(rig) as edit_bones:
        for edit_bone in list(edit_bones):
            if edit_bone.name.startswith(FEATHER_BONE_PREFIX) or edit_bone.name.startswith("CTRL_"):
                edit_bones.remove(edit_bone)
        for side in SIDES:
            mirrored = side == "R"
            for key, spec in feather_specs.items():
                head = _mm_point(spec["base"], mirrored)
                tail = _mm_point(spec["tip"], mirrored)
                if (tail - head).length < MIN_FEATHER_BONE_LENGTH_M:
                    direction = tail - head
                    if direction.length < 1.0e-9:
                        direction = Vector((-1.0, 0.0, 0.0))
                    tail = head + direction.normalized() * MIN_FEATHER_BONE_LENGTH_M
                if spec["group"] == "alula":
                    parent_role = THUMB_ROLE
                else:
                    parent_role = _nearest_chain_role(head, segments[side])
                bone = edit_bones.new(_feather_bone_name(key, side))
                bone.head = head
                bone.tail = tail
                # Parent in Edit Mode keeps the rest position (equivalent to Ctrl+P > Keep Offset).
                bone.parent = edit_bones[_main_bone_name(parent_role, side)]
                bone.use_connect = False
                bone.use_deform = True
                _align_edit_bone_roll(bone)
                parent_info[bone.name] = (key, parent_role, spec["group"])
        # Control bones: one fold slider per wing and one panel bone that holds the switches.
        for side in SIDES:
            shoulder = segments[side][0][1]
            tip_y = segments[side][-1][2].y
            sign = 1.0 if tip_y >= 0.0 else -1.0
            ctrl = edit_bones.new(_fold_ctrl_name(side))
            ctrl.head = Vector((shoulder.x, shoulder.y + sign * 0.02, shoulder.z + 0.05))
            ctrl.tail = ctrl.head + Vector((0.0, 0.0, 0.04))
            ctrl.use_deform = False
        shoulder = segments["L"][0][1]
        panel = edit_bones.new(CTRL_PANEL_BONE)
        panel.head = Vector((shoulder.x - 0.06, 0.0, shoulder.z + 0.12))
        panel.tail = panel.head + Vector((0.0, 0.0, 0.03))
        panel.use_deform = False
    for name, (key, parent_role, group) in parent_info.items():
        bone = rig.data.bones.get(name)
        if bone is not None:
            bone["wingrig_key"] = key
            bone["wingrig_parent_role"] = parent_role
            bone["wingrig_feather_group"] = group
            bone["wingrig_layer"] = "FEATHER"
    for name in (_fold_ctrl_name("L"), _fold_ctrl_name("R"), CTRL_PANEL_BONE):
        _tag_control_bone(rig, name)
    hierarchical = _rig_assign_collections(rig)
    _rig_style_pose_bones(rig)
    rig["wingrig_stage"] = 2
    rig["wingrig_feather_signature"] = _feather_specs_signature(feather_specs)
    rig["wingrig_feather_bone_count"] = len(parent_info)
    rig["wingrig_skinning_status"] = "NOT BUILT"
    return {"feather_bones": len(parent_info), "per_wing": len(feather_specs),
            "control_bones": 3, "nested_bone_collections": hierarchical}


# -----------------------------------------------------------------------------
# Step 4: skinning (vertex groups + Armature modifier) - one feather bone per feather
# -----------------------------------------------------------------------------

def _rig_install_armature_modifier(obj, rig):
    for mod in list(obj.modifiers):
        if mod.type == 'ARMATURE':
            obj.modifiers.remove(mod)
    solids = []
    for mod in list(obj.modifiers):
        if mod.type == 'SOLIDIFY':
            solids.append((float(mod.thickness), float(mod.offset)))
            obj.modifiers.remove(mod)
    arm_mod = obj.modifiers.new(ARMATURE_MODIFIER_NAME, 'ARMATURE')
    arm_mod.object = rig
    arm_mod.use_vertex_groups = True
    arm_mod.use_bone_envelopes = False
    # The thickness modifier must come after the Armature modifier (deform first).
    for thickness, offset in solids:
        solid = obj.modifiers.new(THICKNESS_MODIFIER_NAME, 'SOLIDIFY')
        solid.thickness = thickness
        solid.offset = offset


def _rig_skin_meshes(scene, settings):
    rig = _rig_require_feather_bones()
    _rig_require_source_frame(scene, rig)
    _rig_unbind_meshes(rig)
    build_model(scene)                       # make the meshes match the rest-pose frame
    feather_specs = _rig_collect_feather_specs(scene, settings)
    if _feather_specs_signature(feather_specs) != rig.get("wingrig_feather_signature", ""):
        raise RuntimeError("Feather parameters changed after the feather bones were generated; rebuild the feather bones.")
    bone_names = set(rig.data.bones.keys())
    prepared, missing = [], set()
    for group_id, *_ in GROUP_DEFS:
        obj = bpy.data.objects.get(f"WINGGEN_Feathers_{group_id}")
        if obj is None or obj.type != 'MESH':
            raise RuntimeError(f"Feather mesh is missing: WINGGEN_Feathers_{group_id}")
        mesh = obj.data
        count = len(mesh.vertices)
        ids = json.loads(obj.get("wing_feather_ids_json", "[]"))
        index_attr = mesh.attributes.get("wing_feather_index")
        side_attr = mesh.attributes.get("wing_mirror_side")
        if index_attr is None or side_attr is None:
            raise RuntimeError(f"Feather mesh has no bind attributes: {obj.name}; rebuild the model.")
        feather_index = [0] * count
        mirror_side = [0] * count
        index_attr.data.foreach_get("value", feather_index)
        side_attr.data.foreach_get("value", mirror_side)
        groups = {}
        for vertex in range(count):
            fid = ids[feather_index[vertex]] if 0 <= feather_index[vertex] < len(ids) else None
            key = feather_bone_key(fid) if fid is not None else None
            if key is None:
                raise RuntimeError(f"Unknown feather id on {obj.name}: {fid}")
            name = _feather_bone_name(key, "R" if mirror_side[vertex] else "L")
            if name not in bone_names:
                missing.add(name)
                continue
            groups.setdefault(name, []).append(vertex)
        prepared.append((obj, groups))
    if missing:
        raise RuntimeError(f"{len(missing)} feather bones are missing (e.g. {sorted(missing)[0]}); rebuild the feather bones.")
    weighted = 0
    for obj, groups in prepared:
        for group in list(obj.vertex_groups):
            if group.name.startswith(FEATHER_BONE_PREFIX):
                obj.vertex_groups.remove(group)
        for name, indices in groups.items():
            group = obj.vertex_groups.new(name=name)
            group.add(indices, 1.0, 'REPLACE')
            weighted += len(indices)
        _rig_install_armature_modifier(obj, rig)
        obj.parent = rig
        obj.parent_type = 'OBJECT'
        obj.matrix_parent_inverse = rig.matrix_world.inverted()
    # The per-frame generator rewrites feather vertices; it must not fight the armature.
    if "wingrig_prev_python_anim" not in scene:
        scene["wingrig_prev_python_anim"] = bool(settings.python_animation_enabled)
    settings.python_animation_enabled = False
    rig["wingrig_mesh_bound"] = True
    rig["wingrig_stage"] = max(int(rig.get("wingrig_stage", 2)), 3)
    rig["wingrig_skinning_status"] = "BOUND: one deform bone per feather (weight 1.0)"
    return {"meshes": len(prepared), "weighted_vertices": weighted, "weights": "1.0 per feather bone"}


# -----------------------------------------------------------------------------
# Step 5: Armature constraints - every feather bone is weighted between the main bones
# -----------------------------------------------------------------------------

def _feather_target_weights(point, role_segments, radius_m, falloff, neighbor_cap, max_targets):
    """Weights of the main bones a feather follows.

    The nearest main bone always gets raw weight 1. A neighbouring bone only contributes when
    the feather base is within `radius_m` (extra distance beyond the nearest bone); its raw weight
    is neighbor_cap * (1 - extra/radius) ** falloff, so it decays smoothly with distance and
    both bones weigh equally exactly at a joint. Weights are normalised to sum to 1.
    """
    ranked = []
    for role, a, b in role_segments:
        dist, _t = _point_segment_distance(point, a, b)
        ranked.append((dist, role))
    ranked.sort()
    dmin, nearest = ranked[0]
    raw = [(1.0, nearest)]
    if radius_m > 1.0e-9 and neighbor_cap > 0.0:
        for dist, role in ranked[1:]:
            x = max(0.0, 1.0 - (dist - dmin) / radius_m)
            weight = neighbor_cap * (x ** falloff)
            if weight > 1.0e-3:
                raw.append((weight, role))
    raw.sort(key=lambda item: -item[0])
    raw = raw[:max(1, int(max_targets))]
    total = sum(w for w, _r in raw)
    return [(role, w / total) for w, role in raw]


def _rig_add_armature_constraints(scene, settings):
    rig = _rig_require_feather_bones()
    radius_m = max(0.0, float(settings.rig_blend_radius_mm)) * MM_TO_M
    falloff = max(0.05, float(settings.rig_blend_falloff))
    cap = clamp(float(settings.rig_blend_neighbor_pct) / 100.0, 0.0, 1.0)
    max_targets = int(settings.rig_blend_max_targets)
    # Armature constraints move the bone by themselves, so feather bones must not keep a parent
    # that would apply the same motion a second time.
    with _armature_edit_session(rig) as edit_bones:
        for edit_bone in edit_bones:
            if edit_bone.name.startswith(FEATHER_BONE_PREFIX) and edit_bone.parent is not None:
                edit_bone.use_connect = False
                edit_bone.parent = None
    for pose_bone in rig.pose.bones:
        for constraint in list(pose_bone.constraints):
            if constraint.name == ARMATURE_CONSTRAINT_NAME:
                pose_bone.constraints.remove(constraint)
    count, multi, max_seen = 0, 0, 0
    for side in SIDES:
        chain = _rig_main_segments(rig, side)
        thumb = rig.data.bones[_main_bone_name(THUMB_ROLE, side)]
        by_role = {role: (a, b) for role, a, b in chain}
        by_role[THUMB_ROLE] = (thumb.head_local.copy(), thumb.tail_local.copy())
        for bone in _rig_feather_bones(rig, side):
            if bone.get("wingrig_feather_group", "") == "alula":
                roles = (THUMB_ROLE, "palm", "forearm")
            else:
                roles = MAIN_CHAIN_ROLES
            candidates = [(role,) + by_role[role] for role in roles]
            targets = _feather_target_weights(bone.head_local, candidates, radius_m, falloff, cap, max_targets)
            bone["wingrig_targets_json"] = json.dumps([[role, round(weight, 5)] for role, weight in targets])
            pose_bone = rig.pose.bones[bone.name]
            constraint = pose_bone.constraints.new('ARMATURE')
            constraint.name = ARMATURE_CONSTRAINT_NAME
            for role, weight in targets:
                item = constraint.targets.new()
                item.target = rig
                item.subtarget = _main_bone_name(role, side)
                item.weight = weight
            # Keep an existing fold Action constraint at the top of the stack.
            for index, other in enumerate(list(pose_bone.constraints)):
                if other.name == FOLD_CONSTRAINT_NAME and index != 0:
                    pose_bone.constraints.move(index, 0)
            count += 1
            multi += 1 if len(targets) > 1 else 0
            max_seen = max(max_seen, len(targets))
    rig["wingrig_stage"] = max(int(rig.get("wingrig_stage", 2)), 4)
    return {"armature_constraints": count, "blended_feathers": multi, "max_targets_used": max_seen,
            "radius_mm": round(radius_m / MM_TO_M, 2), "falloff": falloff, "neighbor_cap_pct": round(cap * 100.0, 1)}


def _strip_modifiers(fcurve):
    """Drop the default generator modifiers Blender may attach to a fresh driver F-curve."""
    try:
        for modifier in list(fcurve.modifiers):
            fcurve.modifiers.remove(modifier)
    except Exception:
        pass


def _bind_var(driver, name, rig, data_path):
    """Add a driver variable that reads one custom property path of the rig object."""
    variable = driver.variables.new()
    variable.name = name
    variable.type = 'SINGLE_PROP'
    target = variable.targets[0]
    target.id_type = 'OBJECT'
    target.id = rig
    target.data_path = data_path
    return variable


def _set_prop_ui(pose_bone, prop, lo, hi, default):
    """Give a custom property real UI limits (best effort: older API builds may refuse)."""
    try:
        pose_bone.id_properties_ui(prop).update(
            min=lo, max=hi, soft_min=lo, soft_max=hi, default=default, step=1, precision=2)
    except Exception:
        pass


def _tag_control_bone(rig, name):
    bone = rig.data.bones.get(name)
    if bone is not None:
        bone["wingrig_layer"] = "CONTROL"


def _bone_key(bone):
    """Feather key stored on the bone, with a fallback derived from the bone name."""
    return bone.get("wingrig_key", None) or bone.name[len(FEATHER_BONE_PREFIX):].rsplit(".", 1)[0]


def _rig_place_before_armature(pose_bone):
    """Keep the Armature blend constraint last: move the newest constraint just before it."""
    stack = list(pose_bone.constraints)
    armature_index = next((i for i, c in enumerate(stack) if c.name == ARMATURE_CONSTRAINT_NAME), None)
    if armature_index is not None:
        pose_bone.constraints.move(len(stack) - 1, armature_index)


def _rig_setup_base_control(rig, ctrl_name, kind, range_value):
    """Make a single-axis controller bone the source of truth.

    kind "loc_y": local Y position (fold, row spread); kind "rot_x": local X rotation (bend). The bone can
    be dragged in the viewport (its Limit constraint clamps it); the panel slider (wing_slider /
    wing_slider_pos) reads and writes the very same transform, so both always agree.
    """
    pose_bone = rig.pose.bones[ctrl_name]
    pose_bone["wingrig_ctl"] = kind
    pose_bone["wingrig_ctl_range"] = float(range_value)
    if kind == "loc_y":
        _rig_remove_drivers_matching(rig, f'pose.bones["{ctrl_name}"].location')
        pose_bone.location[1] = 0.0
    else:
        pose_bone.rotation_mode = 'XYZ'
        _rig_remove_drivers_matching(rig, f'pose.bones["{ctrl_name}"].rotation_euler')
        pose_bone.rotation_euler[0] = 0.0


def _ctl_get(pose_bone):
    """Normalised value of a base controller (transform / range)."""
    kind = pose_bone.get("wingrig_ctl", "")
    scale = float(pose_bone.get("wingrig_ctl_range", 0.0)) or 1.0
    if kind == "loc_y":
        return pose_bone.location[1] / scale
    if kind == "rot_x":
        return pose_bone.rotation_euler[0] / scale
    return 0.0


def _ctl_set(pose_bone, value):
    kind = pose_bone.get("wingrig_ctl", "")
    scale = float(pose_bone.get("wingrig_ctl_range", 0.0)) or 1.0
    if kind == "loc_y":
        pose_bone.location[1] = value * scale
    elif kind == "rot_x":
        pose_bone.rotation_euler[0] = value * scale


def _ctl_property(minimum):
    """Registered PoseBone property: a slider view of the controller bone's own transform."""
    return FloatProperty(
        name="控制器值",
        min=minimum, max=1.0, precision=3,
        get=lambda self: clamp(_ctl_get(self), minimum, 1.0),
        set=lambda self, value: _ctl_set(self, value), options=set())


# Row-spread controllers, in anatomical order. Primary / greater coverts have no row of their own:
# they follow the flight feather they overlay.
SPREAD_ROW_LABELS = {
    "P": "初级飞羽", "S": "次级飞羽", "T": "三级飞羽", "MC": "中覆羽",
    "LC": "小覆羽", "LCM": "缘覆羽", "PMC": "掌区中覆羽", "AX": "腋羽", "AL": "小翼羽",
}


def _draw_ctl_rows(box, rig, holder_name, label, rna_prop):
    """One slider row for a base controller, left and right wing side by side (single slider when linked)."""
    sliders = [(side, rig.pose.bones.get(holder_name(side))) for side in SIDES]
    sliders = [(side, holder) for side, holder in sliders if holder is not None and holder.get("wingrig_ctl")]
    if not sliders:
        return
    linked = len(sliders) == 2 and bool(rig.get("wingrig_lr_linked", False))
    if linked:
        sliders = sliders[:1]
    column = box.column(align=True)
    column.label(text=label)
    row = column.row(align=True)
    for side, holder in sliders:
        row.prop(holder, rna_prop, text="左右联动" if linked else ("左" if side == "L" else "右"), slider=True)


def _rig_remove_driver_channel(rig, data_path, index):
    anim = rig.animation_data
    if anim is None:
        return
    for fcurve in list(anim.drivers):
        if fcurve.data_path == data_path and fcurve.array_index == index:
            try:
                anim.drivers.remove(fcurve)
            except Exception as exc:
                _warn("removing an old driver", exc)


def _rig_add_channel_driver(rig, pose_bone, index, holder_name, prop, gain, cycle_path=None, fade_path=None):
    """Drive pose_bone.rotation_euler[index] = (slider [+ cycle]) * gain [* fold fade]; other channels stay untouched."""
    pose_bone.rotation_mode = 'XYZ'
    _rig_remove_driver_channel(rig, f'pose.bones["{pose_bone.name}"].rotation_euler', index)
    fcurve = pose_bone.driver_add("rotation_euler", index)
    _strip_modifiers(fcurve)
    driver = fcurve.driver
    driver.type = 'SCRIPTED'
    _bind_var(driver, "v", rig, f'pose.bones["{holder_name}"]["{prop}"]')
    source = "v"
    if cycle_path:
        _bind_var(driver, "cyc", rig, cycle_path)
        source = "(v+cyc)"
    expression = f"{source}*{gain:.6f}"
    if fade_path:
        _bind_var(driver, "hf", rig, fade_path)
        expression += "*hf"
    driver.expression = expression


def _rig_make_holder_props(holder, props):
    holder.lock_location = (True, True, True)
    holder.lock_rotation = (True, True, True)
    holder.lock_scale = (True, True, True)
    for prop in props:
        holder[prop] = 0.0
        _set_prop_ui(holder, prop, -1.0, 1.0, 0.0)


def _bone_prop_path(fold_ctrl, prop):
    return f'pose.bones["{fold_ctrl}"]["{prop}"]'


def _ensure_fold_fade(rig, side, settings, apply=False):
    """Create the shared fold-fade values on CTRL_fold.<side> (safe to call from any build step).

    fold      - 0..1 value read from the fold control bone's Y position (output, never typed in)
    fade_end  - fold value at which fan spread / bend / hand layers are fully faded out
    hand_keep - share of the wrist/finger layer that survives a full fold
    The outputs spread_fade, hand_fade and fan_fade are drivers of `fold`; constraint influences and
    channel drivers read them, so changing fade_end / hand_keep takes effect live. With apply=True the
    two inputs are reset from the scene settings, otherwise existing (possibly hand-tuned) values stay.
    """
    ctrl_name = _fold_ctrl_name(side)
    holder = rig.pose.bones[ctrl_name]
    holder["wingrig_ctl"] = "loc_y"
    holder["wingrig_ctl_range"] = FOLD_CTRL_RANGE_M
    if "fold" not in holder.keys():
        holder["fold"] = 0.0
        _set_prop_ui(holder, "fold", 0.0, 1.0, 0.0)
    _rig_remove_drivers_matching(rig, _bone_prop_path(ctrl_name, "fold"))
    fcurve = holder.driver_add('["fold"]')
    _strip_modifiers(fcurve)
    driver = fcurve.driver
    driver.type = 'SCRIPTED'
    _bind_var(driver, "v", rig, f'pose.bones["{ctrl_name}"].location[1]')
    driver.expression = f"max(0,min(1,v/{FOLD_CTRL_RANGE_M}))"
    if apply or "fade_end" not in holder.keys():
        holder["fade_end"] = clamp(float(settings.rig_fold_spread_end), 0.05, 1.0)
        _set_prop_ui(holder, "fade_end", 0.05, 1.0, 0.5)
    if apply or "hand_keep" not in holder.keys():
        holder["hand_keep"] = clamp(float(settings.rig_fold_hand_keep_pct) / 100.0, 0.0, 1.0)
        _set_prop_ui(holder, "hand_keep", 0.0, 1.0, 0.0)
    outputs = {
        "spread_fade": ("max(0,1-fold/max(fade_end,0.05))", ("fold", "fade_end")),
        "hand_fade": ("hand_keep+(1-hand_keep)*max(0,1-fold/max(fade_end,0.05))", ("fold", "fade_end", "hand_keep")),
        "fan_fade": ("1-min(1,max(0,fold))", ("fold",)),
    }
    for prop, (expression, names) in outputs.items():
        _rig_remove_drivers_matching(rig, _bone_prop_path(ctrl_name, prop))
        holder[prop] = 1.0
        fcurve = holder.driver_add(f'["{prop}"]')
        _strip_modifiers(fcurve)
        driver = fcurve.driver
        driver.type = 'SCRIPTED'
        for name in names:
            _bind_var(driver, name, rig, _bone_prop_path(ctrl_name, name))
        driver.expression = expression


def _drive_influence(rig, constraint, fold_ctrl, fade_prop, base=1.0):
    """constraint.influence = base * <fade value stored on the fold control bone>."""
    fcurve = constraint.driver_add("influence")
    _strip_modifiers(fcurve)
    driver = fcurve.driver
    driver.type = 'SCRIPTED'
    _bind_var(driver, "f", rig, _bone_prop_path(fold_ctrl, fade_prop))
    driver.expression = f"{base:.4f}*f"


def _rig_attach_fold_fade(rig):
    """(Re)drive every row-spread and bend constraint with the fade value of its wing side."""
    _rig_remove_drivers_matching(rig, f'constraints["{SPREAD_CONSTRAINT_NAME}"].influence')
    _rig_remove_drivers_matching(rig, 'constraints["WING_Bend')
    counts = {"spread": 0, "bend": 0}
    for pose_bone in rig.pose.bones:
        side = pose_bone.name.rsplit(".", 1)[-1]
        if side not in SIDES:
            continue
        data_bone = rig.data.bones.get(pose_bone.name)
        raw = data_bone.get("wingrig_bend_weights_json", None) if data_bone is not None else None
        weights = json.loads(raw) if raw else {}
        for constraint in pose_bone.constraints:
            if constraint.name == SPREAD_CONSTRAINT_NAME:
                kind, base = "spread", 1.0
            else:
                match = re.match(r"^WING_Bend(\d)$", constraint.name)
                if not match or match.group(1) not in weights:
                    continue
                kind, base = "bend", float(weights[match.group(1)])
            _drive_influence(rig, constraint, _fold_ctrl_name(side), "spread_fade", base)
            counts[kind] += 1
    return counts


_CTL_CHANNELS = {"loc_y": ("location", 1), "rot_x": ("rotation_euler", 0)}


def _rig_link_pairs(rig):
    """(left bone, right bone, channel) for every control present on both wings.

    channel is a custom-property name (pose, hand, fold fade) or "loc_y" / "rot_x" for a base
    controller's own transform (fold, row spread, bend)."""
    pairs = []

    def both(holder_of):
        left, right = rig.pose.bones.get(holder_of("L")), rig.pose.bones.get(holder_of("R"))
        return (left, right) if left is not None and right is not None else (None, None)

    def add_props(holder_of, props):
        left, right = both(holder_of)
        if left is not None:
            pairs.extend((left.name, right.name, prop) for prop in props if prop in left.keys() and prop in right.keys())

    def add_ctl(holder_of):
        left, right = both(holder_of)
        if left is not None and left.get("wingrig_ctl") and left.get("wingrig_ctl") == right.get("wingrig_ctl"):
            pairs.append((left.name, right.name, left["wingrig_ctl"]))

    add_props(_pose_ctrl_name, POSE_PROPS)
    add_props(_hand_ctrl_name, HAND_PROPS)
    add_props(_fold_ctrl_name, ("fade_end", "hand_keep"))
    add_ctl(_fold_ctrl_name)
    rows = sorted({pb.name[len("CTRL_spread_"):].rsplit(".", 1)[0] for pb in rig.pose.bones
                   if pb.name.startswith("CTRL_spread_")})
    for row in rows:
        add_ctl(lambda side, row=row: _spread_ctrl_name(row, side))
    for zone in BEND_ZONES:
        add_ctl(lambda side, zone=zone: _bend_ctrl_name(zone, side))
    return pairs


def _rig_apply_lr_link(rig, enable):
    """Drive every right-wing control from its left-wing twin (enable) or release them (disable)."""
    pairs = _rig_link_pairs(rig)
    for left, right, channel in pairs:
        target = rig.pose.bones[right]
        if channel in _CTL_CHANNELS:
            attr, index = _CTL_CHANNELS[channel]
            _rig_remove_driver_channel(rig, f'pose.bones["{right}"].{attr}', index)
            source = f'pose.bones["{left}"].{attr}[{index}]'
            fcurve = target.driver_add(attr, index) if enable else None
        else:
            _rig_remove_drivers_matching(rig, _bone_prop_path(right, channel))
            source = _bone_prop_path(left, channel)
            fcurve = target.driver_add(f'["{channel}"]') if enable else None
        if fcurve is not None:
            _strip_modifiers(fcurve)
            driver = fcurve.driver
            driver.type = 'SCRIPTED'
            _bind_var(driver, "l", rig, source)
            driver.expression = "l"
    rig["wingrig_lr_linked"] = bool(enable)
    return len(pairs)


def _rig_refresh_lr_link():
    """After any build step: if the wings are linked, re-attach the link to whatever now exists."""
    rig = bpy.data.objects.get(RIG_OBJECT)
    if rig is not None and rig.type == "ARMATURE" and rig.get("wingrig_lr_linked", False):
        _rig_apply_lr_link(rig, True)


class WING_OT_KeyBaseControls(bpy.types.Operator):
    bl_idname = "wing_model.key_base_controls"
    bl_label = "给基础控制器打关键帧"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = bpy.data.objects.get(RIG_OBJECT)
        if not (rig and rig.type == "ARMATURE"):
            self.report({'ERROR'}, "尚未生成骨架")
            return {'CANCELLED'}
        linked = bool(rig.get("wingrig_lr_linked", False))
        count = 0
        for pose_bone in rig.pose.bones:
            channel = pose_bone.get("wingrig_ctl")
            if channel not in _CTL_CHANNELS or (linked and pose_bone.name.endswith(".R")):
                continue   # linked right-wing controllers are driven by the left ones
            attr, index = _CTL_CHANNELS[channel]
            try:
                pose_bone.keyframe_insert(attr, index=index)
                count += 1
            except Exception as exc:
                _warn("keyframing a controller", exc)
        self.report({'INFO'}, f"已为 {count} 个控制骨插入关键帧")
        return {'FINISHED'}


def _has_controller_keys(rig):
    """True when the rig's action already animates a controller (a reset would be overwritten on frame change)."""
    try:
        return any(fc.data_path.startswith('pose.bones["CTRL_') for fc in rig.animation_data.action.fcurves)
    except Exception:
        return False


class WING_OT_ResetRigPose(bpy.types.Operator):
    bl_idname = "wing_model.reset_rig_pose"
    bl_label = "回归平摊姿态"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = bpy.data.objects.get(RIG_OBJECT)
        if not (rig and rig.type == "ARMATURE"):
            self.report({'ERROR'}, "尚未生成骨架")
            return {'CANCELLED'}
        linked = bool(rig.get("wingrig_lr_linked", False))
        count = 0
        for pose_bone in rig.pose.bones:
            if linked and pose_bone.name.endswith(".R"):
                continue   # right-wing controllers follow the left ones
            channel = pose_bone.get("wingrig_ctl")
            if channel in _CTL_CHANNELS:
                attr, index = _CTL_CHANNELS[channel]
                getattr(pose_bone, attr)[index] = 0.0
                count += 1
            elif pose_bone.name.startswith(("CTRL_pose.", "CTRL_hand.")):
                for prop in POSE_PROPS + HAND_PROPS:
                    if prop in pose_bone.keys():
                        pose_bone[prop] = 0.0
                        count += 1
        cycle = rig.pose.bones.get(CYCLE_CTRL)
        if cycle is not None and "cycle_on" in cycle.keys():
            cycle["cycle_on"] = 0.0
            count += 1
        context.view_layer.update()
        if _has_controller_keys(rig):
            self.report({'WARNING'}, f"已归位 {count} 项，但控制器有关键帧")
        else:
            self.report({'INFO'}, f"已归位 {count} 项")
        return {'FINISHED'}


class WING_OT_TogglePythonPlayback(bpy.types.Operator):
    bl_idname = "wing_model.toggle_python_playback"
    bl_label = "开始 / 停止 Python 动画"

    def execute(self, context):
        settings = context.scene.wing_model_settings
        screen = context.screen
        if screen is not None and screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
            settings.python_animation_enabled = False
        else:
            settings.python_animation_enabled = True
            bpy.ops.screen.animation_play()
        return {'FINISHED'}


class WING_OT_TogglePlayback(bpy.types.Operator):
    bl_idname = "wing_model.toggle_playback"
    bl_label = "播放 / 暂停"

    def execute(self, context):
        bpy.ops.screen.animation_play()
        return {'FINISHED'}


class WING_OT_SetLRLink(bpy.types.Operator):
    bl_idname = "wing_model.set_lr_link"
    bl_label = "左右联动"
    bl_options = {'REGISTER', 'UNDO'}
    enable: BoolProperty(default=True)

    def execute(self, context):
        rig = bpy.data.objects.get(RIG_OBJECT)
        if not (rig and rig.type == "ARMATURE"):
            self.report({'ERROR'}, "尚未生成骨架")
            return {'CANCELLED'}
        count = _rig_apply_lr_link(rig, self.enable)
        self.report({'INFO'}, f"左右联动已{'开启' if self.enable else '关闭'}：{count} 个滑块")
        return {'FINISHED'}


def _rig_store_mix(rig, kind, side, gains):
    """Remember {bone: {prop: (euler index, gain)}} so the channel drivers can be rebuilt at any time."""
    rig[f"wingrig_mix_{kind}_{side}"] = json.dumps(
        {bone: {prop: [index, gain] for prop, (index, gain) in channels.items()} for bone, channels in gains.items()})


def _rig_refresh_mixers(rig, settings, kinds=("pose", "hand")):
    """(Re)create every pose / hand channel driver from the stored gains.

    Optional layers are attached when their source exists: the cycle output (CTRL_cycle) for the
    channels it animates, and the hand fold fade (CTRL_fold.<side>) for the wrist / finger channels.
    """
    stats = {"drivers": 0, "cycle": 0, "fold": 0}
    cycle = rig.pose.bones.get(CYCLE_CTRL)
    for kind in kinds:
        holder_of = _pose_ctrl_name if kind == "pose" else _hand_ctrl_name
        for side in SIDES:
            raw = rig.get(f"wingrig_mix_{kind}_{side}", None)
            holder = holder_of(side)
            if not raw or holder not in rig.pose.bones:
                continue
            fold_ctrl = _fold_ctrl_name(side)
            fade_path = None
            if kind == "hand" and fold_ctrl in rig.pose.bones:
                _ensure_fold_fade(rig, side, settings)
                fade_path = _bone_prop_path(fold_ctrl, "hand_fade")
            for bone_name, channels in json.loads(raw).items():
                pose_bone = rig.pose.bones.get(bone_name)
                if pose_bone is None:
                    continue
                pose_bone.rotation_mode = 'XYZ'
                for prop, (index, gain) in channels.items():
                    out_prop = f"out_{side}_{prop}"
                    cycle_path = None
                    if cycle is not None and CYCLE_OUTPUTS.get(prop) == kind and out_prop in cycle.keys():
                        cycle_path = f'pose.bones["{CYCLE_CTRL}"]["{out_prop}"]'
                    _rig_add_channel_driver(rig, pose_bone, index, holder, prop, gain, cycle_path, fade_path)
                    stats["drivers"] += 1
                    stats["cycle"] += cycle_path is not None
                    stats["fold"] += fade_path is not None
    return stats


def _pose_ctrl_name(side):
    return f"CTRL_pose.{side}"


POSE_PROPS = ("sweep", "flap", "pitch", "twist")


def _rig_pose_gains(rig, side, settings):
    """Per main bone, radians per slider unit for each euler channel.

    Positive slider values mean: sweep = wing swept back, flap = wing raised,
    pitch / twist = leading edge up (twist grows progressively toward the fingertip).
    Axes: local Z is world up (bone roll), local X lifts the tip, local Y is the span axis.
    """
    sweep = math.radians(float(settings.rig_pose_sweep_deg))
    flap = math.radians(float(settings.rig_pose_flap_deg))
    pitch = math.radians(float(settings.rig_pose_pitch_deg))
    twist = math.radians(float(settings.rig_pose_twist_deg))
    gains = {}
    for role in MAIN_CHAIN_ROLES:
        bone = rig.data.bones[_main_bone_name(role, side)]
        d = bone.tail_local - bone.head_local
        lateral = Vector((d.y, -d.x, 0.0))            # d x (0,0,1): the bone's local X axis
        pitch_sign = -1.0 if lateral.x > 0.0 else 1.0
        entry = {}
        if role == "humerus":
            entry["sweep"] = (2, (1.0 if d.y > 0.0 else -1.0) * sweep)
            entry["flap"] = (0, flap)
            entry["pitch"] = (1, pitch_sign * pitch)
        share = TWIST_SHARE.get(role)
        if share:
            entry["twist"] = (1, pitch_sign * twist * share)
        gains[bone.name] = entry
    return gains


def _rig_build_pose_controls(scene, settings):
    """Whole-wing pose controllers: sweep, flap, pitch and a progressive twist per wing."""
    rig = _rig_require_feather_bones()
    segments = {side: _rig_main_segments(rig, side) for side in SIDES}
    with _armature_edit_session(rig) as edit_bones:
        for edit_bone in list(edit_bones):
            if edit_bone.name.startswith("CTRL_pose."):
                edit_bones.remove(edit_bone)
        for side in SIDES:
            shoulder = segments[side][0][1]
            sign = 1.0 if segments[side][-1][2].y >= 0.0 else -1.0
            ctrl = edit_bones.new(_pose_ctrl_name(side))
            ctrl.head = Vector((shoulder.x, shoulder.y + sign * 0.03, shoulder.z + 0.10))
            ctrl.tail = ctrl.head + Vector((0.0, 0.0, 0.03))
            ctrl.use_deform = False
    for side in SIDES:
        ctrl_name = _pose_ctrl_name(side)
        _tag_control_bone(rig, ctrl_name)
        _rig_make_holder_props(rig.pose.bones[ctrl_name], POSE_PROPS)
        _rig_store_mix(rig, "pose", side, _rig_pose_gains(rig, side, settings))
    drivers = _rig_refresh_mixers(rig, settings, ("pose",))["drivers"]
    _rig_assign_collections(rig)
    _rig_style_pose_bones(rig)
    return {"pose_controllers": 2, "drivers": drivers, "channels": list(POSE_PROPS)}


HAND_PROPS = ("wrist_flex", "wrist_sweep", "finger_curl", "finger_sweep", "thumb_open", "thumb_flex")


def _hand_ctrl_name(side):
    return f"CTRL_hand.{side}"


def _rig_hand_gains(rig, side, settings):
    """{bone: {prop: (euler index, radians per slider unit)}} for wrist, fingers and thumb.

    Positive values: flex / curl / thumb_flex = tip up (rotation about local X, always lifts the tip),
    wrist_sweep / finger_sweep = swept back, thumb_open = thumb swings away from the palm.
    The second phalanx follows the first at `rig_digit2_ratio`.
    """
    bones = rig.data.bones

    def direction(role):
        bone = bones[_main_bone_name(role, side)]
        return bone.tail_local - bone.head_local

    def back_sign(role):
        return 1.0 if direction(role).y > 0.0 else -1.0

    def angle(role):
        d = direction(role)
        return math.atan2(d.y, d.x)

    flex = math.radians(float(settings.rig_wrist_flex_deg))
    wsweep = math.radians(float(settings.rig_wrist_sweep_deg))
    curl = math.radians(float(settings.rig_finger_curl_deg))
    fsweep = math.radians(float(settings.rig_finger_sweep_deg))
    t_open = math.radians(float(settings.rig_thumb_open_deg))
    t_flex = math.radians(float(settings.rig_thumb_flex_deg))
    ratio = float(settings.rig_digit2_ratio)
    open_sign = 1.0 if _wrap_angle(angle(THUMB_ROLE) - angle("palm")) >= 0.0 else -1.0
    return {
        _main_bone_name("palm", side): {"wrist_flex": (0, flex), "wrist_sweep": (2, back_sign("palm") * wsweep)},
        _main_bone_name("digit1", side): {"finger_curl": (0, curl), "finger_sweep": (2, back_sign("digit1") * fsweep)},
        _main_bone_name("digit2", side): {"finger_curl": (0, curl * ratio), "finger_sweep": (2, back_sign("digit2") * fsweep * ratio)},
        _main_bone_name(THUMB_ROLE, side): {"thumb_open": (2, open_sign * t_open), "thumb_flex": (0, t_flex)},
    }


def _rig_build_hand_controls(scene, settings):
    """Wrist / finger / thumb controllers: one holder bone per wing with six -1..1 sliders."""
    rig = _rig_require_feather_bones()
    wrists = {side: rig.data.bones[_main_bone_name("palm", side)].head_local.copy() for side in SIDES}
    signs = {side: (1.0 if rig.data.bones[_main_bone_name("digit2", side)].tail_local.y >= 0.0 else -1.0)
             for side in SIDES}
    with _armature_edit_session(rig) as edit_bones:
        for edit_bone in list(edit_bones):
            if edit_bone.name.startswith("CTRL_hand."):
                edit_bones.remove(edit_bone)
        for side in SIDES:
            ctrl = edit_bones.new(_hand_ctrl_name(side))
            ctrl.head = wrists[side] + Vector((0.0, signs[side] * 0.03, 0.09))
            ctrl.tail = ctrl.head + Vector((0.0, 0.0, 0.03))
            ctrl.use_deform = False
    for side in SIDES:
        name = _hand_ctrl_name(side)
        _tag_control_bone(rig, name)
        _rig_make_holder_props(rig.pose.bones[name], HAND_PROPS)
        _rig_store_mix(rig, "hand", side, _rig_hand_gains(rig, side, settings))
    drivers = _rig_refresh_mixers(rig, settings, ("hand",))["drivers"]
    _rig_assign_collections(rig)
    _rig_style_pose_bones(rig)
    return {"hand_controllers": 2, "drivers": drivers, "channels": list(HAND_PROPS)}


# -----------------------------------------------------------------------------
# Step 5b: per-row fan-spread controllers (P / S / T / coverts ...)
# -----------------------------------------------------------------------------

def _spread_ctrl_name(row, side):
    return f"CTRL_spread_{row}.{side}"


def _rig_spread_plan(rig, side, max_angle):
    """Plan the fan-spread rotation of every feather in each row.

    Feathers of a row are ordered from the shoulder to the fingertip. The centre feather stays
    put (offset 0) and the two ends rotate by +-max_angle, growing linearly. The sign is taken
    from the rest directions, so a positive slider value always opens the fan on both wings.
    Primary/greater coverts reuse the angle of the flight feather they overlay.
    """
    segments = _rig_main_segments(rig, side)
    feathers, rows = {}, {}
    for bone in _rig_feather_bones(rig, side):
        key = _bone_key(bone)
        feathers[key] = bone
    for key, bone in feathers.items():
        if re.match(r"^[SPT]\d+$", key):
            row = key[0]
        elif re.match(r"^(PC|GC)_", key):
            continue
        else:
            row = re.match(r"^([A-Za-z]+)", key).group(1)
        rows.setdefault(row, []).append((_chain_param(bone.head_local, segments), key, bone))

    def direction_angle(bone):
        d = bone.tail_local - bone.head_local
        return math.atan2(d.y, d.x)

    plan, theta_by_key = {}, {}
    for row, items in rows.items():
        items.sort(key=lambda item: item[0])
        n = len(items)
        if n < 2:
            continue
        slope = 1.0 if _wrap_angle(direction_angle(items[-1][2]) - direction_angle(items[0][2])) >= 0.0 else -1.0
        members = []
        for i, (_param, key, bone) in enumerate(items):
            offset = (i - (n - 1) / 2.0) / ((n - 1) / 2.0)
            theta = slope * offset * max_angle
            theta_by_key[key] = theta
            members.append((bone.name, theta))
        plan[row] = {"members": members, "anchor": items[n // 2][2].head_local.copy()}
    for key, bone in feathers.items():
        match = re.match(r"^(PC|GC)_(.+)$", key)
        if match and match.group(2) in theta_by_key:
            source_key = match.group(2)
            row = source_key[0]
            if row in plan:
                plan[row]["members"].append((bone.name, theta_by_key[source_key]))
    return plan


def _rig_build_spread_controls(scene, settings):
    rig = _rig_require_feather_bones()
    for side in SIDES:
        _ensure_fold_fade(rig, side, settings)
    max_angle = math.radians(float(settings.rig_spread_max_angle_deg))
    plans = {side: _rig_spread_plan(rig, side, max_angle) for side in SIDES}
    with _armature_edit_session(rig) as edit_bones:
        for edit_bone in list(edit_bones):
            if edit_bone.name.startswith("CTRL_spread_"):
                edit_bones.remove(edit_bone)
        for side in SIDES:
            for row, data in plans[side].items():
                ctrl = edit_bones.new(_spread_ctrl_name(row, side))
                ctrl.head = data["anchor"] + Vector((0.0, 0.0, 0.05))
                ctrl.tail = ctrl.head + Vector((0.0, 0.0, 0.03))
                ctrl.use_deform = False
    for pose_bone in rig.pose.bones:
        for constraint in list(pose_bone.constraints):
            if constraint.name in (SPREAD_CONSTRAINT_NAME, SPREAD_LIMIT_NAME):
                pose_bone.constraints.remove(constraint)
    count = 0
    for side in SIDES:
        for row, data in plans[side].items():
            name = _spread_ctrl_name(row, side)
            _tag_control_bone(rig, name)
            ctrl = rig.pose.bones[name]
            ctrl.lock_location = (True, False, True)
            ctrl.lock_rotation = (True, True, True)
            ctrl.lock_scale = (True, True, True)
            limit = ctrl.constraints.new('LIMIT_LOCATION')
            limit.name = SPREAD_LIMIT_NAME
            limit.use_min_y = True
            limit.min_y = -SPREAD_CTRL_RANGE_M
            limit.use_max_y = True
            limit.max_y = SPREAD_CTRL_RANGE_M
            limit.owner_space = 'LOCAL'
            try:
                limit.use_transform_limit = True
            except Exception:
                pass
            _rig_setup_base_control(rig, name, "loc_y", SPREAD_CTRL_RANGE_M)
            for member_name, theta in data["members"]:
                pose_bone = rig.pose.bones[member_name]
                constraint = pose_bone.constraints.new('TRANSFORM')
                constraint.name = SPREAD_CONSTRAINT_NAME
                constraint.target = rig
                constraint.subtarget = name
                constraint.map_from = 'LOCATION'
                constraint.from_min_y = -SPREAD_CTRL_RANGE_M
                constraint.from_max_y = SPREAD_CTRL_RANGE_M
                constraint.map_to = 'ROTATION'
                constraint.map_to_z_from = 'Y'
                constraint.to_min_z_rot = -theta
                constraint.to_max_z_rot = theta
                constraint.target_space = 'LOCAL'
                constraint.owner_space = 'LOCAL'
                try:
                    constraint.mix_mode_rot = 'ADD'
                except Exception:
                    pass
                # Stack order: fold Action -> fan spread -> Armature blend.
                _rig_place_before_armature(pose_bone)
                count += 1
    _rig_attach_fold_fade(rig)
    _rig_assign_collections(rig)
    _rig_style_pose_bones(rig)
    rig["wingrig_stage"] = max(int(rig.get("wingrig_stage", 2)), 4)
    return {"row_controllers": sum(len(p) for p in plans.values()), "spread_constraints": count,
            "max_angle_deg": float(settings.rig_spread_max_angle_deg)}


# -----------------------------------------------------------------------------
# Step 5: Copy Rotation fan-follow constraints
# -----------------------------------------------------------------------------

def _add_fan_constraint(rig, owner_name, source_name, base_influence, ctrl_name):
    pose_bone = rig.pose.bones[owner_name]
    constraint = pose_bone.constraints.new('COPY_ROTATION')
    constraint.name = FAN_CONSTRAINT_NAME
    constraint.target = rig
    constraint.subtarget = source_name
    constraint.use_x = True
    constraint.use_y = True
    constraint.use_z = True
    constraint.owner_space = 'LOCAL'
    constraint.target_space = 'LOCAL'
    constraint.influence = base_influence
    _drive_influence(rig, constraint, ctrl_name, "fan_fade", base_influence)


def _rig_add_fan_constraints(scene, settings):
    rig = _rig_require_feather_bones()
    follow = clamp(float(settings.rig_fan_follow_pct) / 100.0, 0.0, 1.0)
    for side in SIDES:
        _ensure_fold_fade(rig, side, settings)
    _rig_remove_drivers_matching(rig, f'constraints["{FAN_CONSTRAINT_NAME}"]')
    for pose_bone in rig.pose.bones:
        for constraint in list(pose_bone.constraints):
            if constraint.name == FAN_CONSTRAINT_NAME:
                pose_bone.constraints.remove(constraint)
    count = 0
    roots = []
    for side in SIDES:
        segments = _rig_main_segments(rig, side)
        ctrl_name = _fold_ctrl_name(side)
        flight, covert_follow, rows = [], [], {}
        for bone in _rig_feather_bones(rig, side):
            key = _bone_key(bone)
            param = _chain_param(bone.head_local, segments)
            if re.match(r"^[SPT]\d+$", key):
                flight.append((param, bone.name))
                continue
            match = re.match(r"^(PC|GC)_(.+)$", key)
            if match:
                covert_follow.append((bone.name, _feather_bone_name(match.group(2), side)))
                continue
            rows.setdefault(re.match(r"^([A-Za-z]+)", key).group(1), []).append((param, bone.name))
        # Backbone: T, S and P feathers form ONE continuous chain from the shoulder to the
        # fingertip, so there is no break at the group boundaries.
        flight.sort()
        if not flight:
            continue
        roots.append(flight[0][1])
        for i in range(1, len(flight)):
            _add_fan_constraint(rig, flight[i][1], flight[i - 1][1], follow, ctrl_name)
            count += 1
        flight_names = [name for _p, name in flight]
        # Coverts that overlay a flight feather copy that feather.
        for owner, source in covert_follow:
            if source not in rig.data.bones:
                source = min(flight_names, key=lambda n: (rig.data.bones[n].head_local - rig.data.bones[owner].head_local).length)
            _add_fan_constraint(rig, owner, source, COVERT_FOLLOW, ctrl_name)
            count += 1
        # Every other row chains internally; its leader attaches to the nearest flight feather.
        for row_items in rows.values():
            row_items.sort()
            leader = rig.data.bones[row_items[0][1]]
            attach = min(flight_names, key=lambda n: (rig.data.bones[n].head_local - leader.head_local).length)
            _add_fan_constraint(rig, row_items[0][1], attach, follow, ctrl_name)
            count += 1
            for i in range(1, len(row_items)):
                _add_fan_constraint(rig, row_items[i][1], row_items[i - 1][1], follow, ctrl_name)
                count += 1
    rig["wingrig_stage"] = max(int(rig.get("wingrig_stage", 2)), 4)
    return {"copy_rotation_constraints": count, "follow_influence": round(follow, 3), "network_roots": roots}


# -----------------------------------------------------------------------------
# Step 6: "wing_collapse" action + Action constraints driven by the fold control bones
# -----------------------------------------------------------------------------

def _rig_fold_rotations(rig):
    """Return {bone_name: local Z rotation (radians)} for the fully folded pose."""
    bones = rig.data.bones
    result = {}

    def rest_angle(name):
        direction = bones[name].tail_local - bones[name].head_local
        return math.atan2(direction.y, direction.x)

    for side in SIDES:
        tip_y = bones[_main_bone_name("digit2", side)].tail_local.y
        sign = 1.0 if tip_y >= 0.0 else -1.0

        def target_angle(back, outward, sign=sign):
            return math.atan2(sign * outward, back)

        phi = {}
        for role in MAIN_CHAIN_ROLES:
            back, outward = FOLD_MAIN_TARGETS[role]
            phi[role] = _wrap_angle(target_angle(back, outward) - rest_angle(_main_bone_name(role, side)))
        phi[THUMB_ROLE] = phi["forearm"]
        local = {"humerus": phi["humerus"], THUMB_ROLE: 0.0}
        for role in ("forearm", "palm", "digit1", "digit2"):
            local[role] = _wrap_angle(phi[role] - phi[MAIN_BONE_PARENT_ROLE[role]])
        for role in MAIN_ROLE_ORDER:
            result[_main_bone_name(role, side)] = local[role]
        for bone in _rig_feather_bones(rig, side):
            key = _bone_key(bone)
            parent_role = bone.get("wingrig_parent_role", None)
            if parent_role is None:
                parent_role = bone.parent.name[len(MAIN_BONE_PREFIX):].rsplit(".", 1)[0] if bone.parent else "humerus"
            # With Armature constraints the feather follows a weighted blend of several main bones.
            blended = None
            raw_targets = bone.get("wingrig_targets_json", None)
            if raw_targets:
                try:
                    pairs = [(r, float(w)) for r, w in json.loads(raw_targets) if r in phi]
                except Exception:
                    pairs = []
                if pairs:
                    base = phi[max(pairs, key=lambda item: item[1])[0]]
                    blended = sum(w * (base + _wrap_angle(phi[r] - base)) for r, w in pairs)
            if key.startswith("AL"):
                result[bone.name] = 0.0
                continue
            spread = math.radians(FOLD_FEATHER_SPREAD_DEG[feather_bone_category(key)])
            absolute = _wrap_angle(target_angle(-math.cos(spread), math.sin(spread)) - rest_angle(bone.name))
            result[bone.name] = _wrap_angle(absolute - (blended if blended is not None else phi.get(parent_role, 0.0)))
    return result


def _rig_build_fold_action(scene, settings):
    rig = _rig_require_feather_bones()
    for pose_bone in rig.pose.bones:
        for constraint in list(pose_bone.constraints):
            if constraint.name in (FOLD_CONSTRAINT_NAME, LIMIT_CONSTRAINT_NAME):
                pose_bone.constraints.remove(constraint)
    if rig.animation_data is not None and rig.animation_data.action is not None:
        rig.animation_data.action = None
    old_action = bpy.data.actions.get(FOLD_ACTION_NAME)
    if old_action is not None:
        old_action.use_fake_user = False
        bpy.data.actions.remove(old_action)

    rotations = _rig_fold_rotations(rig)
    rig.animation_data_create()
    # Channel groups are named after the bones: the Action constraint reads only the owner's group.
    for name in rotations:
        pose_bone = rig.pose.bones[name]
        pose_bone.rotation_mode = 'XYZ'
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.keyframe_insert("rotation_euler", index=2, frame=0.0, group=name)
    for name, angle in rotations.items():
        pose_bone = rig.pose.bones[name]
        pose_bone.rotation_euler = (0.0, 0.0, angle)
        pose_bone.keyframe_insert("rotation_euler", index=2, frame=float(FOLD_END_FRAME), group=name)
    for name in rotations:
        rig.pose.bones[name].rotation_euler = (0.0, 0.0, 0.0)
    action = rig.animation_data.action
    if action is None:
        raise RuntimeError("Keyframing did not create an action.")
    action.name = FOLD_ACTION_NAME
    action.use_fake_user = True
    rig.animation_data.action = None

    slot = None
    try:
        slots = list(action.slots)
        slot = slots[0] if slots else None
    except Exception:
        slot = None
    count = 0
    for side in SIDES:
        ctrl_name = _fold_ctrl_name(side)
        ctrl = rig.pose.bones[ctrl_name]
        ctrl.lock_location = (True, False, True)
        ctrl.lock_rotation = (True, True, True)
        ctrl.lock_scale = (True, True, True)
        limit = ctrl.constraints.new('LIMIT_LOCATION')
        limit.name = LIMIT_CONSTRAINT_NAME
        limit.use_min_y = True
        limit.min_y = 0.0
        limit.use_max_y = True
        limit.max_y = FOLD_CTRL_RANGE_M
        limit.owner_space = 'LOCAL'
        try:
            limit.use_transform_limit = True
        except Exception:
            pass
        _rig_setup_base_control(rig, ctrl_name, "loc_y", FOLD_CTRL_RANGE_M)
        for name in rotations:
            if not name.endswith("." + side):
                continue
            pose_bone = rig.pose.bones[name]
            constraint = pose_bone.constraints.new('ACTION')
            constraint.name = FOLD_CONSTRAINT_NAME
            constraint.target = rig
            constraint.subtarget = ctrl_name
            constraint.action = action
            if slot is not None and hasattr(constraint, "action_slot"):
                try:
                    constraint.action_slot = slot
                except Exception:
                    pass
            constraint.transform_channel = 'LOCATION_Y'
            constraint.target_space = 'LOCAL'
            constraint.min = 0.0
            constraint.max = FOLD_CTRL_RANGE_M
            constraint.frame_start = 0
            constraint.frame_end = FOLD_END_FRAME
            # Evaluate the fold first; fan-follow constraints fade out as the fold slider rises.
            pose_bone.constraints.move(len(pose_bone.constraints) - 1, 0)
            count += 1
    rig["wingrig_stage"] = max(int(rig.get("wingrig_stage", 2)), 5)
    return {"action": FOLD_ACTION_NAME, "action_constraints": count, "frames": f"0-{FOLD_END_FRAME}"}


# -----------------------------------------------------------------------------
# Step 5e: wing-surface bend controllers (four anatomical zones, effects accumulate tip-ward)
# -----------------------------------------------------------------------------

BEND_ZONES = ("arm", "fore", "hand", "tip")      # humerus / forearm / palm / fingers
BEND_MIN_WEIGHT = 0.01


def _bend_ctrl_name(zone, side):
    return f"CTRL_bend_{zone}.{side}"


def _bend_zone_edges(segments):
    """Cumulative chain distances at the zone boundaries: shoulder, elbow, wrist, hand joint, tip."""
    lengths = [(b - a).length for _role, a, b in segments]
    humerus, forearm, palm = lengths[0], lengths[1], lengths[2]
    return [0.0, humerus, humerus + forearm, humerus + forearm + palm, sum(lengths)]


def _bend_zone_weight(param, start, end, ramp):
    """0 before the zone, smoothstep ramp across it, then 1 for everything farther out.

    Because the weight stays 1 beyond the zone, a feather out at the wing tip receives the
    bend of every zone between the shoulder and itself - the bends add up toward the tip.
    """
    if param <= start:
        return 0.0
    span = max((end - start) * ramp, 1.0e-9)
    t = (param - start) / span
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def _chain_point(segments, param):
    cumulative = 0.0
    for _role, a, b in segments:
        length = (b - a).length
        if param <= cumulative + length and length > 1.0e-12:
            return a + (b - a) * max(0.0, (param - cumulative) / length)
        cumulative += length
    return segments[-1][2].copy()


def _rig_build_bend_controls(scene, settings):
    """Four bend controllers per wing. Rotating one about its local X (drag it, or use its slider) copies that
    rotation (Copy Rotation, Add, local space) onto every feather bone beyond it, weighted by position."""
    rig = _rig_require_feather_bones()
    for side in SIDES:
        _ensure_fold_fade(rig, side, settings)
    max_angle = math.radians(float(settings.rig_bend_max_deg))
    ramp = clamp(float(settings.rig_bend_ramp_pct) / 100.0, 0.05, 1.0)
    segments = {side: _rig_main_segments(rig, side) for side in SIDES}
    edges = {side: _bend_zone_edges(segments[side]) for side in SIDES}
    with _armature_edit_session(rig) as edit_bones:
        for edit_bone in list(edit_bones):
            if edit_bone.name.startswith("CTRL_bend_"):
                edit_bones.remove(edit_bone)
        for side in SIDES:
            lift = Vector((0.0, 0.0, 0.035))
            for index, zone in enumerate(BEND_ZONES):
                start = _chain_point(segments[side], edges[side][index])
                end = _chain_point(segments[side], edges[side][index + 1])
                ctrl = edit_bones.new(_bend_ctrl_name(zone, side))
                ctrl.head = start + lift
                ctrl.tail = start + (end - start) * 0.8 + lift
                if (ctrl.tail - ctrl.head).length < 0.004:
                    ctrl.tail = ctrl.head + (end - start).normalized() * 0.004
                ctrl.use_deform = False
                _align_edit_bone_roll(ctrl)
    for pose_bone in rig.pose.bones:
        for constraint in list(pose_bone.constraints):
            if constraint.name.startswith("WING_Bend"):
                pose_bone.constraints.remove(constraint)
    _rig_remove_drivers_matching(rig, 'constraints["WING_Bend')
    weighted = 0
    for side in SIDES:
        for zone in BEND_ZONES:
            name = _bend_ctrl_name(zone, side)
            _tag_control_bone(rig, name)
            holder = rig.pose.bones[name]
            holder.rotation_mode = 'XYZ'
            holder.lock_location = (True, True, True)
            holder.lock_rotation = (False, True, True)
            holder.lock_scale = (True, True, True)
            limit = holder.constraints.new('LIMIT_ROTATION')
            limit.name = "WING_BendLimit"
            limit.use_limit_x = True
            limit.min_x = -max_angle
            limit.max_x = max_angle
            limit.owner_space = 'LOCAL'
            try:
                limit.use_transform_limit = True
            except Exception:
                pass
            _rig_setup_base_control(rig, name, "rot_x", max_angle)
        for bone in _rig_feather_bones(rig, side):
            param = _chain_param(bone.head_local, segments[side])
            pose_bone = rig.pose.bones[bone.name]
            weights = {}
            for index, zone in enumerate(BEND_ZONES):
                weight = _bend_zone_weight(param, edges[side][index], edges[side][index + 1], ramp)
                if weight < BEND_MIN_WEIGHT:
                    continue
                weights[str(index + 1)] = round(weight, 5)
                constraint = pose_bone.constraints.new('COPY_ROTATION')
                constraint.name = f"WING_Bend{index + 1}"
                constraint.target = rig
                constraint.subtarget = _bend_ctrl_name(zone, side)
                constraint.use_x = True
                constraint.use_y = False
                constraint.use_z = False
                constraint.mix_mode = 'ADD'
                constraint.owner_space = 'LOCAL'
                constraint.target_space = 'LOCAL'
                constraint.influence = weight
                # Stack order: fold Action -> spread -> bend -> Armature blend.
                _rig_place_before_armature(pose_bone)
                weighted += 1
            bone["wingrig_bend_weights_json"] = json.dumps(weights)
    _rig_attach_fold_fade(rig)
    _rig_assign_collections(rig)
    _rig_style_pose_bones(rig)
    return {"bend_controllers": 2 * len(BEND_ZONES), "copy_rotation_constraints": weighted,
            "max_angle_deg": float(settings.rig_bend_max_deg), "ramp_pct": round(ramp * 100.0, 1)}


# -----------------------------------------------------------------------------
# Step 5f: flapping-cycle assistant (driver-based, additive to the manual sliders)
# -----------------------------------------------------------------------------

CYCLE_CTRL = "CTRL_cycle"
# (prop, default, min, max, driver variable, description)
CYCLE_SETTINGS = (
    ("cycle_on", 0.0, 0.0, 1.0, "on", ""),
    ("cycle_frames", 24.0, 4.0, 120.0, "P", ""),
    ("cycle_phase", 0.0, -1.0, 1.0, "ph", ""),
    ("downstroke", 0.5, 0.2, 0.8, "r", ""),
    ("flap_amp", 1.0, 0.0, 1.0, "fa", ""),
    ("flap_bias", 0.0, -1.0, 1.0, "fb", ""),
    ("sweep_amp", 0.4, 0.0, 1.0, "sa", ""),
    ("pitch_amp", 0.3, 0.0, 1.0, "pa", ""),
    ("twist_amp", 0.4, 0.0, 1.0, "ta", ""),
    ("wrist_amp", 0.5, 0.0, 1.0, "wa", ""),
    ("curl_amp", 0.5, 0.0, 1.0, "ca", ""),
    ("lag_wrist", 0.08, 0.0, 0.5, "lw", ""),
    ("lag_tip", 0.16, 0.0, 0.5, "lt", ""),
    ("lr_offset", 0.0, -0.5, 0.5, "lr", ""),
)
# output prop -> (controller that receives it)
CYCLE_OUTPUTS = {"flap": "pose", "sweep": "pose", "pitch": "pose", "twist": "pose",
                 "wrist_flex": "hand", "wrist_sweep": "hand", "finger_curl": "hand"}


def _cycle_theta(extra):
    """Warped phase angle: the downstroke occupies [0, r) of the cycle, the upstroke the rest."""
    u = f"fmod(frame/P+ph{extra}+1000,1)"
    return f"(({u}<r)*(pi*{u}/r)+({u}>=r)*(pi+pi*({u}-r)/(1-r)))"


def _cycle_output_expression(name, side, has_fold):
    lr = "+lr" if side == "R" else ""
    arm = _cycle_theta(lr)
    wrist = _cycle_theta(lr + "-lw")
    tip = _cycle_theta(lr + "-lt")
    body = {
        "flap": f"fa*cos({arm})+fb",
        "sweep": f"-sa*sin({arm})",
        "pitch": f"-pa*sin({arm})",
        "twist": f"-ta*sin({tip})",
        "wrist_flex": f"wa*cos({wrist})",
        "wrist_sweep": f"-0.5*wa*sin({wrist})",
        "finger_curl": f"-ca*cos({tip})",
    }[name]
    fold = "*(1-fold)" if has_fold else ""
    return f"max(-1,min(1,on*({body}){fold}))"


def _rig_build_cycle_controls(scene, settings):
    """Master flapping-cycle bone: automatic flap, sweep, pitch, twist, wrist and finger motion
    with adjustable period, downstroke share, amplitudes and phase lags. Added on top of the
    manual pose / hand sliders, fades out while the wing folds."""
    rig = _rig_require_feather_bones()
    shoulder = rig.data.bones[_main_bone_name("humerus", "L")].head_local.copy()
    with _armature_edit_session(rig) as edit_bones:
        for edit_bone in list(edit_bones):
            if edit_bone.name == CYCLE_CTRL:
                edit_bones.remove(edit_bone)
        master = edit_bones.new(CYCLE_CTRL)
        master.head = Vector((shoulder.x, 0.0, shoulder.z + 0.16))
        master.tail = master.head + Vector((0.0, 0.0, 0.04))
        master.use_deform = False
    _tag_control_bone(rig, CYCLE_CTRL)
    holder = rig.pose.bones[CYCLE_CTRL]
    holder.lock_location = (True, True, True)
    holder.lock_rotation = (True, True, True)
    holder.lock_scale = (True, True, True)
    for prop, default, lo, hi, _var, _unused in CYCLE_SETTINGS:
        holder[prop] = float(default)
        _set_prop_ui(holder, prop, lo, hi, float(default))
    drivers = 0
    for side in SIDES:
        _ensure_fold_fade(rig, side, settings)
        for name in CYCLE_OUTPUTS:
            out_prop = f"out_{side}_{name}"
            holder[out_prop] = 0.0
            _rig_remove_drivers_matching(rig, f'["{out_prop}"]')
            fcurve = holder.driver_add(f'["{out_prop}"]')
            _strip_modifiers(fcurve)
            driver = fcurve.driver
            driver.type = 'SCRIPTED'
            for prop, _d, _lo, _hi, var_name, _desc in CYCLE_SETTINGS:
                _bind_var(driver, var_name, rig, f'pose.bones["{CYCLE_CTRL}"]["{prop}"]')
            _bind_var(driver, "fold", rig, _bone_prop_path(_fold_ctrl_name(side), "fold"))
            driver.expression = _cycle_output_expression(name, side, True)
            drivers += 1
    attached = _rig_refresh_mixers(rig, settings)["cycle"]
    _rig_assign_collections(rig)
    _rig_style_pose_bones(rig)
    return {"cycle_bone": CYCLE_CTRL, "output_drivers": drivers, "pose_and_hand_drivers_extended": attached}


# -----------------------------------------------------------------------------
# Step 6b: link fold and spread - folding fades the spread / hand layers back to neutral
# -----------------------------------------------------------------------------

def _rig_link_fold_spread(scene, settings):
    """Fold -> fade link. As the fold slider rises the row-spread and bend constraints fade out and the
    wrist / finger layer fades down to `hand_keep`, so the folded pose is always clean.

    The values live on CTRL_fold.<side> (fade_end, hand_keep) and can be tuned there afterwards without
    rebuilding; this step (re)applies the scene settings and re-attaches every consumer."""
    rig = _rig_require_feather_bones()
    for side in SIDES:
        ctrl = rig.pose.bones.get(_fold_ctrl_name(side))
        if ctrl is None or "fold" not in ctrl.keys():
            raise RuntimeError("Create the fold action (step 6) first: the fold slider does not exist yet.")
    for side in SIDES:
        _ensure_fold_fade(rig, side, settings, apply=True)
    links = _rig_attach_fold_fade(rig)
    mixed = _rig_refresh_mixers(rig, settings, ("hand",))
    return {"spread_constraints_linked": links["spread"], "bend_constraints_linked": links["bend"],
            "hand_drivers_linked": mixed["fold"],
            "fade_end_fold_value": round(clamp(float(settings.rig_fold_spread_end), 0.05, 1.0), 3),
            "hand_keep_pct": round(clamp(float(settings.rig_fold_hand_keep_pct), 0.0, 100.0), 1)}


# -----------------------------------------------------------------------------
# Step 7: control panel (custom property + driver on the feather bone collections)
# -----------------------------------------------------------------------------

def _rig_build_panel(scene, settings):
    """Display switches: integer properties on CTRL_panel drive the bone-collection visibility."""
    rig = _rig_require_feather_bones()
    _rig_assign_collections(rig)               # make sure the collections used below exist
    panel = rig.pose.bones[CTRL_PANEL_BONE]
    arm = rig.data
    _rig_remove_drivers_matching(arm, "collections_all")
    _rig_remove_drivers_matching(arm, "collections[")
    all_collections = getattr(arm, "collections_all", arm.collections)
    names = {c.name: c for c in all_collections}
    nested = getattr(names.get(COLL_FLIGHT), "parent", None) is not None
    driven = []
    for prop, default, collections in SHOW_SWITCHES:
        if prop not in panel.keys():
            panel[prop] = int(default)
        try:
            ui = panel.id_properties_ui(prop)
            ui.update(min=0, max=1, soft_min=0, soft_max=1, default=int(default))
        except Exception:
            pass
        targets = list(collections)
        if prop == SHOW_FEATHER_PROP and not nested:
            targets = [COLL_FLIGHT, COLL_COVERT, COLL_AUX]
        for name in targets:
            if name not in names:
                continue
            try:
                fcurve = arm.driver_add(f'collections_all["{name}"].is_visible')
            except Exception:
                fcurve = arm.driver_add(f'collections["{name}"].is_visible')
            _strip_modifiers(fcurve)
            driver = fcurve.driver
            driver.type = 'SCRIPTED'
            _bind_var(driver, "show", rig, f'pose.bones["{CTRL_PANEL_BONE}"]["{prop}"]')
            driver.expression = "show > 0.5"
            driven.append(name)
    _rig_style_pose_bones(rig)
    rig["wingrig_stage"] = max(int(rig.get("wingrig_stage", 2)), 6)
    return {"panel_bone": CTRL_PANEL_BONE, "switches": [p for p, _d, _c in SHOW_SWITCHES], "driven_collections": driven}


DISPLAY_PRESETS = {
    "ANIMATE": {"show_main_bones": 0, SHOW_FEATHER_PROP: 0, "show_ctrl_fold": 1, "show_ctrl_spread": 1,
                "show_ctrl_bend": 1, "show_ctrl_holders": 0},
    "RIG": {"show_main_bones": 1, SHOW_FEATHER_PROP: 1, "show_ctrl_fold": 1, "show_ctrl_spread": 1,
            "show_ctrl_bend": 1, "show_ctrl_holders": 1},
    "MAIN": {"show_main_bones": 1, SHOW_FEATHER_PROP: 0, "show_ctrl_fold": 0, "show_ctrl_spread": 0,
             "show_ctrl_bend": 0, "show_ctrl_holders": 0},
}


FULL_RIG_STEPS = (
    ("main", _rig_step_main), ("feathers", _rig_build_feather_bones), ("skin", _rig_skin_meshes),
    ("constraints", _rig_add_armature_constraints), ("spread", _rig_build_spread_controls),
    ("pose", _rig_build_pose_controls), ("hand", _rig_build_hand_controls), ("bend", _rig_build_bend_controls),
    ("fold", _rig_build_fold_action), ("link", _rig_link_fold_spread), ("cycle", _rig_build_cycle_controls),
    ("panel", _rig_build_panel),
)


def _rig_build_all(scene, settings):
    stats = {}
    if settings.rig_auto_flat_pose:
        stats["flat_pose"] = _find_flat_pose(scene)
    for label, func in FULL_RIG_STEPS:
        stats[label] = func(scene, settings)
    return stats


def _score_generator_pose(state, angles):
    """Heuristic score only: prefer broad horizontal reach and low out-of-plane displacement."""
    k, hand_joint = bone_points_for_state(state, angles)
    shoulder, elbow, wrist, tip = [list(p) for p in k["points"]]
    chain_points = [shoulder, elbow, wrist, list(hand_joint), tip]
    segment_lengths = [v_len(v_sub(chain_points[i + 1], chain_points[i]))
                       for i in range(len(chain_points) - 1)]
    total_length = max(1.0e-6, sum(segment_lengths))
    # The model's body axis is world/local X and the wings spread laterally along Y.
    # Therefore use lateral reach, not the shoulder-to-tip XY radius (which would wrongly
    # reward a swept-forward/back pose as if it were fully spread).
    lateral_span = abs(tip[1] - shoulder[1]) / total_length
    z_rms = math.sqrt(sum((p[2] - shoulder[2]) ** 2 for p in chain_points[1:]) / (len(chain_points) - 1))
    flatness = clamp(1.0 - z_rms / max(total_length * 0.30, 1.0e-6), 0.0, 1.0)
    score = 0.75 * clamp(lateral_span, 0.0, 1.0) + 0.25 * flatness
    return {"score": score, "lateral_span_ratio": lateral_span,
            "flatness_score": flatness, "vertical_rms_mm": z_rms,
            "chain_length_mm": total_length}


def _find_flat_pose(scene):
    """Scan the timeline for the flattest wing pose, jump to that frame and rebuild the model there."""
    ensure_settings(scene)
    settings = scene.wing_model_settings
    state = build_state(settings)
    start = int(scene.frame_start)
    end = int(scene.frame_end)
    if end < start:
        raise RuntimeError("Timeline frame range is invalid.")
    # Typical project ranges are scanned exhaustively. For very long timelines, sample
    # evenly up to 1000 frames, then choose the best available sampled frame.
    frame_count = end - start + 1
    if frame_count <= 1000:
        frames = list(range(start, end + 1))
    else:
        frames = sorted(set(int(round(start + i * (end - start) / 999.0)) for i in range(1000)))
    best = None
    min_score = float("inf")
    max_score = -float("inf")
    for frame in frames:
        cycles = _motion_cycles_at_frame(scene, settings, frame)
        angles = motion_angles(settings, cycles)
        metrics = _score_generator_pose(state, angles)
        min_score = min(min_score, metrics["score"])
        max_score = max(max_score, metrics["score"])
        item = {"frame": frame, "cycles": cycles, "angles": angles, "metrics": metrics}
        if best is None or metrics["score"] > best["metrics"]["score"]:
            best = item
    if best is None:
        raise RuntimeError("No usable frame was found in the current timeline.")

    scene.frame_set(int(best["frame"]))
    # Explicit rebuild guarantees the visible generator geometry matches the selected frame,
    # even if the optional Python animation frame handler is currently disabled.
    build_model(scene)
    scene["wing_model_flat_pose_frame"] = int(best["frame"])
    scene["wing_model_flat_pose_score"] = float(best["metrics"]["score"])
    scene["wing_model_flat_pose_lateral_span"] = float(best["metrics"]["lateral_span_ratio"])
    scene["wing_model_flat_pose_flatness"] = float(best["metrics"]["flatness_score"])
    scene["wing_model_flat_pose_vertical_rms_mm"] = float(best["metrics"]["vertical_rms_mm"])
    spread = best["metrics"]["lateral_span_ratio"]
    flatness = best["metrics"]["flatness_score"]
    _console("[Wing Flat Pose Search]", {
        "selected_frame": int(best["frame"]),
        "score": round(best["metrics"]["score"], 5),
        "lateral_span_ratio": round(spread, 5),
        "flatness_score": round(flatness, 5),
        "vertical_rms_mm": round(best["metrics"]["vertical_rms_mm"], 4),
        "tested_frames": len(frames),
        "score_range": [round(min_score, 5), round(max_score, 5)],
        "method": "heuristic search over the existing timeline; no animation settings changed",
    })
    return {"frame": int(best["frame"]), "span": round(spread, 3), "flatness": round(flatness, 3),
            "tested_frames": len(frames), "no_variation": max_score - min_score < 1.0e-6}


class WING_OT_FindFlatWingPose(bpy.types.Operator):
    bl_idname = "wing_model.find_flat_wing_pose"
    bl_label = "自动寻找平摊姿态"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            result = _find_flat_pose(context.scene)
        except RuntimeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if result["no_variation"]:
            self.report({'WARNING'}, f"Frame {result['frame']} selected, but the current settings have no meaningful pose "
                                     "variation; inspect animation settings.")
        else:
            self.report({'INFO'}, f"Flat-pose candidate: frame {result['frame']}; span {result['span']:.3f}; "
                                  f"flatness {result['flatness']:.3f}. Review visually before generating bones.")
        return {'FINISHED'}


def _run_rig_step(operator, context, label, func):
    ensure_settings(context.scene)
    try:
        stats = func(context.scene, context.scene.wing_model_settings)
        _rig_refresh_lr_link()
    except Exception as exc:
        operator.report({'ERROR'}, f"{label} failed: {exc}")
        _console("[Wing Rig]", label, "ERROR", repr(exc))
        return {'CANCELLED'}
    operator.report({'INFO'}, f"{label} done: {stats}")
    _console("[Wing Rig]", label, stats)
    return {'FINISHED'}


# Rig operators that only run one build step share a factory:
# (class name, bl_idname suffix, label, description, step name for reports, build function)
_STEP_OPERATORS = (
    ("WING_OT_BuildArchitectureStage1", "build_architecture_stage1",
     "生成主翼骨骼",
     "",
     "Main wing bones", _rig_step_main),
    ("WING_OT_BuildFeatherBones", "build_feather_bones",
     "生成羽毛骨骼并建立层级",
     "",
     "Feather bones", _rig_build_feather_bones),
    ("WING_OT_SkinFeathers", "skin_feathers",
     "绑定羽毛网格并写入权重",
     "",
     "Feather skinning", _rig_skin_meshes),
    ("WING_OT_AddFeatherArmatureConstraints", "add_feather_armature_constraints",
     "添加约束",
     "",
     "Armature constraints", _rig_add_armature_constraints),
    ("WING_OT_BuildSpreadControls", "build_spread_controls",
     "生成排级扇形展开控制器",
     "",
     "Spread controls", _rig_build_spread_controls),
    ("WING_OT_BuildPoseControls", "build_pose_controls",
     "生成整体姿态控制器",
     "",
     "Pose controls", _rig_build_pose_controls),
    ("WING_OT_BuildHandControls", "build_hand_controls",
     "生成手腕与手指控制器",
     "",
     "Hand controls", _rig_build_hand_controls),
    ("WING_OT_LinkFoldSpread", "link_fold_spread",
     "联动折叠与展开",
     "",
     "Fold/spread link", _rig_link_fold_spread),
    ("WING_OT_BuildBendControls", "build_bend_controls",
     "生成翼面弯折控制器",
     "",
     "Bend controls", _rig_build_bend_controls),
    ("WING_OT_BuildCycleControls", "build_cycle_controls",
     "生成拍翅循环辅助控制",
     "",
     "Cycle controls", _rig_build_cycle_controls),
    ("WING_OT_AddFeatherConstraints", "add_feather_constraints",
     "添加复制旋转约束",
     "",
     "Fan constraints", _rig_add_fan_constraints),
    ("WING_OT_BuildFoldAction", "build_fold_action",
     "创建折叠动作并添加约束",
     "",
     "Fold action", _rig_build_fold_action),
    ("WING_OT_BuildRigPanel", "build_rig_panel",
     "创建控制面板",
     "",
     "Control panel", _rig_build_panel),
    ("WING_OT_BuildFullRig", "build_full_rig",
     "一键完成全部绑定",
     "",
     "Full rig", _rig_build_all),
)


def _make_step_operator(cls_name, idname, label, description, step_label, func):
    def execute(self, context):
        return _run_rig_step(self, context, step_label, func)
    return type(cls_name, (bpy.types.Operator,), {
        "bl_idname": "wing_model." + idname, "bl_label": label,
        "bl_options": {'REGISTER', 'UNDO'}, "execute": execute})


STEP_OP_CLASSES = [_make_step_operator(*row) for row in _STEP_OPERATORS]


class WING_OT_CycleSetRange(bpy.types.Operator):
    bl_idname = "wing_model.cycle_set_range"
    bl_label = "时间轴设为一个周期"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = bpy.data.objects.get(RIG_OBJECT)
        holder = rig.pose.bones.get(CYCLE_CTRL) if rig is not None and rig.type == "ARMATURE" else None
        if holder is None or "cycle_frames" not in holder.keys():
            self.report({'ERROR'}, "Build the cycle controls first.")
            return {'CANCELLED'}
        context.scene.frame_start = 1
        context.scene.frame_end = max(2, int(round(float(holder["cycle_frames"]))))
        self.report({'INFO'}, f"Frame range set to 1-{context.scene.frame_end}.")
        return {'FINISHED'}


class WING_OT_SetRigDisplay(bpy.types.Operator):
    bl_idname = "wing_model.set_rig_display"
    bl_label = "切换显示预设"
    bl_options = {'REGISTER', 'UNDO'}

    mode: StringProperty(default="ANIMATE")

    def execute(self, context):
        rig = bpy.data.objects.get(RIG_OBJECT)
        panel = rig.pose.bones.get(CTRL_PANEL_BONE) if rig is not None and rig.type == "ARMATURE" else None
        if panel is None or self.mode not in DISPLAY_PRESETS:
            self.report({'ERROR'}, "Create the control panel first.")
            return {'CANCELLED'}
        for prop, value in DISPLAY_PRESETS[self.mode].items():
            if prop in panel.keys():
                panel[prop] = int(value)
        rig.update_tag()
        context.view_layer.update()
        return {'FINISHED'}


class WING_OT_RefreshRigStyle(bpy.types.Operator):
    bl_idname = "wing_model.refresh_rig_style"
    bl_label = "刷新控制骨形状与颜色"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = bpy.data.objects.get(RIG_OBJECT)
        if rig is None or rig.type != "ARMATURE":
            self.report({'ERROR'}, "The rig has not been generated.")
            return {'CANCELLED'}
        _rig_style_pose_bones(rig)
        self.report({'INFO'}, "Bone shapes and colours refreshed.")
        return {'FINISHED'}


def _rig_diagnose(scene):
    rig = bpy.data.objects.get(RIG_OBJECT)
    errors, lines = [], []
    if rig is None or rig.type != "ARMATURE":
        return ["The rig has not been generated."], ["Rig: missing"]
    bones = rig.data.bones
    if str(rig.get("wingrig_schema_version", "")) != RIG_SCHEMA:
        errors.append("old architecture rig; regenerate it using the current version")
    expected = {_main_bone_name(role, side) for side in SIDES for role in MAIN_ROLE_ORDER}
    missing = sorted(expected - set(bones.keys()))
    for name in missing:
        errors.append(f"missing main bone: {name}")
    for side in SIDES:
        for role in MAIN_ROLE_ORDER:
            bone = bones.get(_main_bone_name(role, side))
            if bone is None:
                continue
            parent_role = MAIN_BONE_PARENT_ROLE[role]
            if parent_role is None:
                if bone.parent is not None:
                    errors.append(f"root bone should not have a parent: {bone.name}")
                continue
            expected_parent = _main_bone_name(parent_role, side)
            if bone.parent is None or bone.parent.name != expected_parent:
                errors.append(f"incorrect parent: {bone.name} should parent to {expected_parent}")
                continue
            if not bone.use_connect:
                errors.append(f"connected parenting is disabled: {bone.name}")
            gap = (bone.head_local - bone.parent.tail_local).length
            if gap > 1.0e-5:
                errors.append(f"bone gap {bone.name}: {gap * 1000.0:.4f} mm")
    feather_bones = _rig_feather_bones(rig)
    left = len(_rig_feather_bones(rig, "L"))
    right = len(_rig_feather_bones(rig, "R"))
    if feather_bones:
        if left != right:
            errors.append(f"feather bone count differs between sides: L={left}, R={right}")
        for bone in feather_bones:
            has_armature = any(c.type == 'ARMATURE' for c in rig.pose.bones[bone.name].constraints)
            if bone.parent is None and has_armature:
                continue
            if bone.parent is None or not bone.parent.name.startswith(MAIN_BONE_PREFIX):
                errors.append(f"feather bone has no main-bone parent: {bone.name}")
            elif has_armature:
                errors.append(f"feather bone has both a parent and an Armature constraint (double transform): {bone.name}")
            elif bone.use_connect:
                errors.append(f"feather bone should not be connected: {bone.name}")
        for name in (_fold_ctrl_name("L"), _fold_ctrl_name("R"), CTRL_PANEL_BONE):
            if bones.get(name) is None:
                errors.append(f"missing control bone: {name}")
    fan = sum(1 for pb in rig.pose.bones for c in pb.constraints if c.name == FAN_CONSTRAINT_NAME)
    fold = sum(1 for pb in rig.pose.bones for c in pb.constraints if c.name == FOLD_CONSTRAINT_NAME)
    spread = sum(1 for pb in rig.pose.bones for c in pb.constraints if c.name == SPREAD_CONSTRAINT_NAME)
    arm_con = sum(1 for pb in rig.pose.bones for c in pb.constraints if c.name == ARMATURE_CONSTRAINT_NAME)
    if fold and bpy.data.actions.get(FOLD_ACTION_NAME) is None:
        errors.append("fold action is missing")
    drivers = len(rig.animation_data.drivers) if rig.animation_data else 0
    bound_meshes = 0
    for group_id, *_ in GROUP_DEFS:
        obj = bpy.data.objects.get(f"WINGGEN_Feathers_{group_id}")
        if obj is None:
            continue
        has_modifier = any(m.type == 'ARMATURE' and m.object == rig for m in obj.modifiers)
        if has_modifier:
            bound_meshes += 1
            stray = [g.name for g in obj.vertex_groups if g.name not in bones]
            if stray:
                errors.append(f"vertex groups without bones on {obj.name}: {stray[:3]}")
    if rig.get("wingrig_mesh_bound", False) and bound_meshes != len(GROUP_DEFS):
        errors.append(f"only {bound_meshes} of {len(GROUP_DEFS)} feather meshes carry the Armature modifier")
    lines = [
        "WING RIG DIAGNOSTIC",
        "===================",
        f"Rig: {rig.name}; schema {rig.get('wingrig_schema_version', 'unknown')}; stage {rig.get('wingrig_stage', 'unknown')}",
        f"Main bones: {len(expected) - len(missing)} of {len(expected)} (6 per wing)",
        f"Feather bones: L={left}, R={right}",
        f"Spread constraints: {spread}; Armature constraints: {arm_con}; fan constraints: {fan}; fold constraints: {fold}; drivers: {drivers}",
        f"Bound meshes: {bound_meshes}",
        f"Pose source frame: {rig.get('wingrig_pose_source_frame', 'unknown')}",
        f"Errors: {len(errors)}",
        "",
        "ERRORS",
    ] + (errors or ["None"])
    return errors, lines


class WING_OT_DiagnoseArchitectureStage1(bpy.types.Operator):
    bl_idname = "wing_model.diagnose_architecture_stage1"
    bl_label = "检查骨骼与绑定"
    bl_options = {'REGISTER'}

    def execute(self, context):
        errors, lines = _rig_diagnose(context.scene)
        text = "\n".join(lines)
        rig = bpy.data.objects.get(RIG_OBJECT)
        if rig is not None:
            rig["wingrig_stage1_last_diagnostic"] = text
        _console(text)
        if errors:
            self.report({'WARNING'}, f"Rig diagnostic found {len(errors)} issue(s). See System Console.")
        else:
            self.report({'INFO'}, "Rig diagnostic passed.")
        return {'FINISHED'}


class WING_OT_RemoveArchitectureStage1(bpy.types.Operator):
    bl_idname = "wing_model.remove_architecture_stage1"
    bl_label = "清除全部骨骼与绑定"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _rig_remove_all(context.scene)
        self.report({'INFO'}, "Rig and bindings removed; generated wing geometry was unchanged.")
        return {'FINISHED'}


def _main_chain_signature(specs):
    """Stable signature of the currently generated main-chain rest geometry."""
    import zlib
    rows = []
    for spec in specs:
        rows.append((spec["name"], spec.get("parent_name") or "",
                     tuple(round(float(v), 7) for v in spec["head"]),
                     tuple(round(float(v), 7) for v in spec["tail"])))
    payload = json.dumps(sorted(rows), separators=(",", ":"), ensure_ascii=True)
    return f"{zlib.crc32(payload.encode('ascii')) & 0xFFFFFFFF:08X}"


CLASSES = [
    WING_PG_LengthReferencePoint, WING_PG_Group, WING_PG_Feather, WING_PG_MeshOverride, WING_PG_Combo,
    WING_PG_Joint, WING_PG_Settings,
    WING_OT_CreateModel, WING_OT_AddCombo, WING_OT_RemoveCombo,
    WING_OT_AddLengthReferencePoint, WING_OT_RemoveLengthReferencePoint, WING_OT_ClearLengthReferencePoints,
    WING_OT_ResetGroup, WING_OT_ResetAll, WING_OT_ScopeCopyToGroup, WING_OT_ImportHTMLParameters, WING_OT_ApplyUV,
    WING_OT_ResetModelPose, WING_PT_ControlPanel, WING_OT_FindFlatWingPose,
    *STEP_OP_CLASSES,
    WING_OT_CycleSetRange, WING_OT_SetRigDisplay, WING_OT_RefreshRigStyle, WING_OT_SetLRLink, WING_OT_KeyBaseControls, WING_OT_ResetRigPose, WING_OT_TogglePlayback, WING_OT_TogglePythonPlayback,
    WING_OT_DiagnoseArchitectureStage1, WING_OT_RemoveArchitectureStage1,
]

# Classes registered by older releases; unregistered on reload so a re-run starts clean.
LEGACY_CLASS_NAMES = (
    "WING_PG_BoneLayer", "WING_OT_GenerateFeatherBones", "WING_OT_RemoveFeatherBones", "WING_OT_RigAndSkin",
    "WING_OT_InitializeFoldAction", "WING_OT_CaptureFoldPose", "WING_OT_RemoveFoldActionLayer",
    "WING_OT_DiagnoseRig", "WING_OT_ExportRigDiagnostic", "WING_OT_RemoveRig", "WING_OT_CleanupLegacyRigAssets",
    "WING_PT_ArchitectureStage1",
    *(f"WING_{kind}_{name}{n}" for n in (2, 3, 4)
      for kind, name in (("OT", "BuildArchitectureStage"), ("OT", "DiagnoseArchitectureStage"),
                         ("OT", "RemoveArchitectureStage"), ("PT", "ArchitectureStage"))),
)


def unregister_previous():
    """Unregister the current classes and any legacy classes on reload."""
    if hasattr(bpy.types.Scene, "wing_model_settings"):
        try:
            del bpy.types.Scene.wing_model_settings
        except Exception:
            pass
    for name in ("wing_slider", "wing_slider_pos"):
        if hasattr(bpy.types.PoseBone, name):
            try:
                delattr(bpy.types.PoseBone, name)
            except Exception:
                pass
    names = list(LEGACY_CLASS_NAMES) + [cls.__name__ for cls in CLASSES]
    for name in reversed(names):
        old = getattr(bpy.types, name, None)
        if old is not None:
            try:
                bpy.utils.unregister_class(old)
            except Exception:
                pass


OPERATOR_TIPS = {
    "create_model": "按当前参数生成或重建翅膀模型。",
    "import_html_parameters": "导入 HTML 工具导出的参数 JSON。",
    "reset_model_pose": "模型回到默认位置和时间轴起始姿态。",
    "add_combo": "添加多组组合修改器。",
    "remove_combo": "删除此组合修改器。",
    "add_length_reference_point": "添加组内长度参考点。",
    "remove_length_reference_point": "删除此参考点。",
    "clear_length_reference_points": "清除全部中间参考点。",
    "reset_group": "重置当前羽毛组参数。",
    "reset_all": "全部参数恢复默认。",
    "scope_copy_to_group": "把此值复制给本组全部羽毛。",
    "apply_uv": "按当前设置重新展开 UV。",
    "toggle_python_playback": "开始播放并启用 Python 动画；停止播放并关闭。",
    "toggle_playback": "播放或暂停时间轴。",
    "find_flat_wing_pose": "在时间轴中寻找翅膀最平摊的帧并跳转。",
    "build_full_rig": "一键完成全部绑定。",
    "build_architecture_stage1": "生成每侧 6 根主翼骨骼。",
    "build_feather_bones": "为每根羽毛生成骨骼并挂到主翼骨骼。",
    "skin_feathers": "为羽毛网格写入顶点组与骨架修改器。",
    "add_feather_armature_constraints": "羽毛骨骼按距离跟随多根主翼骨骼。",
    "add_feather_constraints": "相邻羽毛旋转联动。",
    "build_spread_controls": "生成排级扇形展开控制骨。",
    "build_pose_controls": "生成前后摆、上下扇、俯仰、扭转控制器。",
    "build_hand_controls": "生成手腕、手指、拇指控制器。",
    "build_bend_controls": "生成分区翼面弯折控制骨。",
    "build_fold_action": "创建折叠动作，由折叠控制骨驱动。",
    "link_fold_spread": "折叠时展开与手部控制自动淡出。",
    "build_cycle_controls": "生成自动拍翅控制骨。",
    "cycle_set_range": "时间轴设为一个拍翅周期。",
    "build_rig_panel": "创建骨骼显示开关。",
    "set_rig_display": "切换骨骼显示预设。",
    "refresh_rig_style": "刷新控制骨形状与颜色。",
    "set_lr_link": "开启或关闭左右翼联动。",
    "key_base_controls": "为基础控制骨在当前帧打关键帧。",
    "reset_rig_pose": "全部控制器归零，回到平摊姿态。",
    "diagnose_architecture_stage1": "检查骨骼与绑定，结果输出到控制台。",
    "remove_architecture_stage1": "删除骨架与绑定，羽毛网格保留。",
}


def register():
    unregister_previous()
    for cls in CLASSES:
        if issubclass(cls, bpy.types.Operator) and "bl_description" not in cls.__dict__:
            cls.bl_description = OPERATOR_TIPS.get(cls.bl_idname.split(".", 1)[-1], cls.bl_label + "。")
        bpy.utils.register_class(cls)
    bpy.types.Scene.wing_model_settings = PointerProperty(type=WING_PG_Settings)
    bpy.types.PoseBone.wing_slider = _ctl_property(-1.0)
    bpy.types.PoseBone.wing_slider_pos = _ctl_property(0.0)
    install_frame_handler()


def unregister():
    remove_frame_handler()
    unregister_previous()


def ensure_settings(scene):
    s = scene.wing_model_settings
    with _suppressed_updates():
        if len(s.groups) == 0:
            for gid, label, short, kind in GROUP_DEFS:
                item = s.groups.add(); item.group_id = gid; item.label = label
                for key, value in GROUP_DEFAULTS.items(): setattr(item, key, value)
                # Large flight-feather groups use four axial segments by default.
                if gid in FLIGHT_GROUPS:
                    item.mesh_segments = 4
        # Migrate existing .blend scenes once. Older builds stored station counts in a
        # different property; initialise the new segment controls without touching settings.
        if not s.mesh_settings_migrated:
            for item in s.groups:
                if item.group_id in FLIGHT_GROUPS:
                    item.mesh_segments = 4
                else:
                    item.mesh_segments = 0  # inherit the global 3-segment default
            for item in s.mesh_overrides:
                item.mesh_segments = 0
            s.global_mesh_segments = 3
            s.mesh_settings_migrated = True
        # One-time migration from v1.3.0's too-low defaults. Upgrade only values that still
        # match that release's defaults; leave deliberately customized values untouched.
        if not s.mesh_defaults_migrated_v131:
            if int(s.global_mesh_segments) == 2:
                s.global_mesh_segments = 3
            for item in s.groups:
                if item.group_id in FLIGHT_GROUPS and int(item.mesh_segments) == 3:
                    item.mesh_segments = 4
            s.mesh_defaults_migrated_v131 = True
        # v1.3.2: turn off automatic subdivisions while keeping deliberate non-default edits.
        if not s.mesh_defaults_migrated_v141:
            if int(s.global_mesh_segments) == 3:
                s.global_mesh_segments = 1
            for item in s.groups:
                if item.group_id in FLIGHT_GROUPS and int(item.mesh_segments) == 4:
                    item.mesh_segments = 0
            s.mesh_defaults_migrated_v141 = True
        ensure_feather_count_settings(s)
        if len(s.joints) == 0:
            for i, (label, mean, amp, phase) in enumerate(JOINTS):
                item = s.joints.add(); item.joint_id = f"joint_{i}"; item.label = label
                item.mean_deg = mean; item.amplitude_deg = amp; item.phase = phase


def focus_view_on_wing():
    """Frame the generated static model in any available 3D View."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            try:
                space.region_3d.view_location = Vector((0.075, 0.0, 0.105))
                space.region_3d.view_distance = 0.62
                space.region_3d.view_perspective = 'ORTHO'
                # Use a slight elevated oblique view so feather surfaces and skeleton are both visible.
                direction = Vector((1.5, -2.7, 2.2))
                space.region_3d.view_rotation = direction.to_track_quat('Z', 'Y')
            except Exception:
                pass


def initialize_for_text_editor():
    register()
    scene=bpy.context.scene
    ensure_settings(scene)
    build_model(scene)
    focus_view_on_wing()


if __name__ == "__main__":
    initialize_for_text_editor()
