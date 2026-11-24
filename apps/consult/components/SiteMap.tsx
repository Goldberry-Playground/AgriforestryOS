import type { Area, Practice } from "@/lib/consult-client/types";
import { formatAcres, layoutSiteMap } from "@/lib/consult-client/view";

/**
 * A schematic of the property: one square per area, sized by acreage. Wet
 * areas are hatched and labelled as well as tinted, so they read without
 * colour.
 */
export function SiteMap({ areas, practices }: { areas: Area[]; practices: Practice[] }) {
  const layout = layoutSiteMap(areas);
  const practiceName = new Map(practices.map((p) => [p.id, p.name]));
  const summary = areas
    .map((a) => `${a.name}, ${formatAcres(a.acres)} acres${a.wet ? ", wet" : ""}`)
    .join("; ");
  return (
    <figure style={{ margin: 0 }}>
      {/* Focusable so the map can be scrolled sideways from the keyboard on a narrow screen. */}
      <div className="map-scroll" tabIndex={0} role="group" aria-label="Site map">
      <svg
        className="map"
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="img"
        aria-label={`Schematic of ${areas.length} areas sized by acreage: ${summary}.`}
      >
        <defs>
          <pattern id="wet-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line className="hatch" x1="0" y1="0" x2="0" y2="8" strokeWidth="1.5" opacity="0.45" />
          </pattern>
        </defs>
        {layout.blocks.map((b) => {
          const area = areas[b.index];
          const practice = area.practiceId ? practiceName.get(area.practiceId) : null;
          return (
            <g key={b.index}>
              <rect className={area.wet ? "area wet" : "area"} x={b.x} y={b.y} width={b.w} height={b.h} rx="6" />
              {area.wet ? <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="6" fill="url(#wet-hatch)" /> : null}
              <foreignObject x={b.x} y={b.y} width={b.w} height={b.h}>
                <div className="map-label">
                  <strong>{area.name}</strong>
                  <span>
                    {formatAcres(area.acres)} ac{area.wet ? " · wet" : ""}
                  </span>
                  {practice && b.w >= 110 ? <span>{practice}</span> : null}
                </div>
              </foreignObject>
            </g>
          );
        })}
      </svg>
      </div>
      <figcaption className="legend">
        <span>
          <svg width="14" height="14" aria-hidden="true">
            <rect className="map-key" width="14" height="14" rx="3" />
          </svg>
          Area, sized by acres
        </span>
        <span>
          <svg width="14" height="14" aria-hidden="true">
            <rect className="map-key wet" width="14" height="14" rx="3" />
            <path className="hatch" d="M0 10 L10 0 M4 14 L14 4" strokeWidth="1.5" />
          </svg>
          Wet ground (hatched)
        </span>
        <span>Not to scale or position.</span>
      </figcaption>
    </figure>
  );
}
