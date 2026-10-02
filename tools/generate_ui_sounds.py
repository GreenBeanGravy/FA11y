"""Regenerate assets/sounds/ui_*.ogg, the hub's UI sounds.

Soft sine tones with smooth envelopes, written by hand rather than taken
from a sound pack, so there are no licensing questions. Run from the
repository root:

    python tools/generate_ui_sounds.py
"""
import numpy as np, soundfile as sf
SR = 44100
def tone(freqs, dur, vol=0.35, attack=0.004, decay=None):
    t = np.arange(int(SR*dur))/SR
    sig = sum(np.sin(2*np.pi*f*t)*a for f,a in freqs)
    env = np.minimum(1, t/attack) * np.exp(-t/(decay or dur/4))
    return (sig*env*vol).astype(np.float32)
def seq(*parts, gap=0.0):
    out=[]
    for p in parts:
        out.append(p); out.append(np.zeros(int(SR*gap),np.float32))
    return np.concatenate(out)
def save(name, mono):
    st = np.stack([mono,mono],1)
    sf.write(f"assets/sounds/ui_{name}.ogg", st, SR, format="OGG", subtype="VORBIS")
save("navigate", tone([(1320,1),(2640,.15)], 0.06, 0.22, decay=0.012))
save("open", seq(tone([(660,1),(1320,.2)],0.07,0.25,decay=0.02), tone([(990,1),(1980,.2)],0.12,0.25,decay=0.035), gap=0.0))
save("close", seq(tone([(990,1),(1980,.2)],0.07,0.22,decay=0.02), tone([(660,1),(1320,.2)],0.12,0.22,decay=0.035)))
save("done", seq(tone([(784,1),(1568,.25)],0.09,0.28,decay=0.03), tone([(1175,1),(2350,.25)],0.22,0.28,decay=0.06), gap=0.01))
save("error", seq(tone([(392,1),(784,.3)],0.11,0.3,decay=0.04), tone([(311,1),(622,.3)],0.22,0.3,decay=0.07), gap=0.02))
print("ok")
