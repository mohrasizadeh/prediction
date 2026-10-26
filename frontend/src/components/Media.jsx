// Crest, LeagueMark and PlayerAvatar (docs/19 section 5). Images come only from our own /api/media address.
// If there is no image, or it fails to load, we draw a fallback. Never a broken-image icon.
import { useState } from "react";

const BASE = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
const src = (image) => (image ? (image.startsWith("/") ? BASE + image : image) : null);

function Img({ image, size, alt, round, onFail, eager }) {
  return (
    <img
      src={src(image)}
      width={size}
      height={size}
      alt={alt}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      onError={onFail}
      className={"media-img" + (round ? " media-round" : "")}
    />
  );
}

export function Crest({ team, size = 28, decorative = true, eager }) {
  const [failed, setFailed] = useState(false);
  const alt = decorative ? "" : `${team?.name || "Club"} crest`;
  if (!team?.image || failed) {
    return (
      <span className="media-fallback media-shield" style={{ width: size, height: size }} role={decorative ? undefined : "img"} aria-label={decorative ? undefined : alt}>
        <svg viewBox="0 0 24 24" width={size * 0.7} height={size * 0.7} aria-hidden="true">
          <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3z" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      </span>
    );
  }
  return <span className="media-chip" style={{ width: size, height: size }}><Img image={team.image} size={size} alt={alt} onFail={() => setFailed(true)} eager={eager} /></span>;
}

export function LeagueMark({ league, size = 20, decorative = true }) {
  const [failed, setFailed] = useState(false);
  const code = (league?.name || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  if (!league?.image || failed) {
    return <span className="media-fallback" style={{ width: size, height: size, fontSize: size * 0.42 }} aria-hidden={decorative}>{code}</span>;
  }
  return <span className="media-chip" style={{ width: size, height: size }}><Img image={league.image} size={size} alt={decorative ? "" : league.name} onFail={() => setFailed(true)} /></span>;
}

// Site logo from Site Studio (brand.logo_light / brand.logo_dark). Falls back to the brand mark if missing or broken.
export function BrandLogo({ brand, mode }) {
  const [failed, setFailed] = useState("");
  const image = (mode === "light" ? brand?.logo_light || brand?.logo_dark : brand?.logo_dark || brand?.logo_light) || "";
  if (!image || failed === image) return <span className="brand-mark" aria-hidden="true" />;
  return <img src={src(image)} alt="" height={28} className="brand-logo" decoding="async" onError={() => setFailed(image)} data-testid="brand-logo" />;
}

const TINTS = ["chart1", "chart2", "chart3", "chart4", "chart5", "chart6"];
const tintFor = (id = "") => TINTS[[...String(id)].reduce((a, c) => a + c.charCodeAt(0), 0) % TINTS.length];

export function PlayerAvatar({ player, size = 32, decorative = true }) {
  const [failed, setFailed] = useState(false);
  const parts = (player?.name || "?").trim().split(/\s+/);
  const initials = ((parts[0] || "")[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "");
  if (!player?.image || failed) {
    return (
      <span className="media-fallback media-round media-initials" style={{ width: size, height: size, fontSize: size * 0.38, "--tint": `var(--c-${tintFor(player?.id)})` }} aria-hidden={decorative}>
        {initials.toUpperCase()}
      </span>
    );
  }
  return <Img image={player.image} size={size} alt={decorative ? "" : player.name} round onFail={() => setFailed(true)} />;
}
