// The ONE score→band→hex module (invariant 7). No other file may map a
// score or band word to a colour; payloads never carry one.
//
// Four branches, strict less-than, on the RAW score before display
// rounding (invariant 6). There is no fifth band: anything at or above
// 4.0 is Differentiating, and #185F60 (the prototype's reachable-looking
// M5 hex) must not appear in this file or anywhere else.

export const BANDS = {
  Activating: { fill: "#FFCB99", text: "#7C3C00" },
  Building: { fill: "#62D7B8", text: "#0D4F3C" }, // NOT #B0EDD3 (docs ambiguity; resolver wins)
  Competing: { fill: "#27BBAF", text: "#FFFFFF" },
  Differentiating: { fill: "#139F94", text: "#FFFFFF" },
};

export function bandFor(rawScore) {
  if (rawScore === null || rawScore === undefined) return null; // null → no score, no fill
  const s = Number(rawScore);
  if (Number.isNaN(s)) return null;
  if (s < 2) return "Activating";
  if (s < 3) return "Building";
  if (s < 4) return "Competing";
  return "Differentiating";
}

export function colourFor(rawScore) {
  const band = bandFor(rawScore);
  return band ? { band, ...BANDS[band] } : null;
}
