"""Benchmark every PPI approach we can think of."""
import cv2
import numpy as np
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

img = cv2.imread('maps/main.png', cv2.IMREAD_GRAYSCALE)
h, w = img.shape
crop = img[200:450, 300:550].copy()
snow_crop = img[50:300, w//2-125:w//2+125].copy()

N = 50  # iterations per benchmark


def run_match(setup_fn, match_fn, label, notes=""):
    ctx = setup_fn()
    # Warm up
    match_fn(crop, ctx)
    match_fn(snow_crop, ctx)
    # Time
    t0 = time.perf_counter()
    for _ in range(N):
        match_fn(crop, ctx)
    ms = (time.perf_counter() - t0) / N * 1000
    fn = "OK" if match_fn(crop, ctx) is not None else "FAIL"
    fs = "OK" if match_fn(snow_crop, ctx) is not None else "FAIL"
    print(f"  {label:<45} {ms:>6.1f}ms  {fn:<6} {fs:<6} {notes}")
    return ms, fn, fs


def do_homography(kp1, kp_map, good, capture_shape):
    if len(good) <= 25:
        return None
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_map[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if M is None or not np.all(np.isfinite(M)):
        return None
    ch, cw = capture_shape
    pts = np.float32([[0, 0], [0, ch-1], [cw-1, ch-1], [cw-1, 0]]).reshape(-1, 1, 2)
    tp = cv2.perspectiveTransform(pts, M)
    return tp if np.all(np.isfinite(tp)) else None


def ratio_test(matches, ratio=0.75):
    good = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < ratio * n.distance:
                good.append(m)
    return good


print(f"\n{'='*90}")
print(f"  PPI APPROACH BENCHMARK  ({w}x{h} map, 250x250 captures, {N} iterations)")
print(f"{'='*90}")
print(f"  {'Approach':<45} {'Time':>6}    {'Norm':<6} {'Snow':<6} Notes")
print(f"  {'-'*85}")

# ── 1. CURRENT: SIFT + BFMatcher ──────────────────────────────────────
def setup_current():
    sift_map = cv2.SIFT_create()
    sift_cap = cv2.SIFT_create(contrastThreshold=0.03)
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    kp, des = sift_map.detectAndCompute(img, None)
    return {'sift': sift_cap, 'bf': bf, 'kp': kp, 'des': des}

def match_current(capture, ctx):
    kp1, des1 = ctx['sift'].detectAndCompute(capture, None)
    if des1 is None: return None
    matches = ctx['bf'].knnMatch(des1, ctx['des'], k=2)
    return do_homography(kp1, ctx['kp'], ratio_test(matches), capture.shape)

run_match(setup_current, match_current, "1. Current (SIFT+BF, ct=0.03)")

# ── 2. SIFT + FLANN ───────────────────────────────────────────────────
def setup_flann():
    sift_map = cv2.SIFT_create()
    sift_cap = cv2.SIFT_create(contrastThreshold=0.03)
    ip = dict(algorithm=1, trees=5)
    sp = dict(checks=50)
    flann = cv2.FlannBasedMatcher(ip, sp)
    kp, des = sift_map.detectAndCompute(img, None)
    # Warm FLANN index
    dummy = np.random.rand(10, 128).astype(np.float32)
    try: flann.knnMatch(dummy, des, k=2)
    except: pass
    return {'sift': sift_cap, 'flann': flann, 'kp': kp, 'des': des}

def match_flann(capture, ctx):
    kp1, des1 = ctx['sift'].detectAndCompute(capture, None)
    if des1 is None: return None
    d1 = des1.get() if isinstance(des1, cv2.UMat) else des1
    d2 = ctx['des'].get() if isinstance(ctx['des'], cv2.UMat) else ctx['des']
    matches = ctx['flann'].knnMatch(d1, d2, k=2)
    return do_homography(kp1, ctx['kp'], ratio_test(matches), capture.shape)

run_match(setup_flann, match_flann, "2. SIFT + FLANN (trees=5)", "KD-tree")

# ── 3. ORB ─────────────────────────────────────────────────────────────
def setup_orb():
    orb = cv2.ORB_create(nfeatures=3000)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    kp, des = orb.detectAndCompute(img, None)
    return {'orb': orb, 'bf': bf, 'kp': kp, 'des': des}

def match_orb(capture, ctx):
    kp1, des1 = ctx['orb'].detectAndCompute(capture, None)
    if des1 is None: return None
    matches = ctx['bf'].knnMatch(des1, ctx['des'], k=2)
    return do_homography(kp1, ctx['kp'], ratio_test(matches), capture.shape)

run_match(setup_orb, match_orb, "3. ORB (nfeat=3000)", "binary desc")

# ── 4. AKAZE ───────────────────────────────────────────────────────────
def setup_akaze():
    akaze = cv2.AKAZE_create()
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    kp, des = akaze.detectAndCompute(img, None)
    return {'det': akaze, 'bf': bf, 'kp': kp, 'des': des}

def match_akaze(capture, ctx):
    kp1, des1 = ctx['det'].detectAndCompute(capture, None)
    if des1 is None: return None
    matches = ctx['bf'].knnMatch(des1, ctx['des'], k=2)
    return do_homography(kp1, ctx['kp'], ratio_test(matches), capture.shape)

run_match(setup_akaze, match_akaze, "4. AKAZE", "binary desc")

# ── 5. Template matching ──────────────────────────────────────────────
def setup_template():
    return {'map': img}

def match_template(capture, ctx):
    result = cv2.matchTemplate(ctx['map'], capture, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < 0.5: return None
    return np.array([[[max_loc[0] + capture.shape[1]//2,
                       max_loc[1] + capture.shape[0]//2]]], dtype=np.float32)

run_match(setup_template, match_template, "5. Template matching", "no rotation")

# ── 6. Downscale capture 2x ───────────────────────────────────────────
def setup_ds_cap():
    sift_map = cv2.SIFT_create()
    sift_cap = cv2.SIFT_create(contrastThreshold=0.03)
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    kp, des = sift_map.detectAndCompute(img, None)
    return {'sift': sift_cap, 'bf': bf, 'kp': kp, 'des': des}

def match_ds_cap(capture, ctx):
    small = cv2.resize(capture, (capture.shape[1]//2, capture.shape[0]//2))
    kp1, des1 = ctx['sift'].detectAndCompute(small, None)
    if des1 is None: return None
    matches = ctx['bf'].knnMatch(des1, ctx['des'], k=2)
    good = ratio_test(matches)
    if len(good) <= 25: return None
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2) * 2
    dst = np.float32([ctx['kp'][m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if M is None or not np.all(np.isfinite(M)): return None
    pts = np.float32([[0,0],[0,249],[249,249],[249,0]]).reshape(-1,1,2)
    tp = cv2.perspectiveTransform(pts, M)
    return tp if np.all(np.isfinite(tp)) else None

run_match(setup_ds_cap, match_ds_cap, "6. Downscale capture 2x", "fewer cap kp")

# ── 7. Downscale map+capture 2x ──────────────────────────────────────
def setup_ds_both():
    small_map = cv2.resize(img, (w//2, h//2))
    sift_map = cv2.SIFT_create()
    sift_cap = cv2.SIFT_create(contrastThreshold=0.03)
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    kp, des = sift_map.detectAndCompute(small_map, None)
    return {'sift': sift_cap, 'bf': bf, 'kp': kp, 'des': des, 'scale': 2}

def match_ds_both(capture, ctx):
    small = cv2.resize(capture, (capture.shape[1]//2, capture.shape[0]//2))
    kp1, des1 = ctx['sift'].detectAndCompute(small, None)
    if des1 is None: return None
    matches = ctx['bf'].knnMatch(des1, ctx['des'], k=2)
    good = ratio_test(matches)
    if len(good) <= 25: return None
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([ctx['kp'][m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if M is None or not np.all(np.isfinite(M)): return None
    h2, w2 = capture.shape[0]//2, capture.shape[1]//2
    pts = np.float32([[0,0],[0,h2-1],[w2-1,h2-1],[w2-1,0]]).reshape(-1,1,2)
    tp = cv2.perspectiveTransform(pts, M)
    return (tp * ctx['scale']) if np.all(np.isfinite(tp)) else None

run_match(setup_ds_both, match_ds_both, "7. Downscale map+capture 2x", "half-res")

# ── 8. Spatial restriction with known last pos ────────────────────────
def setup_spatial():
    sift_map = cv2.SIFT_create()
    sift_cap = cv2.SIFT_create(contrastThreshold=0.03)
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    kp, des = sift_map.detectAndCompute(img, None)
    # Build spatial grid
    cell = 100
    grid = {}
    for i, k in enumerate(kp):
        key = (int(k.pt[0] // cell), int(k.pt[1] // cell))
        grid.setdefault(key, []).append(i)
    des_np = des.get() if isinstance(des, cv2.UMat) else des
    return {'sift': sift_cap, 'bf': bf, 'kp': kp, 'des_np': des_np,
            'grid': grid, 'cell': cell}

def match_spatial_warm(capture, ctx, last_pos=(425, 325)):
    kp1, des1 = ctx['sift'].detectAndCompute(capture, None)
    if des1 is None: return None
    # Gather descriptors within radius
    radius = 250
    cs = ctx['cell']
    cx_min = max(0, int((last_pos[0] - radius) // cs))
    cx_max = int((last_pos[0] + radius) // cs) + 1
    cy_min = max(0, int((last_pos[1] - radius) // cs))
    cy_max = int((last_pos[1] + radius) // cs) + 1
    indices = []
    for cx in range(cx_min, cx_max + 1):
        for cy in range(cy_min, cy_max + 1):
            if (cx, cy) in ctx['grid']:
                indices.extend(ctx['grid'][(cx, cy)])
    if len(indices) < 100:
        # Fallback to full
        des_search = ctx['des_np']
        kp_search = ctx['kp']
    else:
        indices = sorted(set(indices))
        des_search = ctx['des_np'][indices]
        kp_search = [ctx['kp'][i] for i in indices]
    matches = ctx['bf'].knnMatch(des1, des_search, k=2)
    good = ratio_test(matches)
    if len(good) <= 25: return None
    src = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_search[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if M is None or not np.all(np.isfinite(M)): return None
    pts = np.float32([[0,0],[0,249],[249,249],[249,0]]).reshape(-1,1,2)
    tp = cv2.perspectiveTransform(pts, M)
    return tp if np.all(np.isfinite(tp)) else None

ctx8 = setup_spatial()
# Warm
match_spatial_warm(crop, ctx8)
t0 = time.perf_counter()
for _ in range(N):
    match_spatial_warm(crop, ctx8, last_pos=(425, 325))
t8 = (time.perf_counter() - t0) / N * 1000
fn8 = "OK" if match_spatial_warm(crop, ctx8) is not None else "FAIL"
# Snow test with appropriate last_pos
fs8 = "OK" if match_spatial_warm(snow_crop, ctx8, last_pos=(w//2, h//5)) is not None else "FAIL"
print(f"  {'8. Spatial (250px radius, warm)':<45} {t8:>6.1f}ms  {fn8:<6} {fs8:<6} needs last_pos")

# ── 9. SIFT capped 500 + sensitive ───────────────────────────────────
def setup_capped():
    sift_map = cv2.SIFT_create()
    sift_cap = cv2.SIFT_create(nfeatures=500, contrastThreshold=0.03)
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    kp, des = sift_map.detectAndCompute(img, None)
    return {'sift': sift_cap, 'bf': bf, 'kp': kp, 'des': des}

run_match(setup_capped, match_current, "9. SIFT nfeat=500, ct=0.03", "capped")

# ── 10. SIFT capped 300 ──────────────────────────────────────────────
def setup_cap300():
    sift_map = cv2.SIFT_create()
    sift_cap = cv2.SIFT_create(nfeatures=300, contrastThreshold=0.03)
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    kp, des = sift_map.detectAndCompute(img, None)
    return {'sift': sift_cap, 'bf': bf, 'kp': kp, 'des': des}

run_match(setup_cap300, match_current, "10. SIFT nfeat=300, ct=0.03", "aggressive cap")

# ── 11. Spatial + FLANN combo ─────────────────────────────────────────
# (Would combine approaches 2+8 but let's skip complex combos for now)

# ── 12. SIFT + nfeat=500 cap + BF, original ct=0.04 (old baseline) ──
def setup_old_baseline():
    sift = cv2.SIFT_create(nfeatures=500)
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    kp, des = sift.detectAndCompute(img, None)
    return {'sift': cv2.SIFT_create(nfeatures=500), 'bf': bf, 'kp': kp, 'des': des}

run_match(setup_old_baseline, match_current, "12. OLD BASELINE (nf=500, ct=0.04)", "reference")

print(f"\n{'='*90}")
print("  NOTES:")
print("  - 'Normal' = green/urban crop, 'Snow' = snow area crop from map")
print("  - Template matching has no rotation invariance (bad for real minimap)")
print("  - Spatial restriction needs a last known position (first frame = full search)")
print(f"{'='*90}")
